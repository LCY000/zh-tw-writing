#!/usr/bin/env python3
"""檢查繁體中文文件的句子節奏、AI 腔、台灣用語與中英混排。

用法：
    python3 check_zh.py report.html
    python3 check_zh.py cover.html body.html appendix.html  # 一次檢查多個檔案，最後印出合計
    python3 check_zh.py report/                         # 檢查資料夾裡的 .html、.htm、.md、.txt（不含子資料夾）
    python3 check_zh.py rewritten.md --source original.md   # 另外比對原稿與改寫稿的數字、網址、引文等事實
    python3 check_zh.py notes.md --fix-spacing          # 自動補中英空格，原檔備份為 .bak
    python3 check_zh.py report.html --min 2.5 --max 4.5 # 調整逗號比例的建議範圍

每個檔案的輸出第一行是各類提醒的總數，細節在後面。

檢查範圍分兩種：
- 句子節奏只看內文段落（HTML 的 <p>、<li>、<div> 等區塊，Markdown 的一般段落與清單），
  表格、標題、圖說本來就短，不列入。中文比例低於 30% 的段落（例如英文參考文獻）也不列入。
- AI 腔、標點與台灣用語看所有可見文字，包括表格、標題與圖說。
兩種都略過程式碼、YAML frontmatter、引用區塊（Markdown 的 > 與 HTML 的 <blockquote>）、
HTML 的 <nav> 與 class 或 id 含 toc、mono 的元素，Markdown 另外略過圖片與夾在內文裡的 HTML。
痕跡（隱形字元、AI 工具的引用標記與網址參數）看原始檔，佔位文字看可見文字。
套話與用語清單來自同一個技能資料夾的 references/ai-phrases.md 與 references/terms.md。
"""
import argparse
import bisect
import collections
import decimal
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
    """回傳 (直接替換 [(避免, 改用, [例外])], 看語意 [詞], 比對時略過的詞 [詞], 字形 [(避免, 改用)])"""
    direct, context, keep, glyphs = [], [], [], []
    path = os.path.join(REF_DIR, "terms.md")
    if not os.path.exists(path):
        return direct, context, keep, glyphs
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
        elif section == "台灣慣用字形" and len(cells) >= 2:
            glyphs.append((cells[0], cells[1]))
    return direct, context, keep, glyphs


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
    s = re.sub(r"\*{1,3}", "", s)
    # 底線只拿掉成對的強調符號，TODO_LIST、_XXX 這類識別字裡的底線保留
    s = re.sub(r"(?<![A-Za-z0-9_])(_{1,3})(?=\S)(.+?)(?<=\S)\1(?![A-Za-z0-9_])", r"\2", s)
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
SKIP = {"script", "style", "head", "template", "noscript", "svg", "nav", "blockquote"}
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
        self.periods = self.commas = 0
        self.summary = ""

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

def analyze(raw, html_mode=False, lo=2.8, hi=4.0, source=None):
    """source 是 (原稿文字, 原稿是否為 HTML)，有給時另外比對事實。"""
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
                f"引用區塊、目錄、導覽與 mono 樣式 {100 * (sk - code) / total:.0f}%")
        if total > code and (total - sk) / (total - code) < 0.7:
            rep.say("⚠ 涵蓋率偏低：程式碼以外的文字有三成以上沒被檢查，請確認內文是不是放在 <blockquote>、<nav>，"
                    "或 class、id 含 toc、mono 的元素裡。")
        elif (total - sk) / total < 0.7:
            # 程式碼本來就不檢查，程式碼以外的文字都有檢查到時，只提醒不必處理
            rep.say("涵蓋率偏低，但略過的大多是程式碼，程式碼以外的文字都有檢查，不用處理。")
    if not psegs:
        rep.say("找不到中文內容（中文比例低於 30% 的段落與程式碼不列入）。")
    else:
        check_rhythm(rep, rsegs, lo, hi)
        check_ai(rep, psegs, labels)
        # 單位只看數字與英文，表格裡只寫「30kW」的儲存格也要檢查，但略過英文段落（例如參考文獻）
        usegs = [s for s in segs if has_chinese(s.text) or ratio_cjk(s.text)[1] < 8]
        check_punct(rep, psegs, usegs)
        check_terms(rep, psegs)
    check_traces(rep, raw, segs, html_mode)
    if source is not None:
        check_facts(rep, raw, html_mode, *source)
    rep.summary = summary(rep.hits, rep.periods, rep.commas, lo, hi, facts=source is not None)
    if not psegs:
        rep.summary += "（找不到中文內容）"
    rep.lines.insert(0, rep.summary)
    return rep


