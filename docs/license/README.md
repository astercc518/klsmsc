# 软件授权(License)说明

一套基于 **Ed25519 签名 + 机器指纹** 的离线授权机制,覆盖三种购买方式:
`saas`(我方托管)/ `private`(私有部署买断)/ `oem`(白标)。

## 原理
- 公钥内嵌在 `backend/app/core/license.py`(`_DEFAULT_PUBLIC_KEY_B64`);**私钥离线保管**(`backend/.secrets/license_private_key.pem`,已 gitignore)。
- `.lic` = `base64( {"payload": {...}, "sig": ed25519签名} )`,纯离线验签,不联网。
- 验证三关:**签名未篡改 → 未过期(含 grace)→ 机器指纹匹配**。
- 失效(到期/被篡改/换机)→ **全停发送 + 后台红色横幅**;后台仍可登录、查看、上传新证。

## 机器指纹
取宿主 `/etc/machine-id` 哈希得到。docker 已在 `api` 与 `worker-sms` 挂载
`/etc/machine-id:/etc/host-machine-id:ro`,保证容器内指纹稳定且等于本机。
**所有运行验签的容器(api、worker-sms)必须挂同一 machine-id,否则指纹不一致会误判换机。**

## 厂商:签发流程
```bash
# 1)(一次性)生成密钥对,把打印的公钥内嵌进 core/license.py
docker compose exec -u 0 -w /app api python scripts/license_keygen.py

# 2) 让客户在其机器上取指纹
docker compose exec -w /app -e PYTHONPATH=/app api python scripts/license_fingerprint.py

# 3) 签发 .lic(私有/OEM 必须 --fingerprint;SaaS 可 --unbound)
docker compose exec -u 0 -w /app api python scripts/license_issue.py \
  --customer "客户名" --edition private --expires 2027-12-31 --grace-days 15 \
  --fingerprint fp_xxxx --out /app/.secrets/cust.lic
# OEM 加品牌种子: --edition oem --brand-name "XX短信" --brand-logo "data:image/png;base64,..."
```

## 客户:安装/续期
后台 **系统设置 → 软件授权** 标签页:查看状态/指纹、粘贴 `.lic` 上传(super_admin)。
上传会先验签+校验指纹,通过才落库(`system_config.license.blob`),即时生效。

## 关键开关:`LICENSE_REQUIRE`
- 默认 `False`:**未安装授权=宽松放行**(只黄条提醒),避免未发证就把系统锁死。
- **分发给客户的 private/OEM 版应在 .env 设 `LICENSE_REQUIRE=1`**,使"未安装/被删除授权"也全停,防止裸跑盗用。
- 注意:`expired/invalid/wrong_machine`(装了证但证有问题)**无论该开关都全停**。

## OEM 白标
`edition=oem` 时,super_admin 可在授权页改 **品牌名称 / Logo**(存 `system_config` 的 `brand.name`/`brand.logo`);
公开接口 `GET /api/v1/license/brand` 输出有效品牌,前端登录页/控制台据此换名换标。授权失效则回退默认考拉品牌。

## 降级行为(到期/欠费/盗用)
- 发送类端点(`/sms/send`、`/sms/batch`、`/batches/upload`)返回 403;
- `send_sms_task`(worker-sms)兜底:即使绕过 API 直推队列,也置失败不外发;
- 后台登录/查看/上传授权不受影响,便于续期。

## 文件清单
- `backend/app/core/license.py` — 验证核心 + `require_valid_license` 依赖
- `backend/app/api/v1/license.py` — status/fingerprint/upload + brand 读写
- `backend/scripts/license_{keygen,fingerprint,issue}.py` — 厂商工具
- `backend/.secrets/` — 私钥与签发的 .lic(**gitignore,勿入库**)
