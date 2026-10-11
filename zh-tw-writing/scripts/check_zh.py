#!/usr/bin/env python3
"""檢查繁體中文文件的句子節奏、AI 腔、台灣用語與中英混排。

用法：
    python3 check_zh.py report.html
    python3 check_zh.py notes.md --fix-spacing          # 自動補中英空格，原檔備份為 .bak
    python3 check_zh.py report.html --min 2.5 --max 4.5 # 調整逗號比例的建議範圍

只統計內文段落：HTML 取 <p> 與 <li>，Markdown／純文字略過標題、表格、程式碼區塊、
圖片與引用區塊。中文比例低於 30% 的段落（例如英文參考文獻）不列入。
套話與用語清單來自同一個技能資料夾的 references/ai-phrases.md 與 references/terms.md。
"""
import argparse
import collections
import html
import os
import re
import shutil
import statistics
import sys

CJK = r"[㐀-䶿一-鿿]"
AN = r"[A-Za-z0-9]"
FW_PUNCT = "，。、：；！？（）「」『』《》〈〉【】"
REF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references")
CODE = "§"  # 程式碼的佔位字元


# ---------- 讀取參考清單 ----------

def phrase_regex(phrase):
    parts = [re.escape(p) for p in phrase.split("…")]
    return "[^。！？\n]{0,15}?".join(parts)


def load_phrases():
    """回傳 {'強提示': [(類別, 片語, regex)], '弱提示': [...], '需要來源': [...]}"""
    out = {"強提示": [], "弱提示": [], "需要來源": []}
    path = os.path.join(REF_DIR, "ai-phrases.md")
    if not os.path.exists(path):
        return out
    section = None
    for line in open(path, encoding="utf-8"):
        if line.startswith("## "):
            title = line[3:].strip()
            section = title if title in out else None
            continue
        m = re.match(r"^- ([^：]+)：(.+)$", line.strip())
        if section and m:
            cat = m.group(1)
            for ph in m.group(2).split("、"):
                ph = ph.strip()
                if ph:
                    out[section].append((cat, ph, phrase_regex(ph)))
    return out


def load_terms():
    """回傳 (直接替換清單 [(避免, 改用, [例外])], 看語意清單 [詞])"""
    direct, context = [], []
    path = os.path.join(REF_DIR, "terms.md")
    if not os.path.exists(path):
        return direct, context
    section = None
    for line in open(path, encoding="utf-8"):
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells[0] or set(cells[0]) <= set("-") or cells[0] in ("避免", "詞", "翻譯腔"):
            continue
        if section == "直接改用台灣用語" and len(cells) >= 2:
            exc = [e.strip() for e in cells[2].split("、")] if len(cells) > 2 and cells[2] else []
            direct.append((cells[0], cells[1], exc))
        elif section == "看語意判斷":
            context.append(cells[0])
    return direct, context


# ---------- 抽取內文 ----------

def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def prose_from_html(text):
    body = text[text.index("<body"):] if "<body" in text else text
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", body, flags=re.S | re.I)
    body = re.sub(r"<(code|pre)[^>]*>.*?</\1>", CODE, body, flags=re.S | re.I)
    blocks = re.findall(r"<(p|li)[^>]*>(.*?)</\1>", body, flags=re.S | re.I)
    return [re.sub(r"\s+", " ", strip_tags(b)).strip() for _, b in blocks]


def prose_from_markdown(text):
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    out, buf = [], []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "|", "![", "<", ">")) or re.match(r"^[-*_]{3,}$", s):
            if buf:
                out.append(join_lines(buf))
                buf = []
            continue
        is_item = re.match(r"^([-*+]|\d+[.)])\s+", s)
        if is_item and buf:
            out.append(join_lines(buf))
            buf = []
        s = re.sub(r"^([-*+]|\d+[.)])\s+", "", s)
        s = re.sub(r"`[^`]*`", CODE, s)
        s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
        s = re.sub(r"[*_]{1,3}", "", s)
        buf.append(s)
    if buf:
        out.append(join_lines(buf))
    return out


