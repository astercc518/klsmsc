package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strings"
	"time"
)

// probeBindRequest 与 Python 管理端 POST 体一致
type probeBindRequest struct {
	Host       string `json:"host"`
	Port       int    `json:"port"`
	SystemID   string `json:"system_id"`
	Password   string `json:"password"`
	BindMode   string `json:"bind_mode"`
	SystemType string `json:"system_type"`
	ChannelRef string `json:"channel_ref"` // 仅用于日志
}

type probeBindResponse struct {
	Success bool   `json:"success"`
	Status  string `json:"status"`
	Message string `json:"message"`
}

func startProbeBindServer(listenAddr string) {
	token := strings.TrimSpace(os.Getenv("SMPP_PROBE_TOKEN"))
	if token == "" {
		log.Println("[SMPP-PROBE] 未设置 SMPP_PROBE_TOKEN，探测服务不启动（避免未授权 bind）")
		return
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/probe-bind", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		if r.Method != http.MethodPost {
			w.WriteHeader(http.StatusMethodNotAllowed)
			_ = json.NewEncoder(w).Encode(probeBindResponse{Success: false, Status: "offline", Message: "仅支持 POST"})
			return
		}
		if strings.TrimSpace(r.Header.Get("X-Smpp-Probe-Token")) != token {
			w.WriteHeader(http.StatusUnauthorized)
			_ = json.NewEncoder(w).Encode(probeBindResponse{Success: false, Status: "offline", Message: "未授权"})
			return
		}
		var body probeBindRequest
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			_ = json.NewEncoder(w).Encode(probeBindResponse{Success: false, Status: "offline", Message: "JSON 解析失败: " + err.Error()})
			return
		}
		ref := strings.TrimSpace(body.ChannelRef)
		if ref == "" {
			ref = "probe"
		}
		cfg := ChannelConfig{
			ID:          0,
			ChannelCode: ref,
			Protocol:    "SMPP",
			Host:        body.Host,
			Port:        body.Port,
			Username:    body.SystemID,
			Password:    body.Password,
			BindMode:    body.BindMode,
			SystemType:  body.SystemType,
		}
		// Short-circuit：若主连接当前已活(watchdog 视为正常)，直接返回 online，无需另开
		// 新 bind 占用上游账号 max_connections 配额。部分上游(woId 实测限连接数=1)再开
		// 新 bind 会被立即 EOF，导致 UI 误以为通道挂了。
		if manager != nil {
			if alive, lastPDU := manager.IsChannelHealthyByCode(ref); alive {
				log.Printf("[SMPP-PROBE] %s 主连接已活(最近 PDU %v 前)，跳过新 bind 探测", ref, time.Since(lastPDU).Round(time.Second))
				_ = json.NewEncoder(w).Encode(probeBindResponse{
					Success: true,
					Status:  "online",
					Message: "主连接持续在线（依据 PDU 心跳），未发起额外 bind",
				})
				return
			}
		}
		if err := smppOneShotBind(cfg); err != nil {
			log.Printf("[SMPP-PROBE] bind 失败 %s: %v", ref, err)
			_ = json.NewEncoder(w).Encode(probeBindResponse{
				Success: false,
				Status:  "offline",
				Message: err.Error(),
			})
			return
		}
		_ = json.NewEncoder(w).Encode(probeBindResponse{
			Success: true,
			Status:  "online",
			Message: "SMPP bind 成功（已关闭探测会话）",
		})
	})

	srv := &http.Server{
		Addr:              listenAddr,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       30 * time.Second,
		WriteTimeout:      30 * time.Second,
	}
	log.Printf("[SMPP-PROBE] 监听 %s （POST /probe-bind）", listenAddr)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("[SMPP-PROBE] HTTP 服务异常: %v", err)
	}
}
