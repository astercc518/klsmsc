package main

import (
	"bytes"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
)

// SMPP 3.4 PDU 命令字
const (
	cmdGenericNack         uint32 = 0x80000000
	cmdBindReceiver        uint32 = 0x00000001
	cmdBindReceiverResp    uint32 = 0x80000001
	cmdBindTransmitter     uint32 = 0x00000002
	cmdBindTransmitterResp uint32 = 0x80000002
	cmdSubmitSM            uint32 = 0x00000004
	cmdSubmitSMResp        uint32 = 0x80000004
	cmdDeliverSM           uint32 = 0x00000005
	cmdDeliverSMResp       uint32 = 0x80000005
	cmdUnbind              uint32 = 0x00000006
	cmdUnbindResp          uint32 = 0x80000006
	cmdBindTransceiver     uint32 = 0x00000009
	cmdBindTransceiverResp uint32 = 0x80000009
	cmdEnquireLink         uint32 = 0x00000015
	cmdEnquireLinkResp     uint32 = 0x80000015
)

// SMPP 3.4 命令状态
const (
	statusOK            uint32 = 0x00000000
	statusInvMsgLen     uint32 = 0x00000001
	statusInvCmdID      uint32 = 0x00000003
	statusInvBindStatus uint32 = 0x00000004
	statusInvSrcAdr     uint32 = 0x0000000A
	statusInvDstAdr     uint32 = 0x0000000B
	statusMsgQFul       uint32 = 0x00000014
	statusInvSysID      uint32 = 0x0000000F
	statusInvPaswd      uint32 = 0x0000000E
	statusBindFail      uint32 = 0x0000000D
	statusThrottled     uint32 = 0x00000058
	statusAlyBnd        uint32 = 0x00000005
	statusSysErr        uint32 = 0x00000008
)

const (
	pduHeaderLen = 16
	maxPDULen    = 65536 // 实际单 PDU 上限远低于此，但留足容量给 message_payload TLV
)

// pduHeader 表示标准 16 字节 PDU 头
type pduHeader struct {
	commandLength  uint32
	commandID      uint32
	commandStatus  uint32
	sequenceNumber uint32
}

// readPDU 从 conn 读取一个完整 PDU（头 16 字节 + body）
func readPDU(r io.Reader) (pduHeader, []byte, error) {
	var hdr [pduHeaderLen]byte
	if _, err := io.ReadFull(r, hdr[:]); err != nil {
		return pduHeader{}, nil, err
	}
	h := pduHeader{
		commandLength:  binary.BigEndian.Uint32(hdr[0:4]),
		commandID:      binary.BigEndian.Uint32(hdr[4:8]),
		commandStatus:  binary.BigEndian.Uint32(hdr[8:12]),
		sequenceNumber: binary.BigEndian.Uint32(hdr[12:16]),
	}
	if h.commandLength < pduHeaderLen || h.commandLength > maxPDULen {
		return h, nil, fmt.Errorf("invalid command_length %d", h.commandLength)
	}
	bodyLen := int(h.commandLength) - pduHeaderLen
	body := make([]byte, bodyLen)
	if bodyLen > 0 {
		if _, err := io.ReadFull(r, body); err != nil {
			return h, nil, err
		}
	}
	return h, body, nil
}

// writePDU 打包并写入一个 PDU（无 TLV）
func writePDU(w io.Writer, cmdID, status, seq uint32, body []byte) error {
	total := uint32(pduHeaderLen + len(body))
	buf := make([]byte, pduHeaderLen+len(body))
	binary.BigEndian.PutUint32(buf[0:4], total)
	binary.BigEndian.PutUint32(buf[4:8], cmdID)
	binary.BigEndian.PutUint32(buf[8:12], status)
	binary.BigEndian.PutUint32(buf[12:16], seq)
	copy(buf[pduHeaderLen:], body)
	_, err := w.Write(buf)
	return err
}

// readCString 从字节流读取 NULL 结尾字符串（不含末尾 0）
func readCString(buf []byte, idx int) (string, int, error) {
	end := bytes.IndexByte(buf[idx:], 0)
	if end < 0 {
		return "", idx, errors.New("c-string missing null terminator")
	}
	return string(buf[idx : idx+end]), idx + end + 1, nil
}

// writeCString 写入 NULL 结尾字符串
func writeCString(b *bytes.Buffer, s string) {
	b.WriteString(s)
	b.WriteByte(0)
}

// bindBody 表示 BIND_TRANSCEIVER/RECEIVER/TRANSMITTER 的请求体
type bindBody struct {
	systemID         string
	password         string
	systemType       string
	interfaceVersion uint8
	addrTon          uint8
	addrNpi          uint8
	addressRange     string
}

func parseBind(body []byte) (bindBody, error) {
	var b bindBody
	idx := 0
	var err error
	if b.systemID, idx, err = readCString(body, idx); err != nil {
		return b, err
	}
	if b.password, idx, err = readCString(body, idx); err != nil {
		return b, err
	}
	if b.systemType, idx, err = readCString(body, idx); err != nil {
		return b, err
	}
	if idx+3 > len(body) {
		return b, errors.New("bind body truncated at fixed fields")
	}
	b.interfaceVersion = body[idx]
	b.addrTon = body[idx+1]
	b.addrNpi = body[idx+2]
	idx += 3
	if idx < len(body) {
		b.addressRange, _, _ = readCString(body, idx)
	}
	return b, nil
}

// buildBindResp 构造 bind_*_resp 的 body：仅 system_id 字段
func buildBindResp(gwSystemID string) []byte {
	var b bytes.Buffer
	writeCString(&b, gwSystemID)
	return b.Bytes()
}

