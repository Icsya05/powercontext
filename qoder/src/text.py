"""Markdown 切块、中文分词、向量化与摘要。仅依赖标准库，不依赖 seekdb。"""

import hashlib
import math
import re
import sys
from bisect import bisect_right
from dataclasses import dataclass

TARGET_CHARS = 700    # 目标块长
HARD_CHARS = 1200     # 硬上限，超过按空行段落再切
MIN_FRAGMENT = 80     # 短于该值的碎片并入前一块
VEC_DIM = 1024

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE_RE = re.compile(r"^ {0,3}(```|~~~)")
TOKEN_RE = re.compile(
    r"([a-z0-9_]+@\d+)"      # recall@10 这类形式
    r"|([a-z]+)"             # 英文整词
    r"|(\d+)"                # 数字
    r"|([\u4e00-\u9fff]+)"   # 中文连续串
)


@dataclass
class Chunk:
    doc_slug: str
    doc_title: str
    heading: str
    index: int
    text: str
    url: str
    tokens: list[str]


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for m in TOKEN_RE.finditer(text.lower()):
        at, word, num, cjk = m.groups()
        if at:
            tokens.append(at)
            head, tail = at.rsplit("@", 1)
            if len(head) >= 2:
                tokens.append(head)
            if len(tail) >= 2:
                tokens.append(tail)
        elif word:
            if len(word) >= 2:
                tokens.append(word)
        elif num:
            if len(num) >= 2:
                tokens.append(num)
        else:
            for i in range(len(cjk) - 1):
                tokens.append(cjk[i:i + 2])
            for i in range(len(cjk) - 2):
                tokens.append(cjk[i:i + 3])
    return tokens


def _pack_lines(lines: list[str]) -> list[str]:
    """把一节的行按空行段落打包成块；代码块是原子单元，不会被切断。"""
    units: list[list[str]] = []
    cur: list[str] = []
    fence = None
    for line in lines:
        stripped = line.lstrip()
        if fence:
            cur.append(line)
            if stripped.startswith(fence):
                fence = None
            continue
        m = FENCE_RE.match(line)
        if m:
            fence = m.group(1)
            cur.append(line)
            continue
        if not line.strip():
            if cur:
                units.append(cur)
                cur = []
        else:
            cur.append(line)
    if cur:
        units.append(cur)

    chunks: list[str] = []
    buf: list[list[str]] = []
    size = 0

    def flush() -> str:
        nonlocal buf, size
        out = "\n\n".join("\n".join(u) for u in buf).strip()
        buf, size = [], 0
        return out

    for u in units:
        s = sum(len(l) for l in u) + len(u) - 1
        if buf and size + s > HARD_CHARS:
            chunks.append(flush())
        buf.append(u)
        size += s + (2 if len(buf) > 1 else 0)
        if size >= TARGET_CHARS:
            chunks.append(flush())
    if buf:
        chunks.append(flush())

    if len(chunks) > 1 and len(chunks[-1]) < MIN_FRAGMENT:
        chunks[-2] += "\n\n" + chunks[-1]
        chunks.pop()
    return [c for c in chunks if c]


def split_into_chunks(md: str, doc_slug: str, doc_title: str, url: str) -> list[Chunk]:
    md = md.replace("\r\n", "\n").replace("\r", "\n")
    sections: list[tuple[str, list[str]]] = []
    path: list[tuple[int, str]] = []
    cur: list[str] = []

    def flush_section() -> None:
        nonlocal cur
        if cur:
            sections.append((" > ".join(t for _, t in path), cur))
            cur = []

    fence = None
    for line in md.split("\n"):
        stripped = line.lstrip()
        if fence:
            cur.append(line)
            if stripped.startswith(fence):
                fence = None
            continue
        m = FENCE_RE.match(line)
        if m:
            fence = m.group(1)
            cur.append(line)
            continue
        m = HEADING_RE.match(line)
        if m:
            flush_section()
            level = len(m.group(1))
            title = m.group(2).strip().strip(" \t*_`~")
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, title))
        else:
            cur.append(line)
    flush_section()

    chunks: list[Chunk] = []
    for heading, lines in sections:
        for text in _pack_lines(lines):
            if heading:
                text = heading + "\n" + text
            chunks.append(Chunk(
                doc_slug=doc_slug,
                doc_title=doc_title,
                heading=heading,
                index=len(chunks),
                text=text,
                url=url,
                tokens=tokenize(text),
            ))
    return chunks


def build_idf(token_lists: list[list[str]]) -> dict[str, float]:
    n = len(token_lists)
    df: dict[str, int] = {}
    for tokens in token_lists:
        for t in set(tokens):
            df[t] = df.get(t, 0) + 1
    return {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}


