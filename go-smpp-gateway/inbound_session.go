package main

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const (
	bindReadTimeout      = 30 * time.Second
	idleReadTimeout      = 120 * time.Second
	enquireLinkInterval  = 30 * time.Second
	gwSystemID           = "kaolach"
	defaultMaxBinds      = 5
)

// tpsLimiter 简易令牌桶限速器（避免外部依赖）
type tpsLimiter struct {
	mu       sync.Mutex
	tokens   float64
	maxTok   float64
	rate     float64 // tokens/second
	lastTime time.Time
}

func newTPSLimiter(rps float64) *tpsLimiter {
	return &tpsLimiter{
		tokens:   rps,
		maxTok:   rps,
		rate:     rps,
		lastTime: time.Now(),
	}
}

func (l *tpsLimiter) Allow() bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	now := time.Now()
	add := now.Sub(l.lastTime).Seconds() * l.rate
	l.lastTime = now
	if l.tokens+add > l.maxTok {
		l.tokens = l.maxTok
	} else {
		l.tokens += add
	}
	if l.tokens >= 1 {
		l.tokens--
		return true
	}
	return false
}

// inboundSession 表示一条已绑定的 SMPP 客户连接
type inboundSession struct {
	conn     net.Conn
	remoteIP string
	systemID string
	account  *inboundAccount
	bindType bindType

	tps     *tpsLimiter
	closed  int32 // atomic
	writeMu chan struct{} // 单令牌信号量；保护 conn.Write 的串行化
}

func newInboundSession(conn net.Conn, ip string) *inboundSession {
	return &inboundSession{
		conn:     conn,
		remoteIP: ip,
		writeMu:  make(chan struct{}, 1),
	}
}

// writePDUSafe 串行化 conn 写
func (s *inboundSession) writePDUSafe(cmdID, status, seq uint32, body []byte) error {
	s.writeMu <- struct{}{}
	defer func() { <-s.writeMu }()
	return writePDU(s.conn, cmdID, status, seq, body)
}

func (s *inboundSession) close() {
	if atomic.CompareAndSwapInt32(&s.closed, 0, 1) {
		_ = s.conn.Close()
	}
}

// handleSession 是每条入站 TCP 连接的主驱动
func handleSession(conn net.Conn) {
	remoteIP, _, _ := net.SplitHostPort(conn.RemoteAddr().String())
	s := newInboundSession(conn, remoteIP)
	defer s.close()

	// 1) 等待 BIND（30s 超时）
	_ = conn.SetReadDeadline(time.Now().Add(bindReadTimeout))
	hdr, body, err := readPDU(conn)
	if err != nil {
		log.Printf("[INBOUND] %s 读初始 PDU 失败: %v", remoteIP, err)
		return
	}
	switch hdr.commandID {
	case cmdBindTransmitter:
		s.bindType = bindTX
	case cmdBindReceiver:
		s.bindType = bindRX
	case cmdBindTransceiver:
		s.bindType = bindTRX
	default:
		log.Printf("[INBOUND] %s 期望 BIND 但收到 cmd=%#x", remoteIP, hdr.commandID)
		_ = s.writePDUSafe(cmdGenericNack, statusInvCmdID, hdr.sequenceNumber, nil)
		return
	}
	bind, err := parseBind(body)
	if err != nil {
		log.Printf("[INBOUND] %s BIND body 解析失败: %v", remoteIP, err)
		_ = s.writePDUSafe(bindRespCmdID(hdr.commandID), statusInvMsgLen, hdr.sequenceNumber, nil)
		return
	}

	// 2) 鉴权
	respStatus, account := authenticateBind(remoteIP, bind)
	if respStatus != statusOK {
		_ = s.writePDUSafe(bindRespCmdID(hdr.commandID), respStatus, hdr.sequenceNumber, buildBindResp(gwSystemID))
		log.Printf("[INBOUND] %s BIND 拒绝: system_id=%s, status=%#x", remoteIP, bind.systemID, respStatus)
		return
	}
	s.account = account
	s.systemID = bind.systemID

	// 3) 单账户最大并发绑定数（优先账户级配置，回退全局环境变量）
	maxBinds := account.SmppMaxBinds
	if maxBinds <= 0 {
		maxBinds = getMaxBindsPerAccount()
	}
	if inboundReg.CountBySystem(s.systemID) >= maxBinds {
		_ = s.writePDUSafe(bindRespCmdID(hdr.commandID), statusBindFail, hdr.sequenceNumber, buildBindResp(gwSystemID))
		log.Printf("[INBOUND] %s BIND 拒绝（超过最大绑定数）: system_id=%s", remoteIP, s.systemID)
		return
	}

	// 4) TPS 限流（依据 accounts.rate_limit；默认 1000）
	tpsCap := account.RateLimit
	if tpsCap <= 0 {
		tpsCap = 1000
	}
	s.tps = newTPSLimiter(float64(tpsCap))

	// 5) 注册并响应 BIND_RESP ESME_ROK
	inboundReg.Add(s)
	defer inboundReg.Remove(s)
	if err := s.writePDUSafe(bindRespCmdID(hdr.commandID), statusOK, hdr.sequenceNumber, buildBindResp(gwSystemID)); err != nil {
		log.Printf("[INBOUND] %s BIND 应答写失败: %v", remoteIP, err)
		return
	}
	log.Printf("[INBOUND] %s BIND 成功: system_id=%s account_id=%d type=%d",
		remoteIP, s.systemID, account.ID, s.bindType)

	// 6) 启动 enquire_link 定时心跳
	go s.enquireLinkLoop()

	// 7) 若是 RX/TRX，补发离线期间累积的 DLR
	if s.bindType == bindRX || s.bindType == bindTRX {
		go s.drainPendingDLRs()
	}

	// 8) 主读循环
	s.readLoop()
}