// submitSMBody 表示 SUBMIT_SM 请求体（只解析必需字段）
type submitSMBody struct {
	serviceType        string
	sourceAddrTon      uint8
	sourceAddrNpi      uint8
	sourceAddr         string
	destAddrTon        uint8
	destAddrNpi        uint8
	destAddr           string
	esmClass           uint8
	protocolID         uint8
	priorityFlag       uint8
	scheduleDelivery   string
	validityPeriod     string
	registeredDelivery uint8
	replaceIfPresent   uint8
	dataCoding         uint8
	smDefaultMsgID     uint8
	smLength           uint8
	shortMessage       []byte
	tlvs               map[uint16][]byte // optional TLVs
}

func parseSubmitSM(body []byte) (submitSMBody, error) {
	var s submitSMBody
	idx := 0
	var err error
	if s.serviceType, idx, err = readCString(body, idx); err != nil {
		return s, err
	}
	if idx+2 > len(body) {
		return s, errors.New("submit_sm: source addr fields truncated")
	}
	s.sourceAddrTon = body[idx]
	s.sourceAddrNpi = body[idx+1]
	idx += 2
	if s.sourceAddr, idx, err = readCString(body, idx); err != nil {
		return s, err
	}
	if idx+2 > len(body) {
		return s, errors.New("submit_sm: dest addr fields truncated")
	}
	s.destAddrTon = body[idx]
	s.destAddrNpi = body[idx+1]
	idx += 2
	if s.destAddr, idx, err = readCString(body, idx); err != nil {
		return s, err
	}
	if idx+3 > len(body) {
		return s, errors.New("submit_sm: ESM/protocol/priority truncated")
	}
	s.esmClass = body[idx]
	s.protocolID = body[idx+1]
	s.priorityFlag = body[idx+2]
	idx += 3
	if s.scheduleDelivery, idx, err = readCString(body, idx); err != nil {
		return s, err
	}
	if s.validityPeriod, idx, err = readCString(body, idx); err != nil {
		return s, err
	}
	if idx+5 > len(body) {
		return s, errors.New("submit_sm: registered/replace/coding/smid/smlen truncated")
	}
	s.registeredDelivery = body[idx]
	s.replaceIfPresent = body[idx+1]
	s.dataCoding = body[idx+2]
	s.smDefaultMsgID = body[idx+3]
	s.smLength = body[idx+4]
	idx += 5
	if int(s.smLength) > 0 {
		if idx+int(s.smLength) > len(body) {
			return s, errors.New("submit_sm: short_message truncated")
		}
		s.shortMessage = make([]byte, s.smLength)
		copy(s.shortMessage, body[idx:idx+int(s.smLength)])
		idx += int(s.smLength)
	}
	// TLVs
	s.tlvs = make(map[uint16][]byte)
	for idx+4 <= len(body) {
		tag := binary.BigEndian.Uint16(body[idx : idx+2])
		ln := binary.BigEndian.Uint16(body[idx+2 : idx+4])
		idx += 4
		if idx+int(ln) > len(body) {
			break
		}
		s.tlvs[tag] = append([]byte{}, body[idx:idx+int(ln)]...)
		idx += int(ln)
	}
	return s, nil
}

// buildSubmitSMResp 构造 submit_sm_resp body：仅 message_id 字段
func buildSubmitSMResp(msgID string) []byte {
	var b bytes.Buffer
	writeCString(&b, msgID)
	return b.Bytes()
}

// deliverSMParams 是发送 deliver_sm 时所需字段
type deliverSMParams struct {
	sourceAddr   string // 客户原始 dest_addr（DLR 中变 source）
	destAddr     string // 客户原始 source_addr
	dataCoding   uint8
	esmClass     uint8 // 0x04 表示 DLR
	shortMessage []byte
}

// buildDeliverSM 构造 deliver_sm body
func buildDeliverSM(p deliverSMParams) []byte {
	var b bytes.Buffer
	writeCString(&b, "")            // service_type
	b.WriteByte(0)                  // source_addr_ton
	b.WriteByte(0)                  // source_addr_npi
	writeCString(&b, p.sourceAddr)
	b.WriteByte(0) // dest_addr_ton
	b.WriteByte(0) // dest_addr_npi
	writeCString(&b, p.destAddr)
	b.WriteByte(p.esmClass) // esm_class
	b.WriteByte(0)          // protocol_id
	b.WriteByte(0)          // priority_flag
	writeCString(&b, "")    // schedule_delivery_time
	writeCString(&b, "")    // validity_period
	b.WriteByte(0)          // registered_delivery
	b.WriteByte(0)          // replace_if_present_flag
	b.WriteByte(p.dataCoding)
	b.WriteByte(0) // sm_default_msg_id
	if len(p.shortMessage) > 254 {
		p.shortMessage = p.shortMessage[:254]
	}
	b.WriteByte(uint8(len(p.shortMessage)))
	b.Write(p.shortMessage)
	return b.Bytes()
}

// decodeShortMessage 根据 data_coding 把 short_message 字节解为 UTF-8 字符串
// data_coding: 0 = SMSC default (treated as ASCII/Latin1), 8 = UCS2 BE, 3 = Latin1
func decodeShortMessage(raw []byte, dataCoding uint8) string {
	switch dataCoding {
	case 0x08:
		// UCS-2 BE
		if len(raw)%2 != 0 {
			return string(raw)
		}
		out := make([]rune, 0, len(raw)/2)
		for i := 0; i+1 < len(raw); i += 2 {
			out = append(out, rune(binary.BigEndian.Uint16(raw[i:i+2])))
		}
		return string(out)
	default:
		// 默认按 Latin1 / ASCII 处理（GSM7 解码留待后续；多数客户用 UCS2 或 ASCII）
		return string(raw)
	}
}
