r"""体检脚本：打印库内表结构、索引、行数与最近查询。

用途是给「验证样例」留一份可复跑的记录：能证明向量索引和全文索引确实建在
seekdb 里，而不是在 Python 里假装检索。

用法（项目根目录）：.\.venv\Scripts\python.exe tools/inspect_db.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import connect, recent_searches, stats


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            tables = [list(r.values())[0] for r in cur.fetchall()]
            print(f"表: {tables}")

            for t in tables:
                cur.execute(f"SHOW INDEX FROM {t}")
                rows = cur.fetchall()
                print(f"\n{t} 的索引:" if rows else f"\n{t}: 无索引")
                for r in rows:
                    print(f"  - {r.get('Key_name'):<14} 列 {r.get('Column_name'):<10} "
                          f"类型 {r.get('Index_type')}")

            cur.execute("SELECT COUNT(*) AS n FROM chunks")
            vec_n = cur.fetchone()["n"]
            print(f"\nchunks 行数: {vec_n}")

    print(f"统计: {stats()}")
    recent = recent_searches(limit=5)
    if recent:
        print("最近查询:")
        for r in recent:
            print(f"  - [{r['id']}] {r['query']}（{r['result_count']} 条 / {r['elapsed_ms']}ms）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
