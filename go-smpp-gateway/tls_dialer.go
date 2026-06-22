package main

import (
	"crypto/tls"
	"encoding/json"
	"net"
	"strings"
	"sync"
	"time"

	"github.com/linxGnu/gosmpp"
)

// —— 每通道 TCP 拨号速率闸门（防重连自激风暴）——
// acquireBindSlot 只串行化「应用层发起的 bind」，挡不住 gosmpp 库在连接被 RST 后于内部
// 紧重拨的自激循环（曾致 SMSCPRO 中继对 KLSMSC ~1000 连接/秒）。dialer 是所有 TCP 拨号
// （明文/TLS、应用层/库内部）的唯一卡点，在此按通道限速即可根治。
const minDialInterval = 500 * time.Millisecond // 同通道两次拨号最小间隔 → 上限 2 拨/秒/通道

var (
	dialGateMu sync.Mutex
	dialChanMu = make(map[int]*sync.Mutex)   // 每通道串行化锁
	lastDialAt = make(map[int]time.Time)      // 每通道上次拨号时刻
)

// waitDialSlot 阻塞直到允许本通道发起下一次 TCP 拨号（串行化 + 最小间隔）。
func waitDialSlot(channelID int) {
	dialGateMu.Lock()
	cmu, ok := dialChanMu[channelID]
	if !ok {
		cmu = &sync.Mutex{}
		dialChanMu[channelID] = cmu
	}
	dialGateMu.Unlock()

	cmu.Lock()
	defer cmu.Unlock()

	dialGateMu.Lock()
	last := lastDialAt[channelID]
	dialGateMu.Unlock()
	if since := time.Since(last); since < minDialInterval {
		time.Sleep(minDialInterval - since)
	}
	dialGateMu.Lock()
	lastDialAt[channelID] = time.Now()
	dialGateMu.Unlock()
}

// parseConfigJSONBool 读取 channels.config_json 里的布尔开关；缺省返回 defaultVal。
// 兼容 true / "true" / 1 等写法（与 phone_utils 的 strip_leading_plus 解析口径一致）。
func parseConfigJSONBool(raw string, key string, defaultVal bool) bool {
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
	case bool:
		return x
	case float64:
		return x != 0
	case string:
		switch strings.ToLower(strings.TrimSpace(x)) {
		case "false", "0", "no", "off", "":
			return false
		default:
			return true
		}
	default:
		return defaultVal
	}
}

// channelUsesTLS 判定通道是否走 SSL/TLS：
// 显式 config_json {"use_tls": true} 开启，或端口为 8887（Infobip SSL 端点约定）时自动开启。
func channelUsesTLS(cfg ChannelConfig) bool {
	if parseConfigJSONBool(cfg.ConfigJSON, "use_tls", false) {
		return true
	}
	return cfg.Port == 8887
}

// dialerForChannel 返回该通道使用的连接拨号器：
// 默认明文（gosmpp.NonTLSDialer）；当 channelUsesTLS 为真时返回 TLS 拨号器。
// TLS 拨号器复用 addr 中的主机名做 SNI / 证书校验（tls.Dial 在 ServerName 为空时自动取 addr 主机名）。
func dialerForChannel(cfg ChannelConfig) gosmpp.Dialer {
	chID := cfg.ID
	if !channelUsesTLS(cfg) {
		return func(addr string) (net.Conn, error) {
			waitDialSlot(chID) // 拨号前过每通道速率闸门（含 gosmpp 内部重拨）
			return gosmpp.NonTLSDialer(addr)
		}
	}
	return func(addr string) (net.Conn, error) {
		waitDialSlot(chID)
		return tls.Dial("tcp", addr, &tls.Config{
			MinVersion: tls.VersionTLS12,
		})
	}
}
