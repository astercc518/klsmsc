package main

import (
    "fmt"
    "log"
    "regexp"
    "sync"
    "time"

    "github.com/linxGnu/gosmpp"
    "github.com/linxGnu/gosmpp/data"
    "github.com/linxGnu/gosmpp/pdu"
)

// SMPPManager manages multiple SMPP connections across different channels
type SMPPManager struct {
    connections  map[int][]*gosmpp.Session
    configs      map[int]ChannelConfig
    mu           sync.RWMutex
    sequenceMap  sync.Map // Maps sequence_number (uint32) to messageID (string) and logID (int64)
}

type sequenceData struct {
    messageID string
    logID     int64
}

var manager *SMPPManager

func InitSMPPManager() {
    manager = &SMPPManager{
        connections: make(map[int][]*gosmpp.Session),
        configs:     make(map[int]ChannelConfig),
    }
}

// ReloadChannels reloads configurations and establishes connections
func (m *SMPPManager) ReloadChannels() error {
    configs, err := GetChannelConfigs()
    if err != nil {
        return err
    }

    newConfigs := make(map[int]ChannelConfig)
    for _, cfg := range configs {
        newConfigs[cfg.ID] = cfg
    }

    m.mu.Lock()
    defer m.mu.Unlock()

    // 1. Identify and remove sessions for channels that are no longer active or were removed
    for id, conns := range m.connections {
        if _, exists := newConfigs[id]; !exists {
            log.Printf("Channel %d (%s) is no longer active, closing %d sessions...", id, m.configs[id].ChannelCode, len(conns))
            for _, session := range conns {
                _ = session.Close()
            }
            delete(m.connections, id)
            delete(m.configs, id)
        }
    }

    // 2. Process current configurations (add new or scale up)
    for id, cfg := range newConfigs {
        m.configs[id] = cfg
        currentConns := m.connections[id]
        needed := cfg.Concurrency - len(currentConns)
        
        if needed > 0 {
            log.Printf("Channel %s needs %d more sessions (current: %d, target: %d)", cfg.ChannelCode, needed, len(currentConns), cfg.Concurrency)
            for i := 0; i < needed; i++ {
                session, err := m.bindSession(cfg)
                if err != nil {
                    log.Printf("Failed to bind session for channel %s: %v", cfg.ChannelCode, err)
                    continue
                }
                m.connections[id] = append(m.connections[id], session)
                log.Printf("Successfully bound new session for channel %s", cfg.ChannelCode)
            }
        } else if needed < 0 {
            // Scale down if concurrency was reduced
            toClose := -needed
            log.Printf("Channel %s reducing concurrency, closing %d sessions...", cfg.ChannelCode, toClose)
            for i := 0; i < toClose && len(m.connections[id]) > 0; i++ {
                session := m.connections[id][0]
                _ = session.Close()
                m.connections[id] = m.connections[id][1:]
            }
        }
    }
    return nil
}

func (m *SMPPManager) bindSession(cfg ChannelConfig) (*gosmpp.Session, error) {
    auth := gosmpp.Auth{
        SMSC:       fmt.Sprintf("%s:%d", cfg.Host, cfg.Port),
        SystemID:   cfg.Username,
        Password:   cfg.Password,
        SystemType: cfg.SystemType,
    }

    var connector gosmpp.Connector
    dialer := gosmpp.NonTLSDialer

    // Default to Transceiver if not specified
    if cfg.BindMode == "transmitter" {
        connector = gosmpp.TXConnector(dialer, auth)
    } else if cfg.BindMode == "receiver" {
        connector = gosmpp.RXConnector(dialer, auth)
    } else {
        connector = gosmpp.TRXConnector(dialer, auth)
    }

    // Initialize session with handlers
    session, err := gosmpp.NewSession(
        connector,
        gosmpp.Settings{
            ReadTimeout: 60 * time.Second,
            EnquireLink: 30 * time.Second,
            OnPDU: func(p pdu.PDU, responded bool) {
                switch pd := p.(type) {
                case *pdu.SubmitSMResp:
                    log.Printf("[SMPP-DEBUG] SubmitSMResp reached: channel=%s, msgID=%s, sequence=%d, status=%d", cfg.ChannelCode, pd.MessageID, pd.SequenceNumber, pd.CommandStatus)
                    
                    if val, ok := m.sequenceMap.LoadAndDelete(pd.SequenceNumber); ok {
                        seqData := val.(sequenceData)
                        log.Printf("[SMPP-DEBUG] Found matching sequence for msg: %s (internal log ID: %d)", seqData.messageID, seqData.logID)
                        
                        if pd.CommandStatus == data.ESME_ROK {
                            err := UpdateSMSLogResult(seqData.logID, seqData.messageID, pd.MessageID, "sent", "")
                            if err != nil {
                                log.Printf("[SMPP-ERROR] Failed to update upstream ID for %s: %v", seqData.messageID, err)
                            } else {
                                log.Printf("[SMPP-DEBUG] Successfully mapped upstream ID: %s => %s", seqData.messageID, pd.MessageID)
                            }
                        } else {
                            log.Printf("[SMPP-ERROR] SubmitSM failed with status %d for msg %s", pd.CommandStatus, seqData.messageID)
                            err := UpdateSMSLogResult(seqData.logID, seqData.messageID, "", "failed", fmt.Sprintf("SMPP Error: %d", pd.CommandStatus))
                            if err != nil {
                                log.Printf("[SMPP-ERROR] Failed to record SMPP error for %s: %v", seqData.messageID, err)
                            }
                        }
                    } else {
                        log.Printf("[SMPP-DEBUG] Warning: Received SubmitSMResp for unknown sequence number %d (possibly from another session or restarted gateway)", pd.SequenceNumber)
                    }

                case *pdu.DeliverSM:
                    log.Printf("[SMPP-DEBUG] Received DeliverSM on channel %s", cfg.ChannelCode)
                    m.handleDeliverSM(pd, cfg)
                
                case *pdu.EnquireLinkResp:
                    // Just log that we received it for health check visibility
                    // log.Printf("[SMPP-DEBUG] EnquireLinkResp reached for channel %s", cfg.ChannelCode)
                
                default:
                    log.Printf("[SMPP-DEBUG] Received PDU type %T on channel %s", p, cfg.ChannelCode)
                }
            },
            OnClosed: func(state gosmpp.State) {
                log.Printf("Session closed for channel %s, state: %v", cfg.ChannelCode, state)
            },
        },
        5*time.Second,
    )

    return session, err
}

