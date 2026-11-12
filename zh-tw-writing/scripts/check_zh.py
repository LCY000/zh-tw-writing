#!/usr/bin/env python3
"""檢查繁體中文文件的句子節奏、AI 腔、台灣用語與中英混排。

用法：
    python3 check_zh.py report.html
    python3 check_zh.py notes.md --fix-spacing          # 自動補中英空格，原檔備份為 .bak
    python3 check_zh.py report.html --min 2.5 --max 4.5 # 調整逗號比例的建議範圍

檢查範圍分兩種：
- 句子節奏只看內文段落（HTML 的 <p>、<li>、<div> 等區塊，Markdown 的一般段落與清單），
  表格、標題、圖說本來就短，不列入。中文比例低於 30% 的段落（例如英文參考文獻）也不列入。
- AI 腔、標點與台灣用語看所有可見文字，包括表格、標題與圖說。
兩種都略過程式碼、YAML frontmatter、HTML 的 <nav> 與 class 或 id 含 toc、mono 的元素，
Markdown 另外略過引用區塊、圖片與夾在內文裡的 HTML。
套話與用語清單來自同一個技能資料夾的 references/ai-phrases.md 與 references/terms.md。
"""
import argparse
import collections
import html
import html.parser
import os
import re
import shutil
import statistics
import sys

CJK = r"[㐀-䶿一-鿿]"
AN = r"[A-Za-z0-9]"
FW_PUNCT = "，。、：；！？（）「」『』《》〈〉【】"
CJKP = f"[㐀-䶿一-鿿{FW_PUNCT}]"  # 中文字或全形標點
REF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references")
CODE = "§"  # 程式碼的佔位字元

# 數字後面直接接這些單位時，提醒加空格。% 與 ° 依規範緊貼數字，不列入。
UNITS = (r"[kMGT]Wh|Wh|[kMGT]W|W|kV|VDC|VAC|V|mA|[kMG]Hz|Hz|[kKMGT]bps|bps|[KMGTP]iB|[KMGTP]B"
         r"|ms|μs|ns|mm|cm|km|kg|nm|dBm|dB|rpm|fps")
NUM = r"\d+(?:\.\d+)?"

# 一個段落、表格儲存格或標題。kind：prose（內文）、table、caption（圖說）、heading
# lines 是每個字元所在的原始行號，用來讓提醒指到命中的那一行；沒有時用 line（段落開頭）
Seg = collections.namedtuple("Seg", "text kind section line lines")

# YAML frontmatter：開頭的 --- 下一行必須是「欄位:」，避免把開頭的分隔線當成 frontmatter
FRONTMATTER = "(?:" + chr(0xFEFF) + ")?---[ \\t]*\\n(?=[ \\t]*[\\w-]+[ \\t]*:).*?\\n(?:---|\\.\\.\\.)[ \\t]*(?=\\n|\\Z)"
# 遮住引文或標題內容時用的填充字元，維持字串長度，位置才對得回原文
FILL = chr(0xE010)


# ---------- 讀取參考清單 ----------

def gap(n):
    """片語中間可以夾的字數。被遮住的引文（一串填充字元）只算一個字，和 v1.1.1 把引文縮成「」一致。"""
    return f"(?:{FILL}+|[^。！？\n{FILL}]){{0,{n}}}?"


def phrase_regex(phrase):
    parts = [re.escape(p) for p in phrase.split("…")]
    return gap(15).join(parts)


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
    """回傳 (直接替換 [(避免, 改用, [例外])], 看語意 [詞], 比對時略過的詞 [詞])"""
    direct, context, keep = [], [], []
    path = os.path.join(REF_DIR, "terms.md")
    if not os.path.exists(path):
        return direct, context, keep
    section = None
    for line in open(path, encoding="utf-8"):
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if section == "比對時略過的詞" and line.startswith("- "):
            keep += [w.strip() for w in line[2:].split("、") if w.strip()]
            continue
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells[0] or set(cells[0]) <= set("-:") or cells[0] in ("避免", "詞", "翻譯腔"):
            continue
        if section == "直接改用台灣用語" and len(cells) >= 2:
            exc = [e.strip() for e in cells[2].split("、") if e.strip()] if len(cells) > 2 else []
            direct.append((cells[0], cells[1], exc))
        elif section == "看語意判斷":
            context.append(cells[0])
    return direct, context, keep


# ---------- 抽取文字 ----------

def blank_frontmatter(text):
    """把開頭的 YAML frontmatter 換成同樣行數的空行，行號才不會跑掉。"""
    m = re.match(FRONTMATTER, text, flags=re.S)
    if not m:
        return text
    return "\n" * m.group().count("\n") + text[m.end():]


MARKER = re.compile(r"(?:[-*+]|\d{1,9}[.)])(?= |$)")
FENCE_OPEN = re.compile(r"(`{3,})(?!.*`)|(~{3,})")