def check_rhythm(rep, rsegs, lo, hi):
    rep.say("\n【句子節奏】")
    if not rsegs:
        rep.say("沒有可以統計節奏的內文段落（只有表格、標題或很短的文字）。")
        return
    rparas = [(s, for_rhythm(s.text)) for s in rsegs]
    periods = sum(p.count("。") for _, p in rparas)
    commas = sum(p.count("，") for _, p in rparas)
    rep.periods, rep.commas = periods, commas
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
    total = f"共 {len(low)} 段，列出最低的 8 段，" if len(low) > 8 else ""
    rep.show("rhythm.low_para", f"比例最低的段落（{total}至少 3 個句號、平均每句逗號低於 {low_cut:g}，先從這些段落改）",
             [(s.line, f"{r:.2f}（句號 {n}、逗號 {c}）{loc(s)}{s.text[:30]}…") for r, s, n, c in low[:8]])
    rep.hits["rhythm.low_para.more"] += [s.text[:30] for _, s, _, _ in low[8:]]  # 只列行號的段落，總數也要算進去
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
    rep.show("punct.semicolon", "分號（自己寫的內文不用分號，重寫整句：短的並列用逗號，其中一項有逗號時把短的放前面，"
             "或把細節移到下一句，不要拆成一句一句的短句。引文裡的照原文，不列入）",
             scan(psegs, "；", without_quotes))
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
    direct, context, keep, glyphs = load_terms()
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

    if glyphs:
        fix = dict(glyphs)
        rx = "|".join(re.escape(a) for a in sorted(fix, key=len, reverse=True))
        gh = []
        for s in psegs:
            q = without_quotes(s.text)
            for mt in re.finditer(rx, q):
                gh.append((line_of(s, mt.start()),
                           f"「{mt.group()}」→「{fix[mt.group()]}」：{loc(s, mt.start())}{ctx(q, mt.start(), mt.end(), 12)}"))
        rep.show("term.glyph", "台灣不用的字形（多半來自簡轉繁工具、香港或日文字形，見 references/terms.md「台灣慣用字形」）",
                 gh, limit=15)

    # 「國立臺灣…」「臺北市立…」這類機構全名依官方寫法，不算混用
    text = "\n".join(s.text for s in psegs)
    plain = re.sub(r"[國市縣私]立[臺台][灣北中南東][^，。、\s]{0,8}?(大學|學院|醫院|博物館|圖書館|美術館)", "", text)
    if re.search("台灣|台北|台中|台南", plain) and re.search("臺灣|臺北|臺中|臺南", plain):
        rep.hits["term.taitai"].append("「台」與「臺」混用")
        rep.say("\n「台」與「臺」混用，請擇一並全文統一。")


# ---------- 痕跡 ----------

# 看不見的字元與 AI 工具標記的清單參考 acchuang/zh-tw-humanizer（MIT）。
# 看不見、但會跟著文字被複製的字元。用 \u 跳脫寫，原始碼裡不放這些字元本身。
INVIS_CHARS = {
    "\u200b": "零寬空格",
    "\u200c": "零寬不連字",
    "\u200d": "零寬連字",
    "\ufeff": "零寬不換行空格（BOM）",
    "\u2060": "字詞連接符",
    "\u00a0": "不換行空格",
    "\u2009": "窄空格",
    "\u202f": "窄不換行空格",
}
INVIS_RX = "[" + "".join(INVIS_CHARS) + "]|[\U000E0000-\U000E007F]+"

TOOL_TRACES = [
    (r"utm_source=(?:chatgpt\.com|openai|perplexity|copilot\.com|claude\.ai)", "AI 工具加在網址上的 utm 參數"),
    (r"turn\d+(?:search|view|news|fetch|image|file)\d+", "ChatGPT 的檢索標記"),
    (r"oai_?cite|contentReference\[|filecite", "ChatGPT 的引用標記"),
    (r"【\d+(?::\d+)?†[^】\n]{0,40}】", "ChatGPT 的檔案引用標記"),
    (r"\[cite(?:_start|_end)?(?::\s*\d+(?:\s*,\s*\d+)*)?\]", "Gemini 的引用標記"),
    (r"\[span_\d+\]\((?:start|end)_span\)", "Gemini 的引用標記"),
    (r"grok_card|grok_render_citation_card_json|referrer=grok\.com", "Grok 的標記"),
    (r"ppl-ai-file-upload", "Perplexity 的上傳標記"),
    (r"\[object Object\]", "程式輸出失敗留下的文字"),
]

PLACEHOLDERS = [
    (r"(?i)lorem ipsum", "模板的假文字"),
    (r"【[^】\n]{0,20}(?:請在此|填寫|填入|插入|請輸入)[^】\n]{0,20}】", "沒填的模板欄位"),
    (r"(?<![A-Za-z0-9_])(?:TBD|TODO|FIXME)(?![A-Za-z0-9_])", "沒補的佔位文字"),
    (r"(?<![A-Za-z0-9_])X{3,}(?![A-Za-z0-9_])", "沒補的佔位文字"),
]


def blank(text, a, b):
    """把 text[a:b] 換成空格，換行保留，長度不變。"""
    return text[:a] + re.sub(r"[^\n]", " ", text[a:b]) + text[b:]


