package main

import (
	"encoding/json"
	"fmt"
	"log"
	"regexp"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/linxGnu/gosmpp"
	"github.com/linxGnu/gosmpp/data"
	"github.com/linxGnu/gosmpp/pdu"
)

// tpsBucket 是简单的令牌桶限速器，用于限制每通道 TPS。
// 使用 time.Ticker 定期补充令牌，SendSMS 调用前阻塞等待令牌。
type tpsBucket struct {
	tokens chan struct{}
	done   chan struct{}
}

// newTPSBucket 创建并启动令牌桶；tps<=0 时返回 nil（不限速）。
func newTPSBucket(tps int) *tpsBucket {
	if tps <= 0 {
		return nil
	}
	// 桶容量 = min(tps, 200)，允许短时突发但不超过 200 令牌
	cap := tps
	if cap > 200 {
		cap = 200
	}
	b := &tpsBucket{
		tokens: make(chan struct{}, cap),
		done:   make(chan struct{}),
	}
	// 预填满令牌桶，避免冷启动时第一批消息全部等待
	for i := 0; i < cap; i++ {
		b.tokens <- struct{}{}
	}
	// 每 100ms 批量补令牌，降低 Ticker 频率，减轻调度器繁忙时 10ms 级「漏帧」导致的吞吐塌陷
	batchSize := tps / 10
	if batchSize < 1 {
		batchSize = 1
	}
	go func() {
		ticker := time.NewTicker(100 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-b.done:
				return
			case <-ticker.C:
			refill:
				for i := 0; i < batchSize; i++ {
					select {
					case b.tokens <- struct{}{}:
					default:
						break refill
					}
				}
			}
		}
	}()
	return b
}

// Wait 阻塞直到令牌可用（最长等待 10 秒，超时后仍放行避免死锁）
func (b *tpsBucket) Wait() {
	if b == nil {
		return
	}
	select {
	case <-b.tokens:
	case <-time.After(10 * time.Second):
		log.Printf("[TPS-WARN] token bucket wait timeout, proceeding anyway")
	}
}

// Stop 停止后台令牌补充 goroutine
func (b *tpsBucket) Stop() {
	if b == nil {
		return
	}
	select {
	case <-b.done:
	default:
		close(b.done)
	}
}

// SMPPManager manages multiple SMPP connections across different channels
type SMPPManager struct {
	connections map[int][]*gosmpp.Session
	configs     map[int]ChannelConfig
	mu          sync.RWMutex
	// 每个 bind 会话独立互斥：Submit 与 sequence 登记串行，避免多 goroutine 同 session 竞态。
	sessionSubmitMu map[*gosmpp.Session]*sync.Mutex
	// sequenceMap 键为「通道ID:序列号」。仅用序列号会与多 bind 会话或其它通道的序号冲突，导致 SubmitSMResp 无法匹配、短信永久 queued。
	sequenceMap sync.Map
	// tpsLimiters 每通道令牌桶限速器（按 max_tps 配置）
	tpsLimiters map[int]*tpsBucket
	// bind 协调：防止同通道多 goroutine 并发 bind 打满上游账号(节点 2026-05-29 反馈：
	// 毫秒级内多个不同源端口 TCP 连接，超过 10 个账号上限即返 ESME_RBINDFAIL)。
	// bindMu 每通道一把锁串行所有 bind 入口(初始/OnClosed/stale-monitor)；
	// lastBindAttempt 与 minBindInterval 共同限制同通道两次 bind 的最小起点间隔。
	bindCoordMu     sync.Mutex
	bindMu          map[int]*sync.Mutex
	lastBindAttempt map[int]time.Time
	// liveness watchdog：gosmpp ReadTimeout 不保证触发 OnClosed (代码注释见 OnClosed 上方)；
	// 上游静默断开(SocketHalfClose 或硅默限流)时 session 会"假活"——连接池里还在但 TCP 死了，
	// 无流量则永不发现。每收到一个 PDU(含 gosmpp 自动收的 enquire_link_resp)更新 lastPDUAt，
	// per-session watchdog 周期检查超过 livenessSilenceThreshold 即主动 Close + 兜底 rebind。
	livenessMu sync.Mutex
	lastPDUAt  map[*gosmpp.Session]time.Time
}

// minBindInterval 同通道两次 bind 之间的最小起点间隔。
// 节点账号上限通常 10 并发；500ms 起点间隔 → 单通道最高 2 bind/s，多通道共用账号也能控制。
// 若未来某通道需要更慢节流（例如某些上游单 IP 限频），改成可配置即可。
const minBindInterval = 500 * time.Millisecond

// liveness watchdog 参数：gosmpp 每 30s 发 enquire_link，正常情况下应在秒级收到 enquire_link_resp；
// silenceThreshold = 90s 给到 3 个心跳周期容忍网络抖动，超过即认为上游静默死亡。
// checkInterval 略小于 1/3 silence 即可及时发现。
const (
	livenessCheckInterval    = 30 * time.Second
	livenessSilenceThreshold = 90 * time.Second
	livenessCloseGracePeriod = 5 * time.Second // 主动 Close 后等多久 OnClosed 还没触发就兜底清理
)

// acquireBindSlot 序列化某通道的所有 bind 操作并保证最小起点间隔。
// 返回 release 函数；调用方拿到 release 后即可调用 bindSession，结束后必须调用 release。
//
// 注意：bind 是慢操作(TCP+握手+bind_resp)，持锁等待可能数百毫秒；这是有意为之——
// 在持锁期间禁止任何重连入口对同一通道并发 bind，避免重连风暴。
func (m *SMPPManager) acquireBindSlot(channelID int) func() {
	m.bindCoordMu.Lock()
	mu, ok := m.bindMu[channelID]
	if !ok {
		mu = &sync.Mutex{}
		m.bindMu[channelID] = mu
	}
	m.bindCoordMu.Unlock()

	mu.Lock()

	// 节流：保证两次 bind 起点至少间隔 minBindInterval
	m.bindCoordMu.Lock()
	last := m.lastBindAttempt[channelID]
	m.bindCoordMu.Unlock()
	if since := time.Since(last); since < minBindInterval {
		time.Sleep(minBindInterval - since)
	}
	m.bindCoordMu.Lock()
	m.lastBindAttempt[channelID] = time.Now()
	m.bindCoordMu.Unlock()

	return mu.Unlock
}

type sequenceData struct {
	messageID  string
	logID      int64
	submitTime time.Time // SubmitSM 写入 TCP 的时刻，用于超时检测
}

func smppSeqMapKey(channelID int, seq int32) string {
	return fmt.Sprintf("%d:%d", channelID, seq)
}

var manager *SMPPManager

