r"""三路召回 + RRF 融合检索：向量（HNSW）+ 全文（ngram）+ 标题，附记忆召回。

用法：.\.venv\Scripts\python.exe -m src.retriever "问题文本"
"""

import json
import re
import sys
import threading
import time
from pathlib import Path

from src.db import connect, insert_note
from src.text import snippet, tokenize, vectorize

ROOT = Path(__file__).resolve().parent.parent
IDF_PATH = ROOT / "data" / "idf.json"
SYN_PATH = ROOT / "data" / "synonyms.json"

PER_ROUTE = 40
TITLE_DOCS = 12
TITLE_CHUNKS_PER_DOC = 3
RRF_K = 60
# 标题/小节标题的实义单元覆盖率加成：score *= 1 + W * ratio**P
# 为什么是平方而不是线性：线性加成压不住 RRF 的名次差。例「AMD 题提交的仓库地址
# 必须是什么格式」里，正确小节《4.1 答题仓库地址格式》覆盖率 0.67，
# 但《比赛仓库地址》那张表在三条路上都靠前，RRF 高 1.55 倍，
# 线性加成（×1.20 vs ×1.10）翻不过来。平方后 ×2.35 vs ×1.33 才翻得过来。
# 取 3.0 的依据：在 2.5~4.0 区间 R@1 都是 96.4%（平台区），取中值避免卡在边界。
TITLE_BONUS_WEIGHT = 3.0
TITLE_BONUS_POWER = 2
# 正文实义单元覆盖率：score *= 1 + W * ratio**P
# 只靠标题不够。问「构建加速比怎么算」时，《全文索引构建性能优化》正文「构建」出现
# 11 次但「加速」「速比」「加速比」各 0 次，靠标题里的「构建」+ 向量/全文名次排到第一；
# 而《AMD》6.1 节 构建 40 次、加速比 14 次却排第三。正文覆盖率把这种"只沾一个词"的块压下去。
# 正文比标题容易命中（块长、单元多），所以权重必须比标题小一个量级，
# 否则长块占便宜：0.5~1.5 区间 28 题 R@1 都是 96.4%，取中值 1.0。
TEXT_COVER_WEIGHT = 1.0
TEXT_COVER_POWER = 2
PROPER_NOUN_MIN_IDF = 2.2
PROPER_NOUN_PENALTY = 0.4
MEMORY_LIMIT = 3
# 构造"实义单元"时剔除的功能字：哪个 n-gram 沾上这些字，哪个 n-gram 就是碎片
_QUERY_FUNC_CHARS = set("的了是么吗哪什这在有和与个每道把当来对呀呢吧就都还也怎该之其")

_CHUNK_COLS = "id, doc_slug, doc_title, heading, chunk_ix, url, text"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


_cache_lock = threading.Lock()
_idf_cache: dict | None = None
_syn_cache: dict | None = None


def _resources() -> tuple[dict, dict]:
    """IDF 和别名表进程内缓存，避免每次查询重读 1.5MB 的 idf.json。"""
    global _idf_cache, _syn_cache
    with _cache_lock:
        if _idf_cache is None:
            _idf_cache = _load_json(IDF_PATH)
            _syn_cache = {k: v for k, v in _load_json(SYN_PATH).items()
                          if not k.startswith("_")}
        return _idf_cache, _syn_cache


def expand_query(query: str, synonyms: dict) -> tuple[str, dict]:
    triggered = {}
    for k, v in synonyms.items():
        if k in query:
            triggered[k] = list(v) if isinstance(v, list) else [v]
    # 扩展词去重：① 查询里已有的写法不再追加，② 多条别名命中同一个词只加一次。
    # 不去重时"每道赛题对应哪个仓库和分支"会把「赛题」追加两次、「题目」两次
    # （「题」和「赛题」两个键都命中），而「赛题」是本语料最通用的词，
    # 重复计数等于给通用词加了三倍权重，把它顶到判别词（仓库/分支）前面。
    q_low = query.lower()
    extra, seen = [], set()
    for words in triggered.values():
        for w in words:
            lw = w.lower()
            if lw in q_low or lw in seen:
                continue
            seen.add(lw)
            extra.append(w)
    expanded = (query + " " + " ".join(extra)).strip()
    return expanded, triggered