def blank_all(text, pattern, flags=0):
    for m in reversed(list(re.finditer(pattern, text, flags))):
        text = blank(text, m.start(), m.end())
    return text


class Lines:
    """位置換成行號。"""

    def __init__(self, text):
        self.starts = [m.end() for m in re.finditer("\n", text)]

    def __call__(self, pos):
        return bisect.bisect_right(self.starts, pos) + 1


def is_emoji_part(c):
    o = ord(c)
    return o >= 0x1F000 or 0x2600 <= o <= 0x27BF or c in "\ufe0f\u20e3"


def check_traces(rep, raw, segs, html_mode):
    rep.say("\n【痕跡】")
    line = Lines(raw)
    hits = []
    for m in re.finditer(INVIS_RX, raw):
        k, c = m.start(), m.group()
        if k == 0 and c == "\ufeff":
            continue  # 檔首的 BOM 是編碼標記，不是內文
        prev, nxt = raw[k - 1:k], raw[m.end():m.end() + 1]
        if c == "\u200d" and prev and nxt and is_emoji_part(prev) and is_emoji_part(nxt):
            continue  # 組合表情符號（例如家庭、職業圖示）用的零寬連字
        if c[0] >= "\U000E0000" and prev == "\U0001F3F4":
            continue  # 英格蘭、蘇格蘭旗幟的標籤字元
        name = INVIS_CHARS.get(c, "標籤字元")
        code = "、".join(sorted({f"U+{ord(x):04X}" for x in c}))
        s = raw.rfind("\n", 0, k) + 1
        e = raw.find("\n", m.end())
        e = len(raw) if e == -1 else e
        show = lambda x: re.sub(INVIS_RX, "", x)  # 前後文只標出這一處，其他看不見的字元各有自己的提醒
        snippet = show(raw[max(s, k - 14):k]) + f"⟦{name}⟧" + show(raw[m.end():min(e, m.end() + 14)])
        hits.append((line(k), f"{name}（{code}）：第 {line(k)} 行：…{snippet.strip()}…"))
    rep.show("trace.invisible", "看不見的字元（複製網頁或 AI 輸出時常夾帶，刪掉或換成一般空格）", hits)

    # 工具痕跡看原始檔，連結網址裡的也要找到；程式碼裡的是範例，不算
    t = raw
    if html_mode:
        t = blank_all(t, r"<(pre|code|script|style|kbd|samp|textarea)\b.*?</\1\s*>", re.S | re.I)
    else:
        lines = t.split("\n")
        code = code_lines(lines)
        t = "\n".join(re.sub(r"[^\n]", " ", ln) if k in code else ln for k, ln in enumerate(lines))
        t = blank_all(t, r"(`+)[^`\n]+?\1")
    hits = []
    for rx, label in TOOL_TRACES:
        for m in re.finditer(rx, t):
            hits.append((line(m.start()), f"{label}「{m.group()[:40]}」：第 {line(m.start())} 行"))
    hits.sort(key=lambda x: x[0])
    rep.show("trace.tool", "AI 工具留下的痕跡（引用標記、網址參數，交出去之前刪掉）", hits)

    hits = []
    for s in segs:
        q = without_quotes(s.text)
        for rx, label in PLACEHOLDERS:
            for m in re.finditer(rx, q):
                hits.append((line_of(s, m.start()), f"{label}「{m.group()}」：{loc(s, m.start())}{ctx(q, m.start(), m.end(), 12)}"))
    hits.sort(key=lambda x: x[0])
    rep.show("trace.placeholder", "沒填的佔位文字（補上真實內容或刪掉，不要自己編）", hits)


# ---------- 與原稿比對 ----------

FW_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
W = "A-Za-z0-9_"
MONTHS = {m: i + 1 for i, ms in enumerate([
    "january jan", "february feb", "march mar", "april apr", "may", "june jun", "july jul",
    "august aug", "september sep sept", "october oct", "november nov", "december dec"]) for m in ms.split()}
MONTH_RX = "(?:" + "|".join(sorted((m.capitalize() for m in MONTHS), key=len, reverse=True)) + r")\.?"
MULT = {"thousand": 3, "million": 6, "billion": 9, "trillion": 12, "千": 3, "萬": 4, "百萬": 6, "千萬": 7, "億": 8, "兆": 12}
FACT_KINDS = [("url", "網址"), ("email", "信箱"), ("date", "日期"), ("version", "版本號或 IP"), ("code", "代碼"),
              ("number", "數字"), ("inline", "行內程式碼"), ("block", "程式碼區塊"), ("quote", "引文")]
COUNT_KINDS = [("heading", "標題"), ("row", "表格列"), ("link", "連結"), ("block", "程式碼區塊")]


INLINE_TAGS = {"a", "abbr", "b", "bdi", "bdo", "cite", "data", "del", "dfn", "em", "font", "i", "ins", "kbd", "mark",
               "q", "s", "samp", "small", "span", "strong", "sub", "sup", "time", "u", "var", "wbr"}