// IsChannelHealthyByCode 判断 channel_code 对应的通道是否当前在用且 watchdog 视为活。
// 用于管理端「测试连接」按钮 short-circuit：若主连接已活，无需另开新 bind 占用上游账号
// 配额(部分上游账号 max_connections=1，probe 新 bind 必被 EOF)。
// 返回 (是否活, 最近一次 PDU 时间)。channel_code 不存在或全部 session 已静默返回 (false, 零值)。
func (m *SMPPManager) IsChannelHealthyByCode(channelCode string) (bool, time.Time) {
	m.mu.RLock()
	var targetID int = -1
	for id, cfg := range m.configs {
		if cfg.ChannelCode == channelCode {
			targetID = id
			break
		}
	}
	if targetID == -1 {
		m.mu.RUnlock()
		return false, time.Time{}
	}
	sessions := append([]*gosmpp.Session(nil), m.connections[targetID]...)
	m.mu.RUnlock()
	if len(sessions) == 0 {
		return false, time.Time{}
	}
	// 任一 session 的 lastPDUAt 在 livenessSilenceThreshold 内即视为通道整体健康。
	m.livenessMu.Lock()
	defer m.livenessMu.Unlock()
	var newest time.Time
	for _, s := range sessions {
		t := m.lastPDUAt[s]
		if t.After(newest) {
			newest = t
		}
	}
	return !newest.IsZero() && time.Since(newest) <= livenessSilenceThreshold, newest
}

// destAddrNoPlus 去掉 E.164 前导 +，与 Python 侧 format_sms_dest_phone(strip=true) 一致
func destAddrNoPlus(phone string) string {
	if len(phone) > 0 && phone[0] == '+' {
		return phone[1:]
	}
	return phone
}

// parseConfigJSONInt 从 config_json 读取整型字段，缺失或解析失败时返回 defaultVal。
func parseConfigJSONInt(raw string, key string, defaultVal int) int {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return defaultVal
	}
	var m map[string]interface{}
	if err := json.Unmarshal([]byte(raw), &m); err != nil {
		return defaultVal
	}
	v, ok := m[key]
	if !ok || v == nil {
		return defaultVal
	}
	switch x := v.(type) {
	case float64:
		return int(x)
	case int:
		return x
	default:
		return defaultVal
	}
}

// stripLeadingPlusFromConfigJSON 解析 channels.config_json 中的 strip_leading_plus；缺省为 true
func stripLeadingPlusFromConfigJSON(raw string) bool {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return true
	}
	var m map[string]interface{}
	if err := json.Unmarshal([]byte(raw), &m); err != nil {
		return true
	}
	v, ok := m["strip_leading_plus"]
	if !ok || v == nil {
		return true
	}
	switch x := v.(type) {
	case bool:
		return x
	case float64:
		return x != 0
	case string:
		s := strings.ToLower(strings.TrimSpace(x))
		if s == "false" || s == "0" || s == "no" || s == "off" || s == "" {
			return false
		}
		return true
	default:
		return true
	}
}

// longMessageModeFromConfigJSON 解析 channels.config_json 中 long_message_mode；
// 取值：
//   "message_payload"（默认）   — UCS-2 编码 > 254 字节时用 message_payload TLV 旁路（兼容多数现代上游）
//   "udh_segmentation"           — 改用标准 UDH 8-bit ref 多段 SMS 分段，每段 ≤ 140 字节
// 在 wold_kafa 这类上游不实现 message_payload TLV、对 PDU 返 ESME_RINVCMDLEN (2) 的场景必须用 udh。
func longMessageModeFromConfigJSON(raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return "message_payload"
	}
	var m map[string]interface{}
	if err := json.Unmarshal([]byte(raw), &m); err != nil {
		return "message_payload"
	}
	v, ok := m["long_message_mode"]
	if !ok || v == nil {
		return "message_payload"
	}
	if s, ok := v.(string); ok {
		s = strings.ToLower(strings.TrimSpace(s))
		if s == "udh_segmentation" || s == "udh" {
			return "udh_segmentation"
		}
	}
	return "message_payload"
}

// splitUCS2ForUDH 把 UCS-2 编码后的字节流拆为多段，每段 ≤ 134 字节
// （UCS-2 字符是 2 字节宽，按 67 字符 = 134 字节切，避免拆中一个字符）。
// 调用方需自己加 6 字节 UDH 头到每段前面。
func splitUCS2ForUDH(encoded []byte) [][]byte {
	const seg = 134
	if len(encoded) <= seg {
		return [][]byte{encoded}
	}
	out := make([][]byte, 0, (len(encoded)+seg-1)/seg)
	for i := 0; i < len(encoded); i += seg {
		end := i + seg
		if end > len(encoded) {
			end = len(encoded)
		}
		// 防御：UCS-2 必须按 2 字节对齐；len(encoded) 一定是偶数，seg 也是偶数，对齐安全
		out = append(out, encoded[i:end])
	}
	return out
}

// concatRefCounter 为同一 gateway 进程内不同消息生成 UDH 8-bit 拼接 ref。
// 同会话/同号码短时间内不重复即可；单字节空间足够（短信预览组按 ref+from+to 三元组判定，
// 67ms 内同号同 ref 撞车的概率可忽略）。
var concatRefCounter uint32

func nextConcatRef() byte {
	v := atomic.AddUint32(&concatRefCounter, 1)
	return byte(v & 0xFF)
}

func InitSMPPManager() {
	manager = &SMPPManager{
		connections:     make(map[int][]*gosmpp.Session),
		configs:         make(map[int]ChannelConfig),
		sessionSubmitMu: make(map[*gosmpp.Session]*sync.Mutex),
		tpsLimiters:     make(map[int]*tpsBucket),
		bindMu:          make(map[int]*sync.Mutex),
		lastBindAttempt: make(map[int]time.Time),
		lastPDUAt:       make(map[*gosmpp.Session]time.Time),
	}
}

// closeSessions 关闭给定会话列表，并在有 in-flight 消息时延迟等待（最多 30 秒）。
// 延迟关闭避免 ReloadChannels 配置重载时中断正在等待 SubmitSMResp 的消息。
func (m *SMPPManager) closeSessions(channelID int, sessions []*gosmpp.Session, channelCode string) {
	for _, session := range sessions {
		delete(m.sessionSubmitMu, session)
		// 检查该会话是否有 in-flight 消息：有则等待最多 30 秒
		prefix := fmt.Sprintf("%d:", channelID)
		waitStart := time.Now()
		for {
			inFlight := 0
			m.sequenceMap.Range(func(k, _ interface{}) bool {
				if key, ok := k.(string); ok && len(key) > len(prefix) && key[:len(prefix)] == prefix {
					inFlight++
				}
				return true
			})
			if inFlight == 0 || time.Since(waitStart) > 30*time.Second {
				if inFlight > 0 {
					log.Printf("[SMPP-WARN] closeSessions: channel %s still has %d in-flight after 30s, force closing", channelCode, inFlight)
				}
				break
			}
			log.Printf("[SMPP-INFO] closeSessions: channel %s waiting for %d in-flight SubmitSMResp...", channelCode, inFlight)
			time.Sleep(500 * time.Millisecond)
		}
		_ = session.Close()
	}
}

