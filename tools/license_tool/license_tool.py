#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
考拉出海 — 离线授权签发工具(Windows/macOS/Linux 通用,带图形界面)

用私钥离线签发 .lic 授权文件。签名算法与后端 app/core/license.py 完全一致:
  payload_canonical = json.dumps(payload, sort_keys=True, separators=(",",":"), ensure_ascii=False)
  sig = Ed25519(私钥, payload_canonical)
  .lic = base64( json{"payload":payload, "sig":base64(sig)} )

依赖:仅 cryptography(`pip install cryptography`)。tkinter 为 Python 自带。
运行:python license_tool.py        # 图形界面
     python license_tool.py --cli ...  # 命令行(见 build_license 参数)

私钥:把服务器 backend/.secrets/license_private_key.pem 安全拷到本机,
     与本程序同目录放置(默认名 license_private_key.pem),或在界面里选择。
【私钥务必离线保管,切勿上传/入库/外发。】
"""
import base64
import json
import os
import secrets
import sys
from datetime import datetime

try:
    from cryptography.hazmat.primitives import serialization as ser
except ImportError:
    sys.stderr.write("缺少依赖,请先运行: pip install cryptography\n")
    raise


# ----------------------- 纯逻辑(可被测试/CLI 复用) -----------------------
def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def build_license(private_key_path: str, *, customer: str, edition: str,
                  expires: str, fingerprint: str = "", unbound: bool = False,
                  grace_days: int = 0, brand_name: str = "", brand_logo: str = "") -> str:
    """构造并签名一张授权,返回 .lic 的 base64 文本。"""
    edition = (edition or "").strip()
    if edition not in ("saas", "private", "oem"):
        raise ValueError("edition 必须是 saas / private / oem")

    fp = "" if unbound else (fingerprint or "").strip()
    if edition in ("private", "oem") and not fp:
        raise ValueError("private/oem 必须填机器指纹(或勾选『不绑定』)")

    e = (expires or "").strip().lower()
    if e in ("", "perpetual", "none", "null", "永久"):
        expires_at = None
    else:
        # 校验日期格式
        datetime.strptime(expires.strip(), "%Y-%m-%d")
        expires_at = expires.strip()

    brand = None
    if brand_name or brand_logo:
        brand = {"name": brand_name or None, "logo": brand_logo or None}

    payload = {
        "license_id": "lic_" + secrets.token_hex(8),
        "customer": customer.strip(),
        "edition": edition,
        "issued_at": datetime.utcnow().date().isoformat(),
        "expires_at": expires_at,
        "machine_fingerprint": fp,
        "grace_days": int(grace_days or 0),
        "brand": brand,
        "limits": {},
        "nonce": secrets.token_hex(8),
    }

    with open(private_key_path, "rb") as f:
        priv = ser.load_pem_private_key(f.read(), password=None)
    sig = priv.sign(_canonical(payload))

    lic = base64.b64encode(json.dumps(
        {"payload": payload, "sig": base64.b64encode(sig).decode()},
        ensure_ascii=False,
    ).encode("utf-8")).decode()
    return lic


# ----------------------- 命令行模式 -----------------------
def _run_cli(argv):
    import argparse
    ap = argparse.ArgumentParser(description="离线签发授权 .lic")
    ap.add_argument("--private-key", default="license_private_key.pem")
    ap.add_argument("--customer", required=True)
    ap.add_argument("--edition", required=True, choices=["saas", "private", "oem"])
    ap.add_argument("--expires", default="perpetual", help="YYYY-MM-DD 或 perpetual")
    ap.add_argument("--fingerprint", default="")
    ap.add_argument("--unbound", action="store_true")
    ap.add_argument("--grace-days", type=int, default=0)
    ap.add_argument("--brand-name", default="")
    ap.add_argument("--brand-logo", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    lic = build_license(a.private_key, customer=a.customer, edition=a.edition,
                        expires=a.expires, fingerprint=a.fingerprint, unbound=a.unbound,
                        grace_days=a.grace_days, brand_name=a.brand_name, brand_logo=a.brand_logo)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(lic + "\n")
    print("已签发:", a.out)


# ----------------------- 图形界面 -----------------------
def _run_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    root = tk.Tk()
    root.title("考拉出海 — 离线授权签发工具")
    root.geometry("680x640")

    pad = {"padx": 8, "pady": 4}
    frm = ttk.Frame(root, padding=12)
    frm.pack(fill="both", expand=True)

    # 私钥路径
    default_key = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "license_private_key.pem")
    key_var = tk.StringVar(value=default_key if os.path.exists(default_key) else "")
    ttk.Label(frm, text="私钥文件 (.pem)").grid(row=0, column=0, sticky="w", **pad)
    key_entry = ttk.Entry(frm, textvariable=key_var, width=52)
    key_entry.grid(row=0, column=1, sticky="we", **pad)
    ttk.Button(frm, text="选择…",
               command=lambda: key_var.set(filedialog.askopenfilename(
                   filetypes=[("PEM 私钥", "*.pem"), ("所有文件", "*.*")]) or key_var.get())
               ).grid(row=0, column=2, **pad)

    # 客户
    customer_var = tk.StringVar()
    ttk.Label(frm, text="客户名称").grid(row=1, column=0, sticky="w", **pad)
    ttk.Entry(frm, textvariable=customer_var, width=52).grid(row=1, column=1, columnspan=2, sticky="we", **pad)

    # 版本
    edition_var = tk.StringVar(value="private")
    ttk.Label(frm, text="版本 edition").grid(row=2, column=0, sticky="w", **pad)
    ed_box = ttk.Combobox(frm, textvariable=edition_var, values=["saas", "private", "oem"],
                          state="readonly", width=20)
    ed_box.grid(row=2, column=1, sticky="w", **pad)

    # 到期
    perpetual_var = tk.BooleanVar(value=False)
    expires_var = tk.StringVar()
    ttk.Label(frm, text="到期日 (YYYY-MM-DD)").grid(row=3, column=0, sticky="w", **pad)
    exp_entry = ttk.Entry(frm, textvariable=expires_var, width=20)
    exp_entry.grid(row=3, column=1, sticky="w", **pad)

    def _toggle_perpetual():
        exp_entry.configure(state="disabled" if perpetual_var.get() else "normal")
    ttk.Checkbutton(frm, text="永久(买断)", variable=perpetual_var,
                    command=_toggle_perpetual).grid(row=3, column=2, sticky="w", **pad)

    # 指纹 + 不绑定
    unbound_var = tk.BooleanVar(value=False)
    fp_var = tk.StringVar()
    ttk.Label(frm, text="机器指纹").grid(row=4, column=0, sticky="w", **pad)
    fp_entry = ttk.Entry(frm, textvariable=fp_var, width=52)
    fp_entry.grid(row=4, column=1, columnspan=2, sticky="we", **pad)

    def _toggle_unbound():
        fp_entry.configure(state="disabled" if unbound_var.get() else "normal")
    ttk.Checkbutton(frm, text="不绑定机器(SaaS 用)", variable=unbound_var,
                    command=_toggle_unbound).grid(row=5, column=1, sticky="w", **pad)

    # 宽限天数
    grace_var = tk.StringVar(value="0")
    ttk.Label(frm, text="到期宽限天数").grid(row=6, column=0, sticky="w", **pad)
    ttk.Entry(frm, textvariable=grace_var, width=10).grid(row=6, column=1, sticky="w", **pad)

    # OEM 品牌
    brand_name_var = tk.StringVar()
    brand_logo_var = tk.StringVar()  # 存 data URL 或 http(s) URL
    ttk.Label(frm, text="OEM 品牌名(可选)").grid(row=7, column=0, sticky="w", **pad)
    ttk.Entry(frm, textvariable=brand_name_var, width=52).grid(row=7, column=1, columnspan=2, sticky="we", **pad)
    ttk.Label(frm, text="OEM Logo(可选)").grid(row=8, column=0, sticky="w", **pad)
    logo_show = ttk.Entry(frm, textvariable=brand_logo_var, width=40)
    logo_show.grid(row=8, column=1, sticky="we", **pad)

    def _pick_logo():
        p = filedialog.askopenfilename(filetypes=[("图片", "*.png *.jpg *.jpeg *.svg *.gif"), ("所有文件", "*.*")])
        if not p:
            return
        if os.path.getsize(p) > 480 * 1024:
            messagebox.showerror("错误", "Logo 过大,请小于 480KB")
            return
        ext = os.path.splitext(p)[1].lower().lstrip(".") or "png"
        mime = "image/svg+xml" if ext == "svg" else f"image/{'jpeg' if ext in ('jpg','jpeg') else ext}"
        with open(p, "rb") as f:
            b = base64.b64encode(f.read()).decode()
        brand_logo_var.set(f"data:{mime};base64,{b}")
    ttk.Button(frm, text="选图片…", command=_pick_logo).grid(row=8, column=2, **pad)

    # 输出区
    ttk.Label(frm, text=".lic 内容").grid(row=9, column=0, sticky="nw", **pad)
    out_text = tk.Text(frm, height=7, width=60, wrap="char")
    out_text.grid(row=9, column=1, columnspan=2, sticky="we", **pad)

    frm.columnconfigure(1, weight=1)

    def _generate():
        try:
            if not key_var.get() or not os.path.exists(key_var.get()):
                messagebox.showerror("错误", "请先选择存在的私钥 .pem 文件")
                return
            lic = build_license(
                key_var.get(),
                customer=customer_var.get(),
                edition=edition_var.get(),
                expires="perpetual" if perpetual_var.get() else expires_var.get(),
                fingerprint=fp_var.get(),
                unbound=unbound_var.get(),
                grace_days=int(grace_var.get() or 0),
                brand_name=brand_name_var.get(),
                brand_logo=brand_logo_var.get(),
            )
            out_text.delete("1.0", "end")
            out_text.insert("1.0", lic)
            messagebox.showinfo("成功", "已生成授权内容,可『保存为文件』或直接复制给客户上传。")
        except Exception as e:
            messagebox.showerror("生成失败", str(e))

    def _save():
        content = out_text.get("1.0", "end").strip()
        if not content:
            messagebox.showwarning("提示", "请先点『生成』")
            return
        default = (customer_var.get().strip() or "license") + ".lic"
        p = filedialog.asksaveasfilename(defaultextension=".lic", initialfile=default,
                                         filetypes=[("授权文件", "*.lic")])
        if p:
            with open(p, "w", encoding="utf-8") as f:
                f.write(content + "\n")
            messagebox.showinfo("已保存", p)

    def _copy():
        content = out_text.get("1.0", "end").strip()
        if content:
            root.clipboard_clear()
            root.clipboard_append(content)
            messagebox.showinfo("已复制", "已复制到剪贴板")

    btns = ttk.Frame(frm)
    btns.grid(row=10, column=0, columnspan=3, pady=12)
    ttk.Button(btns, text="生成授权", command=_generate).pack(side="left", padx=6)
    ttk.Button(btns, text="保存为 .lic", command=_save).pack(side="left", padx=6)
    ttk.Button(btns, text="复制", command=_copy).pack(side="left", padx=6)

    ttk.Label(frm, foreground="#888",
              text="提示:private/OEM 必须填客户机器指纹;指纹由客户在其部署上运行 license_fingerprint 取得。"
              ).grid(row=11, column=0, columnspan=3, sticky="w", **pad)

    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        _run_cli(sys.argv[2:])
    else:
        _run_gui()
