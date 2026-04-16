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

    // 3. Start RabbitMQ Consumer
    rabbitURL := os.Getenv("RABBITMQ_URL")
    go func() {
        if err := StartConsumer(rabbitURL); err != nil {
            log.Fatalf("RabbitMQ Consumer error: %v", err)
        }
    }()

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

    log.Println("Gateway is running. Press CTRL+C to exit.")

    // Wait for termination
    sigChan := make(chan os.Signal, 1)
    signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
    <-sigChan

    log.Println("Shutting down Gateway...")
}