// ReloadChannels reloads configurations and establishes connections asynchronously.
// It no longer holds the global lock during network I/O.
func (m *SMPPManager) ReloadChannels() error {
	configs, err := GetChannelConfigs()
	if err != nil {
		return err
	}

	newConfigs := make(map[int]ChannelConfig)
	for _, cfg := range configs {
		newConfigs[cfg.ID] = cfg
	}

	m.mu.Lock()
	// 1. Identify and remove sessions for channels that are no longer active or were removed
	type closeTask struct {
		channelID   int
		channelCode string
		sessions    []*gosmpp.Session
	}
	var toClose []closeTask

	for id, conns := range m.connections {
		if _, exists := newConfigs[id]; !exists {
			log.Printf("Channel %d (%s) is no longer active, closing %d sessions...", id, m.configs[id].ChannelCode, len(conns))
			toClose = append(toClose, closeTask{channelID: id, channelCode: m.configs[id].ChannelCode, sessions: conns})
			// 停止旧 TPS 限速器
			if b, ok := m.tpsLimiters[id]; ok {
				b.Stop()
				delete(m.tpsLimiters, id)
			}
			delete(m.connections, id)
			delete(m.configs, id)
		}
	}

	// 2. Process current configurations: scaling down immediately, identifying pending additions
	type addTask struct {
		cfg    ChannelConfig
		needed int
	}
	var addTasks []addTask

	for id, cfg := range newConfigs {
		oldCfg := m.configs[id]
		m.configs[id] = cfg
		currentConns := m.connections[id]
		diff := cfg.Concurrency - len(currentConns)

		// 更新 TPS 限速器（TPS 变更时重建）
		if old, ok := m.tpsLimiters[id]; !ok || oldCfg.MaxTPS != cfg.MaxTPS {
			if old != nil {
				old.Stop()
			}
			m.tpsLimiters[id] = newTPSBucket(cfg.MaxTPS)
		}

		if diff > 0 {
			addTasks = append(addTasks, addTask{cfg: cfg, needed: diff})
		} else if diff < 0 {
			// Scale down: collect sessions to close with in-flight wait
			shrink := -diff
			log.Printf("Channel %s reducing concurrency, closing %d sessions...", cfg.ChannelCode, shrink)
			var shrinkSessions []*gosmpp.Session
			for i := 0; i < shrink && len(m.connections[id]) > 0; i++ {
				shrinkSessions = append(shrinkSessions, m.connections[id][0])
				m.connections[id] = m.connections[id][1:]
			}
			toClose = append(toClose, closeTask{channelID: id, channelCode: cfg.ChannelCode, sessions: shrinkSessions})
		}
	}
	m.mu.Unlock()

	// 3. Delayed close in background to avoid interrupting in-flight SubmitSMResp
	for _, tc := range toClose {
		go m.closeSessions(tc.channelID, tc.sessions, tc.channelCode)
	}

	// 4. Process additions asynchronously with exponential backoff on bind failure
	for _, t := range addTasks {
		for i := 0; i < t.needed; i++ {
			go func(cfg ChannelConfig) {
				backoff := 2 * time.Second
				const maxBackoff = 60 * time.Second
				for attempt := 1; ; attempt++ {
					release := m.acquireBindSlot(cfg.ID)
					session, err := m.bindSession(cfg)
					release()
					if err != nil {
						log.Printf("Failed to bind async session for channel %s (attempt %d): %v; retrying in %v", cfg.ChannelCode, attempt, err, backoff)
						time.Sleep(backoff)
						backoff *= 2
						if backoff > maxBackoff {
							backoff = maxBackoff
						}
						// 检查通道是否仍存在（避免已删除通道无限重试）
						m.mu.RLock()
						_, stillExists := m.configs[cfg.ID]
						m.mu.RUnlock()
						if !stillExists {
							log.Printf("Channel %s removed, stopping bind retry", cfg.ChannelCode)
							return
						}
						continue
					}

					m.mu.Lock()
					if _, exists := m.configs[cfg.ID]; exists {
						m.connections[cfg.ID] = append(m.connections[cfg.ID], session)
						m.sessionSubmitMu[session] = &sync.Mutex{}
						log.Printf("Successfully bound new async session for channel %s (total sessions: %d)", cfg.ChannelCode, len(m.connections[cfg.ID]))
					} else {
						log.Printf("Channel %s was removed during async bind, closing new session", cfg.ChannelCode)
						_ = session.Close()
					}
					m.mu.Unlock()
					return
				}
			}(t.cfg)
		}
	}

	return nil
}

// ReconcileConnectionStatus 把 manager 当前的真实 bind 情况回写到 channels.connection_status。
// 真相来源：m.configs 中存在的活跃 SMPP 通道，若 m.connections[id] 非空记为 online，否则 offline。
// 不在 m.configs 中的通道（非 SMPP / inactive / 软删）不在本网关职责范围内，不动其状态。
// 写库走 ProxySQL，每通道一次 UPDATE；通道数量级远小于流量级，无需批量化。
func (m *SMPPManager) ReconcileConnectionStatus() {
	m.mu.RLock()
	statuses := make(map[int]string, len(m.configs))
	codes := make(map[int]string, len(m.configs))
	for id, cfg := range m.configs {
		if len(m.connections[id]) > 0 {
			statuses[id] = "online"
		} else {
			statuses[id] = "offline"
		}
		codes[id] = cfg.ChannelCode
	}
	m.mu.RUnlock()

	for id, status := range statuses {
		if err := UpdateChannelConnectionStatus(id, status); err != nil {
			log.Printf("[STATUS-WARN] write connection_status for channel %s (id=%d) failed: %v", codes[id], id, err)
		}
	}
}

