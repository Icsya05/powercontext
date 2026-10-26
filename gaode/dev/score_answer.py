#!/usr/bin/env python3
"""离线回答校验器：对照 fixtures.json 检查 Agent 回答是否违反硬性规则。

只做可机器判定的检查，不评价文案好坏：
  1. required_patterns —— 每组给出若干等价写法，至少命中一个；
  2. forbidden_patterns —— 出现即违规（错误数值、无依据断言等）；
  3. no_question —— 本题为单轮任务，不许反问或索要信息；
  4. no_recommendation_of —— 超时/未核实的地点不得出现在推荐行里
     （在说明文字里写“已排除”是允许的，这属于如实交代）。

推荐行识别：markdown 表格行，或带距离数字的列表条目，且不含排除类字样。

用法：
  python score_answer.py answers/            # 目录下按 <场景id>.md 命名
  python score_answer.py answers/E.md E
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures.json"

QUESTION_MARKERS = [
    "请问", "请提供", "能否告知", "可以告诉我", "方便告诉我",
    "需要你提供", "请确认", "是否需要我", "要不要我",
]

# 出现这些字样说明该行是在交代“排除”，不是推荐
EXCLUSION_MARKERS = [
    "未纳入推荐", "未列入", "超出", "不符合", "排除", "未核实",
    "查询失败", "无法核实", "未作为推荐", "不推荐", "超时",
]

DIST_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:米|m\b|公里|km)")


def load_scenarios() -> dict[str, dict]:
    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    return {s["id"]: s for s in data["scenarios"]}


def recommendation_lines(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if any(m in line for m in EXCLUSION_MARKERS):
            continue
        if line.count("|") >= 2:
            out.append(line)
        elif re.match(r"^(?:[-*+]|\d+[.、)])\s+", line) and DIST_RE.search(line):
            out.append(line)
    return out


def score(scenario: dict, answer: str) -> tuple[bool, list[str]]:
    exp = scenario["expect"]
    fails: list[str] = []

    for group in exp.get("required_patterns", []):
        if not any(re.search(pat, answer) for pat in group):
            fails.append(f"缺少应有内容：{' / '.join(group)}")

    for pat in exp.get("forbidden_patterns", []):
        if re.search(pat, answer):
            fails.append(f"出现不该出现的内容：/{pat}/")

    if exp.get("no_question") and any(m in answer for m in QUESTION_MARKERS):
        hit = next(m for m in QUESTION_MARKERS if m in answer)
        fails.append(f"出现反问/索要信息：{hit!r}，单轮任务应自行用工具补齐或说明无法核实")

    rec_lines = recommendation_lines(answer)
    for poi in exp.get("no_recommendation_of", []):
        for line in rec_lines:
            if poi in line:
                fails.append(f"把不该推荐的地点 {poi} 列进了推荐行：{line[:60]}…")
                break

    return (not fails), fails


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    target = Path(args[0])
    scen = load_scenarios()

    if target.is_dir():
        pairs = [(scen[p.stem], p) for p in sorted(target.glob("*.md")) if p.stem in scen]
    else:
        sid = args[1] if len(args) > 1 else target.stem
        pairs = [(scen[sid], target)]

    if not pairs:
        print("没有找到可校验的回答文件（按 <场景id>.md 命名）")
        return 2

    ok_count = 0
    for scenario, path in pairs:
        answer = path.read_text(encoding="utf-8")
        ok, fails = score(scenario, answer)
        ok_count += ok
        print(f"[{scenario['id']}] {scenario['title']}  ->  {'PASS' if ok else 'FAIL'}")
        for f in fails:
            print(f"    · {f}")
        if not ok:
            print(f"    （依据：{scenario['expect']['note']}）")
    print(f"\n合计：{ok_count}/{len(pairs)} 通过")
    return 0 if ok_count == len(pairs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