def code_lines(lines):
    """回傳 Markdown 程式碼所在的行（從 0 起算），規則依 CommonMark 簡化：
    - ``` 或 ~~~ 圍住的區塊，可以接在清單符號後面。結尾要同一種符號、至少一樣長、縮排不超過三格；
      沒關閉時，到所在清單項目結束為止，不在清單裡就到檔尾。``` 後面的資訊字串不能有反引號。
    - 空行後、比所在位置的內文多縮排四格以上的行（頂層是四格，清單項目裡是項目內文的縮排再加四格），
      清單符號後面直接空五格以上也是。縮排程式碼裡的 ``` 只是程式碼，不是區塊開頭。"""
    code = set()
    fence = None             # (符號, 長度, 所在容器的縮排)
    stack = []               # 每一層清單項目內文的縮排
    prev_blank, in_indented = True, False
    for k, raw in enumerate(lines):
        line = raw.expandtabs(4)
        blank = not line.strip()
        ind = len(line) - len(line.lstrip())
        if fence:
            ch, n, box = fence
            if blank or ind >= box:
                code.add(k)
                m = re.match(r"^ *(`{3,}|~{3,}) *$", line)
                if m and ind - box <= 3 and m.group(1)[0] == ch and len(m.group(1)) >= n:
                    fence = None
                continue
            fence = None     # 縮排比容器少，清單項目結束，區塊跟著結束，這一行照一般規則處理
        if blank:
            prev_blank = True
            continue
        # 空行後縮排變少，退出比較深的清單層級；沒有空行的是懶惰續行，層級不變
        if prev_blank:
            while stack and ind < stack[-1]:
                stack.pop()
        base = stack[-1] if stack else 0
        if ind >= base + 4 and (in_indented or prev_blank):
            code.add(k)
            in_indented, prev_blank = True, False
            continue
        in_indented = False
        # 清單符號，同一行可以有好幾層，例如「- - 內容」
        pos = ind
        while True:
            m = MARKER.match(line, pos)
            if not m:
                break
            while stack and stack[-1] > pos:
                stack.pop()
            rest = line[m.end():]
            gap = len(rest) - len(rest.lstrip(" "))
            if not rest.strip():
                stack.append(m.end() + 1)
                pos = len(line)
                break
            if gap >= 5:     # 清單符號後空五格以上：內文從符號後一格開始，其餘是縮排程式碼
                stack.append(m.end() + 1)
                code.add(k)
                pos = None
                break
            pos = m.end() + gap
            stack.append(pos)
        if pos is None:
            prev_blank = False
            continue
        box = stack[-1] if stack and pos > ind else base
        f = FENCE_OPEN.match(line, pos)
        if f and pos - box <= 3:
            mark = f.group(1) or f.group(2)
            fence = (mark[0], len(mark), box)
            code.add(k)
        prev_blank = False
    return code


def blank_code_fences(text):
    """把程式碼區塊換成同樣行數的空行，行號才不會跑掉。"""
    lines = text.split("\n")
    code = code_lines(lines)
    return "\n".join("" if k in code else ln for k, ln in enumerate(lines))