// throttleChannel 在检测到 SMSC 静默限流后临时降低该通道的发送 TPS。
// 降速比例和持续时间可通过 config_json 中的 throttle_tps / throttle_duration_s 精确控制；
// 缺省：降至 max_tps 的 1/10（最低 1），持续 120 秒后自动恢复。
func (m *SMPPManager) throttleChannel(channelID int, cfg ChannelConfig) {
	throttleTPS := parseConfigJSONInt(cfg.ConfigJSON, "throttle_tps", 0)
	if throttleTPS <= 0 {
		throttleTPS = cfg.MaxTPS / 10
		if throttleTPS < 1 {
			throttleTPS = 1
		}
	}
	throttleDuration := time.Duration(parseConfigJSONInt(cfg.ConfigJSON, "throttle_duration_s", 120)) * time.Second

	m.mu.Lock()
	if old, ok := m.tpsLimiters[channelID]; ok && old != nil {
		old.Stop()
	}
	m.tpsLimiters[channelID] = newTPSBucket(throttleTPS)
	m.mu.Unlock()

	log.Printf("[SMPP-INFO] channel %s adaptive throttle: TPS %d→%d for %v (SMSC silent throttle detected)",
		cfg.ChannelCode, cfg.MaxTPS, throttleTPS, throttleDuration)

	// 超时后恢复原 TPS
	go func() {
		time.Sleep(throttleDuration)
		m.mu.Lock()
		defer m.mu.Unlock()
		currentCfg, still := m.configs[channelID]
		if !still {
			return
		}
		if old, ok := m.tpsLimiters[channelID]; ok && old != nil {
			old.Stop()
		}
		m.tpsLimiters[channelID] = newTPSBucket(currentCfg.MaxTPS)
		log.Printf("[SMPP-INFO] channel %s adaptive throttle restored: TPS back to %d",
			currentCfg.ChannelCode, currentCfg.MaxTPS)
	}()
}