def join_lines(lines):
    """Markdown 換行接回同一段：兩邊都是英數字時才補空格，中文之間直接相接。"""
    out = ""
    for ln in lines:
        if out and re.search(r"[A-Za-z0-9]$", out) and re.match(r"[A-Za-z0-9]", ln):
            out += " "
        out += ln
    return out


def is_chinese_prose(p):
    letters = re.findall(r"[A-Za-z]|" + CJK, p)
    if len(letters) < 8:
        return False
    return len(re.findall(CJK, p)) / len(letters) >= 0.3


def without_quotes(p):
    """引文（「」『』內）不做套話與用語檢查。"""
    return re.sub(r"「[^」]*」|『[^』]*』", "「」", p)


def clen(s):
    return len(re.sub(r"\s", "", s))


# ---------- 輸出工具 ----------

def ctx(text, i, j, w=16):
    return "…" + text[max(0, i - w):j + w].replace("\n", " ") + "…"


def show_hits(title, hits, limit=8):
    if not hits:
        return
    print(f"\n{title}（{len(hits)} 處）：")
    for h in hits[:limit]:
        print("   " + h)
    if len(hits) > limit:
        print(f"   …另有 {len(hits) - limit} 處")


# ---------- 檢查 ----------

def check(paragraphs, lo, hi, html_mode=False):
    paras = [p for p in paragraphs if is_chinese_prose(p)]
    text = "\n".join(paras)
    print(f"內文段落：{len(paras)} 段")
    if not paras:
        if html_mode and not paragraphs:
            print("找不到 <p> 或 <li>。HTML 只統計這兩種標籤裡的文字，內文如果寫在 <div> 或其他標籤裡，"
                  "請改用 <p>，或把內文另存成 .md／.txt 再檢查。")
        else:
            print("找不到中文內文段落（中文比例低於 30% 的段落、標題、表格與程式碼不列入統計）。")
        return

    # 1. 句子節奏
    print("\n【句子節奏】")
    periods, commas = text.count("。"), text.count("，")
    sents = [s.strip() for p in paras for s in re.split(r"(?<=[。！？])", p) if re.search(CJK, s)]
    if periods:
        ratio = commas / periods
        verdict = ("在建議範圍內" if lo <= ratio <= hi else
                   "偏低：句子可能太碎，可考慮合併同主題短句" if ratio < lo else
                   "偏高：句子可能太長，可考慮拆開並列句")
        print(f"句號 {periods}、逗號 {commas}，平均每句逗號 {ratio:.2f}（建議 {lo:g}–{hi:g}）→ {verdict}")
        print("每句逗號數分布（7 代表 7 個以上）：",
              dict(sorted(collections.Counter(min(s.count("，"), 7) for s in sents).items())))
    lens = [clen(s) for s in sents]
    if len(lens) >= 8:
        m, sd = statistics.mean(lens), statistics.pstdev(lens)
        cv = sd / m if m else 0
        note = "句長太平均，讀起來容易像 AI，長短句可以交錯" if cv < 0.3 else "長短有變化"
        print(f"句長：平均 {m:.0f} 字，標準差 {sd:.0f}，變異係數 {cv:.2f}（一般文章約 0.5–0.7）→ {note}")

    runs, run = [], []
    for s in sents:
        if s.count("，") == 0 and clen(s) < 60:
            run.append(s)
        else:
            if len(run) >= 3:
                runs.append(run)
            run = []
    if len(run) >= 3:
        runs.append(run)
    show_hits("連續 3 句以上無逗號的短句", [" / ".join(x[:22] for x in r) for r in runs])
    show_hits("較長的句子（超過 6 個逗號或 150 字，可考慮拆開，但長度本身不一定是問題）",
              [f"{clen(s)} 字、{s.count('，')} 逗號：{s[:46]}…" for s in sents
               if s.count("，") > 6 or clen(s) > 150])

    # 2. AI 腔
    phrases = load_phrases()
    print("\n【AI 腔】")
    if not any(phrases.values()):
        print("（找不到 references/ai-phrases.md，略過套話檢查）")
    for label, title in (("強提示", "強提示（出現一次就該改）"),
                         ("需要來源", "需要來源（有出處就補上，沒有就改寫或刪除，不要編造來源）")):
        hits = []
        for p in paras:
            q = without_quotes(p)
            for cat, ph, rx in phrases[label]:
                for mt in re.finditer(rx, q):
                    hits.append(f"{cat}「{ph}」：{ctx(q, mt.start(), mt.end())}")
        show_hits(title, hits)
    dense = []
    for p in paras:
        q = without_quotes(p)
        found = [ph for _, ph, rx in phrases["弱提示"] for _ in re.finditer(rx, q)]
        if len(found) >= (2 if clen(q) < 100 else 3):
            dense.append(f"{len(found)} 個（{'、'.join(found)}）：{q[:36]}…")
    show_hits("弱提示密集的段落（單獨出現沒問題，同一段太多才像 AI）", dense)
    unq = without_quotes(text)
    contrast = [ctx(unq, m.start(), m.end()) for m in re.finditer(r"不是[^。！？\n]{0,30}?而是", unq)]
    if len(contrast) > 1:
        show_hits("「不是…而是…」用了不只一次", contrast)

    # 3. 標點
    print("\n【標點】")
    show_hits("分號（並列的條列項目可以用，其他多半改成逗號或句號）",
              [ctx(text, m.start(), m.end()) for m in re.finditer("；", text)])
    show_hits("一段裡有不只一組破折號", [f"{p.count('——')} 組：{p[:36]}…" for p in paras if p.count("——") > 1])
    show_hits("破折號寫法不對（應寫成兩格的——）",
              [ctx(text, m.start(), m.end()) for m in re.finditer(f"(?<={CJK})(?:—(?!—)|--)(?={CJK})", text)])
    show_hits("中文裡用了半形標點",
              [ctx(text, m.start(), m.end())
               for m in re.finditer(f"{CJK}[,;?!()]|[,;?!()]{CJK}|{CJK}:|(?<![0-9]):{CJK}", text)])
    show_hits("用了“ ”或\" \"引號（台灣用「」）",
              [ctx(text, m.start(), m.end()) for m in re.finditer(r"[“”]|\"(?=[^\"\n]*" + CJK + ")", text)])
    show_hits("中英文或數字沒有空格（% 與 ° 後面接中文也要空格）",
              [ctx(text, m.start(), m.end()) for m in re.finditer(f"{CJK}{AN}|{AN}{CJK}|[%°]{CJK}", text)])
    show_hits("全形標點旁多了空格", [ctx(text, m.start(), m.end()) for m in re.finditer(f" [{FW_PUNCT}]|[{FW_PUNCT}] ", text)])

    # 4. 用語
    print("\n【台灣用語】")
    direct, context = load_terms()
    term_hits = []
    for avoid, use, exc in direct:
        for p in paras:
            q = without_quotes(p)
            for mt in re.finditer(re.escape(avoid), q):
                window = q[max(0, mt.start() - 6):mt.end() + 6]
                if any(e and e in window for e in exc):
                    continue
                term_hits.append(f"「{avoid}」→「{use}」：{ctx(q, mt.start(), mt.end(), 12)}")
    show_hits("中國用語，建議改成台灣用語", term_hits)
    counts = {w: unq.count(w) for w in context if unq.count(w)}
    if counts:
        print("\n需要看語意確認的詞（對照 references/terms.md「看語意判斷」）：",
              "、".join(f"{w} {c} 次" for w, c in counts.items()))
    # 「國立臺灣…」「臺北市立…」這類機構全名依官方寫法，不算混用
    plain = re.sub(r"[國市縣私]立[臺台][灣北中南東][^，。、\s]{0,8}?(大學|學院|醫院|博物館|圖書館|美術館)", "", text)
    if re.search("台灣|台北|台中|台南", plain) and re.search("臺灣|臺北|臺中|臺南", plain):
        print("\n「台」與「臺」混用，請擇一並全文統一。")


