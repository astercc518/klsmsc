# Kaolach SMSC — Enterprise International SMS Gateway

## Commercial Solution Whitepaper

> **A self-hosted international SMS gateway that turns "sending SMS worldwide" into an asset you actually own.**
>
> Smart Routing · 3-Tier Billing · Global-Compliant Sender ID · Deep Telegram Integration · Source-Code Delivery

---

## 1. Going Global Means Paying for Losses You Can't See

SMS is still the lowest-cost, widest-reaching, most network-independent way to reach users worldwide. Every OTP, every shipping update, every promo blast is real revenue on the line.

But the moment you operate at global scale, "just sending an SMS" hides four blood-pressure-raising traps:

- **❌ Pricing is a black hole.** Upstream rates are marked up layer by layer, costs swing wildly between countries and operators, and month-end reconciliation never balances. Where exactly are you losing money? Nobody can tell.
- **❌ Deliverability is a black box.** You paid, the user never got it. One flaky route and OTPs time out en masse, support tickets explode — and you can't even see *which hop* it died on.
- **❌ Billing is too complex to self-serve.** How do you split long messages? Settle in multiple currencies? Price per-operator per-country? Doing it by hand in Excel simply doesn't scale.
- **❌ Integration scares everyone off.** SMPP protocol, persistent-connection keepalive, DLR receipts, per-country compliance rules — each is a wall, and getting from kickoff to launch routinely takes months.

**The real problem was never "SMS." It's that you don't own a transparent, controllable communications infrastructure of your own.**

---

## 2. Kaolach SMSC: Turn Communication Capability Into Your Own Asset

**Kaolach SMSC is an enterprise-grade international SMS gateway built for global-facing companies, cross-border e-commerce, fintech, and SMS/marketing integrators.**

It is **not** another "SMS API reseller." It is a platform you deploy **fully on your own infrastructure, delivered with source code.** You connect your own upstream channels, route intelligently by customer / country / price, and run billing, receipts, risk control, and reconciliation entirely yourself.

> **In one line:** Connect your upstream channels, intelligently distribute by customer / price / country, let customers top-up and send on their own, while the platform handles billing, DLR, risk control, and reconciliation end to end — all on **your** servers.

What you buy isn't "usage." It's an entire **moat**: pricing power, data ownership, compliance control, and the right to extend the code — all back in your hands.

---

## 3. Four Killer Capabilities

### 🧠 #1 — Smart Routing Engine: Every Message Takes the Smartest Path

70% of SMS cost and quality is decided by *route selection*. Kaolach ships **four routing strategies**, switchable in one click with automatic decisioning:

| Strategy | What it solves | Business upside |
|---|---|---|
| **Priority-first** | Core channels carry volume first | Stability for critical traffic |
| **Cost-first** | Auto-picks the cheapest compliant route | **Directly cuts cost** |
| **Quality-first** | Auto-picks the highest-deliverability route | **Lifts OTP delivery & conversion** |
| **Load-balancing** | Spreads traffic across channels | Avoids congestion & throttling |

And critically — **automatic failover.** The instant a primary channel falters, traffic shifts to a backup in milliseconds. Users feel nothing; business never stops.

> 💰 **ROI:** A "cost-first + quality-first" combo cuts spend *and* lifts performance. Every cent saved on channel fees drops straight to net profit.

---

### 💴 #2 — Granular 3-Tier Billing: Account for Every Cent

Fuzzy billing is where profit goes to die. Kaolach delivers an **industry-leading 3-tier billing model**:

> **Channel × Country × Operator (MCC/MNC)**

- **Three-dimensional pricing** — precise to "which channel, to which country, landing on which operator."
- **Automatic long-SMS splitting & billing** — oversized content is segmented and billed per segment. No overcharge, no leakage.
- **Multi-currency settlement** — native **USD / CNY / EUR**.
- **Multi-tier packages** — differentiated pricing per customer and per channel; master + sub-accounts with delegated quotas.

> 💰 **ROI:** For integrators this billing engine *is* a money printer — mark up over cost to downstream customers and **earn a stable channel margin**, with every transaction balanced and auditable.

---

### 🌐 #3 — Dynamic Sender ID Compliance: One System, Global Compliance

Sender ID rules worldwide are brutal: the US wants alphabetic SIDs, India requires DLT registration, every country differs. One mistake and an entire batch gets blocked by the operator.

Kaolach tears down that wall with **4-level priority matching**:

> **User-specified  ＞  Dedicated  ＞  Generic  ＞  System default**

The system auto-matches the most appropriate compliant Sender ID per scenario, **fully adapting to US alphabetic SIDs, India DLT, and compliance policies across the globe.** Compliant *and* deliverable.

> ✅ **Value:** While others struggle with compliance one country at a time, you cover the world with a single system — turning compliance from a roadblock into a competitive edge.

---

