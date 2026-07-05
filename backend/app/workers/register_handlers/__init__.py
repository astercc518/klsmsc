"""注水注册专用 handler 插件包。

每个站点族一个模块,统一接口:
  - NAME: str                     handler 名(日志/统计用)
  - detect(page) -> bool          浏览器落地后判断当前页是否本 handler 适配的站
  - register(page, country_code="", phone="") -> (success: bool, reason_or_creds: str)
        驱动页面完成注册;成功时 reason 返回"账号 X ┊ 密码 Y ┊ 站 @ host"凭据串
        (会被 _do_register_sync 写进 water_injection_logs.device_info 供回查/复用)。

分流仍在 web_worker.web_register_task / _do_register_sync 里(先 API 商户→1win→本包 detect→
配置脚本/通用引擎兜底)。新增反自动化站:在本包加一个 <site>.py 实现 detect/register,
再在 _do_register_sync 落地后加一句 `if <site>.detect(page): ... <site>.register(...)` 即可。
web_worker 里的共享工具(_gen_identity/_click_submit/_check_register_success/_wait_through_cf 等)
在 register() 内**懒导入**,避免与 web_worker 循环引用。

已迁移:tk688(孟加拉 TK688 系博彩,算术图形验证码)。
待迁移(仍在 web_worker):1win(_do_register_1win)、jl_api(_do_register_via_api)。
"""
