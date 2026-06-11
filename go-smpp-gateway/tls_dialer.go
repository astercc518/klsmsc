package main

import (
	"crypto/tls"
	"encoding/json"
	"net"
	"strings"

	"github.com/linxGnu/gosmpp"
)

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
	if !channelUsesTLS(cfg) {
		return gosmpp.NonTLSDialer
	}
	return func(addr string) (net.Conn, error) {
		return tls.Dial("tcp", addr, &tls.Config{
			MinVersion: tls.VersionTLS12,
		})
	}
}