def _vector_route(expanded: str, idf: dict) -> list[dict]:
    qv = vectorize(tokenize(expanded), idf)
    lit = "[" + ",".join(format(x, ".8f") for x in qv) + "]"
    sql = (f"SELECT {_CHUNK_COLS}, l2_distance(emb, '{lit}') AS dist "
           f"FROM chunks "
           f"ORDER BY l2_distance(emb, '{lit}') APPROXIMATE "
           f"LIMIT {PER_ROUTE}")
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


def _fulltext_route(expanded: str) -> list[dict]:
    if not expanded.strip():
        return []
    sql = (f"SELECT {_CHUNK_COLS}, MATCH(text) AGAINST(%s) AS score "
           f"FROM chunks "
           f"WHERE MATCH(text) AGAINST(%s) "
           f"ORDER BY score DESC LIMIT {PER_ROUTE}")
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (expanded, expanded))
            return cur.fetchall()


def _clean_units(query: str) -> set[str]:
    """查询的"实义单元"：ASCII 词 + 不含功能字的 CJK 二元组。

    不用全部 n-gram 当分母：2/3-gram 重叠后，一次 14 字的查询能切出 23 个 token，
    其中大半是「每道」「道赛」「题对」这类跨词边界碎片。分母被撑大后
    标题覆盖率对每个候选都接近 0，加成等于没加（这正是旧版加成几乎不起作用的原因）。
    而按 IDF 挑"最重要的词"也不行：语料里 IDF 最高的恰恰是 df=1 的碎片
    （「维护模」「忆处」「发一」IDF 都顶格 6.45），挑出来只会匹配到噪声。
    """
    units = {w.lower() for w in re.findall(r"[A-Za-z0-9_]{2,}", query)}
    for run in re.findall(r"[\u4e00-\u9fff]+", query):
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if not (set(bg) & _QUERY_FUNC_CHARS):
                units.add(bg)
    return units


def _unit_ratio(units: set[str], text: str) -> float:
    if not units or not text:
        return 0.0
    low = text.lower()
    return sum(1 for u in units if u in low) / len(units)


def _title_route(units: set[str]) -> list[dict]:
    if not units:
        return []
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT doc_slug, doc_title FROM chunks")
            docs = cur.fetchall()
    scored = []
    for d in docs:
        ratio = _unit_ratio(units, d["doc_title"])
        if ratio > 0:
            scored.append((ratio, d))
    scored.sort(key=lambda x: -x[0])
    slugs = [d["doc_slug"] for _, d in scored[:TITLE_DOCS]]
    if not slugs:
        return []
    ph = ",".join(["%s"] * len(slugs))
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_CHUNK_COLS} FROM chunks "
                        f"WHERE doc_slug IN ({ph}) ORDER BY chunk_ix ASC", slugs)
            rows = cur.fetchall()
    by_doc: dict[str, list[dict]] = {}
    for r in rows:
        by_doc.setdefault(r["doc_slug"], []).append(r)
    out = []
    for s in slugs:
        out.extend(by_doc.get(s, [])[:TITLE_CHUNKS_PER_DOC])
    return out


def _fuse(routes: dict[str, list[dict]]) -> list[dict]:
    fused: dict[int, dict] = {}
    for name, rows in routes.items():
        for rank, row in enumerate(rows):
            e = fused.setdefault(row["id"], {"row": row, "score": 0.0, "hit": []})
            e["score"] += 1.0 / (RRF_K + rank)
            e["hit"].append(name)
    return list(fused.values())


def _proper_nouns(query: str, idf: dict) -> list[str]:
    words = {w.lower() for w in re.findall(r"[A-Za-z0-9]{2,}", query)}
    return sorted(w for w in words
                  if not w.isdigit() and idf.get(w, 0.0) >= PROPER_NOUN_MIN_IDF)