func (m *SMPPManager) bindSession(cfg ChannelConfig) (*gosmpp.Session, error) {
	auth := gosmpp.Auth{
		SMSC:       fmt.Sprintf("%s:%d", cfg.Host, cfg.Port),
		SystemID:   cfg.Username,
		Password:   cfg.Password,
		SystemType: cfg.SystemType,
	}

	var connector gosmpp.Connector
	dialer := gosmpp.NonTLSDialer

	// Default to Transceiver if not specified
	if cfg.BindMode == "transmitter" {
		connector = gosmpp.TXConnector(dialer, auth)
	} else if cfg.BindMode == "receiver" {
		connector = gosmpp.RXConnector(dialer, auth)
	} else {
		connector = gosmpp.TRXConnector(dialer, auth)
	}

	// sessionPtr 让 OnClosed 闭包在 session 对象创建后仍能引用它自身。
	// gosmpp.NewSession 返回前 OnClosed 闭包已注册，但 session 变量尚未赋值，
	// 故用指针间接引用，NewSession 返回后立即设置。
	var sessionPtr *gosmpp.Session

	// Initialize session with handlers
	session, err := gosmpp.NewSession(
		connector,
		gosmpp.Settings{
			ReadTimeout: 120 * time.Second,
			EnquireLink: 30 * time.Second,
			OnPDU: func(p pdu.PDU, responded bool) {
				// liveness watchdog 心跳：任何到达的 PDU(含 gosmpp 自动收的 enquire_link_resp)
				// 都视为对端仍存活的证据。sessionPtr 在 NewSession 返回后立即赋值。
				if sessionPtr != nil {
					m.livenessMu.Lock()
					m.lastPDUAt[sessionPtr] = time.Now()
					m.livenessMu.Unlock()
				}
				switch pd := p.(type) {
				case *pdu.SubmitSMResp:
					log.Printf("[SMPP-DEBUG] SubmitSMResp reached: channel=%s, msgID=%s, sequence=%d, status=%d", cfg.ChannelCode, pd.MessageID, pd.SequenceNumber, pd.CommandStatus)

					if val, ok := m.sequenceMap.LoadAndDelete(smppSeqMapKey(cfg.ID, pd.SequenceNumber)); ok {
						seqData := val.(sequenceData)
						log.Printf("[SMPP-DEBUG] Found matching sequence for msg: %s (internal log ID: %d)", seqData.messageID, seqData.logID)

						if pd.CommandStatus == data.ESME_ROK {
							// 标记为本系统所有：后续 DeliverSM 将以此作为归属判断依据，外来 DLR 直接丢弃。
							MarkOwned(cfg.ID, pd.MessageID)
							if err := publishSmsSubmitResult(seqData.logID, seqData.messageID, pd.MessageID, "sent", ""); err != nil {
								log.Printf("[SMPP-ERROR] Failed to publish submit result for %s: %v", seqData.messageID, err)
							} else {
								log.Printf("[SMPP-DEBUG] Successfully mapped upstream ID: %s => %s", seqData.messageID, pd.MessageID)
							}
						} else {
							log.Printf("[SMPP-ERROR] SubmitSM failed with status %d for msg %s", pd.CommandStatus, seqData.messageID)
							if err := publishSmsSubmitResult(seqData.logID, seqData.messageID, "", "failed", fmt.Sprintf("SMPP Error: %d", pd.CommandStatus)); err != nil {
								log.Printf("[SMPP-ERROR] Failed to publish SMPP error for %s: %v", seqData.messageID, err)
							}
						}
					} else {
						log.Printf("[SMPP-DEBUG] Warning: SubmitSMResp 无匹配映射: channel_id=%d seq=%d（会话重建、序号跨通道冲突已修复前遗留、或上游异步回包）", cfg.ID, pd.SequenceNumber)
					}

				case *pdu.DeliverSM:
					log.Printf("[SMPP-DEBUG] Received DeliverSM on channel %s", cfg.ChannelCode)
					m.handleDeliverSM(pd, cfg)

				case *pdu.EnquireLinkResp:
					// Just log that we received it for health check visibility
					// log.Printf("[SMPP-DEBUG] EnquireLinkResp reached for channel %s", cfg.ChannelCode)

				default:
					log.Printf("[SMPP-DEBUG] Received PDU type %T on channel %s", p, cfg.ChannelCode)
				}
			},
			OnClosed: func(state gosmpp.State) {
				log.Printf("Session closed for channel %s, state: %v", cfg.ChannelCode, state)
				// 1. 从 connections 中移除已关闭的 session，让 ReloadChannels 能检测到缺口并立即重绑。
				//    不移除会导致 ReloadChannels 认为 concurrency 满足，永远不重建会话。
				closedSession := sessionPtr
				removedHere := false
				m.mu.Lock()
				if closedSession != nil {
					conns := m.connections[cfg.ID]
					for i, s := range conns {
						if s == closedSession {
							m.connections[cfg.ID] = append(conns[:i], conns[i+1:]...)
							delete(m.sessionSubmitMu, closedSession)
							removedHere = true
							break
						}
					}
				}
				m.mu.Unlock()
				// 清理 liveness 状态
				if closedSession != nil {
					m.livenessMu.Lock()
					delete(m.lastPDUAt, closedSession)
					m.livenessMu.Unlock()
				}

				// 2. 立即触发异步重绑（仅当本回调亲手移除了 session 时；否则 watchdog/stale-monitor
				//    已或将 spawn rebind，本处再 spawn 会导致双重连）。
				if removedHere {
				go func() {
					m.mu.RLock()
					_, still := m.configs[cfg.ID]
					m.mu.RUnlock()
					if !still {
						return
					}
					backoff := 2 * time.Second
					const maxBackoff = 60 * time.Second
					for attempt := 1; ; attempt++ {
						release := m.acquireBindSlot(cfg.ID)
						newSession, err := m.bindSession(cfg)
						release()
						if err != nil {
							log.Printf("[SMPP-WARN] OnClosed rebind channel %s attempt %d: %v; retry in %v", cfg.ChannelCode, attempt, err, backoff)
							time.Sleep(backoff)
							backoff *= 2
							if backoff > maxBackoff {
								backoff = maxBackoff
							}
							m.mu.RLock()
							_, still = m.configs[cfg.ID]
							m.mu.RUnlock()
							if !still {
								return
							}
							continue
						}
						m.mu.Lock()
						if _, exists := m.configs[cfg.ID]; exists {
							m.connections[cfg.ID] = append(m.connections[cfg.ID], newSession)
							m.sessionSubmitMu[newSession] = &sync.Mutex{}
							log.Printf("[SMPP-INFO] OnClosed rebind success: channel %s (total sessions: %d)", cfg.ChannelCode, len(m.connections[cfg.ID]))
						} else {
							_ = newSession.Close()
						}
						m.mu.Unlock()
						return
					}
				}()
				} // end if removedHere

				// 3. 清理该通道所有 in-flight sequenceMap 条目（无论谁先移除都要做，避免 orphan）
				// 标为 sent 而非 failed：PDU 已送达 SMSC 网络层，SMSC 可能已接收（静默限流导致未返回 SubmitSMResp）
				// 保持 sent 状态使 DLR 仍可匹配更新终态；若 SMSC 确实未收到，DLR 超时检查（72h）会兜底标 expired
				prefix := fmt.Sprintf("%d:", cfg.ID)
				var orphanKeys []interface{}
				m.sequenceMap.Range(func(k, v interface{}) bool {
					if key, ok := k.(string); ok && len(key) > len(prefix) && key[:len(prefix)] == prefix {
						orphanKeys = append(orphanKeys, k)
					}
					return true
				})
				if len(orphanKeys) > 0 {
					log.Printf("[SMPP-WARN] Session closed with %d in-flight messages for channel %s, marking sent (awaiting DLR)", len(orphanKeys), cfg.ChannelCode)
					for _, k := range orphanKeys {
						if val, loaded := m.sequenceMap.LoadAndDelete(k); loaded {
							seq := val.(sequenceData)
							if err := publishSmsSubmitResult(seq.logID, seq.messageID, "", "sent", ""); err != nil {
								log.Printf("[SMPP-ERROR] Failed to publish orphan sent: msgID=%s err=%v", seq.messageID, err)
							}
						}
					}
				}
			},
		},
		5*time.Second,
	)

	if err != nil {
		return nil, err
	}
	// sessionPtr 在此处设置，使 OnClosed 闭包能通过指针找到 session 对象
	sessionPtr = session

	// liveness watchdog：初始化 lastPDUAt 为 bind 成功时刻，避免 watchdog 启动后立刻
	// 因为没收到过 PDU 而误判为静默。
	m.livenessMu.Lock()
	m.lastPDUAt[session] = time.Now()
	m.livenessMu.Unlock()

	// liveness watchdog goroutine：周期检查 session 是否仍在收到 PDU。
	// 触发条件：超过 livenessSilenceThreshold(90s) 没有任何 PDU(包括 enquire_link_resp)，
	// 视为上游已静默死亡 → 主动 Close → OnClosed 应触发并启动 rebind。
	// 兜底：gosmpp.Session.Close() 不保证同步触发 OnClosed (代码注释见 OnClosed 上方)，
	// 等 livenessCloseGracePeriod(5s) 后若 session 仍在 connections 中，watchdog 自行
	// 完成清理并 spawn rebind goroutine，避免「主动 close 了但既没回调也没重连」的僵局。
	go func() {
		ticker := time.NewTicker(livenessCheckInterval)
		defer ticker.Stop()
		for range ticker.C {
			m.mu.RLock()
			_, stillCfg := m.configs[cfg.ID]
			inPool := false
			if stillCfg {
				for _, s := range m.connections[cfg.ID] {
					if s == session {
						inPool = true
						break
					}
				}
			}
			m.mu.RUnlock()
			if !inPool {
				// session 已被其他路径(OnClosed / stale-monitor / Reload 缩容)移除，watchdog 退出。
				m.livenessMu.Lock()
				delete(m.lastPDUAt, session)
				m.livenessMu.Unlock()
				return
			}

			m.livenessMu.Lock()
			last := m.lastPDUAt[session]
			m.livenessMu.Unlock()

			if time.Since(last) <= livenessSilenceThreshold {
				continue
			}

			log.Printf("[SMPP-WATCHDOG] channel %s session silent for %v (last PDU at %v) — force Close + 等 OnClosed 回调",
				cfg.ChannelCode, time.Since(last).Round(time.Second), last.Format("15:04:05"))
			_ = session.Close()

			// 给 OnClosed 一段宽限期。若到期 session 仍在 connections，自行清理并 spawn rebind。
			time.AfterFunc(livenessCloseGracePeriod, func() {
				m.mu.Lock()
				stillIn := false
				conns := m.connections[cfg.ID]
				for i, s := range conns {
					if s == session {
						m.connections[cfg.ID] = append(conns[:i], conns[i+1:]...)
						delete(m.sessionSubmitMu, session)
						stillIn = true
						break
					}
				}
				m.mu.Unlock()
				m.livenessMu.Lock()
				delete(m.lastPDUAt, session)
				m.livenessMu.Unlock()
				if !stillIn {
					return // OnClosed 已正常处理
				}

				log.Printf("[SMPP-WATCHDOG] channel %s OnClosed 未在 %v 内触发，watchdog 兜底重连",
					cfg.ChannelCode, livenessCloseGracePeriod)
				// 兜底 spawn rebind：与 OnClosed 内逻辑等价
				go func() {
					backoff := 2 * time.Second
					const maxBackoff = 60 * time.Second
					for attempt := 1; ; attempt++ {
						m.mu.RLock()
						_, still := m.configs[cfg.ID]
						m.mu.RUnlock()
						if !still {
							return
						}
						release := m.acquireBindSlot(cfg.ID)
						newSession, err := m.bindSession(cfg)
						release()
						if err != nil {
							log.Printf("[SMPP-WATCHDOG] rebind channel %s attempt %d: %v; retry in %v",
								cfg.ChannelCode, attempt, err, backoff)
							time.Sleep(backoff)
							backoff *= 2
							if backoff > maxBackoff {
								backoff = maxBackoff
							}
							continue
						}
						m.mu.Lock()
						if _, exists := m.configs[cfg.ID]; exists {
							m.connections[cfg.ID] = append(m.connections[cfg.ID], newSession)
							m.sessionSubmitMu[newSession] = &sync.Mutex{}
							log.Printf("[SMPP-WATCHDOG] rebind success: channel %s (sessions: %d)",
								cfg.ChannelCode, len(m.connections[cfg.ID]))
						} else {
							_ = newSession.Close()
						}
						m.mu.Unlock()
						return
					}
				}()
			})
			return // 本 watchdog 退出；新 session 会启动新的 watchdog
		}
	}()

	// 后台超时监测：每 5 秒扫描该通道的 sequenceMap，若有条目超过 20 秒未收到 SubmitSMResp，
	// 直接清理孤儿条目、移除会话、关闭连接并立即重绑。
	// staleTTL=20s（SMSC 正常响应 <5s，20s 足够区分静默限流）。
	// ticker=5s 使最坏情况死区时间 ≈ 25s（原 15s ticker+45s TTL → 60s 最坏）。
	// 注意：不依赖 OnClosed 回调——gosmpp.Session.Close() 不保证同步触发 OnClosed。
	monitorPrefix := fmt.Sprintf("%d:", cfg.ID)
	go func() {
		ticker := time.NewTicker(5 * time.Second)
		defer ticker.Stop()
		const staleTTL = 20 * time.Second
		for range ticker.C {
			// 检查通道是否仍在 manager 中（已被 ReloadChannels 移除则退出）
			m.mu.RLock()
			_, still := m.configs[cfg.ID]
			m.mu.RUnlock()
			if !still {
				return
			}

			now := time.Now()
			var staleKeys []interface{}
			m.sequenceMap.Range(func(k, v interface{}) bool {
				key, ok := k.(string)
				if !ok || len(key) <= len(monitorPrefix) || key[:len(monitorPrefix)] != monitorPrefix {
					return true
				}
				sd := v.(sequenceData)
				if !sd.submitTime.IsZero() && now.Sub(sd.submitTime) > staleTTL {
					staleKeys = append(staleKeys, k)
				}
				return true
			})
			if len(staleKeys) == 0 {
				continue
			}

			log.Printf("[SMPP-WARN] channel %s has %d stale in-flight entries (>%v without SubmitSMResp), self-healing: cleanup+close+rebind (staleTTL=%v)",
				cfg.ChannelCode, len(staleKeys), staleTTL, staleTTL)

			// 1. 清理孤儿 sequenceMap 条目，标为 sent 而非 failed
			// PDU 已提交至 SMSC 网络层，SMSC 可能已接收（静默限流未返回 SubmitSMResp 不等于未收到）
			// 保持 sent 状态使 DLR 仍可匹配；若 SMSC 确实未收到，72h DLR 超时检查会标 expired
			for _, k := range staleKeys {
				if val, loaded := m.sequenceMap.LoadAndDelete(k); loaded {
					sd := val.(sequenceData)
					if err := publishSmsSubmitResult(sd.logID, sd.messageID, "", "sent", ""); err != nil {
						log.Printf("[SMPP-ERROR] stale cleanup publish sent: msgID=%s err=%v", sd.messageID, err)
					}
				}
			}

			// 2. 从 connections 中移除本会话，释放 in-flight 窗口阻塞
			m.mu.Lock()
			conns := m.connections[cfg.ID]
			for i, s := range conns {
				if s == session {
					m.connections[cfg.ID] = append(conns[:i], conns[i+1:]...)
					delete(m.sessionSubmitMu, session)
					break
				}
			}
			m.mu.Unlock()

			// 3. 关闭底层连接
			_ = session.Close()

			// 4. 自适应限流：降低 TPS，防止重绑后立即以原速率再次触发 SMSC 静默限流
			go m.throttleChannel(cfg.ID, cfg)

			// 5. 立即异步重绑，新 session 带自己的 stale monitor
			go func() {
				backoff := 2 * time.Second
				const maxBackoff = 60 * time.Second
				for attempt := 1; ; attempt++ {
					m.mu.RLock()
					_, still2 := m.configs[cfg.ID]
					m.mu.RUnlock()
					if !still2 {
						return
					}
					release := m.acquireBindSlot(cfg.ID)
					newSession, bindErr := m.bindSession(cfg)
					release()
					if bindErr != nil {
						log.Printf("[SMPP-WARN] stale-monitor rebind channel %s attempt %d: %v; retry in %v",
							cfg.ChannelCode, attempt, bindErr, backoff)
						time.Sleep(backoff)
						backoff *= 2
						if backoff > maxBackoff {
							backoff = maxBackoff
						}
						continue
					}
					m.mu.Lock()
					if _, exists := m.configs[cfg.ID]; exists {
						m.connections[cfg.ID] = append(m.connections[cfg.ID], newSession)
						m.sessionSubmitMu[newSession] = &sync.Mutex{}
						log.Printf("[SMPP-INFO] stale-monitor rebind success: channel %s (sessions: %d)",
							cfg.ChannelCode, len(m.connections[cfg.ID]))
					} else {
						_ = newSession.Close()
					}
					m.mu.Unlock()
					return
				}
			}()
			return // 本 monitor goroutine 退出，新 session 的 bindSession 会启动自己的 monitor
		}
	}()

	return session, nil
}

