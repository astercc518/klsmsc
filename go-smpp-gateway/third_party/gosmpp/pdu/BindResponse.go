package pdu

import (
	"github.com/linxGnu/gosmpp/data"
)

// BindResp PDU.
type BindResp struct {
	base
	SystemID string
}

// NewBindResp returns BindResp.
func NewBindResp(req BindRequest) (c *BindResp) {
	c = &BindResp{
		base: newBase(),
	}
	c.SequenceNumber = req.SequenceNumber

	switch req.BindingType {
	case Transceiver:
		c.CommandID = data.BIND_TRANSCEIVER_RESP

	case Receiver:
		c.CommandID = data.BIND_RECEIVER_RESP

	case Transmitter:
		c.CommandID = data.BIND_TRANSMITTER_RESP
	}

	return
}

// NewBindTransmitterResp returns new bind transmitter resp.
func NewBindTransmitterResp() PDU {
	c := &BindResp{
		base: newBase(),
	}
	c.CommandID = data.BIND_TRANSMITTER_RESP
	return c
}

// NewBindTransceiverResp returns new bind transceiver resp.
func NewBindTransceiverResp() PDU {
	c := &BindResp{
		base: newBase(),
	}
	c.CommandID = data.BIND_TRANSCEIVER_RESP
	return c
}

// NewBindReceiverResp returns new bind receiver resp.
func NewBindReceiverResp() PDU {
	c := &BindResp{
		base: newBase(),
	}
	c.CommandID = data.BIND_RECEIVER_RESP
	return c
}

// CanResponse implements PDU interface.
func (c *BindResp) CanResponse() bool {
	return false
}

// GetResponse implements PDU interface.
func (c *BindResp) GetResponse() PDU {
	return nil
}

// Marshal implements PDU interface.
func (c *BindResp) Marshal(b *ByteBuffer) {
	c.base.marshal(b, func(w *ByteBuffer) {
		w.Grow(len(c.SystemID) + 1)

		_ = w.WriteCString(c.SystemID)
	})
}

// Unmarshal implements PDU interface.
func (c *BindResp) Unmarshal(b *ByteBuffer) error {
	return c.base.unmarshal(b, func(w *ByteBuffer) (err error) {
		// SMPP 3.4 允许错误响应(command_status != 0)省略 body，很多上游就是只回 16 字节纯 header。
		// 此时原条件对 transceiver 仍无条件读 system_id，空 buffer 上 ReadCString 返回 io.EOF，
		// 导致 connect() 在 pdu.Parse 阶段就失败，走不到 BindError{CommandStatus} 分支 ——
		// 真实错误码(如 0x0E 密码错、0x05 已绑定)被一律显示成 "EOF"，误导排查方向。
		//
		// 仅补一个「body 非空」前置条件，不动原有的读取时机：Parse() 每次只装一个完整 PDU，
		// 故此处 w.Len() 恰为 command_length-16 即 body 长度。若改成只在 ESME_ROK 时读，
		// 那些「错误响应仍带 system_id」的上游会剩下未读字节，被 base.unmarshal 当作
		// optional param 解析而报 "Not enough byte to read from buffer"，是另一种误导。
		if (c.CommandID == data.BIND_TRANSCEIVER_RESP || c.CommandStatus == data.ESME_ROK) && w.Len() > 0 {
			c.SystemID, err = w.ReadCString()
		}
		return
	})
}
