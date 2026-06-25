package main

import (
	"log"
	"net"
	"os"
	"strconv"
	"sync/atomic"
	"time"
)

const (
	defaultMaxConnsPerIP = 20
	// 超 per-IP 上限连接的兜底（防 TCP 连接洪水）：
	// tarpit 延迟关闭被拒连接，拖慢狂连客户端的重连节奏（立即 close 会被瞬间重连喂养洪水）。
	defaultConnRejectTarpitMs = 2000 // 单条被拒连接延迟关闭时长(ms)
	defaultMaxTarpitConns     = 256  // 全局 tarpit 并发上限，防 FD 耗尽；超限退化为立即 close
)

var (
	tarpitConns     int64 // atomic：当前 tarpit 中的连接数
	connRejectCount int64 // atomic：累计超限拒绝次数，用于节流日志
)

// startInboundServer 在指定地址监听 TCP 2775，接受 SMPP 客户连接
func startInboundServer(addr string) {
	if addr == "" {
		addr = ":2775"
	}
	ln, err := net.Listen("tcp", addr)
	if err != nil {
		log.Fatalf("[INBOUND] 无法监听 %s: %v", addr, err)
	}
	log.Printf("[INBOUND] SMPP 入站服务器已启动，监听 %s", addr)
	for {
		conn, err := ln.Accept()
		if err != nil {
			log.Printf("[INBOUND] Accept 错误: %v", err)
			continue
		}
		remoteIP, _, _ := net.SplitHostPort(conn.RemoteAddr().String())
		maxConns := getEnvInt("INBOUND_MAX_CONNS_PER_IP", defaultMaxConnsPerIP)
		if inboundReg.ipCount(remoteIP) >= maxConns {
			rejectOverLimitConn(conn, remoteIP, maxConns)
			continue
		}
		inboundReg.ipInc(remoteIP)
		go func(c net.Conn, ip string) {
			defer inboundReg.ipDec(ip)
			handleSession(c)
		}(conn, remoteIP)
	}
}

// rejectOverLimitConn 处理超过 per-IP 上限的连接：节流日志 + 有上限的 tarpit 延迟关闭。
// 立即 close 会让狂连客户端瞬间重连、喂养 TCP 连接洪水；延迟关闭可拖慢其重连节奏。
// 全局 tarpit 并发上限防 FD 耗尽，超限退化为立即 close。
// 注：getEnvInt 对 <=0 回退默认值，故 tarpit 不能用 env=0 关闭；如需关闭把 INBOUND_MAX_TARPIT_CONNS 调到极小即可。
func rejectOverLimitConn(conn net.Conn, ip string, maxConns int) {
	if n := atomic.AddInt64(&connRejectCount, 1); n%2000 == 1 {
		log.Printf("[INBOUND] IP %s 连接数超限(max=%d)，累计拒绝 %d 次（tarpit 延迟关闭中）", ip, maxConns, n)
	}
	tarpitMs := getEnvInt("INBOUND_CONN_REJECT_TARPIT_MS", defaultConnRejectTarpitMs)
	maxTarpit := getEnvInt("INBOUND_MAX_TARPIT_CONNS", defaultMaxTarpitConns)
	// 关闭兜底 或 tarpit 池已满：直接立即 close（保护 FD）
	if tarpitMs <= 0 || atomic.AddInt64(&tarpitConns, 1) > int64(maxTarpit) {
		atomic.AddInt64(&tarpitConns, -1)
		_ = conn.Close()
		return
	}
	go func() {
		time.Sleep(time.Duration(tarpitMs) * time.Millisecond)
		_ = conn.Close()
		atomic.AddInt64(&tarpitConns, -1)
	}()
}

// getEnvInt 读取整型环境变量，失败时返回 defaultVal
func getEnvInt(key string, defaultVal int) int {
	v := os.Getenv(key)
	if v == "" {
		return defaultVal
	}
	n, err := strconv.Atoi(v)
	if err != nil || n <= 0 {
		return defaultVal
	}
	return n
}