# ---------- 自動補空格 ----------

PROTECT = "script|style|pre|code|kbd|samp|textarea"


def add_spacing(seg, html_mode):
    if html_mode:
        opn = r"(?:<(?:code|kbd|b|i|em|strong|span|a)(?:\s[^>]*)?>)*"
        cls = r"(?:</(?:code|kbd|b|i|em|strong|span|a)>)*"
    else:
        opn = cls = ""
    # 空格放在行內標籤外側：結束標籤之後、開始標籤之前
    seg = re.sub(f"({CJK})({cls})({opn})({AN})", r"\1\2 \3\4", seg)
    seg = re.sub(f"({AN}|[%°])({cls})({opn})({CJK})", r"\1\2 \3\4", seg)
    return seg


def add_spacing_html(seg):
    """HTML 版：程式碼區塊的內容與標籤屬性先收起來，補完空格再放回去。"""
    store = []

    def keep(s, kind):
        store.append(s)
        return f"{kind[0]}{len(store) - 1}{kind[1]}"

    INNER, COMMENT, ATTR = "", "", ""

    def rep(c):
        # 留一個代表字元，讓 <code> 外側仍能判斷要不要補空格
        return "a" if re.match(AN, c) else "中" if re.match(CJK, c) else ""

    def hide_inner(m):
        inner = m.group(3)
        if not inner:
            return m.group(0)
        return m.group(1) + rep(inner[0]) + keep(inner, INNER) + rep(inner[-1]) + m.group(4)

    seg = re.sub(f"(<({PROTECT})\\b[^>]*>)(.*?)(</\\2\\s*>)", hide_inner, seg, flags=re.S | re.I)
    seg = re.sub(r"<!--.*?-->", lambda m: keep(m.group(0), COMMENT), seg, flags=re.S)
    seg = re.sub(r"(<[A-Za-z][\w-]*)(\s[^>]*)>", lambda m: m.group(1) + " " + keep(m.group(2), ATTR) + ">", seg)
    seg = add_spacing(seg, True)
    back = lambda m: store[int(m.group(1))]
    seg = re.sub(" (\\d+)", back, seg)
    seg = re.sub("(\\d+)", back, seg)
    seg = re.sub("(?<=>)[a中]?(\\d+)[a中]?(?=<)", back, seg)
    return seg


