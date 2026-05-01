package main

import (
	"log"
	"net"
	"os"
	"strconv"
)

const defaultMaxConnsPerIP = 20

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
			log.Printf("[INBOUND] IP %s 连接数超限（max=%d），拒绝连接", remoteIP, maxConns)
			_ = conn.Close()
			continue
		}
		inboundReg.ipInc(remoteIP)
		go func(c net.Conn, ip string) {
			defer inboundReg.ipDec(ip)
			handleSession(c)
		}(conn, remoteIP)
	}
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
