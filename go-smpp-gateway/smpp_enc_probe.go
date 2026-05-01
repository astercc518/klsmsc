//go:build ignore

package main

import (
	"fmt"
	"reflect"
	"github.com/linxGnu/gosmpp/data"
	"github.com/linxGnu/gosmpp/pdu"
)

func main() {
	// 探测 UDH 类型和 ConcatenatedShortMessages / InfoElement
	udhType := reflect.TypeOf(pdu.UDH{})
	fmt.Printf("UDH type: %v, kind: %v\n", udhType, udhType.Kind())
	if udhType.Kind() == reflect.Slice {
		fmt.Printf("UDH elem: %v\n", udhType.Elem())
	}

	// 尝试构造一个 ConcatenatedShortMessages UDH 元素
	// 标准 1-byte ref UDH: IE ID=0x00, IE data=[ref, total, part]
	// 看 gosmpp 是否有内置的 InfoElement 或 ConcatenatedSMSHeader 类型
	fmt.Printf("pdu.InfoElement type: %T\n", pdu.InfoElement{})

	// 测试 SetMessageDataWithEncoding
	s := pdu.NewSubmitSM().(*pdu.SubmitSM)
	encoded, _ := data.UCS2.Encode("Hello World")
	err := s.Message.SetMessageDataWithEncoding(encoded, data.UCS2)
	fmt.Printf("SetMessageDataWithEncoding err: %v, messageData len: %d\n", err, func() int {
		d, _ := s.Message.GetMessageData(); return len(d)
	}())

	// 构造 UDH
	udh := pdu.UDH{pdu.InfoElement{ID: 0x00, Data: []byte{0x01, 0x01, 0x01}}}
	s.Message.SetUDH(udh)
	s.EsmClass = 0x40
	fmt.Printf("UDH set, ESM: 0x%02X\n", s.EsmClass)
}