func (m *SMPPManager) handleDeliverSM(deliver *pdu.DeliverSM, cfg ChannelConfig) {
    msg, _ := deliver.Message.GetMessage()
    log.Printf("Received DeliverSM: %s", msg)

    // Extract id and stat from DLR text
    // Example: id:47bf0b49f97a865a sub:000 dlvrd:000 ... stat:DELIVRD err:000
    idMatch := regexp.MustCompile(`id:([^ ]+)`).FindStringSubmatch(msg)
    statMatch := regexp.MustCompile(`stat:([^ ]+)`).FindStringSubmatch(msg)

    if len(idMatch) > 1 && len(statMatch) > 1 {
        upstreamID := idMatch[1]
        stat := statMatch[1]
        
        // Map SMPP stat to system status
        finalStatus := "sent"
        if stat == "DELIVRD" {
            finalStatus = "delivered"
        } else if stat == "REJECTD" || stat == "UNDELIV" || stat == "EXPIRED" || stat == "DELETED" {
            finalStatus = "failed"
        }

        err := UpdateSMSLogDLR(upstreamID, finalStatus)
        if err != nil {
            log.Printf("Failed to update DLR for upstreamID %s: %v", upstreamID, err)
        } else {
            log.Printf("Successfully updated DLR for message %s: %s", upstreamID, finalStatus)
        }

        // [重要] 通知 Python Worker 进行对账、注水、Webhook 等复杂逻辑
        dlrArgs := []interface{}{
            cfg.ID,         // channel_id
            upstreamID,     // upstream_id
            finalStatus,    // new_status
            stat,           // stat
            "000",          // err (SMPP err context, fixed to 000 if not parsed)
            "",             // dest_addr (optional in Python _process_smpp_dlr_async if upstream_id matches)
            "",             // source_addr (optional)
            upstreamID,     // receipted_message_id (often same as upstreamID)
        }
        err = PublishCeleryTask("sms_dlr", "process_smpp_dlr_task", dlrArgs)
        if err != nil {
            log.Printf("[SMPP-ERROR] Failed to notify Python worker of DLR for %s: %v", upstreamID, err)
        } else {
            log.Printf("[SMPP-DEBUG] Notified Python worker of DLR for %s", upstreamID)
        }
    }
}

// SendSMS picks a session and sends the message
func (m *SMPPManager) SendSMS(logID int64, messageID string, phoneNumber string, message string, channelID int) error {
    m.mu.RLock()
    conns := m.connections[channelID]
    cfg := m.configs[channelID]
    m.mu.RUnlock()

    if len(conns) == 0 {
        return fmt.Errorf("no active connections for channel %d", channelID)
    }

    // Round-robin or pick first
    session := conns[time.Now().UnixNano()%int64(len(conns))]

    s := pdu.NewSubmitSM().(*pdu.SubmitSM)
    s.SourceAddr = pdu.NewAddress()
    s.SourceAddr.SetAddress(cfg.DefaultSenderID)
    s.DestAddr = pdu.NewAddress()
    s.DestAddr.SetAddress(phoneNumber)
    _ = s.Message.SetMessageWithEncoding(message, data.UCS2)
    s.RegisteredDelivery = 1

    trans := session.Transmitter()
    if trans == nil {
        return fmt.Errorf("session has no transmitter")
    }

    m.sequenceMap.Store(s.SequenceNumber, sequenceData{messageID: messageID, logID: logID})

    log.Printf("[SMPP-DEBUG] Submitting SM: channel=%s, sequence=%d, dest=%s, sender=%s, len=%d", 
               cfg.ChannelCode, s.SequenceNumber, phoneNumber, cfg.DefaultSenderID, len(message))

    err := trans.Submit(s)
    if err != nil {
        m.sequenceMap.Delete(s.SequenceNumber)
        log.Printf("[SMPP-ERROR] Submit failed: %v", err)
        return err
    }

    return nil
}
