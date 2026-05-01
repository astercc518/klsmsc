package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sync"
	"time"
)

// submitJob 表示从客户 SUBMIT_SM 解析出的转发任务
type submitJob struct {
	AccountID          int    `json:"account_id"`
	MessageID          string `json:"message_id"`
	SystemID           string `json:"system_id,omitempty"`
	SourceAddr         string `json:"source_addr"`
	DestAddr           string `json:"dest_addr"`
	Message            string `json:"message"`
	IP                 string `json:"ip,omitempty"`
	RegisteredDelivery int    `json:"registered_delivery"`
}

// internalSubmitResp 与 Python /api/v1/_internal/smpp_submit 返回结构对齐
type internalSubmitResp struct {
	Success   bool   `json:"success"`
	MessageID string `json:"message_id"`
	Status    string `json:"status"`
	Error     *struct {
		Code    string `json:"code"`
		Message string `json:"message"`
	} `json:"error"`
}

var (
	submitQueue        chan submitJob
	submitQueueSize    int
	submitHTTPClient   = &http.Client{Timeout: 10 * time.Second}
	internalSubmitURL  string
	internalToken      string
	submitWorkersOnce  sync.Once
)

// startSubmitWorkerPool 在 main 启动时调用一次
// workers: 并发 worker 数；queueCap: 缓冲队列容量
func startSubmitWorkerPool(workers, queueCap int) {
	submitWorkersOnce.Do(func() {
		if workers <= 0 {
			workers = 8
		}
		if queueCap <= 0 {
			queueCap = 10000
		}
		submitQueue = make(chan submitJob, queueCap)
		submitQueueSize = queueCap
		internalSubmitURL = os.Getenv("BACKEND_INTERNAL_URL")
		if internalSubmitURL == "" {
			internalSubmitURL = "http://api:8000"
		}
		internalSubmitURL += "/api/v1/_internal/smpp_submit"
		internalToken = os.Getenv("INTERNAL_TOKEN")
		if internalToken == "" {
			log.Println("[INBOUND] WARNING: INTERNAL_TOKEN 未设置，调用 Python 内部端点会被拒绝")
		}
		for i := 0; i < workers; i++ {
			go submitWorkerLoop(i)
		}
		log.Printf("[INBOUND] 已启动 %d 个 submit worker, queue_cap=%d, target=%s",
			workers, queueCap, internalSubmitURL)
	})
}

// trySubmit 由 inbound_session 在收到 SUBMIT_SM 时调用；非阻塞
// 返回值：(入队成功, 队列高水位（>80% 满）)
func trySubmit(job submitJob) (queued bool, busy bool) {
	if submitQueue == nil {
		return false, true
	}
	// 高水位检测：队列容量 80% 时拒绝（让客户重试，避免内存洪水）
	if len(submitQueue) > submitQueueSize*8/10 {
		return false, true
	}
	select {
	case submitQueue <- job:
		return true, false
	default:
		return false, true
	}
}

func submitWorkerLoop(id int) {
	for job := range submitQueue {
		if err := submitToBackend(job); err != nil {
			log.Printf("[INBOUND] submit worker #%d 后端调用失败 msgid=%s: %v",
				id, job.MessageID, err)
			// 投递失败：发布 REJECTD DLR 到 sms_inbound_dlr，由 inbound_dlr_consumer 推回客户
			publishRejectDLR(job, err.Error())
		}
	}
}

func submitToBackend(job submitJob) error {
	body, err := json.Marshal(job)
	if err != nil {
		return fmt.Errorf("marshal: %w", err)
	}
	req, err := http.NewRequest("POST", internalSubmitURL, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", internalToken)

	resp, err := submitHTTPClient.Do(req)
	if err != nil {
		return fmt.Errorf("http: %w", err)
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(io.LimitReader(resp.Body, 16*1024))
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("http %d: %s", resp.StatusCode, string(respBody))
	}
	var parsed internalSubmitResp
	if err := json.Unmarshal(respBody, &parsed); err != nil {
		return fmt.Errorf("decode resp: %w", err)
	}
	if !parsed.Success && parsed.Error != nil {
		// 业务失败（余额不足、国家不允许等）→ 推 REJECTD DLR
		publishRejectDLR(job, fmt.Sprintf("%s: %s", parsed.Error.Code, parsed.Error.Message))
		return nil
	}
	return nil
}

// publishRejectDLR 在内部端点拒绝 / 不可达时构造一个 REJECTD DLR 事件
// 直接调用 inbound_dlr_consumer 的发布接口（在同进程内）
func publishRejectDLR(job submitJob, reason string) {
	now := time.Now()
	payload := map[string]interface{}{
		"system_id":    job.SystemID,
		"message_id":   job.MessageID,
		"source_addr":  job.DestAddr,   // DLR 中 source 是原 dest
		"dest_addr":    job.SourceAddr, // 反之
		"stat":         "REJECTD",
		"err":          "999",
		"submit_date":  now.Format("0601021504"),
		"done_date":    now.Format("0601021504"),
		"text_preview": truncateForDLR(reason, 20),
	}
	dispatchDLRPayload(payload)
}

func truncateForDLR(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}