### 🤖 #4 — First-of-its-Kind Deep Telegram Integration: Your Whole Business in a Chat

This is Kaolach's most imaginative differentiator. We broke the "an SMS platform must live in a web console" assumption — through a single Telegram bot, the entire workflow closes inside the chat:

- 🚀 **Zero-friction sign-up** — register an account right in Telegram, no web page needed.
- 💰 **Real-time balance** — check balance and statements with one message.
- 📩 **Single & bulk send** — fire single messages or run bulk jobs from the chat.
- 🔔 **Live DLR push** — send results and delivery receipts pushed straight to Telegram.

> 📱 **Experience:** Your sales team and your customers no longer need to sit at a desk. Send and reconcile anytime, from a phone, inside a chat — the "wow" moment that wins deals.

---

## 4. Hard Engineering & Performance Guarantees — Numbers, Not Adjectives

Great features need an engine that holds up. Kaolach runs on a **modern, fully async, horizontally scalable** stack:

| Layer | Technology |
|---|---|
| Backend | **Python FastAPI** (fully async) |
| SMPP Gateway | **Go standalone service** (persistent connections / keepalive / auto-reconnect) |
| Frontend | **Vue 3 + Vite** (bilingual, responsive) |
| Messaging | **RabbitMQ** (multi-queue: send / DLR / result / data / webhook) |
| Task scheduling | **Celery** (distributed task processing) |
| Database | **MySQL 8 + ProxySQL** pool (`sms_logs` partitioned monthly, billions of rows) |
| Cache | **Redis 7** |
| Deployment | **Docker / K8s**, one-command orchestration |

**Architecture design targets (performance):**

- ⚡ **10,000+ TPS** concurrent throughput
- ⚡ **API response P95 < 200ms**
- ⚡ **System availability 99.9%**
- ⚡ **SMS deliverability 95%+** (with quality upstream + smart routing)

**Why it holds up:** fully async architecture + message-queue load shedding + partitioned hot tables + read/write splitting + a high-performance Go persistent-connection gateway. Start on a single node; scale out smoothly as your business grows.

> 🔒 **Enterprise security built in:** JWT + API Key dual authentication, full operation audit trail, config-change timeline, sensitive settings locked by default with confirm-to-edit, login & security logs. Every change is traceable and accountable.

---

## 5. Asset-Grade Delivery: Zero-Friction Handover

Many "systems" sell you a black box — when something breaks, you're at the vendor's mercy. **Kaolach is different: we deliver a complete technical asset your team can own independently.**

- ✅ **Full front-end & back-end source code** — FastAPI backend + Vue 3 frontend + Go SMPP gateway, all readable, modifiable, extensible.
- ✅ **Complete deployment scripts** — Docker Compose / K8s orchestration, one-command bring-up, identical environments.
- ✅ **100,000+ words across 9 professional engineering documents:**
  - Product Requirements (PRD)
  - System Architecture Design
  - Database Design & Data Dictionary
  - API Reference
  - Backend / Frontend Development Plans
  - Deployment Guide
  - Telegram Integration Guide
  - Routing & Billing Specification
  - …making second-stage development and team handover **frictionless.**

> 🎁 **Value:** You're never locked to a vendor again. Your team can read it, change it, extend it. Whether for in-house use or reselling downstream, control stays 100% with you.

---

## 6. Who Should Own It?

| You are | Kaolach solves |
|---|---|
| 🌍 **Global internet companies** | Worldwide OTP & notifications, deliverability + compliance assured |
| 🛒 **Cross-border e-commerce** | Order/shipping alerts & promo blasts at scale, lower cost |
| 🏦 **Fintech companies** | High availability + high deliverability + full audit, strong compliance |
| 🔧 **SMS / marketing integrators** | Ready-made channel orchestration + 3-tier billing — mark up & monetize downstream |

---

## 7. Take Action: Let a Demo Prove It

The earlier you reclaim control of your communications infrastructure, the more it's worth. Every extra day on a third-party black box is another day of invisible losses.

Kaolach SMSC offers three flexible options — **Source-Code Buyout / Perpetual-License Deployment / Annual-License Deployment** — one to match your stage and budget.

**👉 Contact us now:**

- 📞 **Book a 30-minute live demo** — watch smart routing and the Telegram bot run live
- 📄 **Request full technical docs and pricing**
- 🚀 **Apply for a trial deployment** — run real traffic through your own upstream channels

> **Contact:**
> - Telegram: `@____________`
> - WhatsApp / WeChat: `____________`
> - Email: `____________`

---

**Kaolach · Enterprise International SMS Gateway (SMSC)**
*Turn global communication capability into an asset you own.*

---

> *This material is for business communication. Performance figures are architecture design targets; actual results depend on upstream channel quality, network conditions, and deployment specifications. Final delivery scope and commercial terms are governed by the formal contract.*