def clean_inline(s):
    """Markdown 行內語法換成純文字。"""
    s = re.sub(r"`[^`]*`", CODE, s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    # 「**粗體句。** 內文」「文字 **「引號」**」這種空格是 CommonMark 讓粗體成立所必需的，不算多餘空格
    s = re.sub(f"([{FW_PUNCT}])(\\*{{1,3}}|_{{1,3}})[ \\t]+", r"\1\2", s)
    s = re.sub(f"[ \\t]+(\\*{{1,3}}|_{{1,3}})([{FW_PUNCT}])", r"\1\2", s)
    s = re.sub(r"[*_]{1,3}", "", s)
    return s.strip()


def join_lines(lines):
    """Markdown 換行接回同一段：兩邊都是英數字時才補空格，中文之間直接相接。
    lines 是 [(文字, 行號)]，回傳 (段落文字, 每個字元的行號)。"""
    out, where = "", []
    for ln, no in lines:
        if out and re.search(r"[A-Za-z0-9]$", out) and re.match(r"[A-Za-z0-9]", ln):
            out += " "
            where.append(no)
        out += ln
        where += [no] * len(ln)
    return out, tuple(where)


def segs_from_markdown(text):
    text = blank_frontmatter(text)
    text = blank_code_fences(text)
    segs, buf, section = [], [], ""

    def flush():
        nonlocal buf
        if buf:
            t, where = join_lines(buf)
            segs.append(Seg(t, "prose", section, buf[0][1], where))
            buf = []

    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        h = re.match(r"^(#{1,6})\s+(.*?)\s*#*$", s)
        if h:
            flush()
            title = clean_inline(h.group(2))
            if len(h.group(1)) <= 3:
                section = title
            segs.append(Seg(title, "heading", section, i, None))
            continue
        if s.startswith("|"):
            flush()
            if not re.fullmatch(r"[|:\-\s]+", s):
                for cell in s.strip("|").split("|"):
                    cell = clean_inline(cell)
                    if cell:
                        segs.append(Seg(cell, "table", section, i, None))
            continue
        if not s or s.startswith(("![", "<", ">")) or re.match(r"^([-*_]\s*){3,}$", s):
            flush()
            continue
        if re.match(r"^([-*+]|\d+[.)])\s+", s):
            flush()
            s = re.sub(r"^([-*+]|\d+[.)])\s+", "", s)
        buf.append((clean_inline(s), i))
    flush()
    return segs


BLOCK = {"p", "li", "td", "th", "dd", "dt", "figcaption", "caption", "blockquote", "div", "section",
         "article", "header", "footer", "aside", "main", "figure", "table", "tr", "thead", "tbody",
         "tfoot", "ul", "ol", "dl", "form", "fieldset", "details", "summary", "body", "html", "hr",
         "h1", "h2", "h3", "h4", "h5", "h6"}
SKIP = {"script", "style", "head", "template", "noscript", "svg", "nav"}
INVISIBLE = {"script", "style", "head", "template", "svg"}
CODE_TAGS = {"pre", "code", "kbd", "samp", "textarea"}
TEXT_BLOCKS = {"p", "li", "td", "th", "dd", "dt", "figcaption", "caption", "blockquote",
               "h1", "h2", "h3", "h4", "h5", "h6"}
IMPLIED = {  # 開始標籤：(會被它關掉的元素, 往上找到這些就停)
    "li": ({"li"}, {"ul", "ol"}),
    "td": ({"td", "th"}, {"tr", "table"}),
    "th": ({"td", "th"}, {"tr", "table"}),
    "tr": ({"tr"}, {"table", "thead", "tbody", "tfoot"}),
    "dt": ({"dt", "dd"}, {"dl"}),
    "dd": ({"dt", "dd"}, {"dl"}),
}
VOID = {"br", "hr", "img", "input", "meta", "link", "wbr", "area", "base", "col", "embed", "source", "track"}
ASCII_WS = " \t\r\n\f"


def normalize(chars):
    """[(字元, 行號)] → (文字, 每個字元的行號)。中文之間的原始碼換行直接接起來，
    其他連續的半形空白與換行合成一個空格。全形空格與 &nbsp; 保留，和 Markdown 一致。"""
    raw = "".join(c for c, _ in chars)
    drop = set()
    for m in re.finditer(f"(?<={CJKP})[ \\t\\r]*\\n[{ASCII_WS}]*(?={CJKP})", raw):
        drop.update(range(m.start(), m.end()))
    out, where = [], []
    for k, (c, no) in enumerate(chars):
        if k in drop:
            continue
        if c in ASCII_WS:
            if out and out[-1] == " ":
                continue
            c = " "
        out.append(c)
        where.append(no)
    while out and out[0] == " ":
        out.pop(0)
        where.pop(0)
    while out and out[-1] == " ":
        out.pop()
        where.pop()
    return "".join(out), tuple(where)


class _Extractor(html.parser.HTMLParser):
    """把 HTML 的可見文字切成段落，同時記下種類、所屬章節與每個字元的行號。"""

    def __init__(self):
        # 實體自己處理，&#10; 這種換行實體才不會被當成原始碼換行而讓行號多算
        super().__init__(convert_charrefs=False)
        self.labels = []       # 「**粗體標籤：**說明」格式的 <li>：[(行號, 提醒)]
        self.li_probe = None   # 正在檢查的 <li>：{"line", "state", "label"}
        self.stack = []        # [[tag, 是否略過, 這個元素是否直接含有文字]]
        self.buf = []          # [(字元, 行號)]
        self.buf_kind, self.buf_heading_level = "prose", 9
        self.last_end = None
        self.section = ""
        self.segs = []
        self.total = 0         # 可見文字總字數（含程式碼、目錄）
        self.skipped = 0       # 被略過的字數
        self.skipped_code = 0  # 其中屬於程式碼的字數

    def _skipping(self):
        return any(e[1] for e in self.stack)

    def _kind(self):
        for e in reversed(self.stack):
            t = e[0]
            if t in ("td", "th"):
                return "table"
            if t in ("figcaption", "caption"):
                return "caption"
            if re.fullmatch(r"h[1-6]", t):
                return "heading"
        return "prose"

    def _container(self):
        for e in reversed(self.stack):
            if e[0] in BLOCK:
                return e
        return None

    def _add(self, text, line, count_lines=True):
        if not any(c not in ASCII_WS for c, _ in self.buf) and text.strip(ASCII_WS):
            self.buf_kind = self._kind()
            levels = [int(e[0][1]) for e in self.stack if re.fullmatch(r"h[1-6]", e[0])]
            self.buf_heading_level = levels[-1] if levels else 9
        for c in text:
            self.buf.append((c, line))
            if c == "\n" and count_lines:
                line += 1

    def _flush(self):
        t, where = normalize(self.buf)
        self.buf = []
        if t and t != CODE:
            if self.buf_kind == "heading" and self.buf_heading_level <= 3:
                self.section = t
            self.segs.append(Seg(t, self.buf_kind, self.section, where[0], where))

    def _implied_end(self, tag):
        """HTML 允許省略 </li>、</td>、</p> 等結束標籤，新的同類元素開始時，先關掉前一個。"""
        rule = IMPLIED.get(tag)
        if rule:
            closes, stops = rule
            for i in range(len(self.stack) - 1, -1, -1):
                t = self.stack[i][0]
                if t in stops:
                    return
                if t in closes:
                    del self.stack[i:]
                    return
        if tag in BLOCK:
            # 區塊元素開始時，前面沒關的 <p> 也結束
            for i in range(len(self.stack) - 1, -1, -1):
                t = self.stack[i][0]
                if t == "p":
                    del self.stack[i:]
                    return
                if t in BLOCK:
                    return

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        mark = f"{a.get('class') or ''} {a.get('id') or ''}".lower()
        # </span><span> 緊貼、而且外層容器只放 span、沒有直接的文字時，多半是用 CSS 排成兩欄的標籤與內容
        # （例如「我的問題」｜「dnstwist 是什麼」），分成兩段。<p>、<li>、<td> 裡，或容器有直接文字時，照常接成同一句。
        box = self._container()
        split_span = (tag == "span" and self.last_end == "span" and box is not None
                      and box[0] not in TEXT_BLOCKS and not box[2])
        if tag in BLOCK or split_span:
            self._flush()
        self.last_end = None
        self._implied_end(tag)
        if tag == "br":
            self._add("\n", self.getpos()[0])
        if tag in VOID:
            return
        if tag in CODE_TAGS and not self._skipping():
            self._add(CODE, self.getpos()[0])
        if not self._skipping():
            if tag == "li":
                self.li_probe = {"line": self.getpos()[0], "state": "start", "label": ""}
            elif tag in ("strong", "b") and self.li_probe and self.li_probe["state"] == "start":
                self.li_probe["state"] = "in_bold"
            elif tag not in ("p", "span") and self.li_probe and self.li_probe["state"] == "start":
                self.li_probe["state"] = "done"
        skip = tag in SKIP or tag in CODE_TAGS or bool(re.search(r"\b(toc|mono)\b", mark))
        self.stack.append([tag, skip, False])

    def handle_endtag(self, tag):
        self.last_end = tag
        if tag in ("li", "ul", "ol"):
            self.li_probe = None
        pr = self.li_probe
        if pr and tag in ("strong", "b") and pr["state"] == "in_bold":
            if pr["label"].strip().endswith(("：", ":")):
                self._label(pr)
                pr["state"] = "done"
            else:
                pr["state"] = "after_bold"
        if tag in VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                if tag in BLOCK:
                    self._flush()
                del self.stack[i:]
                break

    def handle_entityref(self, name):
        self._text(html.unescape(f"&{name};"), count_lines=False)

    def handle_charref(self, name):
        self._text(html.unescape(f"&#{name};"), count_lines=False)

    def handle_data(self, data):
        self._text(data)

    def _probe(self, data):
        """<li> 開頭是粗體、粗體以冒號結尾或後面緊接冒號時，記成粗體標籤。"""
        pr = self.li_probe
        if not pr or not data.strip():
            if pr and pr["state"] == "in_bold":
                pr["label"] += data
            return
        if pr["state"] == "in_bold":
            pr["label"] += data
        elif pr["state"] == "after_bold":
            if data.lstrip().startswith(("：", ":")):
                self._label(pr)
            pr["state"] = "done"
        elif pr["state"] == "start":
            pr["state"] = "done"

    def _label(self, pr):
        label = re.sub(r"\s+", " ", pr["label"]).strip()
        self.labels.append((pr["line"], f"第 {pr['line']} 行：{label}"))

    def _text(self, data, count_lines=True):
        n = len(re.sub(r"\s", "", data))
        if n:
            self.last_end = None
        if any(e[0] in INVISIBLE for e in self.stack):
            return
        self.total += n
        if self._skipping():
            self.skipped += n
            if any(e[0] in CODE_TAGS for e in self.stack):
                self.skipped_code += n
            return
        if n and self.stack and self.stack[-1][0] in BLOCK:
            self.stack[-1][2] = True
        self._probe(data)
        self._add(data, self.getpos()[0], count_lines)

    def close(self):
        super().close()
        self._flush()


def segs_from_html(text):
    p = _Extractor()
    p.feed(text)
    p.close()
    return p.segs, p.total, (p.skipped, p.skipped_code), p.labels


# ---------- 文字工具 ----------

def ratio_cjk(p):
    letters = re.findall(r"[A-Za-z]|" + CJK, p)
    return (len(re.findall(CJK, p)) / len(letters)) if letters else 0, len(letters)


def is_chinese_prose(p):
    r, n = ratio_cjk(p)
    return n >= 8 and r >= 0.3


def has_chinese(p):
    r, n = ratio_cjk(p)
    return bool(re.search(CJK, p)) and (n < 8 or r >= 0.3)


def _fill(m):
    return m.group()[0] + FILL * (len(m.group()) - 2) + m.group()[-1]


def no_titles(p):
    """書名、篇名（《》〈〉內）換成填充字元，長度不變。"""
    return re.sub(r"《[^》]*》|〈[^〉]*〉", _fill, p)


def without_quotes(p):
    """引文（「」『』內，可以巢狀）與標題（《》〈〉內）換成填充字元，不做套話與用語檢查，長度不變。"""
    p = list(no_titles(p))
    depth, start = 0, 0
    for k, c in enumerate(p):
        if c in "「『":
            if depth == 0:
                start = k
            depth += 1
        elif c in "」』" and depth:
            depth -= 1
            if depth == 0:
                p[start + 1:k] = FILL * (k - start - 1)
    return "".join(p)


def for_rhythm(p):
    """引文裡的句號換成填充字元，不另外斷句，只保留緊貼下引號、作為整句結尾的那一個。長度不變。"""
    return re.sub(r"「[^「」]*」|『[^『』]*』",
                  lambda m: m.group()[0] + re.sub(r"[。！？](?=.)", FILL, m.group()[1:-1]) + m.group()[-1], p)


def drop_foreign_quotes(s):
    """中文比例低於 30% 的引文（例如英文原文）不算進句子長度。"""
    def f(m):
        r, n = ratio_cjk(m.group()[1:-1])
        return "「」" if n and r < 0.3 else m.group()
    return re.sub(r"「[^「」]*」|『[^『』]*』|“[^“”]*”|\"[^\"\n]*\"", f, s)


def clen(s):
    return len(re.sub(r"\s", "", s))


def sent_spans(p):
    """回傳每個句子在 p 裡的 (起點, 終點)。"""
    out, start = [], 0
    for m in re.finditer(r"[。！？][」』]|[。！？](?![」』])", p):
        out.append((start, m.end()))
        start = m.end()
    out.append((start, len(p)))
    spans = []
    for a, b in out:
        while a < b and p[a].isspace():
            a += 1
        while b > a and p[b - 1].isspace():
            b -= 1
        if re.search(CJK, p[a:b]):
            spans.append((a, b))
    return spans


def covered(q, i, j, words):
    """q[i:j] 是否落在 words 任一詞的某次出現範圍內。"""
    for w in words:
        k = q.find(w, max(0, i - len(w) + 1))
        while k != -1 and k <= i:
            if k + len(w) >= j:
                return True
            k = q.find(w, k + 1)
    return False


# ---------- 輸出 ----------

class Report:
    def __init__(self):
        self.lines = []
        self.hits = collections.defaultdict(list)

    def say(self, s=""):
        self.lines.append(s)

    def show(self, key, title, items, limit=8):
        """items 是 [(行號, 提醒)]。超過 limit 的部分只列行號，每一處都找得到。"""
        self.hits[key] += [h for _, h in items]
        if not items:
            return
        self.say(f"\n{title}（{len(items)} 處）：")
        for _, h in items[:limit]:
            self.say("   " + h)
        if len(items) > limit:
            self.say(f"   其餘 {len(items) - limit} 處在第 {line_list(items[limit:])} 行")


def line_list(items):
    return "、".join(str(n) for n in sorted({n for n, _ in items}))


def line_of(seg, pos=None):
    if pos is not None and seg.lines and 0 <= pos < len(seg.lines):
        return seg.lines[pos]
    return seg.line


def loc(seg, pos=None):
    sec = seg.section if len(seg.section) <= 18 else seg.section[:17] + "…"
    return f"第 {line_of(seg, pos)} 行" + (f"〈{sec}〉" if sec else "") + "："


def ctx(text, i, j, w=16):
    """命中處的前後文。被遮住的引文、書名縮成「…」，縮完再取前後各 w 字，才不會被引文占滿。"""
    fold = lambda t: re.sub(FILL + "+", "…", t)
    left, right = fold(text[:i]), fold(text[j:])
    return ("…" + left[-w:] + fold(text[i:j]) + right[:w] + "…").replace("\n", " ")


def scan(segs, pattern, prep=None, w=16):
    """在每個段落裡找 pattern，回傳 [(行號, 提醒)]。prep 不能改變字串長度，行號才對得上。"""
    hits = []
    for s in segs:
        t = prep(s.text) if prep else s.text
        for m in re.finditer(pattern, t):
            hits.append((line_of(s, m.start()), loc(s, m.start()) + ctx(t, m.start(), m.end(), w)))
    return hits


def bold_labels_md(raw):
    """Markdown 清單項目開頭是「**標籤：**」或「**標籤**：」的行。HTML 的在解析時一併檢查。"""
    raw = blank_code_fences(blank_frontmatter(raw))
    rx = r"(?m)^[ \t]*(?:[-*+]|\d+[.)])[ \t]+(?:\*\*|__)[^*_\n]{1,30}?(?:[：:](?:\*\*|__)|(?:\*\*|__)[ \t]*[：:])"
    out = []
    for m in re.finditer(rx, raw):
        line = raw.count("\n", 0, m.start()) + 1
        label = re.sub(r"[*_]", "", m.group()).strip()
        label = re.sub(r"^([-*+]|\d+[.)])\s+", "", label)
        out.append((line, f"第 {line} 行：{label}"))
    return out


# ---------- 檢查 ----------

def analyze(raw, html_mode=False, lo=2.8, hi=4.0):
    rep = Report()
    if html_mode:
        segs, total, skipped, labels = segs_from_html(raw)
    else:
        segs, total, skipped = segs_from_markdown(raw), 0, (0, 0)
        labels = bold_labels_md(raw)

    psegs = [s for s in segs if has_chinese(s.text)]                       # 標點、用語、AI 腔
    rsegs = [s for s in psegs if s.kind == "prose" and is_chinese_prose(s.text)]  # 句子節奏
    kinds = collections.Counter(s.kind for s in psegs)
    rep.say(f"檢查範圍：內文 {kinds['prose']} 段、表格 {kinds['table']} 格、圖說 {kinds['caption']} 則、"
            f"標題 {kinds['heading']} 個（句子節奏只看內文，標點、用語與 AI 腔看全部）")
    if html_mode and total:
        sk, code = skipped
        rep.say(f"涵蓋率：檢查了 body 可見文字的 {100 * (total - sk) / total:.0f}%，略過程式碼 {100 * code / total:.0f}%，"
                f"目錄、導覽與 mono 樣式 {100 * (sk - code) / total:.0f}%")
        if total > code and (total - sk) / (total - code) < 0.7:
            rep.say("⚠ 涵蓋率偏低：程式碼以外的文字有三成以上沒被檢查，請確認內文是不是放在 <nav>，"
                    "或 class、id 含 toc、mono 的元素裡。")
        elif (total - sk) / total < 0.7:
            # 程式碼本來就不檢查，程式碼以外的文字都有檢查到時，只提醒不必處理
            rep.say("涵蓋率偏低，但略過的大多是程式碼，程式碼以外的文字都有檢查，不用處理。")
    if not psegs:
        rep.say("找不到中文內容（中文比例低於 30% 的段落與程式碼不列入）。")
        return rep

    check_rhythm(rep, rsegs, lo, hi)
    check_ai(rep, psegs, labels)
    # 單位只看數字與英文，表格裡只寫「30kW」的儲存格也要檢查，但略過英文段落（例如參考文獻）
    usegs = [s for s in segs if has_chinese(s.text) or ratio_cjk(s.text)[1] < 8]
    check_punct(rep, psegs, usegs)
    check_terms(rep, psegs)
    return rep


def check_rhythm(rep, rsegs, lo, hi):
    rep.say("\n【句子節奏】")
    if not rsegs:
        rep.say("沒有可以統計節奏的內文段落（只有表格、標題或很短的文字）。")
        return
    rparas = [(s, for_rhythm(s.text)) for s in rsegs]
    periods = sum(p.count("。") for _, p in rparas)
    commas = sum(p.count("，") for _, p in rparas)
    # (段落, 句子起點, 句子原文, 句子去掉引文句號後的版本)
    sents = [(s, a, s.text[a:b], p[a:b]) for s, p in rparas for a, b in sent_spans(p)]
    if periods:
        ratio = commas / periods
        verdict = ("在建議範圍內" if lo <= ratio <= hi else
                   "偏低：句子可能太碎，可考慮合併同主題短句" if ratio < lo else
                   "偏高：句子可能太長，可考慮拆開並列句")
        rep.say(f"句號 {periods}、逗號 {commas}，平均每句逗號 {ratio:.2f}（建議 {lo:g}–{hi:g}，以報告類長文為準）→ {verdict}")
        rep.say("每句逗號數分布（7 代表 7 個以上）："
                + str(dict(sorted(collections.Counter(min(r.count("，"), 7) for *_, r in sents).items()))))
    lens = [clen(r.replace(FILL, "")) for *_, r in sents]
    if len(lens) >= 8:
        m, sd = statistics.mean(lens), statistics.pstdev(lens)
        cv = sd / m if m else 0
        note = "句長太平均，讀起來容易像 AI，長短句可以交錯" if cv < 0.3 else "長短有變化"
        rep.say(f"句長：平均 {m:.0f} 字，標準差 {sd:.0f}，變異係數 {cv:.2f}（一般文章約 0.5–0.7）→ {note}")

    # 各節比例：全文平均會把局部問題平均掉
    by_sec = collections.OrderedDict()
    for s, p in rparas:
        a = by_sec.setdefault(s.section or "（開頭）", [0, 0])
        a[0] += p.count("。")
        a[1] += p.count("，")
    secs = [(k, c / n, n) for k, (n, c) in by_sec.items() if n]
    if secs and any(k != "（開頭）" for k, _, _ in secs):
        rep.say("\n各節的平均每句逗號（句號少於 5 個的節樣本太少，只列出不標示）：")
        off = []
        for k, r, n in secs:
            mark = "" if n < 5 else "  ← 偏低" if r < lo else "  ← 偏高" if r > hi else ""
            rep.say(f"   {k}：{r:.2f}（句號 {n}）{mark}")
            if mark:
                off.append(f"{k}：{r:.2f}")
        rep.hits["rhythm.section"] += off

    low_cut = min(2.0, lo)
    low = []
    for s, p in rparas:
        n = p.count("。")
        if n >= 3 and p.count("，") / n < low_cut:
            low.append((p.count("，") / n, s, n, p.count("，")))
    low.sort(key=lambda x: x[0])
    rep.show("rhythm.low_para", f"比例最低的段落（至少 3 個句號、平均每句逗號低於 {low_cut:g}，先從這些段落改）",
             [(s.line, f"{r:.2f}（句號 {n}、逗號 {c}）{loc(s)}{s.text[:30]}…") for r, s, n, c in low[:8]])
    if len(low) > 8:
        rep.say(f"   其餘 {len(low) - 8} 段在第 {line_list([(s.line, '') for _, s, _, _ in low[8:]])} 行")

    runs, run = [], []
    for item in sents:
        r = item[3]
        if r.count("，") == 0 and clen(r) < 60:
            run.append(item)
        else:
            if len(run) >= 3:
                runs.append(run)
            run = []
    if len(run) >= 3:
        runs.append(run)
    rep.show("rhythm.short_run", "連續 3 句以上無逗號的短句",
             [(line_of(r[0][0], r[0][1]), loc(r[0][0], r[0][1]) + " / ".join(x[2][:22] for x in r)) for r in runs])
    longs = []
    for s, a, x, r in sents:
        y = drop_foreign_quotes(x)
        if r.count("，") > 6 or clen(y) > 150:
            longs.append((line_of(s, a), f"{loc(s, a)}{clen(y)} 字、{r.count('，')} 逗號：{x[:46]}…"))
    rep.show("rhythm.long", "較長的句子（超過 6 個逗號或 150 字，可考慮拆開，但長度本身不一定是問題）", longs)


def check_ai(rep, psegs, labels):
    phrases = load_phrases()
    rep.say("\n【AI 腔】")
    if not any(phrases.values()):
        rep.say("（找不到 references/ai-phrases.md，略過套話檢查）")
    for label, key, title in (("強提示", "ai.strong", "強提示（出現一次就該改）"),
                              ("需要來源", "ai.source", "需要來源（有出處就補上，沒有就改寫或刪除，不要編造來源）")):
        hits = []
        for s in psegs:
            q = without_quotes(s.text)
            for cat, ph, rx in phrases[label]:
                for mt in re.finditer(rx, q):
                    hits.append((line_of(s, mt.start()),
                                 f"{cat}「{ph}」：{loc(s, mt.start())}{ctx(q, mt.start(), mt.end())}"))
        rep.show(key, title, hits)
    dense = []
    for s in psegs:
        if s.kind == "heading":
            continue
        q = without_quotes(s.text)
        found = [ph for _, ph, rx in phrases["弱提示"] for _ in re.finditer(rx, q)]
        if len(found) >= (2 if clen(re.sub(FILL + "+", "", q)) < 100 else 3):
            dense.append((s.line, f"{len(found)} 個（{'、'.join(found)}）：{loc(s)}{s.text[:36]}…"))
    rep.show("ai.weak_dense", "弱提示密集的段落（單獨出現沒問題，同一段太多才像 AI）", dense)
    contrast = scan(psegs, f"不是{gap(30)}而是", without_quotes)
    if len(contrast) > 1:
        rep.show("ai.contrast", "「不是…而是…」用了不只一次", contrast)
    if len(labels) >= 3:
        rep.show("ai.bold_label", "「**粗體標籤：**說明」格式的條列（SKILL.md 第二節不建議，可改成完整句子或段落）", labels)


def check_punct(rep, psegs, usegs):
    rep.say("\n【標點】")
    rep.show("punct.semicolon", "分號（只有每項句型相同、本來可以寫成清單的並列才用，其他改寫成連貫的句子）",
             scan(psegs, "；"))
    # 書名、篇名依原文，不檢查裡面的破折號
    rep.show("punct.dash_multi", "一段裡有不只一組破折號（成對夾住補充說明的──…──算一組）",
             [(s.line, f"{no_titles(s.text).count('──')} 個：{loc(s)}{s.text[:36]}…") for s in psegs
              if no_titles(s.text).count("──") > 2])
    rep.show("punct.dash_form", "破折號寫法不對（教育部手冊寫成兩格的──）",
             scan(psegs, f"——|――|{CJKP} ?--+ ?{CJKP}|(?<!─)(?:(?<={CJKP})─|─(?={CJKP}))(?!─)", no_titles))
    rep.show("punct.dash_single", "單一的—（表示起訖的連接號可以保留，當破折號用時改成──）",
             scan(psegs, f"(?<!—)(?:(?<={CJKP})—|—(?={CJKP}))(?!—)", no_titles))
    rep.show("punct.interpunct", "間隔號寫法不對（外國人名、原住民名字與書名篇名之間用全形的．）",
             scan(psegs, f"(?<={CJK})[·・‧•](?={CJK})"))
    rep.show("punct.halfwidth", "中文裡用了半形標點",
             scan(psegs, f"{CJK}[,;?!()]|[,;?!()]{CJK}|{CJK}:|(?<![0-9]):{CJK}"))
    rep.show("punct.quotes", "用了“ ”或\" \"引號（台灣用「」）",
             scan(psegs, r"[“”]|\"(?=[^\"\n]*" + CJK + ")"))
    rep.show("punct.cjk_space", "中英文或數字沒有空格（% 與 ° 後面接中文也要空格）",
             scan(psegs, f"{CJK}{AN}|{AN}{CJK}|[%°]{CJK}"))
    rep.show("punct.unit", "數字與英文單位沒有空格（例如 10 Gbps、5 MW，% 與 ° 除外，引文內的不算）",
             scan(usegs, f"(?<![A-Za-z0-9_.\\-/\\\\])-?{NUM}(?:{UNITS})(?![A-Za-z0-9]|\\.[A-Za-z0-9])", without_quotes, w=10))
    rep.show("punct.fw_space", "全形標點旁多了空格", scan(psegs, f" [{FW_PUNCT}]|[{FW_PUNCT}] "))
    rep.show("punct.cjk_gap", "中文字之間多了半形空格（引文內的不算）",
             scan(psegs, f"(?<={CJK}) +(?={CJK})", without_quotes))


def check_terms(rep, psegs):
    rep.say("\n【台灣用語】")
    direct, context, keep = load_terms()
    avoid_words = [a for a, _, _ in direct]
    pool = keep + [u for _, u, _ in direct]
    hits = []
    for avoid, use, exc in direct:
        # 例外與台灣用語中包含這個詞的（例如「演算法」包含「算法」），出現在那些詞裡面時不算，
        # 更長的中國用語也包含這個詞時（例如「字符串」包含「字符」），只報長的那個
        masks = [e for e in exc if avoid in e] + [w for w in pool + avoid_words if avoid in w and w != avoid]
        legacy = [e for e in exc if avoid not in e]
        for s in psegs:
            q = without_quotes(s.text)
            for mt in re.finditer(re.escape(avoid), q):
                if covered(q, mt.start(), mt.end(), masks):
                    continue
                window = q[max(0, mt.start() - 6):mt.end() + 6]
                if any(e in window for e in legacy):
                    continue
                hits.append((line_of(s, mt.start()),
                             f"「{avoid}」→「{use}」：{loc(s, mt.start())}{ctx(q, mt.start(), mt.end(), 12)}"))
    rep.show("term.direct", "中國用語，建議改成台灣用語", hits, limit=15)

    found = collections.OrderedDict()
    for word in context:
        masks = [w for w in pool + avoid_words if word in w and w != word]
        for s in psegs:
            q = without_quotes(s.text)
            for mt in re.finditer(re.escape(word), q):
                if not covered(q, mt.start(), mt.end(), masks):
                    found.setdefault(word, []).append(
                        (line_of(s, mt.start()), loc(s, mt.start()) + ctx(q, mt.start(), mt.end(), 12)))
    if found:
        rep.say("\n需要看語意確認的詞（對照 references/terms.md「看語意判斷」，每一處都要回到句子判斷，不要一律替換）：")
        for word, items in found.items():
            rep.hits["term.context"] += [f"「{word}」：{x}" for _, x in items]
            rep.say(f"   「{word}」{len(items)} 處：")
            for _, x in items[:5]:
                rep.say("      " + x)
            if len(items) > 5:
                # 其餘只列行號，每一處都找得到，輸出又不會被同一個詞洗版
                rep.say(f"      其餘 {len(items) - 5} 處在第 {line_list(items[5:])} 行")

    # 「國立臺灣…」「臺北市立…」這類機構全名依官方寫法，不算混用
    text = "\n".join(s.text for s in psegs)
    plain = re.sub(r"[國市縣私]立[臺台][灣北中南東][^，。、\s]{0,8}?(大學|學院|醫院|博物館|圖書館|美術館)", "", text)
    if re.search("台灣|台北|台中|台南", plain) and re.search("臺灣|臺北|臺中|臺南", plain):
        rep.hits["term.taitai"].append("「台」與「臺」混用")
        rep.say("\n「台」與「臺」混用，請擇一並全文統一。")


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

    # 佔位標記用 Unicode 私用區字元，用 chr() 產生，避免編輯器或複製時把看不見的字元弄丟
    P = [chr(0xE000 + k) for k in range(6)]
    INNER, COMMENT, ATTR = P[0] + P[1], P[2] + P[3], P[4] + P[5]

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
    seg = re.sub(f" {P[4]}(\\d+){P[5]}", back, seg)
    seg = re.sub(f"{P[2]}(\\d+){P[3]}", back, seg)
    seg = re.sub(f"(?<=>)[a中]?{P[0]}(\\d+){P[1]}[a中]?(?=<)", back, seg)
    return seg


def spaced(text, html_mode):
    """回傳補好中英空格的文字，不寫檔。"""
    m0 = re.search(r"<body", text, flags=re.I)
    if html_mode and m0:
        b0 = m0.start()
        m1 = re.search(r"</body>", text, flags=re.I)
        b1 = m1.start() if m1 else len(text)
        return text[:b0] + add_spacing_html(text[b0:b1]) + text[b1:]
    if html_mode:
        return add_spacing_html(text)
    fm = re.match(FRONTMATTER, text, flags=re.S)
    head, body = (fm.group(), text[fm.end():]) if fm else ("", text)
    lines = body.split("\n")
    code = code_lines(lines)
    out = []
    for k, line in enumerate(lines):
        if k not in code:
            parts = re.split(r"(`[^`\n]*`|https?://\S+)", line)
            line = "".join(p if i % 2 else add_spacing(p, False) for i, p in enumerate(parts))
            line = re.sub(f"({CJK})(`[^`\\n]+`)", r"\1 \2", line)
            line = re.sub(f"(`[^`\\n]+`)({CJK})", r"\1 \2", line)
        out.append(line)
    new = "\n".join(out)
    return head + new


def fix_spacing(path, text, html_mode):
    new = spaced(text, html_mode)
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
    print("\n".join(analyze(text, html_mode, a.min, a.max).lines))


if __name__ == "__main__":
    sys.exit(main())
