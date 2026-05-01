package main

import (
	"sync"
	"sync/atomic"
)

// bindType 绑定类型
type bindType uint8

const (
	bindTX  bindType = 1 // transmitter
	bindRX  bindType = 2 // receiver
	bindTRX bindType = 3 // transceiver
)

// inboundRegistry 维护 system_id → 在线会话集合
type inboundRegistry struct {
	mu       sync.RWMutex
	bySystem map[string][]*inboundSession
	perIP    map[string]int
}

func newInboundRegistry() *inboundRegistry {
	return &inboundRegistry{
		bySystem: make(map[string][]*inboundSession),
		perIP:    make(map[string]int),
	}
}

func (r *inboundRegistry) ipCount(ip string) int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.perIP[ip]
}

func (r *inboundRegistry) ipInc(ip string) {
	r.mu.Lock()
	r.perIP[ip]++
	r.mu.Unlock()
}

func (r *inboundRegistry) ipDec(ip string) {
	r.mu.Lock()
	if r.perIP[ip] > 0 {
		r.perIP[ip]--
	}
	if r.perIP[ip] == 0 {
		delete(r.perIP, ip)
	}
	r.mu.Unlock()
}

// CountBySystem 返回当前 system_id 已绑定数（用于 max_binds_per_account 限流）
func (r *inboundRegistry) CountBySystem(systemID string) int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return len(r.bySystem[systemID])
}

// Add 注册一个新绑定的会话
func (r *inboundRegistry) Add(s *inboundSession) {
	r.mu.Lock()
	r.bySystem[s.systemID] = append(r.bySystem[s.systemID], s)
	r.mu.Unlock()
}

// Remove 注销会话（连接断开时调用）
func (r *inboundRegistry) Remove(s *inboundSession) {
	r.mu.Lock()
	defer r.mu.Unlock()
	arr := r.bySystem[s.systemID]
	out := arr[:0]
	for _, ss := range arr {
		if ss != s {
			out = append(out, ss)
		}
	}
	if len(out) == 0 {
		delete(r.bySystem, s.systemID)
	} else {
		r.bySystem[s.systemID] = out
	}
}

// PickReceiver 选择一个能接收 deliver_sm 的会话（RX/TRX 优先）
func (r *inboundRegistry) PickReceiver(systemID string) *inboundSession {
	r.mu.RLock()
	defer r.mu.RUnlock()
	arr := r.bySystem[systemID]
	if len(arr) == 0 {
		return nil
	}
	// 优先 RECEIVER，其次 TRANSCEIVER；TRANSMITTER 不接收 DLR
	for _, s := range arr {
		if s.bindType == bindRX && atomic.LoadInt32(&s.closed) == 0 {
			return s
		}
	}
	for _, s := range arr {
		if s.bindType == bindTRX && atomic.LoadInt32(&s.closed) == 0 {
			return s
		}
	}
	return nil
}

// 全局单例（main.go 启动入站时初始化）
var inboundReg = newInboundRegistry()