func bindRespCmdID(reqCmdID uint32) uint32 {
	switch reqCmdID {
	case cmdBindTransmitter:
		return cmdBindTransmitterResp
	case cmdBindReceiver:
		return cmdBindReceiverResp
	case cmdBindTransceiver:
		return cmdBindTransceiverResp
	}
	return reqCmdID | 0x80000000
}

// authenticateBind 检查 system_id 存在性、状态、protocol、IP 白名单、密码
// 返回 (statusCode, account)；statusCode == statusOK 时 account 非空
func authenticateBind(ip string, bind bindBody) (uint32, *inboundAccount) {
	a, err := LoadAccountBySystemID(bind.systemID)
	if err != nil {
		log.Printf("[INBOUND] LoadAccountBySystemID(%s) 错误: %v", bind.systemID, err)
		return statusSysErr, nil
	}
	if a == nil {
		return statusInvSysID, nil
	}
	if !strings.EqualFold(strings.TrimSpace(a.Protocol), "SMPP") {
		return statusInvSysID, nil
	}
	if a.Status != "active" {
		return statusBindFail, nil
	}
	if !a.IPWhitelistAllow(ip) {
		return statusBindFail, nil
	}
	// SMPP 3.4 密码字段最长 8 字节；DB 可能存全长，取前 8 位比较
	dbPwd := a.Password
	if len(dbPwd) > 8 {
		dbPwd = dbPwd[:8]
	}
	clientPwd := bind.password
	if len(clientPwd) > 8 {
		clientPwd = clientPwd[:8]
	}
	if !constantTimeEqualString(dbPwd, clientPwd) {
		return statusInvPaswd, nil
	}
	return statusOK, a
}

// constantTimeEqualString 防侧信道字符串比较
func constantTimeEqualString(a, b string) bool {
	if len(a) != len(b) {
		return false
	}
	var v byte
	for i := 0; i < len(a); i++ {
		v |= a[i] ^ b[i]
	}
	return v == 0
}

func getMaxBindsPerAccount() int {
	return getEnvInt("INBOUND_MAX_BINDS_PER_ACCOUNT", defaultMaxBinds)
}

// enquireLinkLoop 周期发送 enquire_link，对端无响应到 idleReadTimeout 由 readLoop 触发关闭
func (s *inboundSession) enquireLinkLoop() {
	ticker := time.NewTicker(enquireLinkInterval)
	defer ticker.Stop()
	for {
		<-ticker.C
		if atomic.LoadInt32(&s.closed) != 0 {
			return
		}
		if err := s.writePDUSafe(cmdEnquireLink, statusOK, nextSeq(), nil); err != nil {
			return
		}
	}
}

var seqCounter uint32

func nextSeq() uint32 {
	return atomic.AddUint32(&seqCounter, 1)
}

// readLoop 读取并 dispatch 客户后续 PDU
func (s *inboundSession) readLoop() {
	for {
		_ = s.conn.SetReadDeadline(time.Now().Add(idleReadTimeout))
		hdr, body, err := readPDU(s.conn)
		if err != nil {
			if !errors.Is(err, io.EOF) && !isTimeoutErr(err) {
				log.Printf("[INBOUND] %s readLoop 错误: %v", s.remoteIP, err)
			}
			return
		}
		switch hdr.commandID {
		case cmdSubmitSM:
			s.handleSubmitSM(hdr, body)
		case cmdEnquireLink:
			_ = s.writePDUSafe(cmdEnquireLinkResp, statusOK, hdr.sequenceNumber, nil)
		case cmdEnquireLinkResp:
			// noop：客户对我们 enquire_link 的应答
		case cmdUnbind:
			_ = s.writePDUSafe(cmdUnbindResp, statusOK, hdr.sequenceNumber, nil)
			return
		case cmdDeliverSMResp:
			// 客户对我们推送的 deliver_sm 的应答；当前不做严格 sequence 跟踪
		default:
			_ = s.writePDUSafe(cmdGenericNack, statusInvCmdID, hdr.sequenceNumber, nil)
		}
	}
}

func isTimeoutErr(err error) bool {
	var ne net.Error
	if errors.As(err, &ne) {
		return ne.Timeout()
	}
	return false
}