def _rank(fused: list[dict], expanded_tokens: list[str], query: str,
          idf: dict, topk: int) -> list[dict]:
    # 标题加成用原查询词，不用扩展词。
    # 别名扩展出的子词（"构建"→"索引构建"→ 索引/引构/索引构）会落在无关文档的
    # 标题里，给长标题文档白送加成。实测"构建加速比怎么算"因此把
    # 《全文索引构建性能优化》顶到了《AMD / 九、性能计分》前面。
    # 职责划分：扩展词只用于召回（向量路/全文路），不用于排序判定。
    # RRF 只看排名，所以用标题加成和专有名词校验把"名次高但无关"的块压下去
    proper = _proper_nouns(query, idf)
    units = _clean_units(query)
    for e in fused:
        row = e["row"]
        # 用标题+小节标题覆盖了多少"实义单元"，而不是覆盖了多少个 n-gram：
        # 分母是实义单元数，长标题因此不能再无条件占便宜，
        # 也不会再被「每道」「题对」这类碎片把覆盖率压成 0。
        ratio = _unit_ratio(units, (row["heading"] or "") + " " + row["doc_title"])
        e["score"] *= 1.0 + TITLE_BONUS_WEIGHT * (ratio ** TITLE_BONUS_POWER)
        # 正文覆盖率：再压一次"标题沾到一个词、正文其实没讲"的块
        body = _unit_ratio(units, row["text"])
        e["score"] *= 1.0 + TEXT_COVER_WEIGHT * (body ** TEXT_COVER_POWER)
        if proper:
            hay = (row["text"] + " " + (row["heading"] or "") + " " + row["doc_title"]).lower()
            if not any(p in hay for p in proper):
                e["score"] *= PROPER_NOUN_PENALTY
    fused.sort(key=lambda e: -e["score"])

    doc_slots: dict[str, int] = {}
    results = []
    for e in fused:
        row = e["row"]
        if doc_slots.get(row["doc_slug"], 0) >= 2:
            continue
        doc_slots[row["doc_slug"]] = doc_slots.get(row["doc_slug"], 0) + 1
        results.append({
            "doc_slug": row["doc_slug"],
            "doc_title": row["doc_title"],
            "heading": row["heading"] or "",
            "url": row["url"],
            "snippet": snippet(row["text"], expanded_tokens),
            "score": round(e["score"], 6),
            "routes": {n: n in e["hit"] for n in ("vector", "fulltext", "title")},
        })
        if len(results) >= topk:
            break
    return results


def _memory_route(expanded: str) -> list[dict]:
    if not expanded.strip():
        return []
    sql = ("SELECT id, author, question, answer, tags, created_at, "
           "MATCH(search_text) AGAINST(%s) AS score "
           "FROM notes "
           "WHERE MATCH(search_text) AGAINST(%s) "
           f"ORDER BY score DESC LIMIT {MEMORY_LIMIT}")
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (expanded, expanded))
            return cur.fetchall()


def search(query: str, topk: int = 6) -> dict:
    t0 = time.time()
    idf, synonyms = _resources()
    expanded, triggered = expand_query(query, synonyms)
    expanded_tokens = tokenize(expanded)
    units = _clean_units(query)

    route_rows = {
        "vector": _vector_route(expanded, idf),
        "fulltext": _fulltext_route(expanded),
        # 标题路用原查询的实义单元：别名展开词太生僻，会抢走 top-6 IDF 名额
        "title": _title_route(units),
    }
    fused = _fuse(route_rows)
    results = _rank(fused, expanded_tokens, query, idf, topk)
    return {
        "query": query,
        "elapsed_ms": int((time.time() - t0) * 1000),
        "routes": {name: len(rows) for name, rows in route_rows.items()}
                  | {"fused": len(fused)},
        "expanded_by": triggered,
        "results": results,
        "memory": _memory_route(expanded),
    }


def remember(author: str, question: str, answer: str, tags: str = "") -> int:
    return insert_note(author, question, answer, tags)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        print('用法: python -m src.retriever "问题文本"')
        raise SystemExit(1)
    query = " ".join(sys.argv[1:])
    res = search(query)
    idf = _load_json(IDF_PATH)
    print(f"查询: {res['query']}   耗时 {res['elapsed_ms']} ms")
    print(f"routes: {res['routes']}")
    print(f"专有名词: {_proper_nouns(query, idf)}")
    if res["expanded_by"]:
        print(f"别名扩展: {list(res['expanded_by'])}")
    print(f"\n===== TOP {min(5, len(res['results']))} =====")
    for i, r in enumerate(res["results"][:5], 1):
        print(f"{i}. [{r['score']:.4f}] {r['doc_title']} > {r['heading']}")
    if res["memory"]:
        print(f"\n记忆 {len(res['memory'])} 条")
        for m in res["memory"]:
            print(f"  - {m['question']} -> {m['answer'][:60]}")