def fix_spacing(path, text, html_mode):
    if html_mode and "<body" in text:
        b0 = text.index("<body")
        b1 = text.index("</body>") if "</body>" in text else len(text)
        new = text[:b0] + add_spacing_html(text[b0:b1]) + text[b1:]
    elif html_mode:
        new = add_spacing_html(text)
    else:
        parts = re.split(r"(```.*?```|`[^`\n]*`|https?://\S+)", text, flags=re.S)
        new = "".join(p if i % 2 else add_spacing(p, False) for i, p in enumerate(parts))
        new = re.sub(f"({CJK})(`[^`\\n]+`)", r"\1 \2", new)
        new = re.sub(f"(`[^`\\n]+`)({CJK})", r"\1 \2", new)
    if new != text:
        shutil.copyfile(path, path + ".bak")
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
        print(f"已補上中英空格，原檔備份為 {path}.bak")
    else:
        print("沒有需要補的空格。")
    return new


def main():
    ap = argparse.ArgumentParser(description="檢查繁體中文文件的句子節奏、AI 腔、台灣用語與中英混排")
    ap.add_argument("path")
    ap.add_argument("--fix-spacing", action="store_true", help="自動補中英文、中文與數字之間的空格")
    ap.add_argument("--min", type=float, default=2.8, help="每句逗號數建議下限（預設 2.8）")
    ap.add_argument("--max", type=float, default=4.0, help="每句逗號數建議上限（預設 4）")
    a = ap.parse_args()

    with open(a.path, encoding="utf-8") as f:
        text = f.read()
    html_mode = a.path.lower().endswith((".html", ".htm"))
    if a.fix_spacing:
        text = fix_spacing(a.path, text, html_mode)
        print()
    paras = prose_from_html(text) if html_mode else prose_from_markdown(text)
    check(paras, a.min, a.max, html_mode)


if __name__ == "__main__":
    sys.exit(main())
