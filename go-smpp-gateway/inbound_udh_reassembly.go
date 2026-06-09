package main

import (
	"fmt"
	"log"
	"strings"
	"sync"
	"time"
)

// 入站 UDH 多段重组。
//
// 背景：客户(如 SMSCPRO 中继)对长短信用标准 UDH 客户端分段，发来 N 条 submit_sm，
// 每条 short_message 前缀挂 6/7 字节 UDH 头(8-bit ref IEI=0x00 / 16-bit ref IEI=0x08)。
// 入站若按单条解码 short_message，会把 UDH 头当正文解出乱码、且 N 段各成一条独立消息。
// 本模块在 esm_class 含 UDHI 位时剥头、按 (account,src,dst,ref,total) 缓冲分段，
// 集齐后合并成「一条」完整文本向后端转发，DLR 沿用整组共享的 message_id。
//
// 仅在 UDHI 位置位时介入；普通短信路径完全不变。

const (
	udhiBit             = 0x40             // esm_class 的 UDHI(User Data Header Indicator)位
	reassemblyTTL       = 60 * time.Second // 一组分段最长等待集齐时间
	reassemblyReapEvery = 30 * time.Second // reaper 扫描周期
	reassemblyMaxGroups = 20000            // 并发缓冲组上限，防 OOM/恶意半包洪水
)

// concatInfo 从 UDH 解出的拼接信息
type concatInfo struct {
	ref       uint16
	total     byte
	part      byte
	hasConcat bool
}

// parseUDH 解析 short_message 前缀的 UDH，返回拼接信息与「去掉 UDH 后的正文 payload」。
// 调用方需已确认 esm_class 含 UDHI 位。UDH 越界等异常时按原样返回(不剥)，保持鲁棒。
func parseUDH(sm []byte) (concatInfo, []byte) {
	var ci concatInfo
	if len(sm) < 1 {
		return ci, sm
	}
	udhl := int(sm[0])
	if 1+udhl > len(sm) {
		return ci, sm // 长度字段越界，原样返回
	}
	udh := sm[1 : 1+udhl]
	payload := sm[1+udhl:]
	// 遍历 IE：[IEI, IEDL, data...]
	for i := 0; i+2 <= len(udh); {
		iei := udh[i]
		iedl := int(udh[i+1])
		if i+2+iedl > len(udh) {
			break
		}
		d := udh[i+2 : i+2+iedl]
		switch {
		case iei == 0x00 && iedl == 3: // 8-bit ref 拼接 IE
			ci.ref = uint16(d[0])
			ci.total = d[1]
			ci.part = d[2]
			ci.hasConcat = true
		case iei == 0x08 && iedl == 4: // 16-bit ref 拼接 IE
			ci.ref = uint16(d[0])<<8 | uint16(d[1])
			ci.total = d[2]
			ci.part = d[3]
			ci.hasConcat = true
		}
		i += 2 + iedl
	}
	return ci, payload
}

// reassemblyGroup 缓冲一组(同 src/dst/ref/total)的分段
type reassemblyGroup struct {
	parts     map[byte]string // part(1..total) → 该段解码后文本
	total     byte
	tmpl      submitJob // 首段捕获的转发模板(已含 MessageID=组共享 ID)
	createdAt time.Time
}

type reassemblyStore struct {
	mu     sync.Mutex
	groups map[string]*reassemblyGroup
}

var udhStore = &reassemblyStore{groups: make(map[string]*reassemblyGroup)}

func reassemblyKey(accountID int, src, dst string, ref uint16, total byte) string {
	return fmt.Sprintf("%d|%s|%s|%d|%d", accountID, src, dst, ref, total)
}

// addSegment 加入一段。
// 返回 (ready, respMsgID)：respMsgID 是整组共享的 message_id(每段都用它回 submit_sm_resp，
// 客户仅跟踪第 1 段→拿到正确 ID)；ready 非 nil 表示本段使整组集齐、可直接入队转发。
func (rs *reassemblyStore) addSegment(key string, ci concatInfo, segText string, tmpl submitJob) (ready *submitJob, respMsgID string) {
	rs.mu.Lock()
	defer rs.mu.Unlock()

	g := rs.groups[key]
	if g == nil {
		if len(rs.groups) >= reassemblyMaxGroups {
			rs.evictOldestLocked()
		}
		tmpl.MessageID = generateMessageID() // 整组共享 ID
		g = &reassemblyGroup{
			parts:     make(map[byte]string, ci.total),
			total:     ci.total,
			tmpl:      tmpl,
			createdAt: time.Now(),
		}
		rs.groups[key] = g
	}
	g.parts[ci.part] = segText // 重复段(重投)覆盖，天然去重
	if tmpl.RegisteredDelivery == 1 {
		g.tmpl.RegisteredDelivery = 1 // 任一段(通常第1段)要 DLR → 整条要 DLR
	}

	if byte(len(g.parts)) < g.total {
		return nil, g.tmpl.MessageID // 未集齐
	}
	// 集齐：按 part 升序拼接成整条
	job := g.tmpl
	job.Message = assembleParts(g.parts, g.total)
	msgID := g.tmpl.MessageID
	delete(rs.groups, key)
	return &job, msgID
}

// assembleParts 按 part 序号 1..total 升序拼接；缺段则跳过(超时 flush 时可能缺段)
func assembleParts(parts map[byte]string, total byte) string {
	var b strings.Builder
	for p := byte(1); p <= total; p++ {
		if seg, ok := parts[p]; ok {
			b.WriteString(seg)
		}
	}
	return b.String()
}

// evictOldestLocked 容量超限时驱逐最旧的一组(调用方须持锁)
func (rs *reassemblyStore) evictOldestLocked() {
	var oldestKey string
	var oldestAt time.Time
	first := true
	for k, g := range rs.groups {
		if first || g.createdAt.Before(oldestAt) {
			oldestKey, oldestAt, first = k, g.createdAt, false
		}
	}
	if !first {
		log.Printf("[INBOUND-UDH] 缓冲组超上限(%d)，驱逐最旧组 key=%s", reassemblyMaxGroups, oldestKey)
		delete(rs.groups, oldestKey)
	}
}

// reap 扫描并 flush 超时未集齐的组：把已到的段按序拼接转发，避免整条丢失(记日志)
func (rs *reassemblyStore) reap() {
	now := time.Now()
	var flush []submitJob
	rs.mu.Lock()
	for k, g := range rs.groups {
		if now.Sub(g.createdAt) > reassemblyTTL {
			job := g.tmpl
			job.Message = assembleParts(g.parts, g.total)
			flush = append(flush, job)
			log.Printf("[INBOUND-UDH] 组超时 %d/%d 段，flush 部分 msgid=%s dst=%s",
				len(g.parts), g.total, g.tmpl.MessageID, g.tmpl.DestAddr)
			delete(rs.groups, k)
		}
	}
	rs.mu.Unlock()
	for _, job := range flush {
		if queued, _ := trySubmit(job); !queued {
			publishRejectDLR(job, "reassembly timeout: queue full")
		}
	}
}

// startReassemblyReaper 在 main 启动时调用一次
func startReassemblyReaper() {
	go func() {
		t := time.NewTicker(reassemblyReapEvery)
		defer t.Stop()
		for range t.C {
			udhStore.reap()
		}
	}()
}
