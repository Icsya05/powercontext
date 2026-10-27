#!/usr/bin/env python3
"""把 gaode/SKILL.md 打包上传到魔搭社区（ModelScope）并创建 Skill。

只用标准库，不需要 requests。凭据只从环境变量读，不打印、不落盘。

用法：
  export MODELSCOPE_API_KEY=xxx
  python modelscope/publish_skill.py --owner <用户名>
  python modelscope/publish_skill.py --owner <用户名> --dry-run   # 只打包

两步流程（魔搭 OpenAPI）：
  1. POST /openapi/v1/files/upload   multipart(file=<zip>, type=skill) -> data.id
  2. POST /openapi/v1/skills         JSON(skill_file=data.id ...)      -> 作品页
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # 仓库里的 ecosystem 根
SKILL = ROOT / "gaode" / "SKILL.md"
ZIP_OUT = Path(__file__).resolve().parent / "nearby-walk-recommendations.zip"

ENDPOINT = os.environ.get("MODELSCOPE_ENDPOINT", "https://modelscope.cn").rstrip("/")
SKILL_NAME = "nearby-walk-recommendations"
DISPLAY_NAME = "周边去哪儿"
CATEGORY = "other"          # 魔搭分类：developer-tools / analytics / other ...
LICENSE = "Apache-2.0"
DESCRIPTION = (
    "根据城市、起点坐标和自然语言需求，调用高德 MCP 的地点搜索与步行路线规划，"
    "推荐最多 3 个从同一起点出发的备选地点，给出实测步行距离、耗时与逐条理由；"
    "步行时间只用路线规划结果，超时、无结果、路线失败分别如实说明。"
)
TAGS = ["gaode", "amap", "walking-distance", "poi-search", "travel"]
SOURCE_URL = "https://github.com/Icsya05/powercontext"


def build_zip() -> Path:
    """魔搭要求：zip 根目录只能有 1 个 SKILL.md，不能带其他文件。"""
    if not SKILL.is_file():
        raise SystemExit(f"找不到 {SKILL}")
    if ZIP_OUT.exists():
        ZIP_OUT.unlink()
    with zipfile.ZipFile(ZIP_OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(SKILL, arcname="SKILL.md")     # 不带 gaode/ 目录层
    names = zipfile.ZipFile(ZIP_OUT).namelist()
    if names != ["SKILL.md"]:
        raise SystemExit(f"包结构不符合要求，实际内容：{names}")
    size = ZIP_OUT.stat().st_size
    if size > 5 * 1024 * 1024:
        raise SystemExit(f"包超过 5 MB：{size} 字节")
    print(f"已打包 {ZIP_OUT.name}（{size} 字节，内含 {names[0]}）")
    return ZIP_OUT


def _post_multipart(url: str, token: str, fields: dict[str, str], file_field: str,
                    file_path: Path) -> dict:
    boundary = "----msform" + uuid.uuid4().hex
    body = bytearray()
    for k, v in fields.items():
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    body += (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
        f"filename=\"{file_path.name}\"\r\nContent-Type: application/zip\r\n\r\n"
    ).encode()
    body += file_path.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(url, data=bytes(body), method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    return _send(req)


def _post_json(url: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    return _send(req)


def _get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    return _send(req)


def _send(req: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        raise SystemExit(f"HTTP {e.code}：{detail}") from None
    except urllib.error.URLError as e:
        raise SystemExit(f"网络不可达：{e.reason}") from None


def main() -> int:
    ap = argparse.ArgumentParser(description="上传 SKILL.md 到魔搭并创建 Skill")
    ap.add_argument("--owner", help="魔搭用户名（作品会归属到它）")
    ap.add_argument("--dry-run", action="store_true", help="只打包，不上传")
    args = ap.parse_args()

    pkg = build_zip()
    if args.dry_run:
        print("dry-run：已打包，未上传。")
        return 0
    if not args.owner:
        raise SystemExit("需要 --owner（魔搭用户名）")

    token = os.environ.get("MODELSCOPE_API_KEY", "").strip()
    if not token:
        raise SystemExit(
            "未设置 MODELSCOPE_API_KEY。\n"
            "在 https://www.modelscope.cn 的『我的 → API-KEY』创建后，\n"
            "自行 export MODELSCOPE_API_KEY=... 再运行；不要把 Key 贴到聊天或提交到仓库。"
        )

    print("1/3 上传包 …")
    up = _post_multipart(f"{ENDPOINT}/openapi/v1/files/upload", token,
                         {"type": "skill"}, "file", pkg)
    file_id = (up.get("data") or {}).get("id")     # 注意键名是 id
    if not file_id:
        raise SystemExit(f"上传未返回 data.id：{json.dumps(up, ensure_ascii=False)[:400]}")
    print(f"    得到文件 id：{file_id}")

    print("2/3 创建 Skill …")
    created = _post_json(f"{ENDPOINT}/openapi/v1/skills", token, {
        "owner": args.owner,
        "skill_name": SKILL_NAME,
        "display_name": DISPLAY_NAME,
        "description": DESCRIPTION,
        "skill_file": file_id,
        "category": CATEGORY,
        "license": LICENSE,
        "tags": TAGS,
        "source_url": SOURCE_URL,
    })
    print(f"    返回：{json.dumps(created, ensure_ascii=False)[:300]}")

    print("3/3 回查确认 …")
    url = f"{ENDPOINT}/openapi/v1/skills/{args.owner}/{SKILL_NAME}"
    try:
        detail = _get(url, token)
        data = detail.get("data", detail)
        print(f"    名称：{data.get('display_name')} | 分类：{data.get('category')}"
              f" | 许可：{data.get('license')}")
    except SystemExit as e:
        print(f"    回查失败（不影响已创建结果，请稍后在网页确认）：{e}")

    page = f"https://modelscope.cn/skills/@{args.owner}/{SKILL_NAME}"
    print(f"\n作品页：{page}")
    print("请打开该页确认能看到 SKILL.md 内容，再把网址提交到大赛的魔搭题入口。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