func (m *SMPPManager) handleDeliverSM(deliver *pdu.DeliverSM, cfg ChannelConfig) {
	msg, _ := deliver.Message.GetMessage()

	// 兼容上游回执的非标准 data_coding：部分上游（如 YZ_kafa/一正卡发）把 deliver_sm 回执的
	// data_coding 置为 0x04(8-bit binary)，gosmpp 的编码感知 GetMessage() 对该 DCS 解不出文本（返回空），
	// 导致回执串 "id:.. stat:DELIVRD" 丢失、消息永远卡在 sent。回执正文按 SMPP 规范恒为 ASCII，
	// 故 GetMessage() 取不到标准回执串时，回退用原始字节按 ASCII 解析。
	if !strings.Contains(msg, "id:") || !strings.Contains(msg, "stat:") {
		if raw, err := deliver.Message.GetMessageData(); err == nil && len(raw) > 0 {
			if rawStr := string(raw); strings.Contains(rawStr, "id:") || strings.Contains(rawStr, "stat:") {
				msg = rawStr
			}
		}
	}
	log.Printf("Received DeliverSM: %s", msg)

	// Extract id and stat from DLR text
	// Example: id:47bf0b49f97a865a sub:000 dlvrd:000 ... stat:DELIVRD err:000
	idMatch := regexp.MustCompile(`id:([^ ]+)`).FindStringSubmatch(msg)
	statMatch := regexp.MustCompile(`stat:([^ ]+)`).FindStringSubmatch(msg)

	if len(idMatch) > 1 && len(statMatch) > 1 {
		upstreamID := idMatch[1]
		stat := statMatch[1]

		// 归属过滤：当多套系统共用同一上游 SMPP 账号时，过滤掉不属于本系统的外来 DLR。
		// 未启用时 IsOwned 永远返回 true，行为与之前一致。
		if owns, _ := IsOwned(cfg.ID, upstreamID); !owns {
			log.Printf("[SMPP-DEBUG] DLR dropped (not owned by this system): channel=%s upstream=%s stat=%s", cfg.ChannelCode, upstreamID, stat)
			return
		}

		// Map SMPP stat to system status
		finalStatus := "sent"
		if stat == "DELIVRD" {
			finalStatus = "delivered"
		} else if stat == "REJECTD" || stat == "UNDELIV" || stat == "EXPIRED" || stat == "DELETED" {
			finalStatus = "failed"
		}

		// 不在 PDU 线程内同步写 MySQL（会阻塞读包与后续 DeliverSM）；由 Python process_smpp_dlr_task 写库与副作用。

		// [重要] 通知 Python Worker 写回执、对账、注水、Webhook 等
		dlrArgs := []interface{}{
			cfg.ID,      // channel_id
			upstreamID,  // upstream_id
			finalStatus, // new_status
			stat,        // stat
			"000",       // err (SMPP err context, fixed to 000 if not parsed)
			"",          // dest_addr (optional in Python _process_smpp_dlr_async if upstream_id matches)
			"",          // source_addr (optional)
			upstreamID,  // receipted_message_id (often same as upstreamID)
		}
		if pubErr := PublishCeleryTask("sms_dlr", "process_smpp_dlr_task", dlrArgs); pubErr != nil {
			log.Printf("[SMPP-ERROR] Failed to notify Python worker of DLR for %s: %v", upstreamID, pubErr)
		} else {
			log.Printf("[SMPP-DEBUG] Notified Python worker of DLR for %s", upstreamID)
		}
	}
}

