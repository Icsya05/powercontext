r"""赛题速查 Web 服务：标准库 http.server，无第三方框架。

用法：.\.venv\Scripts\python.exe -m src.server [--host 127.0.0.1] [--port 8000]
"""

import argparse
import json
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from src.db import ensure_schema, list_notes, log_search, recent_searches, stats
from src.retriever import remember, search

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
MAX_BODY = 1024 * 1024

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
}


def _static_file(name: str) -> Path | None:
    """白名单：只允许 web 目录下实际存在的 .html/.css/.js 文件，不接受路径参数。"""
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        return None
    path = (WEB_DIR / name).resolve()
    if path.parent != WEB_DIR.resolve() or path.suffix not in _CONTENT_TYPES:
        return None
    return path if path.is_file() else None


class Handler(BaseHTTPRequestHandler):
    server_version = "kaoti-sucha/1.0"

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _error(self, code: int, msg: str) -> None:
        self._json(code, {"error": msg})

    def _log(self, code: int, t0: float) -> None:
        ms = int((time.time() - t0) * 1000)
        print(f"{self.command} {self.path} {code} {ms}ms", flush=True)

    def log_message(self, format, *args):  # 关掉默认的 "127.0.0.1 - - [...]" 行，只留自定义格式
        pass

    def do_GET(self) -> None:
        t0 = time.time()
        code = 500
        try:
            code = self._handle_get()
        except Exception:
            traceback.print_exc()
            self._error(500, "internal error")
        self._log(code, t0)

    def do_POST(self) -> None:
        t0 = time.time()
        code = 500
        try:
            code = self._handle_post()
        except Exception:
            traceback.print_exc()
            self._error(500, "internal error")
        self._log(code, t0)

    def _handle_get(self) -> int:
        url = urlsplit(self.path)
        path = url.path

        if path == "/":
            index = _static_file("index.html")
            if index is None:
                self._error(404, "index.html not found")
                return 404
            self._send(200, index.read_bytes(), _CONTENT_TYPES[".html"])
            return 200

        if path == "/api/search":
            params = parse_qs(url.query)
            q = (params.get("q") or [""])[0].strip()
            if not q:
                self._error(400, "缺少参数 q")
                return 400
            try:
                k = int((params.get("k") or ["6"])[0])
            except ValueError:
                self._error(400, "参数 k 必须是整数")
                return 400
            k = max(1, min(k, 30))
            res = search(q, topk=k)
            try:
                log_search(q, len(res["results"]), res["elapsed_ms"])
            except Exception:
                # seekdb 的 AUTO_INCREMENT 计数器在进程被强杀后会回退，日志写入
                # 可能撞上已存在的 id。日志失败不影响查询结果返回。
                traceback.print_exc()
            self._json(200, res)
            return 200

        if path == "/api/notes":
            self._json(200, {"notes": list_notes(limit=20)})
            return 200

        if path == "/api/stats":
            self._json(200, {"stats": stats(), "recent": recent_searches(limit=20)})
            return 200

        static = _static_file(path.lstrip("/"))
        if static is not None:
            self._send(200, static.read_bytes(), _CONTENT_TYPES[static.suffix])
            return 200

        self._error(404, "not found")
        return 404

    def _handle_post(self) -> int:
        url = urlsplit(self.path)
        if url.path != "/api/notes":
            self._error(404, "not found")
            return 404

        length = self.headers.get("Content-Length")
        if length is None:
            self._error(400, "缺少请求体")
            return 400
        try:
            size = int(length)
        except ValueError:
            self._error(400, "Content-Length 非法")
            return 400
        if size <= 0 or size > MAX_BODY:
            self._error(400, "请求体长度非法")
            return 400

        raw = self.rfile.read(size)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error(400, "请求体必须是合法 JSON")
            return 400
        if not isinstance(data, dict):
            self._error(400, "请求体必须是 JSON 对象")
            return 400

        author = str(data.get("author") or "").strip()
        question = str(data.get("question") or "").strip()
        answer = str(data.get("answer") or "").strip()
        tags = str(data.get("tags") or "").strip()
        if not question or not answer:
            self._error(400, "question 和 answer 不能为空")
            return 400

        note_id = remember(author or "匿名", question, answer, tags)
        self._json(200, {"id": note_id, "notes": list_notes(limit=20)})
        return 200


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="赛题速查 Web 服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    ensure_schema()
    t0 = time.time()
    search("预热")  # 冷启动约 2.5s：加载 idf.json + 打开 seekdb；之后约 130ms
    print(f"预热完成 {int((time.time() - t0) * 1000)}ms", flush=True)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"监听 http://{args.host}:{args.port} (Ctrl+C 停止)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
