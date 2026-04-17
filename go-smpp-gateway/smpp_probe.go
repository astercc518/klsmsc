package main

import (
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/linxGnu/gosmpp"
	"github.com/linxGnu/gosmpp/pdu"
)

// smppOneShotBind 执行一次真实 SMPP bind，成功后立即关闭会话；用于管理端「通道检测」。
func smppOneShotBind(cfg ChannelConfig) error {
	if strings.TrimSpace(cfg.Host) == "" || cfg.Port <= 0 {
		return fmt.Errorf("未配置主机或端口")
	}
	auth := gosmpp.Auth{
		SMSC:       fmt.Sprintf("%s:%d", strings.TrimSpace(cfg.Host), cfg.Port),
		SystemID:   cfg.Username,
		Password:   cfg.Password,
		SystemType: cfg.SystemType,
	}

	var connector gosmpp.Connector
	dialer := gosmpp.NonTLSDialer
	bm := strings.ToLower(strings.TrimSpace(cfg.BindMode))
	switch bm {
	case "transmitter":
		connector = gosmpp.TXConnector(dialer, auth)
	case "receiver":
		connector = gosmpp.RXConnector(dialer, auth)
	default:
		connector = gosmpp.TRXConnector(dialer, auth)
	}

	// gosmpp 要求 ReadTimeout > EnquireLink；探测会话短连接，关闭主动 EnquireLink 以免误配
	session, err := gosmpp.NewSession(
		connector,
		gosmpp.Settings{
			ReadTimeout: 35 * time.Second,
			EnquireLink: 0,
			OnPDU: func(p pdu.PDU, responded bool) {
				// 探测会话：不处理业务 PDU
				log.Printf("[SMPP-PROBE] %s ignore PDU type %T", cfg.ChannelCode, p)
			},
			OnClosed: func(state gosmpp.State) {
				log.Printf("[SMPP-PROBE] %s closed: %v", cfg.ChannelCode, state)
			},
		},
		12*time.Second,
	)
	if err != nil {
		return err
	}
	defer func() {
		if err := session.Close(); err != nil {
			log.Printf("[SMPP-PROBE] %s Close: %v", cfg.ChannelCode, err)
		}
	}()
	return nil
}