// SendSMS picks a session and sends the message
func (m *SMPPManager) SendSMS(logID int64, messageID string, phoneNumber string, message string, channelID int) error {
	// 若当前无活跃连接（stale monitor 正在重绑中），阻塞等待最多 30 秒。
	// 避免重绑空窗口期间（通常 1-3 秒）所有并发消息立即失败。
	const noConnWaitMax = 30 * time.Second
	const noConnWaitInterval = 200 * time.Millisecond
	noConnWaited := time.Duration(0)
	for {
		m.mu.RLock()
		hasConn := len(m.connections[channelID]) > 0
		m.mu.RUnlock()
		if hasConn {
			break
		}
		if noConnWaited >= noConnWaitMax {
			// 等待超时仍无连接：以 _temp_error 前缀返回，consumer 会 nack+requeue 而非写 failed
			return fmt.Errorf("_temp_error: no active connections for channel %d after %v", channelID, noConnWaited)
		}
		if noConnWaited == 0 {
			log.Printf("[SMPP-WARN] channel %d no active connections, waiting for rebind...", channelID)
		}
		time.Sleep(noConnWaitInterval)
		noConnWaited += noConnWaitInterval
	}

	m.mu.RLock()
	conns := m.connections[channelID]
	cfg := m.configs[channelID]
	limiter := m.tpsLimiters[channelID]
	if len(conns) == 0 {
		m.mu.RUnlock()
		return fmt.Errorf("no active connections for channel %d", channelID)
	}
	// Round-robin 分散到不同 bind，配合每会话互斥实现多路并行 Submit。
	session := conns[time.Now().UnixNano()%int64(len(conns))]
	subMu := m.sessionSubmitMu[session]
	m.mu.RUnlock()

	// TPS 限速：令牌桶阻塞等待（MaxTPS>0 时生效）
	limiter.Wait()

	// 发送窗口检查：统计该通道当前 in-flight 数量。
	// 若超过阈值，说明 SMSC 已停止回包（静默限流/会话异常），阻塞等待窗口释放。
	// 调用方（processSingleSMS）不应在此情况下写 DB failed；此处阻塞而非返回错误，
	// 消息保持 pending/queued 状态，待 stale monitor（每 5s）关闭会话后窗口清空自动重试。
	// max_inflight 可通过 config_json 按通道定制（默认 500）。
	// inflightWaitInterval=200ms：stale monitor 清空条目后最快 200ms 内重新尝试（原 5s）。
	inflightWindowMax := parseConfigJSONInt(cfg.ConfigJSON, "max_inflight", 500)
	const inflightWaitInterval = 200 * time.Millisecond
	const inflightWaitMax = 120 * time.Second
	prefix := fmt.Sprintf("%d:", channelID)
	inflightWaited := time.Duration(0)
	for {
		inflightCount := 0
		m.sequenceMap.Range(func(k, _ interface{}) bool {
			if key, ok := k.(string); ok && len(key) > len(prefix) && key[:len(prefix)] == prefix {
				inflightCount++
			}
			return true
		})
		if inflightCount < inflightWindowMax {
			break
		}
		if inflightWaited == 0 {
			log.Printf("[SMPP-WARN] channel %d in-flight window full (%d/%d), blocking until SMSC responds or session rebuilds",
				channelID, inflightCount, inflightWindowMax)
		}
		if inflightWaited >= inflightWaitMax {
			// 超过最大等待时间仍未释放：返回错误让消费者 nack+requeue，但不写 DB（由调用方判断）
			return fmt.Errorf("_window_full: channel %d in-flight window full after %v", channelID, inflightWaited)
		}
		time.Sleep(inflightWaitInterval)
		inflightWaited += inflightWaitInterval
	}

	if subMu != nil {
		subMu.Lock()
		defer subMu.Unlock()
	}

	s := pdu.NewSubmitSM().(*pdu.SubmitSM)
	s.SourceAddr = pdu.NewAddress()
	s.SourceAddr.SetAddress(cfg.DefaultSenderID)
	s.DestAddr = pdu.NewAddress()
	destDigits := phoneNumber
	if stripLeadingPlusFromConfigJSON(cfg.ConfigJSON) {
		destDigits = destAddrNoPlus(phoneNumber)
	}
	s.DestAddr.SetAddress(destDigits)
	encoded, encErr := data.UCS2.Encode(message)
	if encErr != nil {
		log.Printf("[SMPP-ERROR] UCS2 Encode failed: channel=%s, msg=%s err=%v", cfg.ChannelCode, messageID, encErr)
		return fmt.Errorf("ucs2 encode: %w", encErr)
	}

	trans := session.Transmitter()
	if trans == nil {
		return fmt.Errorf("session has no transmitter")
	}

	// 短消息：直接 short_message 字段，与历史行为一致
	if len(encoded) <= data.SM_MSG_LEN {
		if err := s.Message.SetMessageDataWithEncoding(encoded, data.UCS2); err != nil {
			log.Printf("[SMPP-ERROR] SetMessageDataWithEncoding failed: channel=%s, msg=%s len=%d err=%v",
				cfg.ChannelCode, messageID, len(encoded), err)
			return fmt.Errorf("short_message: %w", err)
		}
		s.RegisteredDelivery = 1
		return m.submitOneAndTrack(s, trans, channelID, messageID, logID, destDigits, cfg, len(encoded), false, 0, 0, 0)
	}

	// 长消息：按通道配置选择 message_payload TLV 或 UDH 多段分段
	mode := longMessageModeFromConfigJSON(cfg.ConfigJSON)

	if mode == "udh_segmentation" {
		// UDH 8-bit ref 多段 SMS：每段 6 字节 UDH 头 + 134 字节 UCS-2 payload = 140 字节
		// 第一段持有 sequenceMap 条目（决定整条消息的 sent/failed/DLR 归属），
		// 其它段静默 Submit；其 SubmitSMResp 命中 OnPDU 的「无匹配映射」分支被忽略。
		// 折中：若第一段 sent 而后续段 failed，只能查日志发现；多数运营商对同一 concat 组
		// 全段同状态，跨段 status 分裂极少见。换全段联动跟踪需要在 Python 端引入「分段表」
		// 与 DLR 汇总逻辑，工程量大；当前最小可用方案优先解决发不出去的问题。
		segments := splitUCS2ForUDH(encoded)
		ref := nextConcatRef()
		total := byte(len(segments))
		for i, seg := range segments {
			part := byte(i + 1)
			var psm *pdu.SubmitSM
			if i == 0 {
				psm = s
			} else {
				psm = pdu.NewSubmitSM().(*pdu.SubmitSM)
				psm.SourceAddr = pdu.NewAddress()
				psm.SourceAddr.SetAddress(cfg.DefaultSenderID)
				psm.DestAddr = pdu.NewAddress()
				psm.DestAddr.SetAddress(destDigits)
				psm.RegisteredDelivery = s.RegisteredDelivery
			}

			// 清掉 short_message 后挂 UDH + payload
			if err := psm.Message.SetMessageDataWithEncoding(seg, data.UCS2); err != nil {
				log.Printf("[SMPP-ERROR] UDH SetMessageData failed: channel=%s msg=%s part=%d/%d err=%v",
					cfg.ChannelCode, messageID, part, total, err)
				if i == 0 {
					return fmt.Errorf("udh segment 1 set: %w", err)
				}
				continue
			}
			// 标准 1-byte ref concat UDH：IEI=0x00, IEDL=0x03, [ref, total, part]
			psm.Message.SetUDH(pdu.UDH{pdu.InfoElement{ID: 0x00, Data: []byte{ref, total, part}}})

			if i == 0 {
				psm.RegisteredDelivery = 1
				if err := m.submitOneAndTrack(psm, trans, channelID, messageID, logID, destDigits, cfg, len(encoded), true, ref, total, part); err != nil {
					return err
				}
			} else {
				// 后续段：不要求 DLR（避免 N 段各回一条 DLR），不存 sequenceMap
				psm.RegisteredDelivery = 0
				if err := trans.Submit(psm); err != nil {
					errMsg := err.Error()
					if strings.Contains(errMsg, "closing") || strings.Contains(errMsg, "closed") {
						log.Printf("[SMPP-WARN] UDH part %d/%d submit temp error (session closing): channel=%s msg=%s %v",
							part, total, cfg.ChannelCode, messageID, err)
						// 主段已成功提交，这里不返回 _temp_error 以免上层重发整条
						return nil
					}
					log.Printf("[SMPP-ERROR] UDH part %d/%d submit failed: channel=%s msg=%s %v",
						part, total, cfg.ChannelCode, messageID, err)
					// 不阻断后续段；接收端能收到的段会拼接展示，缺段处显示空白
				} else {
					log.Printf("[SMPP-DEBUG] Submitting SM (UDH part %d/%d): channel=%s sequence=%d dest=%s ref=%d seg_bytes=%d",
						part, total, cfg.ChannelCode, psm.SequenceNumber, destDigits, ref, len(seg))
				}
			}
		}
		return nil
	}

	// 默认：message_payload TLV（多数现代 SMSC 支持，且效率高于多段）
	if err := s.Message.SetMessageDataWithEncoding(nil, data.UCS2); err != nil {
		log.Printf("[SMPP-ERROR] clear short_message failed: channel=%s, msg=%s err=%v", cfg.ChannelCode, messageID, err)
		return fmt.Errorf("empty short_message: %w", err)
	}
	payload := make([]byte, len(encoded))
	copy(payload, encoded)
	s.RegisterOptionalParam(pdu.Field{Tag: pdu.TagMessagePayload, Data: payload})
	s.RegisteredDelivery = 1
	return m.submitOneAndTrack(s, trans, channelID, messageID, logID, destDigits, cfg, len(encoded), false, 0, 0, 0)
}

