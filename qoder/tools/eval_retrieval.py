r"""检索回归评测：Recall@1/@3/@5、平均耗时、未命中题目的实际名次。

用法：.\.venv\Scripts\python.exe tools/eval_retrieval.py [--k 5]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.retriever import search

QUESTIONS_PATH = ROOT / "data" / "eval_questions.json"
DEPTH = 30  # 名次分析用：比 --k 更深的召回深度


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="检索回归评测")
    parser.add_argument("--k", type=int, default=5, help="命中判定的名次上限")
    args = parser.parse_args()

    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    n = len(questions)
    hit = {1: 0, 3: 0, 5: 0}
    times: list[int] = []
    missed: list[dict] = []
    for item in questions:
        q, expect = item["q"], item["expect"]
        res = search(q, topk=max(args.k, DEPTH))
        times.append(res["elapsed_ms"])
        slugs = [r["doc_slug"] for r in res["results"]]
        rank = next((i for i, s in enumerate(slugs, 1) if s in expect), None)
        if rank is not None:
            for k in (1, 3, 5):
                if rank <= k:
                    hit[k] += 1
        else:
            missed.append({"q": q, "expect": expect})
        print(f"[{rank if rank is not None else '-'}] {q}")

    print(f"\n===== {n} 题，判定 k={args.k} =====")
    for k in (1, 3, 5):
        print(f"Recall@{k}: {hit[k] / n * 100:.1f}% ({hit[k]}/{n})")
    times.sort()
    median = (times[n // 2] if n % 2 else (times[n // 2 - 1] + times[n // 2]) / 2)
    print(f"检索耗时: 中位 {median:.0f} ms，平均 {sum(times) / n:.0f} ms"
          f"（topk={max(args.k, DEPTH)}，含约 40 条结果的序列化）")
    if missed:
        print(f"未进入前 {DEPTH} 名的题目:")
        for m in missed:
            print(f"  - {m['q']}（期望 {m['expect']}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