HTML_TAG = re.compile(r"""<(?:[^>"']|"[^"]*"|'[^']*')*>""")  # 屬性引號裡的 > 不算標籤結束
MD_FENCE = re.compile(r"^\s*(?:(?:[-*+]|\d{1,9}[.)])\s+)*(`{3,}|~{3,})")


class _Links(html.parser.HTMLParser):
    """收集 <a href> 的網址、行號與連結文字，屬性有沒有引號都認得。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.cur = [], None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.cur = [(dict(attrs).get("href") or "").strip(), self.getpos()[0], ""]

    def handle_data(self, data):
        if self.cur is not None:
            self.cur[2] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.cur is not None:
            self.links.append(self.cur)
            self.cur = None

    def close(self):
        super().close()
        if self.cur is not None:
            self.links.append(self.cur)


def _tag(m):
    """HTML 標籤拿掉：行內標籤直接接起來（1<b>23</b> 還是 123），區塊標籤換成空格，換行保留。"""
    name = re.match(r"</?\s*([A-Za-z][A-Za-z0-9]*)", m.group())
    keep = "\n" * m.group().count("\n")
    return keep if name and name.group(1).lower() in INLINE_TAGS else " " + keep


def _entity(m):
    s = html.unescape(m.group())
    return " " if "\n" in s else s


def _code_body(lines):
    """程式碼內容只去掉共同縮排與前後的空行，裡面的空格（包括行尾空白）、全形字都照原樣比。"""
    lines = list(lines)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return textwrap_dedent("\n".join(lines))


def fact_view(raw, html_mode):
    """回傳 (掃描用的文字, {種類: [(值, 行號)]}, {結構: 數量})。掃描用的文字和原檔的換行位置相同，
    行號用換行數算。程式碼在轉換全形數字之前先取出，內容照原樣比。"""
    found = collections.defaultdict(list)
    counts = collections.Counter()
    t = raw
    if html_mode:
        t = blank_all(t, r"<!--.*?-->", re.S)
        t = blank_all(t, r"<(script|style|head|template|svg)\b.*?</\1\s*>", re.S | re.I)
        line = Lines(t)
        for m in re.finditer(r"<pre\b[^>]*>(.*?)</pre\s*>", t, re.S | re.I):
            body = html.unescape(re.sub(r"<[^>]*>", "", m.group(1)))
            found["block"].append((_code_body(body.split("\n")), line(m.start())))
            counts["block"] += 1
        t = blank_all(t, r"<pre\b.*?</pre\s*>", re.S | re.I)
        for m in re.finditer(r"<code\b[^>]*>(.*?)</code\s*>", t, re.S | re.I):
            found["inline"].append((html.unescape(re.sub(r"<[^>]*>", "", m.group(1))).strip(), line(m.start())))
        t = blank_all(t, r"<code\b.*?</code\s*>", re.S | re.I)
        p = _Links()
        p.feed(t)
        p.close()
        for href, no, text in p.links:
            if href and not href.startswith("#"):
                counts["link"] += 1
                if href != text.strip():  # 連結文字就是網址時，網址只算一次
                    found["url"].append((href, no))
        counts["heading"] = len(re.findall(r"<h[1-6]\b", t, re.I))
        counts["row"] = len(re.findall(r"<tr\b", t, re.I))
        t = re.sub(HTML_TAG, _tag, t)
        t = re.sub(r"&#?[A-Za-z0-9]+;", _entity, t)
    else:
        t = blank_frontmatter(t)
        lines = t.split("\n")
        code = code_lines(lines)
        k = 0
        while k < len(lines):
            if k not in code:
                k += 1
                continue
            j = k
            while j + 1 in code:
                j += 1
            # 一段連續的程式碼行可能是好幾個相鄰的區塊，依圍欄分開
            # 結尾圍欄要和開頭同一種符號、至少一樣長、後面沒有其他字，四個反引號裡的 ``` 只是內容
            cur, start, fenced = [], k, None
            for idx in range(k, j + 1):
                f = MD_FENCE.match(lines[idx])
                if f and fenced and not (f.group(1)[0] == fenced[0] and len(f.group(1)) >= len(fenced)
                                         and not lines[idx][f.end():].strip()):
                    f = None
                if f:
                    if fenced:
                        found["block"].append((_code_body(cur), start + 1))
                        counts["block"] += 1
                        cur, fenced = [], None
                    else:
                        if cur:
                            found["block"].append((_code_body(cur), start + 1))
                            counts["block"] += 1
                        cur, start, fenced = [], idx, f.group(1)
                else:
                    if not cur and not fenced:
                        start = idx
                    cur.append(lines[idx])
            if cur or fenced is not None:
                found["block"].append((_code_body(cur), start + 1))
                counts["block"] += 1
            k = j + 1
        prose = [ln for k, ln in enumerate(lines) if k not in code]
        counts["heading"] = sum(bool(re.match(r"^\s{0,3}#{1,6}\s", ln)) for ln in prose)
        counts["row"] = sum(ln.strip().startswith("|") and not re.fullmatch(r"[|:\-\s]+", ln.strip()) for ln in prose)
        counts["link"] = sum(len(re.findall(r"(?<!!)\[[^\]]*\]\([^)]*\)|<https?://[^>]+>", ln)) for ln in prose)
        t = "\n".join(re.sub(r"[^\n]", " ", ln) if k in code else ln for k, ln in enumerate(lines))
        line = Lines(t)
        for m in re.finditer(r"(`+)([^`\n]+?)\1", t):
            found["inline"].append((m.group(2).strip(), line(m.start())))
        t = blank_all(t, r"(`+)[^`\n]+?\1")
        # 圖片只留替代文字；連結留文字與網址，連結文字就是網址時只留一次；<https://…> 拿掉角括號
        t = re.sub(r"!\[([^\]\n]*)\]\([^)\n]*\)", r"\1", t)
        t = re.sub(r"\[([^\]\n]*)\]\(\s*([^)\s]*)[^)\n]*\)",
                   lambda m: m.group(1) + ("" if m.group(2) == m.group(1).strip() else " " + m.group(2)), t)
        t = re.sub(r"<(https?://[^>\s]+)>", r"\1", t)
        t = blank_all(t, r"(?m)^[ \t]*\d{1,9}[.)](?=[ \t])")  # 編號清單的編號
    return t, found, counts


def textwrap_dedent(s):
    ind = [len(ln) - len(ln.lstrip()) for ln in s.split("\n") if ln.strip()]
    n = min(ind) if ind else 0
    return "\n".join(ln[n:] for ln in s.split("\n"))


def _num(sign, intpart, frac, mult, pct):
    digits = intpart.replace(",", "") + ("." + frac if frac else "")
    with decimal.localcontext() as c:
        c.prec = len(digits) + 20  # 預設 28 位會把很長的數字捨入成同一個值
        d = decimal.Decimal(digits).scaleb(MULT.get(mult.lower() if mult else "", 0))
        s = format(d.normalize(), "f")
    if sign and s != "0":
        s = "-" + s
    return s + ("%" if pct else "")


def extract_facts(raw, html_mode, quotes=True):
    """回傳 ({種類: [(正規化的值, 原文寫法, 行號)]}, {結構: 數量})"""
    orig, found, counts = fact_view(raw, html_mode)
    # 比對用全形數字轉成半形的版本，顯示與潤稿比對用原文寫法（長度相同，位置對得上）
    t = orig.translate(FW_DIGITS)
    line = Lines(t)
    out = collections.defaultdict(list)
    clean = lambda s: s

    for v, no in found["url"]:
        out["url"].append((v, v, no))
    for v, no in found["inline"]:
        if v:
            out["inline"].append((v, v, no))
    for v, no in found["block"]:
        first = v.split("\n")[0]
        out["block"].append((v, first[:30] + ("…" if len(first) > 30 or "\n" in v else ""), no))

    # 引文要在數字、網址被遮掉之前取出，引文裡改了一個數字也要看得出來
    if quotes:
        # 書名號也算：潤稿時把法規名稱從「」改成《》是正常的修改，內容沒變就不報
        for m in re.finditer(r"「([^「」]+)」|『([^『』]+)』|“([^“”]+)”|\"([^\"\n]+)\"|《([^《》]+)》|〈([^〈〉]+)〉", t):
            body = next(g for g in m.groups() if g is not None)
            # 引文裡補中英空格（腳本與 --fix-spacing 都會建議）不算改了引文
            out["quote"].append((re.sub(r"\s+", "", body), body[:30], line(m.start())))

    def take(kind, rx, norm, flags=0):
        """抽出一類事實，再把命中的範圍一次遮掉（逐次重組字串在大檔案會很慢）。"""
        nonlocal t
        spans = []
        for m in re.finditer(rx, t, flags):
            v = norm(m)
            if v is None:
                continue
            out[kind].append((v, orig[m.start():m.end()].strip(), line(m.start())))
            spans.append((m.start(), m.end()))
        if spans:
            chars = list(t)
            for a, b in spans:
                for k in range(a, b):
                    if chars[k] != "\n":
                        chars[k] = " "
            t = "".join(chars)

    def url(m):
        u = clean(m.group())
        while u and u[-1] in ".,;:!?*_'\"":
            u = u[:-1]
        while u.endswith(")") and u.count("(") < u.count(")"):
            u = u[:-1]
        return u

    take("url", r"https?://[A-Za-z0-9\-._~:/?#@!$&*+,;=%()]+", url)  # 網址只算 ASCII，後面緊接的中文不算進去
    take("email", f"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{{2,}}", lambda m: m.group().lower())

    def ymd(y, mo, d):
        y = int(y) if y else None
        mo = int(mo) if mo else None
        d = int(d) if d else None
        if mo is not None and not 1 <= mo <= 12 or d is not None and not 1 <= d <= 31:
            return None
        return "-".join(x for x in (f"{y:04d}" if y else "", f"{mo:02d}" if mo else "", f"{d:02d}" if d else "") if x)

    mon = lambda s: MONTHS[s.rstrip(".").lower()]
    take("date", r"民國\s*(\d{2,3})\s*年(?:\s*(\d{1,2})\s*月(?:\s*(\d{1,2})\s*[日號])?)?",
         lambda m: ymd(int(m.group(1)) + 1911, m.group(2), m.group(3)))
    take("date", rf"(?<![{W}.])(\d{{4}})[-/.](\d{{1,2}})[-/.](\d{{1,2}})(?![{W}])",
         lambda m: ymd(m.group(1), m.group(2), m.group(3)))
    take("date", r"(?<!\d)(\d{4})\s*年\s*(\d{1,2})\s*月(?:\s*(\d{1,2})\s*[日號])?",
         lambda m: ymd(m.group(1), m.group(2), m.group(3)))
    take("date", r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*[日號]", lambda m: ymd(None, m.group(1), m.group(2)))
    od = r"(\d{1,2})(?:st|nd|rd|th)?"
    take("date", rf"\b({MONTH_RX})\s+{od},?\s+(\d{{4}})\b", lambda m: ymd(m.group(3), mon(m.group(1)), m.group(2)))
    take("date", rf"\b{od}\s+({MONTH_RX}),?\s+(\d{{4}})\b", lambda m: ymd(m.group(3), mon(m.group(2)), m.group(1)))
    take("date", rf"\b({MONTH_RX}),?\s+(\d{{4}})\b", lambda m: ymd(m.group(2), mon(m.group(1)), None))
    take("date", rf"\b({MONTH_RX})\s+{od}(?![\d:])", lambda m: ymd(None, mon(m.group(1)), m.group(2)))
    # 只有月份：in March 與「3 月」都算成月份 03，英翻中才不會把「3 月」的 3 當成新增的數字
    # 單獨的月名要接在介系詞後面，才不會把 May I… 的 May 當成五月
    take("date", rf"\b(?:in|by|since|until|till|from|through|during|before|after|early|late|mid-?|of|next|last|this|every)"
                 rf"\s+({MONTH_RX})(?![A-Za-z])", lambda m: ymd(None, mon(m.group(1)), None), flags=re.I)
    take("date", r"(?<![\d.])(\d{1,2})\s*月份?", lambda m: ymd(None, m.group(1), None))

    take("version", rf"(?<![{W}.])[vV]\d+(?:\.\d+)*(?![{W}]|\.\d)|(?<![{W}.])\d+\.\d+\.\d+(?:\.\d+)*(?![{W}]|\.\d)",
         lambda m: m.group().lower().lstrip("v"))

    def code(m):
        s = m.group()
        if not (re.search("[A-Za-z]", s) and re.search(r"\d", s)):
            return None
        if re.fullmatch(rf"-?{NUM}(?:{UNITS}|%|x|st|nd|rd|th)", s, flags=re.I):
            return None
        return s
    take("code", rf"(?<![{W}.:/-])[A-Za-z0-9](?:[A-Za-z0-9._:/-]*[A-Za-z0-9])?(?![{W}])", code)

    # 負號只在前面不是英數字時才算（5-10 的 - 是範圍）；% 與 percent 算進值裡，50% 改成 50 也看得出來
    take("number", r"(?:(?<![A-Za-z0-9_.])([-−－])|(?<![A-Za-z0-9_.]))(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?![\d])"
                   r"(?:\s*(thousand|million|billion|trillion|千萬|百萬|千|萬|億|兆)(?![A-Za-z]))?"
                   r"(\s*(?:%|％|percent(?![A-Za-z])))?",
         lambda m: _num(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)), flags=re.I)

    return out, counts


def check_facts(rep, raw, html_mode, src_raw, src_html):
    rep.say("\n【與原稿比對】")
    src_segs = segs_from_html(src_raw)[0] if src_html else segs_from_markdown(src_raw)
    # 網址不算進中文比例；原稿中文少、改寫稿中文多才是英翻中，英文術語多的中文技術文件兩邊都低，照潤稿比
    plain = lambda segs: re.sub(r"https?://[!-~]+", "", "\n".join(s.text for s in segs))
    r, n = ratio_cjk(plain(src_segs))
    r2, _ = ratio_cjk(plain(segs_from_html(raw)[0] if html_mode else segs_from_markdown(raw)))
    translate = n > 0 and r < 0.3 and r2 >= 0.3
    if translate:
        rep.say("比對模式：英翻中（原稿中文比例低於 30%）。比數字、日期、網址、信箱、代碼、版本號與行內程式碼，"
                "日期換算成同一種寫法再比，引文與程式碼區塊的內容不比，只比區塊數量。")
    else:
        rep.say("比對模式：潤稿（原稿是中文）。比數字、日期、網址、信箱、代碼、版本號、程式碼與引文，"
                "修改別人的文件時這些要一字不動，所以比的是原文的寫法（只忽略空格），3,200 改成 3200 也會報。")
    src, src_counts = extract_facts(src_raw, src_html, quotes=not translate)
    dst, dst_counts = extract_facts(raw, html_mode, quotes=not translate)
    missing, added = [], []
    for kind, label in FACT_KINDS:
        if translate and kind in ("quote", "block"):
            continue
        a = collections.defaultdict(list)
        b = collections.defaultdict(list)
        # 英翻中比換算後的值；潤稿比原文寫法，只忽略空格（補中英空格不算改）
        key = (lambda v, shown: v) if translate or kind in ("url", "inline", "block", "quote") else \
            (lambda v, shown: re.sub(r"\s+", "", shown))
        for v, shown, no in src.get(kind, []):
            a[key(v, shown)].append((shown, no))
        for v, shown, no in dst.get(kind, []):
            b[key(v, shown)].append((shown, no))
        for v in sorted(set(a) | set(b), key=lambda x: min([no for _, no in a.get(x, []) + b.get(x, [])])):
            na, nb = len(a.get(v, [])), len(b.get(v, []))
            if na == nb:
                continue
            shown = (a.get(v) or b.get(v))[0][0]
            where_a = "、".join(str(no) for no in sorted({no for _, no in a.get(v, [])}))
            where_b = "、".join(str(no) for no in sorted({no for _, no in b.get(v, [])}))
            msg = (f"{label}「{shown}」：原稿 {na} 次" + (f"（第 {where_a} 行）" if na else "")
                   + f"，改寫稿 {nb} 次" + (f"（第 {where_b} 行）" if nb else ""))
            if na > nb:
                missing.append((min(no for _, no in a[v]), msg))
            else:
                added.append((min(no for _, no in b[v]), msg))
    rep.show("fact.missing", "原稿有、改寫稿比較少（可能遺失或被改掉，回到原文確認）", missing, limit=20)
    rep.show("fact.added", "改寫稿有、原稿比較少（可能是新增的內容，原文沒有就刪掉）", added, limit=20)
    diff = [(0, f"{label}：原稿 {src_counts[k]} 個，改寫稿 {dst_counts[k]} 個")
            for k, label in COUNT_KINDS if src_counts[k] != dst_counts[k]]
    rep.show("fact.count", "結構的數量不同（標題、表格列、連結或程式碼區塊少了或多了）", diff)
    if missing or added:
        rep.say("\n數字只比阿拉伯數字。國字和阿拉伯數字互換（「三成」改成「30%」、three 改成「3」）、"
                "日期範圍與序數（1st、第一）會被當成遺失或新增，要回到原文確認。")
    elif not diff:
        rep.say("沒有發現遺失或新增的數字、網址、代碼與引文。")


# ---------- 總數 ----------

SUMMARY = [
    ("句子節奏", [("rhythm.low_para", "比例偏低的段落"), ("rhythm.section", "比例偏離的節"),
              ("rhythm.short_run", "連續短句"), ("rhythm.long", "較長的句子")]),
    ("AI 腔", [("ai.strong", "強提示"), ("ai.source", "需要來源"), ("ai.weak_dense", "弱提示密集"),
              ("ai.contrast", "不是…而是"), ("ai.bold_label", "粗體標籤條列")]),
    ("標點", [("punct.semicolon", "分號"), ("punct.dash_multi", "破折號過多"), ("punct.dash_form", "破折號寫法"),
            ("punct.dash_single", "單一的—"), ("punct.interpunct", "間隔號"), ("punct.halfwidth", "半形標點"),
            ("punct.quotes", "引號"), ("punct.cjk_space", "中英空格"), ("punct.unit", "數字單位空格"),
            ("punct.fw_space", "標點旁空格"), ("punct.cjk_gap", "中文字間空格")]),
    ("台灣用語", [("term.direct", "中國用語"), ("term.glyph", "字形"), ("term.context", "需確認用語"),
              ("term.taitai", "台臺混用")]),
    ("痕跡", [("trace.invisible", "隱形字元"), ("trace.tool", "工具痕跡"), ("trace.placeholder", "佔位文字")]),
]
FACT_SUMMARY = ("與原稿比對", [("fact.missing", "可能遺失"), ("fact.added", "可能新增"), ("fact.count", "數量不同")])


def summary(hits, periods, commas, lo, hi, facts=False):
    parts = []
    if periods:
        r = commas / periods
        parts.append(f"逗號比例 {r:.2f}（{'範圍內' if lo <= r <= hi else '偏低' if r < lo else '偏高'}）")
    for group, items in SUMMARY + ([FACT_SUMMARY] if facts else []):
        sub = [(label, len(hits.get(k, [])) + len(hits.get(k + ".more", []))) for k, label in items]
        n = sum(c for _, c in sub)
        detail = "、".join(f"{label} {c}" for label, c in sub if c)
        parts.append(f"{group} {n}" + (f"（{detail}）" if detail else ""))
    return "總數：" + "｜".join(parts)


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
            parts = re.split(r"(`[^`\n]*`|https?://[A-Za-z0-9\-._~:/?#@!$&*+,;=%()]+)", line)
            line = "".join(p if i % 2 else add_spacing(p, False) for i, p in enumerate(parts))
            line = re.sub(f"({CJK})(`[^`\\n]+`)", r"\1 \2", line)
            line = re.sub(f"(`[^`\\n]+`)({CJK})", r"\1 \2", line)
        out.append(line)
    new = "\n".join(out)
    return head + new


def fix_spacing(path, text, html_mode):
    """回傳 (補好空格的文字, 訊息)。"""
    new = spaced(text, html_mode)
    if new != text:
        shutil.copyfile(path, path + ".bak")
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
        return new, f"已補上中英空格，原檔備份為 {path}.bak"
    return new, "沒有需要補的空格。"


EXTS = (".html", ".htm", ".md", ".txt")


def is_html(path):
    return path.lower().endswith((".html", ".htm"))


def expand(paths):
    """資料夾展開成裡面的 .html、.htm、.md、.txt（不含子資料夾），回傳 (檔案, 警告)。"""
    files, notes = [], []
    for p in paths:
        if os.path.isdir(p):
            fs = sorted(f for f in os.listdir(p) if f.lower().endswith(EXTS) and not f.startswith(".")
                        and os.path.isfile(os.path.join(p, f)))
            if not fs:
                notes.append(f"{p} 裡沒有 .html、.htm、.md、.txt 檔案。")
            files += [os.path.join(p, f) for f in fs]
        else:
            files.append(p)
    return files, notes


def run(paths, fix=False, lo=2.8, hi=4.0, source=None):
    """檢查一個或多個檔案，回傳要印出的文字。source 是原稿路徑，只能搭配一個檔案。"""
    files, out = expand(paths)
    src = None
    if source:
        if len(files) != 1:
            return "--source 只能搭配一個要檢查的檔案。"
        try:
            with open(source, encoding="utf-8") as f:
                src = (f.read(), is_html(source))
        except (OSError, UnicodeDecodeError) as e:
            return f"讀不到原稿 {source}：{e}"
    multi = len(files) > 1
    reps = []
    for path in files:
        if multi:
            out.append(f"\n━━━━ {path} ━━━━")
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            out.append(f"讀不到這個檔案：{e}")
            reps.append((path, None))
            continue
        msg = None
        if fix:
            text, msg = fix_spacing(path, text, is_html(path))
        rep = analyze(text, is_html(path), lo, hi, source=src)
        reps.append((path, rep))
        # 總數一定在第一行，補空格的訊息放在它後面
        out += rep.lines[:1] + ([msg] if msg else []) + rep.lines[1:]
    bad = [path for path, rep in reps if rep is None]
    reps = [(path, rep) for path, rep in reps if rep is not None]
    if multi and (reps or bad):
        # 開頭也列一次各檔案的總數，輸出被截斷時，後面的檔案也看得到有沒有問題
        out[:0] = [f"共 {len(files)} 個檔案，各檔案的總數如下，細節在後面，全部的合計在最後："] + \
                  [f"   {path}：{rep.summary[3:]}" for path, rep in reps] + [f"   {path}：讀不到" for path in bad]
        hits = collections.defaultdict(list)
        for _, rep in reps:
            for k, v in rep.hits.items():
                hits[k] += v
        out.append(f"\n━━━━ 全部 {len(reps)} 個檔案合計 ━━━━")
        out.append(summary(hits, sum(r.periods for _, r in reps), sum(r.commas for _, r in reps), lo, hi))
        out.append("各檔案：")
        out += [f"   {path}：{rep.summary[3:]}" for path, rep in reps]
        if len(reps) < len(files):
            out.append(f"⚠ 有 {len(files) - len(reps)} 個檔案讀不到，沒有算進合計。")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="檢查繁體中文文件的句子節奏、AI 腔、台灣用語與中英混排")
    ap.add_argument("paths", nargs="+", metavar="path", help="要檢查的檔案或資料夾，可以給好幾個")
    ap.add_argument("--fix-spacing", action="store_true", help="自動補中英文、中文與數字之間的空格")
    ap.add_argument("--source", metavar="原稿", help="潤稿或翻譯的原稿，比對數字、網址、引文等事實有沒有遺失或新增")
    ap.add_argument("--min", type=float, default=2.8, help="每句逗號數建議下限（預設 2.8）")
    ap.add_argument("--max", type=float, default=4.0, help="每句逗號數建議上限（預設 4）")
    a = ap.parse_args()
    print(run(a.paths, a.fix_spacing, a.min, a.max, a.source))


if __name__ == "__main__":
    sys.exit(main())