def vectorize(tokens: list[str], idf: dict[str, float], dim: int = VEC_DIM) -> list[float]:
    # 哈希必须确定性：内置 hash() 每个进程带随机盐，建库和查询会算出不同向量，
    # 所以用 blake2b；用哈希的一个 bit 决定正负号，抵消特征哈希的碰撞偏差。
    tf: dict[str, int] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    vec = [0.0] * dim
    for t, c in tf.items():
        w = (1.0 + math.log(c)) * idf.get(t, 1.0)
        h = hashlib.blake2b(t.encode("utf-8"), digest_size=16).digest()
        idx = int.from_bytes(h[:8], "big") % dim
        sign = 1.0 if h[8] & 1 else -1.0
        vec[idx] += sign * w
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def cosine(a: list[float], b: list[float]) -> float:
    """两个已 L2 归一化的向量的余弦相似度（即点积）。"""
    return sum(x * y for x, y in zip(a, b))


_MD_TABLE_SEP = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")


def strip_markdown(text: str) -> str:
    """把 markdown 标记去掉，只留可读文字。

    摘要直接展示给用户，留着 `**`、`| --- |`、反引号和 emoji 图片语法会显得像
    没处理过的原始文档。这些标记对"找命中窗口"没有信息量，先清再截更干净。
    """
    lines = [ln for ln in text.splitlines()
             if not (_MD_TABLE_SEP.match(ln) and "." not in ln)]
    t = "\n".join(lines)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)             # 图片整段丢掉
    t = re.sub(r"\[([^\]]{1,120})\]\(([^)\s]+)\)", r"\1", t)  # 链接只留文字
    t = re.sub(r"`{3}.*?`{3}", " ", t, flags=re.S)           # 代码块
    t = t.replace("**", "").replace("__", "")                # 粗体/斜体
    t = re.sub(r"`([^`]*)`", r"\1", t)                       # 行内代码
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)      # 标题井号
    t = re.sub(r"^\s{0,3}>\s*", "", t, flags=re.M)           # 引用块
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.M)           # 列表符号
    t = re.sub(r"^\s*([-*_])\1{2,}\s*$", "", t, flags=re.M)  # 分隔线
    t = t.replace("|", " ")                                  # 表格竖线
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip()


def _one_line(text: str) -> str:
    """摘要压成一行：结果卡片里换行会把高度撑得忽大忽小。"""
    return re.sub(r"\s+", " ", text).strip()


def snippet(text: str, query_tokens: list[str], width: int = 180) -> str:
    """找命中查询词最密的窗口做摘要；无命中时取开头。"""
    text = strip_markdown(text or "")
    if not text:
        return ""
    if not query_tokens:
        return text[:width].strip()
    n = len(text)
    if n <= width:
        return _one_line(text)
    low = text.lower()
    hits: list[int] = []
    for tok in set(query_tokens):
        start = 0
        while True:
            i = low.find(tok, start)
            if i < 0:
                break
            hits.append(i)
            start = i + 1
    if not hits:
        return _one_line(text[:width]) + "…"
    hits.sort()
    best_pos, best_count = hits[0], 0
    for i, pos in enumerate(hits):
        count = bisect_right(hits, pos + width - 1) - i
        if count > best_count:
            best_count, best_pos = count, pos
    start = max(0, min(best_pos, n - width))
    prefix = "…" if start else ""
    suffix = "…" if start + width < n else ""
    return prefix + _one_line(text[start:start + width]) + suffix


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    s1 = "OceanBase 数据库大赛赛题一要求选手在 AMD 显卡上部署 seekdb 嵌入式数据库，实现向量检索，评测指标包括 recall@10 与 QPS。"
    s2 = "seekdb 是 AI 原生嵌入式数据库，支持向量检索与全文索引，大赛要求基于 seekdb 实现召回率 recall@10 评测。"
    s3 = "今天天气很好，我们去公园散步，顺便在路边小店买了一些水果。"

    t1, t2 = tokenize(s1), tokenize(s2)
    print("== 分词自测 ==")
    print("文本1:", s1)
    print("前 20 个 token:", t1[:20])
    print()
    print("文本2:", s2)
    print("前 20 个 token:", t2[:20])
    print()
    print("== 向量自测 ==")
    idf = build_idf([t1, t2, tokenize(s3)])
    v1 = vectorize(t1, idf)
    v2 = vectorize(t2, idf)
    v3 = vectorize(tokenize(s3), idf)
    print(f"维度: {len(v1)}，文本1 向量 L2 范数: {math.sqrt(sum(x * x for x in v1)):.6f}")
    print(f"文本1 vs 文本2（相关）余弦相似度: {cosine(v1, v2):.4f}")
    print(f"文本1 vs 文本3（无关）余弦相似度: {cosine(v1, v3):.4f}")
