package gosmpp

import (
	"log"
	"sync/atomic"

	"github.com/linxGnu/gosmpp/pdu"
)

type transceivable struct {
	settings Settings

	conn *Connection
	in   *receivable
	out  *transmittable

	aliveState int32
}

func newTransceivable(conn *Connection, settings Settings) *transceivable {
	t := &transceivable{
		settings: settings,
		conn:     conn,
	}

	t.out = newTransmittable(conn, Settings{
		WriteTimeout: settings.WriteTimeout,

		EnquireLink: settings.EnquireLink,

		OnSubmitError: settings.OnSubmitError,

		OnClosed: func(state State) {
			switch state {
			case ExplicitClosing:
				return

			case ConnectionIssue:
				// also close input
				_ = t.in.close(ExplicitClosing)

				if t.settings.OnClosed != nil {
					t.settings.OnClosed(ConnectionIssue)
				}
			}
		},
	})

	t.in = newReceivable(conn, Settings{
		ReadTimeout: settings.ReadTimeout,

		OnPDU: settings.OnPDU,

		OnAllPDU: settings.OnAllPDU,

		OnReceivingError: settings.OnReceivingError,

		OnClosed: func(state State) {
			switch state {
			case ExplicitClosing:
				return

			case InvalidStreaming, UnbindClosing:
				// also close output
				_ = t.out.close(ExplicitClosing)

				if t.settings.OnClosed != nil {
					t.settings.OnClosed(state)
				}
			}
		},

		response: func(p pdu.PDU) {
			// [KAOLACH PATCH] 原版静默丢弃 Submit 错误。deliver_sm_resp/enquire_resp 发送失败
			// （通常 ErrConnectionClosing：会话正在关闭/重绑）是上游对 DLR 重传的直接前兆，
			// 记日志以便观测 ACK 丢失、定位重传根因（详见事故复盘）。
			if err := t.Submit(p); err != nil {
				log.Printf("[gosmpp][KAOLACH] auto-response send FAILED (%T, conn closing?): %v", p, err)
			}
		},
	})

	t.out.start()
	t.in.start()

	return t
}

// SystemID returns tagged SystemID which is attached with bind_resp from SMSC.
func (t *transceivable) SystemID() string {
	return t.conn.systemID
}

// Close transceiver and stop underlying daemons.
func (t *transceivable) Close() (err error) {
	if atomic.CompareAndSwapInt32(&t.aliveState, Alive, Closed) {
		// closing input and output
		_ = t.out.close(StoppingProcessOnly)
		_ = t.in.close(StoppingProcessOnly)

		// close underlying conn
		err = t.conn.Close()

		// notify transceiver closed
		if t.settings.OnClosed != nil {
			t.settings.OnClosed(ExplicitClosing)
		}
	}
	return
}

// Submit a PDU.
func (t *transceivable) Submit(p pdu.PDU) error {
	return t.out.Submit(p)
}
