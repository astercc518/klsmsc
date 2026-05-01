package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"net"
	"strings"
	"time"
)

// inboundAccount 表示从 accounts 表加载的客户接入记录
type inboundAccount struct {
	ID            int
	AccountName   string
	Status        string
	Protocol      string
	SystemID      string
	Password      string
	IPWhitelist   string
	RateLimit     int
	SmppMaxBinds  int
	CountryCode   string
}

// LoadAccountBySystemID 按 smpp_system_id 查找账户
func LoadAccountBySystemID(systemID string) (*inboundAccount, error) {
	if db == nil {
		return nil, fmt.Errorf("db not initialized")
	}
	row := db.QueryRowx(`
		SELECT id, account_name, status, protocol,
		       COALESCE(smpp_system_id,'') AS smpp_system_id,
		       COALESCE(smpp_password,'')  AS smpp_password,
		       COALESCE(ip_whitelist,'')   AS ip_whitelist,
		       COALESCE(rate_limit,1000)   AS rate_limit,
		       COALESCE(smpp_max_binds,5)  AS smpp_max_binds,
		       COALESCE(country_code,'')   AS country_code
		FROM accounts
		WHERE smpp_system_id = ?
		  AND COALESCE(is_deleted,0) = 0
		LIMIT 1
	`, systemID)
	var a inboundAccount
	if err := row.Scan(
		&a.ID, &a.AccountName, &a.Status, &a.Protocol,
		&a.SystemID, &a.Password, &a.IPWhitelist, &a.RateLimit, &a.SmppMaxBinds, &a.CountryCode,
	); err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, err
	}
	return &a, nil
}

// IPWhitelistAllow 检查客户来源 IP 是否在账户白名单内（白名单为空 = 不限制）
// 支持逗号分隔字符串和 JSON 数组两种格式；支持 CIDR 范围
func (a *inboundAccount) IPWhitelistAllow(remoteIP string) bool {
	wl := strings.TrimSpace(a.IPWhitelist)
	if wl == "" || wl == "[]" || wl == "null" {
		return true
	}

	// 尝试解析 JSON 数组 ["1.2.3.4","10.0.0.0/8"]
	var ips []string
	if wl[0] == '[' {
		if err := json.Unmarshal([]byte(wl), &ips); err != nil {
			ips = nil
		}
	}
	// 回退到逗号分隔
	if ips == nil {
		ips = strings.Split(wl, ",")
	}

	parsedRemote := net.ParseIP(remoteIP)
	for _, raw := range ips {
		entry := strings.TrimSpace(raw)
		if entry == "" {
			continue
		}
		if strings.Contains(entry, "/") {
			_, cidr, err := net.ParseCIDR(entry)
			if err == nil && parsedRemote != nil && cidr.Contains(parsedRemote) {
				return true
			}
			continue
		}
		if entry == remoteIP {
			return true
		}
	}
	return false
}

// InsertInboundSubmission 在 SUBMIT_SM 应答前持久化一条入站记录
func InsertInboundSubmission(messageID string, accountID int, systemID, sourceAddr, destAddr string) error {
	if db == nil {
		return fmt.Errorf("db not initialized")
	}
	_, err := db.Exec(`
		INSERT INTO smpp_inbound_submissions (message_id, account_id, system_id, source_addr, dest_addr)
		VALUES (?, ?, ?, ?, ?)
	`, messageID, accountID, systemID, sourceAddr, destAddr)
	return err
}

// InsertPendingDLR 客户未在线时把 DLR 落库等待补发
func InsertPendingDLR(systemID string, payload map[string]interface{}, ttl time.Duration) error {
	if db == nil {
		return fmt.Errorf("db not initialized")
	}
	bytes, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	expires := time.Now().Add(ttl)
	_, err = db.Exec(`
		INSERT INTO smpp_pending_dlrs (system_id, payload, expires_at)
		VALUES (?, ?, ?)
	`, systemID, string(bytes), expires)
	return err
}

// pendingDLR 是从 smpp_pending_dlrs 表读出的一行
type pendingDLR struct {
	ID      int64
	Payload map[string]interface{}
}

// LoadPendingDLRs 取出指定 system_id 未过期的待发 DLR（限 200 条/批）
func LoadPendingDLRs(systemID string, limit int) ([]pendingDLR, error) {
	if db == nil {
		return nil, fmt.Errorf("db not initialized")
	}
	if limit <= 0 {
		limit = 200
	}
	rows, err := db.Queryx(`
		SELECT id, payload
		FROM smpp_pending_dlrs
		WHERE system_id = ? AND expires_at > NOW()
		ORDER BY id ASC
		LIMIT ?
	`, systemID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []pendingDLR
	for rows.Next() {
		var id int64
		var raw string
		if err := rows.Scan(&id, &raw); err != nil {
			continue
		}
		var p map[string]interface{}
		if err := json.Unmarshal([]byte(raw), &p); err != nil {
			continue
		}
		out = append(out, pendingDLR{ID: id, Payload: p})
	}
	return out, nil
}

// DeletePendingDLR 在补发成功后删除
func DeletePendingDLR(id int64) error {
	if db == nil {
		return fmt.Errorf("db not initialized")
	}
	_, err := db.Exec(`DELETE FROM smpp_pending_dlrs WHERE id = ?`, id)
	return err
}
