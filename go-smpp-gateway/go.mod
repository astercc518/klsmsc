module github.com/kaolach/go-smpp-gateway

go 1.21.0

toolchain go1.21.13

require (
	github.com/go-sql-driver/mysql v1.9.3
	github.com/google/uuid v1.6.0
	github.com/jmoiron/sqlx v1.4.0
	github.com/linxGnu/gosmpp v0.2.1
	github.com/rabbitmq/amqp091-go v1.9.0
	github.com/redis/go-redis/v9 v9.7.0
)

require (
	filippo.io/edwards25519 v1.1.0 // indirect
	github.com/cespare/xxhash/v2 v2.2.0 // indirect
	github.com/dgryski/go-rendezvous v0.0.0-20200823014737-9f7001d12a5f // indirect
	golang.org/x/text v0.14.0 // indirect
)

// [KAOLACH PATCH] 用本地 fork 替换 gosmpp：把发送端缓冲 1→256，修复高峰期 deliver_sm_resp
// 被出站流量堵死导致上游对 DLR 4 倍重传（仅改 transmittable.go 一处，其余与 v0.2.1 一致）。
replace github.com/linxGnu/gosmpp => ./third_party/gosmpp
