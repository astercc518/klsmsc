#!/usr/bin/env python3
"""
打印本机授权指纹 —— 在【客户部署的机器】上运行,把输出发给厂商以签发绑定 license。

用法(api 容器内):
  docker compose exec -w /app -e PYTHONPATH=/app api python scripts/license_fingerprint.py

注意:私有部署务必把宿主 /etc/machine-id 挂进容器(见 docker-compose),
否则指纹会随容器重建而变化。
"""
import sys
sys.path.insert(0, "/app")
from app.core.license import compute_fingerprint, _machine_id_path  # noqa: E402

print("机器指纹 :", compute_fingerprint())
print("指纹来源 :", _machine_id_path(), "(读不到则回退 /etc/machine-id)")
