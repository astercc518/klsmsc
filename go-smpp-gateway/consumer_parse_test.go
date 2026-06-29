package main

import (
	"encoding/json"
	"testing"
)

// 验证 Python apply_async(args=[payload, None]) 产生的 kombu JSON 信封可被解析
func TestExtractSmsPayloads_CeleryJSONEnvelope(t *testing.T) {
	raw := `[[{"log_id": 1242608, "message_id": "msg_x", "phone_number": "+8801625628151", "message": "hi", "channel_id": 74, "batch_status": "processing", "record_status": "pending"}, null], {}, {"callbacks": null, "errbacks": null, "chain": null, "chord": null}]`
	got, poison := extractSmsPayloads([]byte(raw))
	if poison {
		t.Fatal("unexpected poison")
	}
	if len(got) != 1 {
		t.Fatalf("len=%d", len(got))
	}
	if got[0].LogID != 1242608 || got[0].ChannelID != 74 || got[0].MessageID != "msg_x" {
		t.Fatalf("%+v", got[0])
	}
}

func TestExtractSmsPayloads_LegacyObjectShape(t *testing.T) {
	obj := map[string]interface{}{
		"task": "send_sms_task",
		"id":   "abc",
		"args": []interface{}{
			map[string]interface{}{
				"log_id": 1, "message_id": "m", "phone_number": "p", "message": "x",
				"channel_id": float64(2), "batch_status": "processing", "record_status": "pending",
			},
		},
	}
	body, _ := json.Marshal(obj)
	got, poison := extractSmsPayloads(body)
	if poison || len(got) != 1 || got[0].LogID != 1 {
		t.Fatalf("poison=%v got=%+v", poison, got)
	}
}

// Protocol v2 示例：顶层 [args, kwargs, embed]，且 args[0] 为「对象数组」（批量）
func TestExtractSmsPayloads_CeleryV2ArgsFirstIsArray(t *testing.T) {
	raw := `[[[{"log_id": 1, "message_id": "a", "phone_number": "", "message": "", "channel_id": 0, "batch_status": "", "record_status": ""},{"log_id": 2, "message_id": "b", "phone_number": "", "message": "", "channel_id": 0, "batch_status": "", "record_status": ""}], null], {}, {"callbacks": null}]`
	got, poison := extractSmsPayloads([]byte(raw))
	if poison {
		t.Fatal("unexpected poison")
	}
	if len(got) != 2 || got[0].LogID != 1 || got[1].MessageID != "b" {
		t.Fatalf("got=%+v", got)
	}
}

func TestExtractSmsPayloads_BareSMSLogObject(t *testing.T) {
	raw := `{"log_id": 3, "message_id": "bare", "phone_number": "p", "message": "m", "channel_id": 5, "batch_status": "", "record_status": "pending"}`
	got, poison := extractSmsPayloads([]byte(raw))
	if poison || len(got) != 1 || got[0].MessageID != "bare" {
		t.Fatalf("poison=%v got=%+v", poison, got)
	}
}

// republishSmppPayloads 重投格式：json.Marshal([]SMSLogData) == [{obj}, {obj}]。
// 首元素是对象而非 Celery 位置参数数组；88 限流重投走此路径，必须被识别而非当毒消息丢弃。
func TestExtractSmsPayloads_NativeRepublishArray(t *testing.T) {
	raw := `[{"log_id": 11694852, "message_id": "msg_a", "phone_number": "+66826483489", "message": "hi", "channel_id": 64, "batch_status": "processing", "record_status": "queued", "throttle_retry": 1},{"log_id": 11694898, "message_id": "msg_b", "phone_number": "+66986908818", "message": "hi", "channel_id": 64, "batch_status": "processing", "record_status": "queued", "throttle_retry": 1}]`
	got, poison := extractSmsPayloads([]byte(raw))
	if poison {
		t.Fatal("unexpected poison: 限流重投包被当毒消息丢弃")
	}
	if len(got) != 2 || got[0].LogID != 11694852 || got[1].MessageID != "msg_b" {
		t.Fatalf("got=%+v", got)
	}
}

// 单条限流重投：connector.go 走 republishSmppPayloads([]SMSLogData{pl}) → [{obj}]。
func TestExtractSmsPayloads_NativeRepublishSingle(t *testing.T) {
	raw := `[{"log_id": 7, "message_id": "solo", "phone_number": "p", "message": "m", "channel_id": 64, "batch_status": "processing", "record_status": "queued", "throttle_retry": 2}]`
	got, poison := extractSmsPayloads([]byte(raw))
	if poison || len(got) != 1 || got[0].MessageID != "solo" || got[0].ThrottleRetry != 2 {
		t.Fatalf("poison=%v got=%+v", poison, got)
	}
}

func TestExtractSmsPayloads_PoisonUnknown(t *testing.T) {
	got, poison := extractSmsPayloads([]byte(`"garbage"`))
	if !poison || len(got) != 0 {
		t.Fatalf("poison=%v len=%d", poison, len(got))
	}
}
