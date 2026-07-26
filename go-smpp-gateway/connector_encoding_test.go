package main

import (
	"encoding/hex"
	"strings"
	"testing"

	"github.com/linxGnu/gosmpp/data"
)

func TestStandardSMPPGSM7WireBytes(t *testing.T) {
	// SMPP.org 官方 submit_sm 示例的正文与字节序列：DCS=0，
	// GSM-7 septet 在 SMPP short_message 中按每个 septet 一个 octet 传输。
	encoded, err := data.GSM7BIT.Encode("Hello World €$£")
	if err != nil {
		t.Fatal(err)
	}
	if got, want := hex.EncodeToString(encoded), "48656c6c6f20576f726c64201b650201"; got != want {
		t.Fatalf("wire bytes=%s, want %s", got, want)
	}
	if got := data.GSM7BIT.DataCoding(); got != 0 {
		t.Fatalf("data_coding=%d, want 0", got)
	}
}

func TestGSM7EnabledDefaultsToStandard(t *testing.T) {
	tests := []struct {
		name string
		raw  string
		want bool
	}{
		{name: "empty config", raw: "", want: true},
		{name: "unrelated config", raw: `{"long_message_mode":"udh_segmentation"}`, want: true},
		{name: "explicit enable", raw: `{"gsm7_enabled":true}`, want: true},
		{name: "explicit disable", raw: `{"gsm7_enabled":false}`, want: false},
		{name: "invalid flag type", raw: `{"gsm7_enabled":"true"}`, want: false},
		{name: "force ucs2 wins", raw: `{"gsm7_enabled":true,"force_ucs2":true}`, want: false},
		{name: "malformed config keeps legacy behavior", raw: `{`, want: false},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if got := gsm7EnabledFromConfigJSON(tc.raw); got != tc.want {
				t.Fatalf("gsm7EnabledFromConfigJSON(%q)=%v, want %v", tc.raw, got, tc.want)
			}
		})
	}
}

func TestStandardGSM7FrenchMessageIsOnePart(t *testing.T) {
	message := "Tradingdecryptomonnaiesquantitatifpilotéparl'IA avecdesrendementsquotidiensde3%à5%.Réservez dèsmaintenant : https://chat.whatsapp.com/Lau2wJe7EhhLAVhkQalEz1"
	if invalid := data.ValidateGSM7String(message); len(invalid) != 0 {
		t.Fatalf("message contains non-GSM7 characters: %q", string(invalid))
	}
	encoded, err := data.GSM7BIT.Encode(message)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := len(encoded), 156; got != want {
		t.Fatalf("septets=%d, want %d", got, want)
	}
	if len(encoded) > 160 {
		t.Fatalf("message should fit one standard GSM-7 part, septets=%d", len(encoded))
	}
}

func TestNonGSM7Latin1CharacterRequiresUnicodeOrExplicitChannelOverride(t *testing.T) {
	// á 属于 Latin-1，但不在 GSM 03.38 默认表或扩展表中。标准路径
	// 必须走 Unicode；仅 latin1_single 通道配置可以启用供应商特殊映射。
	if invalid := data.ValidateGSM7String("á"); len(invalid) == 0 {
		t.Fatal("á must not be accepted as standard GSM-7")
	}
	if latin1SingleFromConfigJSON("") {
		t.Fatal("Latin-1 override must be disabled by default")
	}
	if !latin1SingleFromConfigJSON(`{"latin1_single":true}`) {
		t.Fatal("explicit Latin-1 channel override should be enabled")
	}
}

func TestSplitGSM7TextCountsExtensionCharactersAsTwoSeptets(t *testing.T) {
	message := strings.Repeat("{", 81) // 162 septets
	segments := splitGSM7Text(message, 153)
	if got, want := len(segments), 2; got != want {
		t.Fatalf("segments=%d, want %d", got, want)
	}
	if strings.Join(segments, "") != message {
		t.Fatal("split changed message content")
	}
	for i, segment := range segments {
		encoded, err := data.GSM7BIT.Encode(segment)
		if err != nil {
			t.Fatal(err)
		}
		if len(encoded) > 153 {
			t.Fatalf("segment %d has %d septets", i+1, len(encoded))
		}
	}
}

func TestSegmentUnicodeUsesSixtySevenUTF16UnitsPerPart(t *testing.T) {
	segments := segmentUCS2Text(strings.Repeat("中", 68), 134)
	if got, want := len(segments), 2; got != want {
		t.Fatalf("segments=%d, want %d", got, want)
	}
	if got, want := len(segments[0]), 134; got != want {
		t.Fatalf("first segment bytes=%d, want %d", got, want)
	}
	if got, want := len(segments[1]), 2; got != want {
		t.Fatalf("second segment bytes=%d, want %d", got, want)
	}
}

func TestSegmentUnicodeDoesNotSplitEmojiSurrogatePair(t *testing.T) {
	segments := segmentUCS2Text(strings.Repeat("😀", 34), 134)
	if got, want := len(segments), 2; got != want {
		t.Fatalf("segments=%d, want %d", got, want)
	}
	if got, want := len(segments[0]), 132; got != want {
		t.Fatalf("first segment bytes=%d, want %d", got, want)
	}
	if got, want := len(segments[1]), 4; got != want {
		t.Fatalf("second segment bytes=%d, want %d", got, want)
	}
}
