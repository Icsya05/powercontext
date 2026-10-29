#!/usr/bin/env python3
"""从语雀公开知识库抓取 OceanBase 大赛官方文档，保存为本地 Markdown。

用法：python tools/fetch_docs.py
产物：data/docs/{slug}.md（清洗后的正文）、data/docs/index.json（元信息索引）
仅依赖标准库。
"""

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "data" / "docs"
INDEX_PATH = DOCS_DIR / "index.json"

TOC_URL = "https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/ocqe6xv6mlgapq24"
BOOK_ID = "81051108"
DOC_API = f"https://oceanbase.yuque.com/api/docs/{{slug}}?book_id={BOOK_ID}&mode=markdown"
WEB_DOC = "https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/{slug}"

SLEEP_SECONDS = 0.6
RETRIES = 3
TIMEOUT = 30
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

# 目录树是 URL 编码的 JSON 内嵌在服务端渲染的 HTML 里，以 %7B 或 %5B 开头
PAYLOAD_RE = re.compile(r'"((?:%7B|%5B)[^"]{200,})"')
ZERO_WIDTH_RE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
FONT_TAG_RE = re.compile(r"</?font\b[^>]*>", re.IGNORECASE)


def log(msg: str = "") -> None:
    print(msg, flush=True)


def http_get(url: str) -> str:
    """GET 请求；网络失败重试 RETRIES 次（4xx 不重试）。"""
    last_err = None
    for attempt in range(RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as err:
            if 400 <= err.code < 500:
                raise
            last_err = err
        except Exception as err:
            last_err = err
        if attempt < RETRIES:
            log(f"    请求失败（{last_err}），{attempt + 1}s 后重试 {attempt + 1}/{RETRIES}...")
            time.sleep(attempt + 1)
    raise last_err


def extract_toc(html: str) -> list[dict]:
    matches = PAYLOAD_RE.findall(html)
    if not matches:
        raise RuntimeError("未在目录页 HTML 中找到 URL 编码的 JSON 片段")
    longest = max(matches, key=len)
    payload = json.loads(urllib.parse.unquote(longest))
    toc = payload.get("book", {}).get("toc")
    if not isinstance(toc, list):
        raise RuntimeError("payload 中缺少 book.toc")

    items: list[dict] = []
    seen: set[str] = set()

    def walk(nodes: list) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            slug = node.get("url")
            title = node.get("title")
            if slug and title and slug not in seen:
                seen.add(slug)
                items.append({
                    "slug": slug,
                    "title": title,
                    "level": node.get("level", 0),
                })
            children = node.get("children")
            if isinstance(children, list):
                walk(children)

    walk(toc)
    return items


def clean_markdown(text: str) -> str:
    text = FONT_TAG_RE.sub("", text)
    text = ZERO_WIDTH_RE.sub("", text)
    out: list[str] = []
    blank_run = 0
    for line in text.splitlines():
        line = line.rstrip()
        if line:
            blank_run = 0
            out.append(line)
        else:
            blank_run += 1
            if blank_run == 1:
                out.append("")
    return "\n".join(out).strip() + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    log(f"== 抓取目录页: {TOC_URL}")
    toc = extract_toc(http_get(TOC_URL))
    log(f"== 目录共 {len(toc)} 篇文档，开始抓取（每篇间隔 {SLEEP_SECONDS}s）")
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    docs: list[dict] = []
    failed: list[dict] = []
    total = len(toc)
    for i, item in enumerate(toc, 1):
        slug = item["slug"]
        try:
            raw = http_get(DOC_API.format(slug=slug))
            data = json.loads(raw).get("data") or {}
            source = data.get("sourcecode") or ""
            if not source.strip():
                raise RuntimeError("sourcecode 为空")
            text = clean_markdown(source)
            (DOCS_DIR / f"{slug}.md").write_text(text, encoding="utf-8")
            entry = {
                "slug": slug,
                "title": item["title"],
                "level": item["level"],
                "url": WEB_DOC.format(slug=slug),
                "updated_at": data.get("content_updated_at") or data.get("published_at"),
                "chars": len(re.sub(r"\s+", "", text)),
            }
            docs.append(entry)
            log(f"[{i:>3}/{total}] OK   {entry['title']}  ({entry['chars']} 字)")
        except Exception as err:
            failed.append({"slug": slug, "title": item["title"], "error": str(err)})
            log(f"[{i:>3}/{total}] 失败 {item['title']}: {err}")
        if i < total:
            time.sleep(SLEEP_SECONDS)

    index = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_in_toc": total,
        "ok": len(docs),
        "failed": len(failed),
        "docs": docs,
    }
    INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    log("\n===== 汇总 =====")
    log(f"成功 {len(docs)} 篇，失败 {len(failed)} 篇")
    for f in failed:
        log(f"  - {f['title']} ({f['slug']}): {f['error']}")
    log(f"索引已写入 {INDEX_PATH}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
