# 考拉出海 — 离线授权签发工具(Windows)

`license_tool.py` 是一个**离线、带图形界面**的授权签发工具,用私钥在本机生成 `.lic` 授权文件。
签名算法与后端 `app/core/license.py` 完全一致,生成的证可直接在客户后台上传使用。

> 已实测:本工具生成的 `.lic` 后端 `verify_blob` 校验通过(`state=valid`)。

## 一、准备私钥(关键)
把签发私钥从服务器安全拷到这台 Windows 机器:
- 文件:服务器 `backend/.secrets/license_private_key.pem`
- 放到与工具同目录,文件名保持 `license_private_key.pem`(或运行时在界面里『选择…』)。

⚠️ **私钥决定一切,务必离线保管:不要上传网盘、不要进 git、不要外发。** 建议这台 Windows 机器不联网。

## 二、方式 A:直接用 Python 跑(最省事)
1. 安装 Python 3.9+(勾选 *Add Python to PATH*)。
2. 装依赖:
   ```cmd
   pip install cryptography
   ```
3. 双击或命令行运行:
   ```cmd
   python license_tool.py
   ```
   出现图形界面,填写后点『生成授权』→『保存为 .lic』。

## 三、方式 B:打包成单文件 .exe(免装 Python,可分发)
在一台 Windows 上执行一次:
```cmd
pip install cryptography pyinstaller
pyinstaller --onefile --windowed --name 考拉授权工具 license_tool.py
```
产物在 `dist\考拉授权工具.exe`,双击即用。把私钥 `license_private_key.pem` 放到 exe 同目录即可。

> macOS/Linux 同样可跑 `python license_tool.py`;打 mac/Linux 包同理(PyInstaller 产物是当前系统平台的,做 Windows .exe 必须在 Windows 上打)。

## 四、签发流程
1. **取指纹**:让客户在其部署上运行(私有/OEM 必需):
   ```bash
   docker compose exec -w /app -e PYTHONPATH=/app api python scripts/license_fingerprint.py
   ```
   把输出的 `fp_xxxx` 发你。
2. **填表生成**:
   - 版本:`saas`(我方托管,可勾『不绑定』)/ `private`(私有买断)/ `oem`(白标)
   - 到期:填 `YYYY-MM-DD` 或勾『永久(买断)』
   - 机器指纹:粘贴客户的 `fp_xxxx`(private/oem 必填)
   - 宽限天数、OEM 品牌名/Logo(可选)
   - 点『生成授权』→『保存为 .lic』或『复制』。
3. **交付**:把 `.lic` 内容发客户,客户在后台 **系统设置 → 软件授权 → 安装/更新授权** 粘贴上传。

## 五、命令行模式(可选,批量/脚本用)
```cmd
python license_tool.py --cli --private-key license_private_key.pem ^
  --customer "广州XX科技" --edition private --expires 2027-12-31 ^
  --grace-days 15 --fingerprint fp_xxxx --out xx.lic
```

## 六、要点
- 续期 = 重签一张新到期日的 `.lic`,客户重新上传覆盖。
- 换机 = 用新指纹重签。
- 给客户的 private/OEM 部署,记得让其 `.env` 设 `LICENSE_REQUIRE=1`(防删证裸跑)。
- 换私钥需同步更新后端内嵌公钥(`_DEFAULT_PUBLIC_KEY_B64`)并重签所有在用证。
