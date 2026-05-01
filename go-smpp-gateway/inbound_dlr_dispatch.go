package main

import (
	"log"
	"time"
)

const pendingDLRTTL = 24 * time.Hour

// dispatchDLRPayload 将 DLR payload 推送到在线会话，或落 smpp_pending_dlrs 离线缓存
// 此函数同时被 inbound_submit_worker（REJECTD DLR）和 inbound_dlr_consumer（真实 DLR）调用
func dispatchDLRPayload(payload map[string]interface{}) {
	systemID, _ := payload["system_id"].(string)
	if systemID == "" {
		log.Printf("[DLR] dispatchDLRPayload: 缺少 system_id，丢弃")
		return
	}
	sess := inboundReg.PickReceiver(systemID)
	if sess != nil {
		if err := sess.pushDeliverSM(payload); err == nil {
			return
		}
		log.Printf("[DLR] pushDeliverSM(%s) 失败，落库待补发", systemID)
	}
	// 客户未在线，持久化等待下次 BIND 时补发
	if err := InsertPendingDLR(systemID, payload, pendingDLRTTL); err != nil {
		log.Printf("[DLR] InsertPendingDLR(%s) 错误: %v", systemID, err)
	}
}
