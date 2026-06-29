package main

import (
    "context"
    "log"
    "os"
    "os/signal"
    "sync"
    "syscall"
    "time"
)

func main() {
    log.Println("Initializing Kaolach Go SMPP Gateway v3 (Diagnostic Update)...")

    // 1. Initialize Database
    InitDB()

    // 1b. DLR 归属过滤（多系统共用同一上游 SMPP 账号时过滤外来 DLR）
    //     依赖 DB 用于启动回填，必须在 InitDB 之后
    InitDLROwnership()

    // 1b'. DLR 源头去重（上游对每条回执重发约 4 次，跨度数分钟）：在发布到 sms_dlr 前折叠
    //      同 (channel,upstream_id,stat) 的重传，根治大批次时 sms_dlr 队列爆炸 + Worker 4 倍 DB 负载。
    InitDLRDedup()

    // 1c. 批次取消运行期标记（Redis）：消费 sms_send_smpp 单条短信前查询，跳过已取消批次
    InitBatchCancel()

    // 1d. 出站每通道每日计数器（Redis，按 China 日期累加）：submit_sm/ROK/88限流/88重投/其它失败。
    //     用于和上游"提交量"对账——重投会让 submit 数 > 客户消息数(按提交计费即多计成本)。
    //     跨重启可查，根治"上游报数对不上又查不了"。
    InitChannelStats()

    // 2. Initialize SMPP Manager
    InitSMPPManager()
    go func() {
        if err := manager.ReloadChannels(); err != nil {
            log.Printf("Final warning: Initial SMPP channel load encountered errors: %v", err)
        }
    }()

    // 3. RabbitMQ 消费：断线/ Broker 重建后自动重连，避免 sms_send_smpp 无消费者
    // ctx 用于 graceful shutdown：SIGTERM 时停止派发新 delivery、等 in-flight 完成
    rootCtx, cancelRoot := context.WithCancel(context.Background())
    var consumerWg sync.WaitGroup
    consumerWg.Add(1)
    rabbitURL := os.Getenv("RABBITMQ_URL")
    go func() {
        defer consumerWg.Done()
        RunConsumerForever(rootCtx, rabbitURL)
    }()

    // 3a. 每通道独立队列消费者(SMPP_PER_CHANNEL_QUEUES=1 启用)：消除单一 sms_send_smpp
    //     FIFO 的 head-of-line 阻塞，使被限流的慢通道不再饿死其它通道。未启用时为 no-op，
    //     legacy 单队列消费者(上面 RunConsumerForever)始终运行。
    StartPerChannelSupervisor(rootCtx, rabbitURL)

    // 3c. SMPP 入站服务器（客户接入）
    inboundListen := os.Getenv("INBOUND_LISTEN")
    if inboundListen == "" {
        inboundListen = ":2775"
    }
    startSubmitWorkerPool(
        getEnvInt("INBOUND_SUBMIT_WORKERS", 8),
        getEnvInt("INBOUND_QUEUE_CAP", 10000),
    )
    startReassemblyReaper() // 入站 UDH 多段重组的超时清理
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

    log.Println("Shutting down Gateway... draining in-flight RabbitMQ deliveries")
    cancelRoot()

    // 等消费者优雅退出：停止派发新 delivery、等 worker 把已 prefetch 的处理完。
    // 超时 60s 作为兜底，避免 Docker SIGKILL 前不能正常退出（默认 10s 太短，已通过 stop_grace_period 调到 90s）。
    done := make(chan struct{})
    go func() {
        consumerWg.Wait()
        close(done)
    }()
    select {
    case <-done:
        log.Println("Gateway shutdown complete (consumers drained cleanly).")
    case <-time.After(60 * time.Second):
        log.Println("WARN: shutdown timeout, some deliveries may be requeued by RabbitMQ.")
    }
}