// handleSubmitSM 处理客户 SUBMIT_SM：限流 → 解码 → 入队 → 立即应答 submit_sm_resp
func (s *inboundSession) handleSubmitSM(hdr pduHeader, body []byte) {
	if s.bindType == bindRX {
		// RX 不允许提交
		_ = s.writePDUSafe(cmdSubmitSMResp, statusInvBindStatus, hdr.sequenceNumber, buildSubmitSMResp(""))
		return
	}
	if !s.tps.Allow() {
		_ = s.writePDUSafe(cmdSubmitSMResp, statusThrottled, hdr.sequenceNumber, buildSubmitSMResp(""))
		return
	}
	sm, err := parseSubmitSM(body)
	if err != nil {
		_ = s.writePDUSafe(cmdSubmitSMResp, statusInvMsgLen, hdr.sequenceNumber, buildSubmitSMResp(""))
		return
	}
	// message_payload TLV (0x0424) 优先于 short_message
	rawMsg := sm.shortMessage
	if v, ok := sm.tlvs[0x0424]; ok && len(v) > 0 {
		rawMsg = v
	}
	text := decodeShortMessage(rawMsg, sm.dataCoding)

	msgID := generateMessageID()
	job := submitJob{
		AccountID:          s.account.ID,
		MessageID:          msgID,
		SystemID:           s.systemID,
		SourceAddr:         sm.sourceAddr,
		DestAddr:           normalizeDestAddr(sm.destAddr),
		Message:            text,
		IP:                 s.remoteIP,
		RegisteredDelivery: int(sm.registeredDelivery & 0x01),
	}

	queued, busy := trySubmit(job)
	if !queued {
		if busy {
			_ = s.writePDUSafe(cmdSubmitSMResp, statusMsgQFul, hdr.sequenceNumber, buildSubmitSMResp(""))
			return
		}
		_ = s.writePDUSafe(cmdSubmitSMResp, statusSysErr, hdr.sequenceNumber, buildSubmitSMResp(""))
		return
	}

	// 入站审计
	_ = InsertInboundSubmission(msgID, s.account.ID, s.systemID, sm.sourceAddr, job.DestAddr)

	_ = s.writePDUSafe(cmdSubmitSMResp, statusOK, hdr.sequenceNumber, buildSubmitSMResp(msgID))
}

// generateMessageID 生成 16-字符 hex（与 Python 端 message_id 字段长度匹配；Python 接到后直接作为 SMSLog.message_id）
func generateMessageID() string {
	var buf [8]byte
	_, _ = rand.Read(buf[:])
	return hex.EncodeToString(buf[:])
}

// normalizeDestAddr 把 SMPP destination_addr 转为 Python 校验需要的 E.164 风格
// 客户可能会传 "8801712345678"（无 +）或 "+8801712345678"
func normalizeDestAddr(s string) string {
	s = strings.TrimSpace(s)
	if s == "" || strings.HasPrefix(s, "+") {
		return s
	}
	// 国际号码经验：长度 ≥ 7 时加 +
	if len(s) >= 7 {
		return "+" + s
	}
	return s
}

// drainPendingDLRs 客户 RX/TRX 上线时补发离线期间未推送的 DLR
func (s *inboundSession) drainPendingDLRs() {
	rows, err := LoadPendingDLRs(s.systemID, 200)
	if err != nil {
		log.Printf("[INBOUND] LoadPendingDLRs(%s) 错误: %v", s.systemID, err)
		return
	}
	if len(rows) == 0 {
		return
	}
	log.Printf("[INBOUND] %s 上线，补发 %d 条 DLR", s.systemID, len(rows))
	for _, r := range rows {
		if atomic.LoadInt32(&s.closed) != 0 {
			return
		}
		if err := s.pushDeliverSM(r.Payload); err == nil {
			_ = DeletePendingDLR(r.ID)
		} else {
			log.Printf("[INBOUND] 补发 DLR 失败 id=%d: %v", r.ID, err)
			return
		}
	}
}

// pushDeliverSM 把 DLR payload 编码并写入 conn
func (s *inboundSession) pushDeliverSM(payload map[string]interface{}) error {
	src, _ := payload["dest_addr"].(string)   // DLR：原 dest 变 source
	dst, _ := payload["source_addr"].(string) // 反之
	stat, _ := payload["stat"].(string)
	errCode, _ := payload["err"].(string)
	msgID, _ := payload["message_id"].(string)
	subDate, _ := payload["submit_date"].(string)
	doneDate, _ := payload["done_date"].(string)
	textPreview, _ := payload["text_preview"].(string)
	if errCode == "" {
		errCode = "000"
	}
	if subDate == "" {
		subDate = time.Now().Format("0601021504")
	}
	if doneDate == "" {
		doneDate = subDate
	}
	dlrText := fmt.Sprintf("id:%s sub:001 dlvrd:001 submit date:%s done date:%s stat:%s err:%s text:%s",
		msgID, subDate, doneDate, stat, errCode, textPreview)
	body := buildDeliverSM(deliverSMParams{
		sourceAddr:   src,
		destAddr:     dst,
		dataCoding:   0,
		esmClass:     0x04,
		shortMessage: []byte(dlrText),
	})
	return s.writePDUSafe(cmdDeliverSM, statusOK, nextSeq(), body)
}
