# -*- coding: utf-8 -*-
"""一键配置 GitHub Actions secret：FEISHU_WEBHOOK_URL（2026-08-28 PENDING §1）。

用法（webhook URL 从飞书群机器人设置页复制，https://open.feishu.cn/open-apis/bot/v2/hook/xxx）：
    set FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
    .venv\\Scripts\\python.exe tools\\alert\\set_feishu_secret.py

安全说明：
- secret 经 GitHub repo public key（libsodium sealed box）加密后上传，仓库内无明文；
- 本脚本不落盘、不打印完整 URL（仅显示前缀掩码）；
- token 经 git credential fill 获取，需对该仓库有 Actions secrets 写权限
  （fine-grained PAT 勾选 Secrets: RW，或 classic PAT 含 repo scope）。

依赖：pynacl（.venv 已装）。
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import urllib.request

REPO = "xmuhl/smi"
SECRET_NAME = "FEISHU_WEBHOOK_URL"


def _token() -> str:
    out = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("ERROR: git credential fill 未取到 token")


def _api(method: str, path: str, token: str, payload: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8")
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def main() -> int:
    webhook = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
    if not webhook.startswith("https://open.feishu.cn/open-apis/bot/v2/hook/"):
        print("ERROR: FEISHU_WEBHOOK_URL 未设置或不是飞书机器人 webhook 地址")
        return 2

    masked = webhook[:46] + "..." + webhook[-4:]
    token = _token()

    status, key = _api("GET", f"/repos/{REPO}/actions/secrets/public-key", token)
    if status != 200:
        print(f"ERROR: 读取 repo public key 失败 HTTP {status}: {key.get('message','')}")
        print("提示：token 需对该仓库有 Actions secrets 写权限（或代理临时故障，稍后重试）")
        return 1

    from nacl import encoding, public

    pk = public.PublicKey(
        key["key"].encode("utf-8"), encoding.Base64Encoder()
    )
    sealed = public.SealedBox(pk).encrypt(webhook.encode("utf-8"))

    status, resp = _api(
        "PUT",
        f"/repos/{REPO}/actions/secrets/{SECRET_NAME}",
        token,
        {
            "encrypted_value": base64.b64encode(sealed).decode("utf-8"),
            "key_id": key["key_id"],
        },
    )
    if status in (201, 204):
        print(f"OK: {SECRET_NAME} 已写入 {REPO}（{masked}）")
        print("验证：GitHub 仓库 → Settings → Secrets and variables → Actions")
        return 0

    print(f"ERROR: 写入失败 HTTP {status}: {resp.get('message','')}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