// submitOneAndTrack 注册 sequenceMap 后 Submit，统一处理 closing/closed 临时错误。
// udhInfo 仅供日志，udhTotal=0 表示非 UDH。
func (m *SMPPManager) submitOneAndTrack(
	s *pdu.SubmitSM, trans gosmpp.Transmitter,
	channelID int, messageID string, logID int64,
	destDigits string, cfg ChannelConfig,
	utf16Len int,
	udh bool, udhRef byte, udhTotal byte, udhPart byte,
) error {
	m.sequenceMap.Store(smppSeqMapKey(channelID, s.SequenceNumber), sequenceData{
		messageID:  messageID,
		logID:      logID,
		submitTime: time.Now(),
	})

	if udh {
		log.Printf("[SMPP-DEBUG] Submitting SM (UDH part %d/%d): channel=%s sequence=%d dest=%s ref=%d total_utf16_len=%d",
			udhPart, udhTotal, cfg.ChannelCode, s.SequenceNumber, destDigits, udhRef, utf16Len)
	} else {
		log.Printf("[SMPP-DEBUG] Submitting SM: channel=%s, sequence=%d, dest=%s, sender=%s, utf16_len=%d message_payload=%v",
			cfg.ChannelCode, s.SequenceNumber, destDigits, cfg.DefaultSenderID, utf16Len, utf16Len > data.SM_MSG_LEN)
	}

	err := trans.Submit(s)
	if err != nil {
		m.sequenceMap.Delete(smppSeqMapKey(channelID, s.SequenceNumber))
		errMsg := err.Error()
		if strings.Contains(errMsg, "closing") || strings.Contains(errMsg, "closed") {
			log.Printf("[SMPP-WARN] Submit temp error (session closing): channel=%s %v", cfg.ChannelCode, err)
			return fmt.Errorf("_temp_error: session closing: %v", err)
		}
		log.Printf("[SMPP-ERROR] Submit failed: %v", err)
		return err
	}
	return nil
}
