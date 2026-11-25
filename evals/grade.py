#!/usr/bin/env python3
"""行為 eval 的評分腳本：檢查 AI 在有、沒有 skill 時的產出。

用法：
    python3 evals/grade.py --prompts                 # 印出每個案例要給 AI 的提示
    python3 evals/grade.py evals/runs/2026-11-25     # 評分一次執行的產出

執行資料夾的結構：
    <run>/<案例 id>/<條件>.md          產出的文件本身，只放要交出去的內容
    <run>/<案例 id>/<條件>.notes.md    給使用者的說明（改了哪些詞、夾帶的指令），不評分，可省略
條件名稱自訂，例如 with_skill、without_skill，同一個條件跑兩次可以寫成 with_skill-2。

每份產出會檢查：
- must_keep 有沒有原樣保留，must_not 有沒有出現（cases.json 裡寫的）
- 用 check_zh.py 檢查中國用語、台灣不用的字形、強提示、破折號寫法、分號、半形標點、看不見的字元、
  AI 工具痕跡與逗號比例；潤稿、英翻中、信件另外和原稿比對，數出新增與遺失的數字、網址、代碼
這些都是程式檢查得到的部分。捏造、改過頭、語氣這類要靠 cases.json 的 judge 欄人工或請另一個模型評。
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "zh-tw-writing", "scripts"))
import check_zh as cz  # noqa: E402

# (check_zh 的類別, 表格欄名)。這幾類出現就算錯，列入「通過」的判斷
HARD = [("term.direct", "中國用語"), ("term.glyph", "字形"), ("ai.strong", "強提示"), ("punct.dash_form", "破折號"),
        ("punct.halfwidth", "半形標點"), ("trace.invisible", "隱形字元"), ("trace.tool", "工具痕跡")]
# 只列出數量、不列入通過判斷的類別（可能是合理的寫法，要回到文件看）
SOFT = [("punct.semicolon", "分號"), ("ai.contrast", "不是而是"), ("ai.source", "需要來源"),
        ("fact.added", "新增事實"), ("fact.missing", "遺失事實")]


def load_cases():
    with open(os.path.join(HERE, "cases.json"), encoding="utf-8") as f:
        return {c["id"]: c for c in json.load(f)}


def prompt_of(c):
    if c.get("input"):
        return f"{c['instruction']}\n\n{c['input']}"
    return c["instruction"]


def grade_one(c, text):
    res = {}
    res["keep"] = [k for k in c.get("must_keep", []) if k not in text]
    bad = []
    for pat in c.get("must_not", []):
        if pat.startswith("re:"):
            if re.search(pat[3:], text):
                bad.append(pat)
        elif pat in text:
            bad.append(pat)
    res["not"] = bad
    src = (c["input"], False) if c["kind"] in ("rewrite", "translate", "letter") and c.get("input") else None
    rep = cz.analyze(text, html_mode=False, source=src)
    res["hits"] = {k: len(rep.hits.get(k, [])) for k, _ in HARD + SOFT}
    res["ratio"] = rep.commas / rep.periods if rep.periods else None
    res["pass"] = not res["keep"] and not res["not"] and not any(res["hits"][k] for k, _ in HARD)
    return res


def main():
    ap = argparse.ArgumentParser(description="行為 eval 的評分")
    ap.add_argument("run", nargs="?", help="執行資料夾")
    ap.add_argument("--prompts", action="store_true", help="印出每個案例的提示")
    a = ap.parse_args()
    cases = load_cases()
    if a.prompts:
        for cid, c in cases.items():
            print(f"===== {cid}（{c['kind']}）{c['title']} =====\n{prompt_of(c)}\n")
        return 0
    if not a.run:
        ap.error("要給執行資料夾，或用 --prompts")

    rows, by_cond = [], collections.defaultdict(list)
    for cid in cases:
        d = os.path.join(a.run, cid)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".md") or fn.endswith(".notes.md"):
                continue
            cond = fn[:-3]
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                res = grade_one(cases[cid], f.read())
            rows.append((cid, cond, res))
            by_cond[re.sub(r"-\d+$", "", cond)].append(res)

    cols = HARD + SOFT
    print("| 案例 | 條件 | 通過 | 缺 must_keep | 出現 must_not | " + " | ".join(n for _, n in cols) + " | 逗號比例 |")
    print("|" + "---|" * (6 + len(cols)))
    for cid, cond, r in rows:
        ratio = f"{r['ratio']:.2f}" if r["ratio"] is not None else "-"
        print(f"| {cid} | {cond} | {'✓' if r['pass'] else '✗'} | {'、'.join(r['keep']) or 0} | "
              f"{'、'.join(r['not']) or 0} | " + " | ".join(str(r["hits"][k]) for k, _ in cols) + f" | {ratio} |")

    print("\n各條件合計：")
    for cond, rs in sorted(by_cond.items()):
        n = len(rs)
        parts = [f"通過 {sum(r['pass'] for r in rs)}/{n}",
                 f"缺 must_keep {sum(len(r['keep']) for r in rs)}",
                 f"出現 must_not {sum(len(r['not']) for r in rs)}"]
        parts += [f"{name} {sum(r['hits'][k] for r in rs)}" for k, name in cols]
        ratios = [r["ratio"] for r in rs if r["ratio"] is not None]
        if ratios:
            parts.append(f"逗號比例中位數 {sorted(ratios)[len(ratios) // 2]:.2f}")
        print(f"- {cond}：" + "，".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
