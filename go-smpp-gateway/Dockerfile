FROM golang:1.21-alpine as builder

WORKDIR /app

# Install git for private modules or dependencies if needed
RUN apk add --no-cache git

COPY go.mod go.sum* ./
RUN go mod tidy

COPY . .
RUN go mod tidy
RUN grep "SMPP-DEBUG" connector.go || (echo "CRITICAL: SMPP-DEBUG not found in connector.go during build!" && exit 1)
RUN CGO_ENABLED=0 GOOS=linux go build -o gateway .

FROM alpine:latest

RUN apk add --no-cache ca-certificates tzdata
ENV TZ=Asia/Shanghai

WORKDIR /root/

COPY --from=builder /app/gateway .

# Explicitly set permissions
RUN chmod +x ./gateway

EXPOSE 2775

CMD ["./gateway"]
