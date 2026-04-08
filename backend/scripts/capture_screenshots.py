#!/usr/bin/env python3
"""
使用 Playwright 截取系统客户页面截图，供操作指南使用。
"""
from playwright.sync_api import sync_playwright
import time

BASE = "http://127.0.0.1"
IMG_DIR = "/var/smsc/docs/guides/images"

API_KEY = "bd8bda2a49d04c6f8dfeb05b6dcd315236415b964d5799775ddd8d3b6245e296"
ACCOUNT_ID = "21"
ACCOUNT_NAME = "TG_7380365802_32f6"

PAGES = [
    ("login", "/login", "登录页面"),
    ("dashboard", "/dashboard", "工作台"),
    ("sms_send", "/sms/send", "发送短信"),
    ("sms_tasks", "/sms/tasks", "发送任务"),
    ("sms_records", "/sms/records", "发送记录"),
    ("sms_stats", "/sms/send-stats", "发送统计"),
    ("sms_approvals", "/sms/approvals", "短信审核"),
    ("sms_recharge", "/sms/recharge-records", "充值记录"),
    ("account_apikeys", "/account/api-keys", "API密钥"),
    ("account_settings", "/account/settings", "账户设置"),
    ("account_balance", "/account/balance", "余额"),
    ("account_tickets", "/account/tickets", "我的工单"),
    ("channels", "/channels", "通道管理"),
]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
            locale="zh-CN",
        )
        page = ctx.new_page()

        # 拦截外部字体请求，避免 "waiting for fonts to load" 超时
        page.route("**/*.woff2", lambda route: route.abort())
        page.route("**/*.woff", lambda route: route.abort())
        page.route("**/fonts.googleapis.com/**", lambda route: route.abort())
        page.route("**/fonts.gstatic.com/**", lambda route: route.abort())

        def _goto(url: str, sleep: int = 5):
            page.goto(url, wait_until="commit", timeout=60000)
            time.sleep(sleep)

        def _goto_stats():
            """发送统计页含 ECharts，需等待 DOM 与图表渲染后再截图"""
            page.goto(f"{BASE}/sms/send-stats", wait_until="commit", timeout=60000)
            try:
                page.wait_for_selector(".send-stats-page", timeout=25000)
            except Exception:
                pass
            try:
                page.wait_for_selector(".filter-panel", timeout=15000)
            except Exception:
                pass
            time.sleep(10)

        def _shot(name: str, label: str):
            page.screenshot(path=f"{IMG_DIR}/{name}.png", full_page=False, timeout=60000)
            print(f"截图: {name}.png ({label})")

        # 1. 登录页
        _goto(f"{BASE}/login", 5)
        _shot("login", "登录页面")

        # 2. 代客登录
        impersonate_url = (
            f"{BASE}/login?impersonate=1"
            f"&api_key={API_KEY}"
            f"&account_id={ACCOUNT_ID}"
            f"&account_name={ACCOUNT_NAME}"
            f"&redirect=/dashboard"
        )
        _goto(impersonate_url, 6)

        # 3. 客户各页面
        for name, path, label in PAGES:
            if name == "login":
                continue
            try:
                if name == "sms_stats":
                    _goto_stats()
                else:
                    _goto(f"{BASE}{path}", 4)
                _shot(name, label)
            except Exception as e:
                print(f"截图失败: {name} - {e}")

        browser.close()
        print("全部截图完成。")


if __name__ == "__main__":
    main()
