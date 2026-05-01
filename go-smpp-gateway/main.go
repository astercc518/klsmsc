package main

import (
    "log"
    "os"
    "os/signal"
    "syscall"
    "time"
)

func main() {
    log.Println("Initializing Kaolach Go SMPP Gateway v3 (Diagnostic Update)...")

    // 1. Initialize Database
    InitDB()

    // 2. Initialize SMPP Manager
    InitSMPPManager()
    go func() {
        if err := manager.ReloadChannels(); err != nil {
            log.Printf("Final warning: Initial SMPP channel load encountered errors: %v", err)
        }
    }()

    // 3. RabbitMQ 消费：断线/ Broker 重建后自动重连，避免 sms_send_smpp 无消费者
    rabbitURL := os.Getenv("RABBITMQ_URL")
    go RunConsumerForever(rabbitURL)

    // 3c. SMPP 入站服务器（客户接入）
    inboundListen := os.Getenv("INBOUND_LISTEN")
    if inboundListen == "" {
        inboundListen = ":2775"
    }
    startSubmitWorkerPool(
        getEnvInt("INBOUND_SUBMIT_WORKERS", 8),
        getEnvInt("INBOUND_QUEUE_CAP", 10000),
    )
    go startInboundServer(inboundListen)
    go RunInboundDLRConsumerForever(rabbitURL)

    // 3b. 管理端「真实 bind」探测（仅内网 + Token；供 Python API 调用）
    if probeListen := os.Getenv("SMPP_PROBE_BIND_LISTEN"); probeListen != "" {
        go startProbeBindServer(probeListen)
    }

    // 4. Start periodic configuration reload (every 5 minutes)
    go func() {
        ticker := time.NewTicker(5 * time.Minute)
        defer ticker.Stop()
        for range ticker.C {
            log.Println("Starting periodic channel configuration reload...")
            if err := manager.ReloadChannels(); err != nil {
                log.Printf("Error during periodic channel reload: %v", err)
            }
        }
    }()

    // 5. Start periodic connection_status writeback (every 20s).
    // 让前端 channels.connection_status 反映 SMPPManager 真实 bind 情况，
    // 避免「配置 active 但 bind 失败」长期显示为假阳性。
    go func() {
        ticker := time.NewTicker(20 * time.Second)
        defer ticker.Stop()
        for range ticker.C {
            manager.ReconcileConnectionStatus()
        }
    }()

    log.Println("Gateway is running. Press CTRL+C to exit.")

    // Wait for termination
    sigChan := make(chan os.Signal, 1)
    signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
    <-sigChan

    log.Println("Shutting down Gateway...")
}
