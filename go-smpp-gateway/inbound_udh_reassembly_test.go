package main

import "testing"

func TestParseUDH8bit(t *testing.T) {
	// UDHL=05, IEI=00 IEDL=03 [ref=0x2A total=3 part=2] + payload "Hi"
	sm := []byte{0x05, 0x00, 0x03, 0x2A, 0x03, 0x02, 'H', 'i'}
	ci, payload := parseUDH(sm)
	if !ci.hasConcat || ci.ref != 0x2A || ci.total != 3 || ci.part != 2 {
		t.Fatalf("8bit concat parse wrong: %+v", ci)
	}
	if string(payload) != "Hi" {
		t.Fatalf("8bit payload wrong: %q", payload)
	}
}

func TestParseUDH16bit(t *testing.T) {
	// UDHL=06, IEI=08 IEDL=04 [refHi=0x12 refLo=0x34 total=2 part=1] + payload "Yo"
	sm := []byte{0x06, 0x08, 0x04, 0x12, 0x34, 0x02, 0x01, 'Y', 'o'}
	ci, payload := parseUDH(sm)
	if !ci.hasConcat || ci.ref != 0x1234 || ci.total != 2 || ci.part != 1 {
		t.Fatalf("16bit concat parse wrong: %+v", ci)
	}
	if string(payload) != "Yo" {
		t.Fatalf("16bit payload wrong: %q", payload)
	}
}

func TestParseUDHNoConcat(t *testing.T) {
	// UDHL=00 (无 IE) + payload；hasConcat 应为 false，payload 完整剥出
	sm := append([]byte{0x00}, []byte("plain")...)
	ci, payload := parseUDH(sm)
	if ci.hasConcat {
		t.Fatalf("expected no concat, got %+v", ci)
	}
	if string(payload) != "plain" {
		t.Fatalf("payload wrong: %q", payload)
	}
}

func TestReassembleOutOfOrder(t *testing.T) {
	rs := &reassemblyStore{groups: make(map[string]*reassemblyGroup)}
	key := reassemblyKey(1, "8888", "+8613800138000", 0x2A, 3)
	tmpl := submitJob{AccountID: 1, SourceAddr: "8888", DestAddr: "+8613800138000", RegisteredDelivery: 1}

	// part 2 先到
	ready, id2 := rs.addSegment(key, concatInfo{ref: 0x2A, total: 3, part: 2, hasConcat: true}, "B", tmpl)
	if ready != nil {
		t.Fatal("should not be ready after part 2")
	}
	// part 1 到（带 RD=1）
	ready, id1 := rs.addSegment(key, concatInfo{ref: 0x2A, total: 3, part: 1, hasConcat: true}, "A", tmpl)
	if ready != nil {
		t.Fatal("should not be ready after part 1")
	}
	// part 3 到 → 集齐
	tmpl3 := submitJob{AccountID: 1, SourceAddr: "8888", DestAddr: "+8613800138000", RegisteredDelivery: 0}
	ready, id3 := rs.addSegment(key, concatInfo{ref: 0x2A, total: 3, part: 3, hasConcat: true}, "C", tmpl3)
	if ready == nil {
		t.Fatal("should be ready after all 3 parts")
	}
	// 三段共享同一 msgID
	if id1 != id2 || id2 != id3 || ready.MessageID != id1 {
		t.Fatalf("msgID not shared: %s %s %s ready=%s", id1, id2, id3, ready.MessageID)
	}
	// 按 part 升序拼接（乱序到达也要正确顺序）
	if ready.Message != "ABC" {
		t.Fatalf("reassembled order wrong: %q", ready.Message)
	}
	// 任一段 RD=1 → 整条 RD=1
	if ready.RegisteredDelivery != 1 {
		t.Fatalf("registered delivery should be 1, got %d", ready.RegisteredDelivery)
	}
	// 集齐后组应被清除
	if len(rs.groups) != 0 {
		t.Fatalf("group not cleaned up: %d", len(rs.groups))
	}
}

func TestReassembleDuplicatePart(t *testing.T) {
	rs := &reassemblyStore{groups: make(map[string]*reassemblyGroup)}
	key := reassemblyKey(1, "s", "d", 1, 2)
	tmpl := submitJob{AccountID: 1, SourceAddr: "s", DestAddr: "d"}
	// part1 到两次（重投）→ 不应误判集齐
	if ready, _ := rs.addSegment(key, concatInfo{ref: 1, total: 2, part: 1, hasConcat: true}, "A", tmpl); ready != nil {
		t.Fatal("dup part1 should not complete a 2-part group")
	}
	if ready, _ := rs.addSegment(key, concatInfo{ref: 1, total: 2, part: 1, hasConcat: true}, "A", tmpl); ready != nil {
		t.Fatal("dup part1 again should not complete")
	}
	ready, _ := rs.addSegment(key, concatInfo{ref: 1, total: 2, part: 2, hasConcat: true}, "B", tmpl)
	if ready == nil || ready.Message != "AB" {
		t.Fatalf("expected AB after part2, got %+v", ready)
	}
}
