package main

import (
    "encoding/json"
    "fmt"
    "log"
    "regexp"
    "strings"
    "sync"
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
    interval := time.Second / time.Duration(tps)
    go func() {
        ticker := time.NewTicker(interval)
        defer ticker.Stop()
        for {
            select {
            case <-b.done:
                return
            case <-ticker.C:
                select {
                case b.tokens <- struct{}{}:
                default:
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
	connections  map[int][]*gosmpp.Session
	configs      map[int]ChannelConfig
	mu           sync.RWMutex
	// 每个 bind 会话独立互斥：Submit 与 sequence 登记串行，避免多 goroutine 同 session 竞态。
	sessionSubmitMu map[*gosmpp.Session]*sync.Mutex
	// sequenceMap 键为「通道ID:序列号」。仅用序列号会与多 bind 会话或其它通道的序号冲突，导致 SubmitSMResp 无法匹配、短信永久 queued。
	sequenceMap sync.Map
	// tpsLimiters 每通道令牌桶限速器（按 max_tps 配置）
	tpsLimiters map[int]*tpsBucket
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

func InitSMPPManager() {
	manager = &SMPPManager{
		connections:     make(map[int][]*gosmpp.Session),
		configs:         make(map[int]ChannelConfig),
		sessionSubmitMu: make(map[*gosmpp.Session]*sync.Mutex),
		tpsLimiters:     make(map[int]*tpsBucket),
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
                    session, err := m.bindSession(cfg)
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
                switch pd := p.(type) {
				case *pdu.SubmitSMResp:
					log.Printf("[SMPP-DEBUG] SubmitSMResp reached: channel=%s, msgID=%s, sequence=%d, status=%d", cfg.ChannelCode, pd.MessageID, pd.SequenceNumber, pd.CommandStatus)
					
					if val, ok := m.sequenceMap.LoadAndDelete(smppSeqMapKey(cfg.ID, pd.SequenceNumber)); ok {
                        seqData := val.(sequenceData)
                        log.Printf("[SMPP-DEBUG] Found matching sequence for msg: %s (internal log ID: %d)", seqData.messageID, seqData.logID)
                        
                        if pd.CommandStatus == data.ESME_ROK {
                            err := UpdateSMSLogResult(seqData.logID, seqData.messageID, pd.MessageID, "sent", "")
                            if err != nil {
                                log.Printf("[SMPP-ERROR] Failed to update upstream ID for %s: %v", seqData.messageID, err)
                            } else {
                                log.Printf("[SMPP-DEBUG] Successfully mapped upstream ID: %s => %s", seqData.messageID, pd.MessageID)
                            }
                        } else {
                            log.Printf("[SMPP-ERROR] SubmitSM failed with status %d for msg %s", pd.CommandStatus, seqData.messageID)
                            err := UpdateSMSLogResult(seqData.logID, seqData.messageID, "", "failed", fmt.Sprintf("SMPP Error: %d", pd.CommandStatus))
                            if err != nil {
                                log.Printf("[SMPP-ERROR] Failed to record SMPP error for %s: %v", seqData.messageID, err)
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
                m.mu.Lock()
                if closedSession != nil {
                    conns := m.connections[cfg.ID]
                    for i, s := range conns {
                        if s == closedSession {
                            m.connections[cfg.ID] = append(conns[:i], conns[i+1:]...)
                            delete(m.sessionSubmitMu, closedSession)
                            break
                        }
                    }
                }
                m.mu.Unlock()

                // 2. 立即触发异步重绑，不等 5 分钟 ReloadChannels 周期
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
                        newSession, err := m.bindSession(cfg)
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

                // 3. 清理该通道所有 in-flight sequenceMap 条目
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
                            if err := UpdateSMSLogResult(seq.logID, seq.messageID, "", "sent", ""); err != nil {
                                log.Printf("[SMPP-ERROR] Failed to mark orphan as sent: msgID=%s err=%v", seq.messageID, err)
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
                    if err := UpdateSMSLogResult(sd.logID, sd.messageID, "", "sent", ""); err != nil {
                        log.Printf("[SMPP-ERROR] stale cleanup mark sent: msgID=%s err=%v", sd.messageID, err)
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
                    newSession, bindErr := m.bindSession(cfg)
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
    log.Printf("Received DeliverSM: %s", msg)

    // Extract id and stat from DLR text
    // Example: id:47bf0b49f97a865a sub:000 dlvrd:000 ... stat:DELIVRD err:000
    idMatch := regexp.MustCompile(`id:([^ ]+)`).FindStringSubmatch(msg)
    statMatch := regexp.MustCompile(`stat:([^ ]+)`).FindStringSubmatch(msg)

    if len(idMatch) > 1 && len(statMatch) > 1 {
        upstreamID := idMatch[1]
        stat := statMatch[1]
        
        // Map SMPP stat to system status
        finalStatus := "sent"
        if stat == "DELIVRD" {
            finalStatus = "delivered"
        } else if stat == "REJECTD" || stat == "UNDELIV" || stat == "EXPIRED" || stat == "DELETED" {
            finalStatus = "failed"
        }

        err := UpdateSMSLogDLR(upstreamID, finalStatus)
        if err != nil {
            log.Printf("Failed to update DLR for upstreamID %s: %v", upstreamID, err)
        } else {
            log.Printf("Successfully updated DLR for message %s: %s", upstreamID, finalStatus)
        }

        // [重要] 通知 Python Worker 进行对账、注水、Webhook 等复杂逻辑
        dlrArgs := []interface{}{
            cfg.ID,         // channel_id
            upstreamID,     // upstream_id
            finalStatus,    // new_status
            stat,           // stat
            "000",          // err (SMPP err context, fixed to 000 if not parsed)
            "",             // dest_addr (optional in Python _process_smpp_dlr_async if upstream_id matches)
            "",             // source_addr (optional)
            upstreamID,     // receipted_message_id (often same as upstreamID)
        }
        err = PublishCeleryTask("sms_dlr", "process_smpp_dlr_task", dlrArgs)
        if err != nil {
            log.Printf("[SMPP-ERROR] Failed to notify Python worker of DLR for %s: %v", upstreamID, err)
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
	_ = s.Message.SetMessageWithEncoding(message, data.UCS2)
	s.RegisteredDelivery = 1

	trans := session.Transmitter()
	if trans == nil {
		return fmt.Errorf("session has no transmitter")
	}

	m.sequenceMap.Store(smppSeqMapKey(channelID, s.SequenceNumber), sequenceData{
		messageID:  messageID,
		logID:      logID,
		submitTime: time.Now(),
	})

	log.Printf("[SMPP-DEBUG] Submitting SM: channel=%s, sequence=%d, dest=%s, sender=%s, len=%d",
		cfg.ChannelCode, s.SequenceNumber, destDigits, cfg.DefaultSenderID, len(message))

	err := trans.Submit(s)
	if err != nil {
		m.sequenceMap.Delete(smppSeqMapKey(channelID, s.SequenceNumber))
		errMsg := err.Error()
		// session 正在关闭/已关闭属临时错误：调用方 nack+requeue，不写 DB failed
		if strings.Contains(errMsg, "closing") || strings.Contains(errMsg, "closed") {
			log.Printf("[SMPP-WARN] Submit temp error (session closing): channel=%s %v", cfg.ChannelCode, err)
			return fmt.Errorf("_temp_error: session closing: %v", err)
		}
		log.Printf("[SMPP-ERROR] Submit failed: %v", err)
		return err
	}

	return nil
}
