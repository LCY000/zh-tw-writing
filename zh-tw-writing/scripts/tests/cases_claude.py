# 2026-11-12 實作者調整：Codex 審查指出「回調」（價格回調）與「棧」（棧橋、貨棧）台灣也有正常用法，
# 依待辦第十二項的收錄門檻移到看語意判斷，所以把這幾題對「回調」「棧」的預期從 term.direct 改成 term.context。
# 獨立測試題（只依待辦清單第一到第十四項、SKILL.md 與 references/ 出題，沒有讀實作）
# 每題的 why 寫依據；標「推論」的是規範沒有明寫、出題者自行判斷的部分。

CASES = [
    # ── 第一項：YAML frontmatter ──────────────────────────────
    dict(
        name="開頭的 frontmatter 整段略過（半形逗號、欄位接中文、長欄位、用語、台臺）",
        ext="md",
        text="""---
title: 星盾商業模式畫布
tags: [資安, 商業模式, 畫布]
version: v1.2,依審稿意見修訂,補上台灣市場規模
description: 比較三種軟件授權模式的收入結構
differentiation: 以AI分析端點紀錄，結合威脅情資，自動產生處置建議，支援地端部署，也支援雲端部署，提供中文介面，提供在地服務，價格低於國際品牌
---

# 星盾商業模式

星盾鎖定臺灣中小型製造業，提供端點偵測與事件處置服務，客戶按端點數量每年付費。
""",
        hit=[],
        miss=[("punct.halfwidth", ""), ("punct.cjk_space", ""), ("term.direct", ""),
              ("rhythm.long", ""), ("term.taitai", "")],
        why="待辦第一項。frontmatter 裡的「台灣」不該和正文的「臺灣」算成混用（推論：整段略過，所以所有檢查都不看）",
    ),
    dict(
        name="略過 frontmatter 後正文照樣檢查，行號仍對應原始檔案",
        ext="md",
        text="""---
title: 資料處理流程說明
version: 1.0
---

# 資料處理流程

本系統使用Python撰寫，每天凌晨從三個資料來源匯入紀錄，整理後寫入資料庫。
""",
        hit=[("punct.cjk_space", "Python"), ("punct.cjk_space", "第 8 行")],
        miss=[],
        why="待辦第一項。行號部分是推論：略過的是檢查範圍，行號應該仍是原始檔的第 8 行，使用者才找得到",
    ),
    dict(
        name="不在檔案開頭的 --- 是分隔線，中間的內文不能被當成 frontmatter 略過",
        ext="md",
        text="""# 第一章 系統架構

本章說明系統架構，並比較三種部署方式的成本。

---

本系統使用Python撰寫，部署在公司內部的伺服器上。

---

下一章說明測試方法，並列出測試環境的規格。
""",
        hit=[("punct.cjk_space", "Python")],
        miss=[],
        why="待辦第一項只說「.md 檔開頭是 --- 時」才略過",
    ),

    # ── 第二項：粗體句後的空格 ────────────────────────────────
    dict(
        name="「**粗體句。** 內文」與「*斜體句。* 內文」的空格不算全形標點旁多餘空格，也不是粗體標籤條列",
        ext="md",
        text="""**買方怎麼花錢。** 依 SANS 2025 年的調查，多數企業把資安預算優先放在端點防護，網路監控排在第二位。

**誰來做決定。** 中型企業的採購多半由資訊主管提案，再交由財務主管核准，整個流程約需三個月。

**預算多大。** 年營收十億元以下的製造業，每年的資安支出多在 300 萬元以內，其中約一半用於授權費。

*初步判斷。* 端點防護的訂閱制最符合這群客戶的付款習慣，建議作為第一階段的主力方案。
""",
        hit=[],
        miss=[("punct.fw_space", ""), ("ai.bold_label", "")],
        why="待辦第二項（** 與 * 都要排除）；第五項只抓清單項目開頭的「**……：**」，段落開頭的粗體句不算",
    ),
    dict(
        name="粗體例外不能蓋掉同一份文件裡真正的全形標點後空格",
        ext="md",
        text="""**買方怎麼花錢。** 依 SANS 2025 年的調查，多數企業把資安預算優先放在端點防護，網路監控排在第二位。

今年的資安預算比去年增加。 下一步要確認的是，這些預算有多少會用在外部服務。
""",
        hit=[("punct.fw_space", "增加。")],
        miss=[("punct.fw_space", "怎麼花錢")],
        why="待辦第二項：只有 ** 或 * 夾在全形標點與空格之間才不算",
    ),
    dict(
        name="__ 粗體的「__粗體句。__ 內文」空格也不該報",
        ext="md",
        text="""__買方怎麼花錢。__ 依 SANS 2025 年的調查，多數企業把資安預算優先放在端點防護，網路監控排在第二位。
""",
        hit=[],
        miss=[("punct.fw_space", "")],
        why="推論：待辦第二項只寫 ** 與 *，但理由（CommonMark 結尾分隔符前是標點時，後面要接空格或標點才會結束）對 __ 完全相同",
    ),

    # ── 第三項：中文字之間的半形空格 ──────────────────────────
    dict(
        name="中文字之間夾半形空格",
        ext="md",
        text="""本研究在 第 7.1 節說明系統架構，並比較三種方案的優缺點與成本。

測試環境的詳細規格見 第 7.2 節，表中列出每台主機的處理器與記憶體配置。
""",
        hit=[("punct.cjk_gap", "在 第"), ("punct.cjk_gap", "見 第")],
        miss=[],
        why="待辦第三項（也是第十四項列的例句）",
    ),
    dict(
        name="引號內 PDF 摘錄的斷行空格不報，同一句引號外的真錯誤要報",
        ext="md",
        text="""附錄 D 摘錄的報告原文為「本 系統 於 2024 年 上線 後，事件 回應 時間 明顯 縮短」，這段文字直接從 PDF 擷取，保留原本的斷行空格，本研究在 第 7.1 節會再說明這個數字的來源。
""",
        hit=[("punct.cjk_gap", "在 第")],
        miss=[("punct.cjk_gap", "本 系統"), ("punct.cjk_gap", "事件 回應")],
        why="待辦第三項：排除引號內的原文摘錄",
    ),
    dict(
        name="Markdown 表格的 | 分隔不能被當成中文字之間的空格",
        ext="md",
        text="""各方案的比較如下表。

| 方案 | 部署方式 | 年費 |
| --- | --- | --- |
| 甲 | 雲端 | 120 萬元 |
| 乙 | 地端 | 180 萬元 |

乙方案的年費較高，但資料不必離開廠區，較符合製造業客戶的要求。
""",
        hit=[],
        miss=[("punct.cjk_gap", "")],
        why="待辦第三項：排除 Markdown 表格的分隔",
    ),
    dict(
        name="Markdown 表格儲存格裡的空格錯誤與單位錯誤仍要抓",
        ext="md",
        text="""充電樁的主要規格整理如下表。

| 項目 | 規格 |
| --- | --- |
| 額定功率 | 30kW |
| 測試方法 | 詳見 第 4 節 |
""",
        hit=[("punct.unit", "30kW"), ("punct.cjk_gap", "見 第")],
        miss=[],
        why="待辦第三、四項，加上第六項 11/12 補充：標點要掃表格。排除的是表格分隔，不是儲存格內容",
    ),
    dict(
        name="HTML 行內標籤與相鄰儲存格不能被接成中間有空格的文字",
        ext="html",
        text="""<html><body>
<h2>二、研究方法</h2>
<p>本研究<strong>採用</strong>混合方法，先以問卷蒐集<em>一百二十家</em>企業的資料，再挑選其中六家進行<a href="#interview">深度訪談</a>。</p>
<table><tr><td>甲方案</td><td>雲端部署</td></tr></table>
</body></html>
""",
        hit=[],
        miss=[("punct.cjk_gap", "")],
        why="待辦第三、六項：原始 HTML 沒有空格，行內元素要接在一起，td 是各自的段落",
    ),

    # ── 第四項：數字與英文單位 ────────────────────────────────
    dict(
        name="數字後面直接接單位（含 kWh、VDC、小數）",
        ext="md",
        text="""這座儲能案場的總容量為 5MW，單一機櫃輸出 500kW，直流側採用 800VDC 架構。

每座充電樁的功率為 30kW，每日用電約 120kWh，機房對外頻寬為 2.5Gbps。
""",
        hit=[("punct.unit", "5MW"), ("punct.unit", "500kW"), ("punct.unit", "800VDC"),
             ("punct.unit", "30kW"), ("punct.unit", "120kWh"), ("punct.unit", "2.5Gbps")],
        miss=[],
        why="待辦第四項（5MW 也是第十四項列的例句）。kWh 要整個單位比對，不能因為 kW 先比對到就失敗",
    ),
    dict(
        name="% 與 ° 緊貼數字、已加空格的單位、10GBASE-T 與 5G 都不報",
        ext="md",
        text="""今年的營收成長 15%，機櫃的進風溫度維持在 25° 以下，散熱風扇的導流角度為 90°。

機房的骨幹交換器採用 10GBASE-T 介面，對外線路為 10 Gbps，並保留升級到 5G 專網的空間。
""",
        hit=[],
        miss=[("punct.unit", "")],
        why="待辦第四項（% 與 ° 不列入）。10GBASE-T 與 5G 是推論：GB 後面還接著英文字母，不是獨立的單位，5G 的 G 不在單位清單",
    ),

    # ── 第五項：「**粗體標籤：**說明」條列 ─────────────────────
    dict(
        name="三個清單項目用「**標籤：**說明」",
        ext="md",
        text="""評估結果整理如下。

- **成本：**每年授權費約 120 萬元，另需一名專職人員維運。
- **時程：**從採購到上線約需四個月，其中測試占一半。
- **風險：**供應商在臺灣沒有原廠工程師，緊急事件需等待國外支援。
""",
        hit=[("ai.bold_label", "成本")],
        miss=[],
        why="待辦第五項",
    ),
    dict(
        name="只有兩個「**標籤：**」項目不報",
        ext="md",
        text="""評估結果整理如下。

- **成本：**每年授權費約 120 萬元，另需一名專職人員維運。
- **時程：**從採購到上線約需四個月，其中測試占一半。
""",
        hit=[],
        miss=[("ai.bold_label", "")],
        why="待辦第五項：同一份文件三次以上才列出",
    ),
    dict(
        name="編號清單、冒號在粗體外的「**標籤**：」也算",
        ext="md",
        text="""評估結果整理如下。

1. **成本**：每年授權費約 120 萬元，另需一名專職人員維運。
2. **時程**：從採購到上線約需四個月，其中測試占一半。
3. **風險**：供應商在臺灣沒有原廠工程師，緊急事件需等待國外支援。
""",
        hit=[("ai.bold_label", "成本")],
        miss=[],
        why="待辦第五項列了「**……**：」寫法；編號清單也是清單項目（推論）",
    ),

    # ── 第六項：HTML 抽取範圍 ────────────────────────────────
    dict(
        name="HTML 的 td、figcaption、dd、巢狀 div 卡片、span 葉節點、混合內容 div 裡的分號都要抓",
        ext="html",
        text="""<html><body>
<h2>三、觀察結果</h2>
<p>本節整理三週的觀察紀錄，並附上對應的截圖與查詢條件。</p>
<table>
<tr><th>查詢條件</th><th>結果</th></tr>
<tr><td>站內搜尋</td><td>找不到公開的會議紀錄；改用第二頁的結果後找到兩筆</td></tr>
</table>
<figure><img src="fig1.png"><figcaption>左：原始查詢結果；右：加上檔案類型條件後的結果</figcaption></figure>
<dl><dt>誤報</dt><dd>查詢條件過寬；需要加上網域限制</dd></dl>
<div class="card"><div class="card-body">第二週的命中數明顯下降；原因是目標網站更新了索引設定</div></div>
<div class="qa"><span class="q">為什麼要改查詢條件</span><span class="a">原本的條件會帶出大量論壇文章；篩選後只剩官方公告</span></div>
<div class="note">本次觀察發現兩種行為；<span class="tag">高風險</span></div>
</body></html>
""",
        hit=[("punct.semicolon", "會議紀錄；"), ("punct.semicolon", "查詢結果；"),
             ("punct.semicolon", "過寬；"), ("punct.semicolon", "明顯下降；"),
             ("punct.semicolon", "論壇文章；"), ("punct.semicolon", "兩種行為；")],
        miss=[],
        why="待辦第六項（抽取 body 所有可見文字）；figcaption 的「左：……；右：……」見第八項",
    ),
    dict(
        name="「不是…而是…」在 p、span 卡片、td 各一次，三處都要列出",
        ext="html",
        text="""<html><body>
<h2>四、討論</h2>
<p>這次的誤報不是規則寫錯，而是資料來源的時間格式不一致。</p>
<div class="obs-card"><span class="label">觀察 2</span><span class="body">攻擊者用的不是新工具，而是系統內建的管理程式。</span></div>
<table><tr><td>延遲原因</td><td>問題不是頻寬不足，而是查詢沒有使用索引。</td></tr></table>
</body></html>
""",
        hit=[("ai.contrast", "規則寫錯"), ("ai.contrast", "新工具"), ("ai.contrast", "頻寬不足")],
        miss=[],
        why="待辦第六項（實際報告用了 3 次只報 1 次）",
    ),
    dict(
        name="巢狀區塊（li>p、div>div>p）裡只出現一次「不是…而是…」，不能被重複計算",
        ext="html",
        text="""<html><body>
<ul>
<li><p>這次的誤報不是規則寫錯，而是資料來源的時間格式不一致。</p></li>
</ul>
<blockquote><p>防禦方需要的是完整的端點紀錄，才能重建攻擊者的行動順序。</p></blockquote>
<div class="card"><div class="card-body"><p>第二週的命中數下降，原因是目標網站更新了索引設定。</p></div></div>
</body></html>
""",
        hit=[],
        miss=[("ai.contrast", "")],
        why="待辦第六項改成以區塊元素切段後，巢狀區塊的文字只能算一次，否則一次的「不是…而是…」會被當成兩次",
    ),
    dict(
        name="略過 nav、class 含 toc（多值、巢狀）、class 含 mono 的儲存格、pre、code、script、style",
        ext="html",
        text="""<html><head><style>body { font-family: "Noto Sans TC"; }</style></head><body>
<nav class="toc">
<p>目錄</p>
<ol>
<li>研究背景3</li>
<li>研究方法5</li>
<li>觀察結果9</li>
</ol>
</nav>
<div class="toc-box toc"><ul><li><a href="#a">附錄A資料來源</a></li><li><a href="#b">附錄B查詢紀錄</a></li></ul></div>
<h2>一、研究背景</h2>
<p>本研究整理公開網站上不慎外流的會議紀錄，並比較不同查詢條件的命中數，作為後續稽核的參考。</p>
<table><tr><th>查詢條件</th><th>命中數</th></tr>
<tr><td class="cell mono">"會議紀錄" filetype:pdf</td><td>42</td></tr></table>
<pre># 使用數組儲存查詢結果
results = []</pre>
<p>錯誤訊息出現在 <code>log.error("內存不足")</code> 這一行，代表程式沒有取得足夠的記憶體。</p>
<script>var label = "軟件版本";</script>
</body></html>
""",
        hit=[],
        miss=[("term.direct", ""), ("punct.quotes", ""), ("punct.cjk_space", ""),
              ("punct.halfwidth", ""), ("rhythm.short_run", ""), ("punct.cjk_gap", "")],
        why="待辦第六項與第十一項（目錄、mono 儲存格）。cjk_gap 是推論：略過 <code> 後「在」與「這」之間不是真的夾空格",
    ),
    dict(
        name="一般 HTML 報告輸出涵蓋率，script 與 style 不是可見文字，不能拉低涵蓋率",
        ext="html",
        text="""<html><head><style>
body { font-family: "Noto Sans TC", sans-serif; line-height: 1.8; }
h1, h2 { font-weight: 700; }
table { border-collapse: collapse; width: 100%; }
td, th { border: 1px solid #ccc; padding: 4px 8px; }
.note { background: #f6f6f6; border-left: 4px solid #999; padding: 8px 12px; }
</style></head><body>
<h1>端點偵測導入評估</h1>
<h2>一、背景</h2>
<p>本公司目前有四百台員工電腦與六十台伺服器，過去只安裝傳統防毒軟體，去年發生兩次勒索軟體事件後，管理階層決定評估端點偵測與回應產品。</p>
<p>評估小組由資訊部與稽核室組成，從十月開始測試三家廠商的產品，每家測試兩週，測試期間記錄告警數量、誤報比例與管理介面的操作時間。</p>
<p>指令範例為 <code>edr --scan</code>，執行一次完整掃描約需五分鐘。</p>
<script>
window.addEventListener("load", function () {
  document.querySelectorAll("table").forEach(function (t) { t.classList.add("ready"); });
  console.log("report loaded");
});
</script>
</body></html>
""",
        hit=[("_out", "涵蓋")],
        miss=[("_out", "涵蓋率偏低")],
        why="待辦第六項：涵蓋率以 body 可見文字為分母，script、style 不是可見文字（推論）",
    ),
    dict(
        name="大部分內容在 pre 裡的 HTML，涵蓋率低於 70% 要警告",
        ext="html",
        text="""<html><body>
<h2>附錄 A　偵測腳本</h2>
<p>以下是完整的偵測腳本。</p>
<pre>import json
import sys
from datetime import datetime, timedelta

def load_events(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def suspicious_logons(events, window_minutes=10, threshold=5):
    alerts = []
    by_user = {}
    for e in events:
        if e.get("event_id") != 4625:
            continue
        ts = datetime.fromisoformat(e["timestamp"])
        by_user.setdefault(e["user"], []).append(ts)
    for user, times in by_user.items():
        times.sort()
        for i in range(len(times)):
            j = i
            while j &lt; len(times) and times[j] - times[i] &lt;= timedelta(minutes=window_minutes):
                j += 1
            if j - i &gt;= threshold:
                alerts.append({"user": user, "start": times[i].isoformat(), "count": j - i})
                break
    return alerts

if __name__ == "__main__":
    print(json.dumps(suspicious_logons(load_events(sys.argv[1])), ensure_ascii=False, indent=2))
</pre>
</body></html>
""",
        hit=[("_out", "涵蓋率偏低")],
        miss=[],
        why="待辦第六項：涵蓋率低於 70% 時明確警告",
    ),
    dict(
        name="HTML 表格的短句不算節奏問題，但表格、標題裡的用語和台臺混用要抓",
        ext="html",
        text="""<html><body>
<h2>四、線程排程</h2>
<p>臺灣廠區的系統啟動時會建立固定數量的工作執行緒，每個執行緒負責一個資料來源，處理完畢後回到待命狀態，等待下一批工作。</p>
<table>
<tr><th>項目</th><th>狀態</th><th>備註</th></tr>
<tr><td>線程池大小</td><td>已完成。</td><td>不適用。</td></tr>
<tr><td>逾時設定</td><td>待確認。</td><td>下週提供。</td></tr>
<tr><td>錯誤重試</td><td>已完成。</td><td>台灣廠區先上線。</td></tr>
</table>
</body></html>
""",
        hit=[("term.direct", "線程排程"), ("term.direct", "線程池"), ("term.taitai", "")],
        miss=[("rhythm.short_run", ""), ("rhythm.low_para", "")],
        why="待辦第六項 11/12 補充：節奏只看內文段落，用語與標點掃所有可見文字",
    ),
    dict(
        name="Markdown 的標題與表格也要做用語檢查，表格短句不算節奏問題",
        ext="md",
        text="""## 三、數組的記憶體配置

本節列出部署時需要調整的設定，未列出的項目沿用預設值。

| 設定項目 | 預設值 | 狀態 |
| --- | --- | --- |
| 管理端口 | 8443 | 已完成。 |
| 紀錄保留天數 | 90 | 待確認。 |
| 備份排程 | 每日 | 已完成。 |
""",
        hit=[("term.direct", "數組"), ("term.direct", "管理端口")],
        miss=[("rhythm.short_run", "")],
        why="待辦第六項 11/12 補充（Markdown 用語檢查要納入表格與標題）；數組、端口是第十二項新詞",
    ),

    # ── 第七項：比例最低的段落、分節比例 ────────────────────────
    dict(
        name="比例低於 2.0 的段落要列出並附段落開頭",
        ext="md",
        text="""## 五、心得反思

這次實作讓我理解偵測規則的寫法。一開始我只看單一事件，漏掉很多攻擊。後來改成串接多個事件，誤報減少了一半。這個做法也有代價，規則變得比較難維護。

下一階段會把規則放進測試環境，連續觀察兩週的告警數量，再決定是否上線。
""",
        hit=[("rhythm.low_para", "這次實作")],
        miss=[],
        why="待辦第七項（4 個句號、3 個逗號，平均 0.75）",
    ),
    dict(
        name="平均剛好 2.0 的段落、只有兩個句號的段落都不列",
        ext="md",
        text="""本研究蒐集三家廠商的報價，比較授權費、維運費，以及教育訓練的費用。甲廠商的總價最低，但不提供在地支援，需要另外委外。乙廠商提供駐點工程師，價格高出兩成，合約期間也比較長。

丙廠商沒有回覆報價。我們會在下週再次聯繫，並同步更新比較表。
""",
        hit=[],
        miss=[("rhythm.low_para", "")],
        why="待辦第七項：「至少 3 個句號、比例低於 2.0」。第一段 3 句 6 個逗號（頓號不算），平均剛好 2.0；第二段只有 2 個句號",
    ),
    dict(
        name="低比例段落只列前 8 段，第 9 低的不列",
        ext="md",
        text="""第一週完成環境建置，安裝了兩台虛擬機。網路設定沒有問題。防火牆規則也已套用。

第二週開始蒐集紀錄，每天匯出一次。資料量比預期少。部分主機沒有開啟稽核。

第三週補上稽核設定，重新收集資料。紀錄數量回到正常。我們也整理了欄位說明。

第四週撰寫第一版規則，先處理登入事件。誤報數量偏高。多數來自備份帳號。

第五週排除備份帳號，誤報降到每天十筆。剩下的多半是排程工作。這部分留到下週處理。

第六週調整排程工作的判斷，加上時間條件。誤報再降一半。規則開始穩定。

第七週加入橫向移動的規則，測試了三種情境。兩種可以偵測。第三種沒有觸發。

第八週分析沒有觸發的原因，發現是欄位名稱不同。修正後順利觸發。整體規則完成。

第九週把規則部署到測試環境，連續觀察五天，記錄每天的告警數量。告警集中在上班時間，晚上幾乎沒有，符合預期。下週會整理結果，交給指導老師確認。
""",
        hit=[("rhythm.low_para", "第一週"), ("rhythm.low_para", "第八週")],
        miss=[("rhythm.low_para", "第九週")],
        why="待辦第七項：依比例由低到高列前 8 段。前八段都是 3 句 1 個逗號（0.33），第九段 3 句 5 個逗號（1.67），排第 9",
    ),
    dict(
        name="Markdown 分節：偏低的節要標示，在範圍內的節與不到 5 個句號的節不標",
        ext="md",
        text="""## 一、市場規模

臺灣的工控資安市場仍在起步階段，主要買方是半導體與電子製造業，其他產業的採購規模較小，多半只買基本的防火牆。依經濟部的統計，2024 年國內約有八千家中型製造業，其中設有專職資安人員的不到兩成，多數由資訊人員兼任。以每家每年 50 萬元的預算估算，可服務的市場約為 40 億元，實際能觸及的客戶有限，初期以中部工業區為主。

這個估算沒有計入政府補助，若補助計畫延續，部分廠商的預算會提高，市場規模也會跟著擴大。本報告採用保守估計，只計入已有資訊部門的廠商，沒有資訊部門的小廠暫不納入，之後再視訪談結果調整。

## 二、競爭者

目前市場上有三家主要競爭者，都來自國外。甲公司的產品功能最完整，價格也最高。乙公司主打雲端管理，在中小企業的市占率較高。丙公司去年才進入臺灣，目前只有兩家客戶。三家公司都沒有提供中文的事件報告，這是我們的切入點。

## 三、後續工作

下個月會完成十家廠商的訪談。訪談結果會用來修正市場規模的估算。定價策略預計在年底前確定。試營運的客戶名單由業務部門提供。
""",
        hit=[("rhythm.section", "二、競爭者")],
        miss=[("rhythm.section", "一、市場規模"), ("rhythm.section", "三、後續工作")],
        why="待辦第七項。第一節 5 句各 3 個逗號（3.0），第二節 5 句各 1 個逗號（1.0），第三節只有 4 個句號不算",
    ),
    dict(
        name="HTML 依 h3 分節，比例偏高（超過 4）的節也要標示",
        ext="html",
        text="""<html><body>
<h2>一、部署架構</h2>
<p>本系統部署在客戶的廠區機房，採用兩台實體主機互為備援，任一台故障時，另一台會在一分鐘內接手。分析主機與資料庫分開放置，資料庫只接受分析主機的連線，管理介面只能從跳板主機存取，不直接對外開放。所有紀錄先寫入本機磁碟，每小時同步到備份主機，備份主機放在另一棟建築，避免單一機房失火造成資料遺失。</p>
<p>主機的作業系統採用長期支援版本，每季套用一次安全更新，更新前會先做完整備份，確認可以還原後才進行。這套架構的建置成本約 300 萬元，其中硬體占六成，其餘是授權與安裝費用，後續每年的維護費約為建置成本的一成五。</p>
<h3>1.1 網路分區</h3>
<p>廠區網路分成四個區域，辦公區、生產區、管理區與外部服務區，各區之間以防火牆隔開，只開放必要的連線，其餘一律阻擋，並記錄被阻擋的連線。生產區的機台大多使用舊版作業系統，無法安裝端點代理程式，所以改用網路側的流量監控，在交換器上設定鏡像連接埠，把流量送到分析主機，再由分析主機比對規則。管理區只允許跳板主機連入，管理人員先登入跳板主機，再從跳板主機連到各區主機，所有操作都會錄影，錄影檔留存九十天，到期後自動刪除。</p>
<p>外部服務區放置對外的網站與郵件閘道，這一區的主機每週更新一次，更新前先在測試環境驗證，驗證通過才排入維護時段，維護時段固定在週六凌晨，避開生產排程。辦公區的電腦統一由網域控制站管理，使用者沒有本機管理員權限，安裝軟體要先提出申請，資訊人員審核後遠端安裝，安裝紀錄會寫入資產清單，方便日後盤點。</p>
</body></html>
""",
        hit=[("rhythm.section", "1.1 網路分區")],
        miss=[("rhythm.section", "一、部署架構")],
        why="待辦第七項：HTML 依 h2／h3 分節，「偏離建議範圍」包含偏高。h2 節 5 句各 3 個逗號（3.0），h3 節 5 句各 5 個逗號（5.0）",
    ),

    # ── 第八項：分號 ─────────────────────────────────────────
    dict(
        name="敘事段落裡用分號串起的列舉要提醒",
        ext="md",
        text="""我們試了幾種查詢方式，站內搜尋找不到任何結果；翻到第二頁才出現相關的會議紀錄；同一個查詢隔天再跑，結果又不一樣。
""",
        hit=[("punct.semicolon", "任何結果；"), ("punct.semicolon", "會議紀錄；")],
        miss=[],
        why="待辦第八項：敘事段落裡的列舉不是並列條列，分號一律要改寫",
    ),

    # ── 第九項、第十三項：看語意判斷每一處附前後文 ───────────────
    dict(
        name="看語意判斷的詞每一處各一則提醒，附前後文",
        ext="md",
        text="""攻擊者取得帳號後，開始訪問檔案伺服器上的共用資料夾，並下載了三份設計圖。

為了了解事件經過，研究團隊訪問了三位資安主管，請他們描述當天的處理流程。
""",
        hit=[("term.context", "訪問檔案"), ("term.context", "訪問了三位")],
        miss=[],
        why="待辦第九項第 5 點與第十三項 11/12 補充：腳本負責多抓，每一處都附前後文，由 AI 判斷",
    ),
    dict(
        name="第十三項新詞：調用、交互、遠程列為看語意判斷，不在直接改用",
        ext="md",
        text="""這支程式在啟動時會調用外部的驗證服務，取得權杖後才開始處理資料。

年底的盤點作業需要調用其他部門的人力，預計動用十名同仁。

從量測資料可以看出，溫度與濕度之間有明顯的交互作用，兩者一起升高時故障率最高。

國防部的十年遠程規劃把無人機列為優先項目，預算逐年增加。
""",
        hit=[("term.context", "調用外部"), ("term.context", "調用其他部門"),
             ("term.context", "交互作用"), ("term.context", "遠程規劃")],
        miss=[("term.direct", "交互"), ("term.direct", "遠程")],
        why="待辦第十三項（交互、遠程已從第十二項移到這裡）",
    ),

    # ── 第十項：HTML 提醒的位置 ──────────────────────────────
    dict(
        name="HTML 提醒附最近的 h3 標題與原始行號",
        ext="html",
        text="""<html><body>
<h2>三、研究方法</h2>
<p>本研究以問卷與訪談蒐集資料，問卷回收一百二十份，受訪者為六位資安主管。</p>
<h3>3.1 資料來源</h3>
<p>問卷由產業公會協助發放；訪談則由研究團隊親自進行，每次約一小時。</p>
</body></html>
""",
        hit=[("punct.semicolon", "3.1 資料來源"), ("punct.semicolon", "第 5 行")],
        miss=[],
        why="待辦第十項寫「章節標題或行號」，測試說明的提醒格式兩者都有，所以兩個都測；分號在原始檔第 5 行，最近的是 h3",
    ),

    # ── 第十一項：用語誤報、長句誤報 ──────────────────────────
    dict(
        name="網域名稱、網域產生演算法不報，別段真正的域名、算法要報",
        ext="md",
        text="""攻擊者使用網域產生演算法（DGA），每天產生數百個隨機的網域名稱，用來躲避黑名單。

另一個樣本則把指令伺服器的域名寫死在程式裡，分析人員很快就找到連線目標。

這套算法的缺點是容易被預測，研究人員只要取得種子值就能算出所有網域。
""",
        hit=[("term.direct", "伺服器的域名"), ("term.direct", "這套算法")],
        miss=[("term.direct", "產生演算法"), ("term.direct", "隨機的網域名稱")],
        why="待辦第十一項（遮罩改用欄與台灣常用詞）",
    ),
    dict(
        name="例外詞（比特幣、在線上、客棧）不報，旁邊真正的錯誤要報",
        ext="md",
        text="""比特幣價格在 2024 年大幅波動，交易所的成交量也跟著增加。

比特幣錢包的私鑰長度為 256 比特，遺失後就無法復原。

員工在線上會議中確認了修補時程，並指派專人追蹤。

監控程式會定期確認伺服器是否在線，離線超過五分鐘就發出告警。

這個函式把區域變數放在棧上，函式結束後就會釋放。

這棟老建築原本是清代的客棧，現在改建成文史館。
""",
        hit=[("term.direct", "256 比特"), ("term.direct", "是否在線"), ("term.context", "放在棧上")],
        miss=[("term.direct", "比特幣價格"), ("term.direct", "在線上會議"), ("term.direct", "清代的客棧")],
        why="待辦第十二項的例外欄（比特幣、在線上、客棧）與第十一項的遮罩；同一句有例外詞時，真正的錯誤仍要抓",
    ),
    dict(
        name="引號外英文長引文不算長句",
        ext="md",
        text="""CISA 在公告中描述了這個組織的手法：「Volt Typhoon actors have been observed using living-off-the-land techniques, including built-in network administration tools, to maintain long-term access to critical infrastructure networks while avoiding detection by endpoint security products.」

這段說明和我們在客戶環境看到的紀錄一致，攻擊者幾乎沒有留下惡意程式。
""",
        hit=[],
        miss=[("rhythm.long", "")],
        why="待辦第十一項：引號內中文比例低於 30% 時不列入長句",
    ),
    dict(
        name="遮罩改用欄的詞（文件）不能讓看語意判斷的同一個詞消失",
        ext="md",
        text="""請把掃描結果另存成文件，上傳到專案的共用資料夾。
""",
        hit=[("term.context", "另存成文件")],
        miss=[],
        why="推論：第十一項的遮罩是「比對前先把正確的台灣用語遮起來，再找中國用語」，用於直接改用。「文件」是第十二項「文檔」的改用，但也在看語意判斷表，遮掉它會讓第九項第 5 點的逐處判斷失效",
    ),

    # ── 第十二項：直接改用的新詞 ────────────────────────────
    dict(
        name="第十二項新詞，長詞優先（字符串要建議字串，不是字元）",
        ext="md",
        text="""前端把使用者輸入的字符串轉成 JSON，再以異步請求送到後端。

後端收到資料後計算哈希值，比對成功才執行回調，結果寫入資料庫。

測試用的映像檔放在U盤裡，插入後就能開機。

晶圓的主要材料是硅，切割後再送去封裝。
""",
        hit=[("term.direct", "「字符串」"), ("term.direct", "異步"), ("term.direct", "哈希"),
             ("term.direct", "回調"), ("term.direct", "U盤"), ("term.direct", "硅")],
        miss=[("term.direct", "「字符」")],
        why="待辦第十二項。字符串與字符都在表內，字符串應整個比對，建議改成「字串」；提醒開頭格式依測試說明的「「軟件」→「軟體」：」",
    ),
    dict(
        name="書名號與引號內的用語不報，同一句引號外的要報",
        ext="md",
        text="""參考書目包括《軟件工程導論》與《計算機網絡》兩本教科書。

該公司的新聞稿寫「這套軟件能自動修補漏洞」，我們在實驗室連續測試兩週，並比對三個版本的紀錄後發現，這套軟件只能偵測，無法修補。
""",
        hit=[("term.direct", "軟件只能")],
        miss=[("term.direct", "工程導論"), ("term.direct", "計算機網絡"), ("term.direct", "軟件能自動")],
        why="SKILL.md「檢查方式」：引號與書名號內不列入用語檢查。第十一、十二項改比對方式時容易弄壞，列為回歸測試",
    ),

    # ── 第十四項：測試檔列舉的不應該被抓到 ─────────────────────
    dict(
        name="第十四項列的「不應該被抓到」寫法放在同一份文件",
        ext="md",
        text="""---
title: 網域監控報告
tags: [DGA, 網域, 監控]
---

**主要發現。** 攻擊者使用網域產生演算法，每天註冊新的網域名稱，再以比特幣支付註冊費用。

團隊在線上會議中確認了封鎖清單，並請廠商更新防火牆規則。
""",
        hit=[],
        miss=[("term.direct", ""), ("punct.fw_space", ""), ("punct.halfwidth", ""),
              ("punct.cjk_space", "")],
        why="待辦第十四項列的過去誤報：網域名稱、網域產生演算法、比特幣、在線上會議、**粗體句。** 內文、YAML frontmatter",
    ),

    # ---------- v1.3.0（2026-11-25）----------
    # 只依 SKILL.md〈檢查方式〉、references/terms.md、ai-phrases.md 與待辦第二十八到三十一、三十六、三十九項出題

    # ── 第二十八項：用語表的複合詞、新詞、略過的詞 ─────────────
    dict(
        name="v1.3 複合詞報完整的長詞：視頻通話、激光打印機，不拆成視頻、打印、激光",
        ext="md",
        text="我們用視頻通話開會，再用激光打印機印出賬號清單與二維碼，下班前寄給各組。\n",
        hit=[("term.direct", "「視頻通話」→「視訊通話」"),
             ("term.direct", "「激光打印機」→「雷射印表機」"),
             ("term.direct", "「賬號」→「帳號」"),
             ("term.direct", "「二維碼」→「QR Code」")],
        miss=[("term.direct", "「視頻」→「影片」"), ("term.direct", "「打印」→「列印」"),
              ("term.direct", "「激光」→「雷射」"), ("term.direct", "「打印機」→「印表機」")],
        why="待辦第二十八項與 terms.md：視頻通話→視訊通話、激光打印機→雷射印表機要整個比對，"
            "拆開會變成「影片通話」「列印機」；賬號、二維碼是新增的直接改用詞",
    ),
    dict(
        name="v1.3 單獨的打印機報成印表機，不報成列印",
        ext="md",
        text="會議室的打印機卡紙了，行政人員已經聯絡廠商來修理。\n",
        hit=[("term.direct", "「打印機」→「印表機」")],
        miss=[("term.direct", "「打印」→「列印」")],
        why="待辦第二十八項：「打印機」被報成「打印→列印」是已實測的 bug，照改會變「列印機」",
    ),
    dict(
        name="v1.3 新增的直接改用詞：筆記本電腦、局域網、宕機、移動硬盤、剪貼板、攝像頭、點贊、便利店",
        ext="md",
        text="""工程師把筆記本電腦接上局域網後，伺服器突然宕機，備份只好先存到移動硬盤。

他把錯誤訊息複製到剪貼板，順手關掉攝像頭，再去便利店買晚餐，回來時貼文已經有人點贊。
""",
        hit=[("term.direct", "「筆記本電腦」→「筆記型電腦」"), ("term.direct", "「局域網」→「區域網路」"),
             ("term.direct", "「宕機」→「當機」"), ("term.direct", "「移動硬盤」→「外接硬碟」"),
             ("term.direct", "「剪貼板」→「剪貼簿」"), ("term.direct", "「攝像頭」→"),
             ("term.direct", "「便利店」→「便利商店」"), ("term.direct", "「點贊」→「按讚」")],
        miss=[("term.direct", "「硬盤」→「硬碟」")],
        why="terms.md「直接改用」新增的詞；移動硬盤要報整個長詞，不再另外報裡面的「硬盤」（推論：比照視頻通話的長詞優先）",
    ),
    dict(
        name="v1.3「比對時略過的詞」不能誤報（致死機率、賭博主要、批發貨品、手機號稱、小區域、本科系、本周刊、地圖上周邊）",
        ext="md",
        text="""這種病毒的致死機率不高，非法賭博主要透過境外網站進行，批發貨品則由物流公司配送。

廠商手機號稱可以防水，實測時卻在小區域內進水，本科系的學生把結果整理成報告，投稿到本周刊。

地圖上周邊的商家都有標示營業時間。
""",
        hit=[],
        miss=[("term.direct", ""), ("term.context", "「小區」"), ("term.context", "「本科」"),
              ("term.context", "「本周」"), ("term.context", "「上周」")],
        why="terms.md「比對時略過的詞」列了致死機、賭博主、批發貨、手機號稱、小區域、本科系、本周刊、上周邊；"
            "看語意判斷表也寫「小區域」「本科系」「本周刊」「周邊」裡的不算",
    ),
    dict(
        name="v1.3 新增的看語意判斷詞報在 term.context，不報成直接改用",
        ext="md",
        text="""本周會議討論音頻處理模組，下周再確認銷售渠道、數碼相機的保修條款。

周末加班的工資由保安公司支付，招聘公告也引來不少網民留言。
""",
        hit=[("term.context", "「本周」"), ("term.context", "「下周」"), ("term.context", "「音頻」"),
             ("term.context", "「渠道」"), ("term.context", "「數碼」"), ("term.context", "「保修」"),
             ("term.context", "「周末」"), ("term.context", "「工資」"), ("term.context", "「保安」"),
             ("term.context", "「招聘」"), ("term.context", "「網民」")],
        miss=[("term.direct", "")],
        why="terms.md「看語意判斷」新增音頻、渠道、數碼、保安、招聘、工資、保修、網民、周末、本周、上周、下周；"
            "待辦第二十八項：周末、本周放看語意判斷",
    ),
    dict(
        name="v1.3 周年、周邊、周圍、四周是正確寫法，不報",
        ext="md",
        text="公司成立十周年，主辦單位在會場周邊加派人力，周圍道路與四周停車場也都實施交通管制。\n",
        hit=[],
        miss=[("term.context", "周"), ("term.direct", "周")],
        why="待辦第二十八項：「周年」「周邊」是正確寫法；看語意判斷表寫「周邊」「周遭」「周圍」裡的不算",
    ),

    # ── 第二十九項：台灣慣用字形 ─────────────────────────────
    dict(
        name="v1.3 台灣不用的字形：裏、綫、爲、着",
        ext="md",
        text="工程師在機房裏找到一條鬆脫的網路綫，爲了確認影響範圍，隨即着手檢查其他機櫃。\n",
        hit=[("term.glyph", "「裏」→「裡」"), ("term.glyph", "「綫」→「線」"),
             ("term.glyph", "「爲」→「為」"), ("term.glyph", "「着」→「著」")],
        why="terms.md「台灣慣用字形」與 SKILL.md〈檢查方式〉：台灣不用的字形（裏、綫、爲、内）直接報",
    ),
    dict(
        name="v1.3 長得像台灣寫法的字形：户、内、説、税",
        ext="md",
        text="這份内部説明列出每個用户的税務資料存放位置，只有稽核人員可以查閱。\n",
        hit=[("term.glyph", "「内」→「內」"), ("term.glyph", "「説」→「說」"),
             ("term.glyph", "「户」→「戶」"), ("term.glyph", "「税」→「稅」")],
        why="terms.md「台灣慣用字形」：户、内、説、税肉眼難分辨，靠腳本找",
    ),
    dict(
        name="v1.3 引號與書名號裡的字形不報，引號外的照報",
        ext="md",
        text="""原廠手冊寫著「設定檔放在安裝資料夾裏」，參考書目另有《羣衆心理》一書。

我們爲了比對版本差異，另外下載了舊版手冊。
""",
        hit=[("term.glyph", "「爲」→「為」")],
        miss=[("term.glyph", "「裏」→「裡」"), ("term.glyph", "「羣」→「群」"), ("term.glyph", "「衆」→「眾」")],
        why="SKILL.md〈檢查方式〉：引號裡的引文與書名號裡的標題不列入字形檢查；terms.md：引號裡的引文照原文",
    ),
    dict(
        name="v1.3 台灣正常字形不誤報（裡、線、為、著、內、說、戶、稅、黃、溫、錄、綠）",
        ext="md",
        text="機房裡的線路為主機供電，內部說明寫著每戶的稅務紀錄位置，黃色與綠色標籤代表溫度是否過高，異常時要登錄在表單上。\n",
        hit=[],
        miss=[("term.glyph", "")],
        why="terms.md「台灣慣用字形」的改用欄都是台灣正常寫法，不能被報",
    ),

    # ── 第三十項：痕跡 ──────────────────────────────────────
    dict(
        name="v1.3 內文的零寬空格要報",
        ext="md",
        text="本報告說明三台主機的\u200b設定檢查結果，並列出需要更新的項目。\n",
        hit=[("trace.invisible", "")],
        why="SKILL.md〈檢查方式〉痕跡類：看不見的字元（零寬空格）；待辦第三十項 U+200B",
    ),
    dict(
        name="v1.3 不換行空格、Unicode 標籤字元要報",
        ext="md",
        text="系統設定\u00a0已經完成，管理者可以登入後台確認。\U000e0041\U000e0042\n",
        hit=[("trace.invisible", "")],
        why="待辦第三十項：U+00A0、U+E0000–U+E007F 都在隱形字元的範圍",
    ),
    dict(
        name="v1.3 檔首的 BOM 不報",
        ext="md",
        text="\ufeff# 檢查報告\n\n團隊檢查了三台主機的設定，確認其中兩台需要更新憑證。\n",
        hit=[],
        miss=[("trace.invisible", "")],
        why="待辦第三十項：U+FEFF 檔首 BOM 除外",
    ),
    dict(
        name="v1.3 檔案中間的 U+FEFF 要報",
        ext="md",
        text="# 檢查報告\n\n團隊檢查了三台主機的\ufeff設定，確認其中兩台需要更新憑證。\n",
        hit=[("trace.invisible", "")],
        why="待辦第三十項：只有檔首 BOM 除外，其他位置的 U+FEFF 照報",
    ),
    dict(
        name="v1.3 引號裡的隱形字元與工具痕跡照報",
        ext="md",
        text="原廠回覆寫著「設定\u200b完成後請參考 https://example.com/faq?utm_source=chatgpt.com 的說明」，我們照做後問題就解決了。\n",
        hit=[("trace.invisible", ""), ("trace.tool", "utm_source=chatgpt.com")],
        why="（推論）SKILL.md〈檢查方式〉引文只排除套話、用語、字形、數字單位與中文字間空格，痕跡不在排除範圍；"
            "痕跡類「幾乎不會誤報，看到就處理」",
    ),
    dict(
        name="v1.3 Markdown 程式碼裡的痕跡不報",
        ext="md",
        text="""設定方式如下，執行前請先備份。

```
config = load()\u200b
url = "https://example.com/?utm_source=chatgpt.com"
owner = "TBD"
```

行內程式碼 `status = XXX` 也只是範例。
""",
        hit=[],
        # 2026-11-25 維護者修改：SKILL.md 補寫「看不見的字元連程式碼一起檢查」，程式碼裡的零寬空格同樣會讓指令出錯，
        # 所以從 miss 拿掉 trace.invisible，工具痕跡與佔位文字在程式碼裡仍然不報。
        miss=[("trace.tool", ""), ("trace.placeholder", "")],
        why="（推論）SKILL.md〈檢查方式〉：程式碼不檢查；待辦第三十項沒有另外說程式碼要報",
    ),
    dict(
        name="v1.3 HTML 的 pre 與 code 裡的痕跡不報",
        ext="html",
        text="<html><body><p>以下是設定範例，執行前請先備份。</p>"
             "<pre>token = load()\u200b\nnote = \"[cite: 1]\"</pre>"
             "<p>欄位 <code>owner = TBD</code> 要換成實際的負責人。</p></body></html>",
        hit=[],
        # 2026-11-25 維護者修改：SKILL.md 補寫「看不見的字元連程式碼一起檢查」，程式碼裡的零寬空格同樣會讓指令出錯，
        # 所以從 miss 拿掉 trace.invisible，工具痕跡與佔位文字在程式碼裡仍然不報。
        miss=[("trace.tool", ""), ("trace.placeholder", "")],
        why="（推論）SKILL.md〈檢查方式〉：程式碼不檢查，HTML 的 pre、code 屬於程式碼",
    ),
    dict(
        name="v1.3 AI 工具痕跡：[cite: 1]、utm_source=chatgpt.com、turn0search0、oaicite",
        ext="md",
        text="""這項調查涵蓋 1,200 家企業[cite: 1]，完整報告放在 https://example.com/report?utm_source=chatgpt.com 頁面。

另一份資料的來源標記是 turn0search0，原文還留著 :contentReference[oaicite:0]{index=0} 這段文字。
""",
        hit=[("trace.tool", "[cite: 1]"), ("trace.tool", "utm_source=chatgpt.com"),
             ("trace.tool", "turn0search0"), ("trace.tool", "oaicite")],
        why="SKILL.md〈檢查方式〉痕跡類與待辦第三十項列的工具痕跡",
    ),
    dict(
        name="v1.3 沒填的佔位文字：【請在此處填寫】、TBD、XXX",
        ext="md",
        text="""專案負責人是【請在此處填寫】，由資訊處統籌。

正式上線日期仍是 TBD，要等測試完成後才能決定。

聯絡窗口為 XXX 先生，有問題可以直接寄信。
""",
        hit=[("trace.placeholder", "【請在此處填寫】"), ("trace.placeholder", "TBD"),
             ("trace.placeholder", "XXX")],
        why="SKILL.md〈檢查方式〉痕跡類與待辦第三十項列的佔位文字",
    ),
    dict(
        name="v1.3 一般的【】標題與 XXXL 尺寸不算佔位文字",
        ext="md",
        text="【公告】本季的制服新增 XXXL 尺寸，需要的同仁請在月底前向總務處登記。\n",
        hit=[],
        miss=[("trace.placeholder", "")],
        why="（推論）佔位文字指【請在此處填寫】、獨立的 TBD、XXX 這類沒填的內容；"
            "SKILL.md 說痕跡類「幾乎不會誤報」，一般的【公告】與 XXXL 不該被當成佔位",
    ),

    # ── 第三十一項：--source 事實比對 ─────────────────────────
    dict(
        name="v1.3 潤稿只改說法、事實都在，不報",
        ext="md",
        text="專案會議將於 2026 年 3 月 5 日舉行，預算上限為 120 萬元，相關資料請寄到 ops@example.com 信箱。\n",
        source="專案會議訂在 2026 年 3 月 5 日舉行，預算上限是 120 萬元，資料請寄到 ops@example.com 信箱。\n",
        source_ext="md",
        hit=[],
        miss=[("fact.missing", ""), ("fact.added", ""), ("fact.count", "")],
        why="SKILL.md〈檢查方式〉--source：只列原稿與改寫稿不同的事實，數字、日期、信箱都沒變就不報",
    ),
    dict(
        name="v1.3 潤稿改了數字，報遺失與新增",
        ext="md",
        text="專案會議訂在 2026 年 3 月 5 日舉行，預算上限是 150 萬元。\n",
        source="專案會議訂在 2026 年 3 月 5 日舉行，預算上限是 120 萬元。\n",
        source_ext="md",
        hit=[("fact.missing", "120"), ("fact.added", "150")],
        why="SKILL.md〈檢查方式〉--source：原稿有、改寫稿比較少，以及改寫稿多出來的數字",
    ),
    dict(
        name="v1.3 潤稿拿掉網址、換了信箱",
        ext="md",
        text="詳細說明放在專案頁面，聯絡人信箱是 help@example.com，有問題請直接寄信。\n",
        source="詳細說明放在 https://example.com/plan 頁面，聯絡人信箱是 ops@example.com，有問題請直接寄信。\n",
        source_ext="md",
        hit=[("fact.missing", "https://example.com/plan"), ("fact.missing", "ops@example.com"),
             ("fact.added", "help@example.com")],
        why="SKILL.md〈檢查方式〉--source：比對網址與信箱",
    ),
    dict(
        name="v1.3 潤稿改了版本號、拿掉漏洞代碼",
        ext="md",
        text="系統已經升級到 v2.4，修補了先前通報的漏洞。\n",
        source="系統已經升級到 v2.3.1，修補了先前通報的 CVE-2026-12345 漏洞。\n",
        source_ext="md",
        hit=[("fact.missing", "2.3.1"), ("fact.missing", "CVE-2026-12345"), ("fact.added", "2.4")],
        why="SKILL.md〈檢查方式〉--source：比對代碼與版本號",
    ),
    dict(
        name="v1.3「三成」改成「30%」會被當成新增",
        ext="md",
        text="今年的客訴件數比去年減少了 30%，主要來自退貨流程的改善。\n",
        source="今年的客訴件數比去年減少了三成，主要來自退貨流程的改善。\n",
        source_ext="md",
        hit=[("fact.added", "30")],
        why="SKILL.md〈檢查方式〉：比的是阿拉伯數字，「三成」改成「30%」會被當成新增；待辦第三十一項列為已知誤報",
    ),
    dict(
        name="v1.3 潤稿改了引文內容",
        ext="md",
        text="經理在會議上說：「我們下週上線。」大家隨即分頭準備。\n",
        source="經理在會議上說：「我們下個月上線。」大家隨即分頭準備。\n",
        source_ext="md",
        hit=[("fact.missing", "我們下個月上線"), ("fact.added", "我們下週上線")],
        why="SKILL.md〈檢查方式〉--source：比對引文；第四節：引文一字不動",
    ),
    dict(
        name="v1.3 標題數量不同",
        ext="md",
        text="""# 檢查報告

## 背景

團隊這次檢查了三台主機的設定，並記錄每台主機的狀態。

## 結果

其中兩台主機需要更新憑證，另一台的設定沒有問題。
""",
        source="""# 檢查報告

## 背景

團隊這次檢查了三台主機的設定，並記錄每台主機的狀態。

## 方法

檢查人員逐台登入主機，比對設定檔與基準設定的差異。

## 結果

其中兩台主機需要更新憑證，另一台的設定沒有問題。
""",
        source_ext="md",
        hit=[("fact.count", "標題")],
        why="SKILL.md〈檢查方式〉--source：比較標題的數量",
    ),
    dict(
        name="v1.3 表格列與程式碼區塊數量不同",
        ext="md",
        text="""以下是主機的檢查狀態，詳細指令另外附在附錄。

| 主機 | 狀態 |
|---|---|
| 甲 | 正常 |
| 乙 | 憑證過期 |
""",
        source="""以下是主機的檢查狀態，詳細指令另外附在附錄。

| 主機 | 狀態 |
|---|---|
| 甲 | 正常 |
| 乙 | 憑證過期 |
| 丙 | 正常 |

```
check --all
```
""",
        source_ext="md",
        hit=[("fact.count", "表格"), ("fact.count", "程式碼")],
        why="SKILL.md〈檢查方式〉--source：比較表格列與程式碼區塊的數量",
    ),
    dict(
        name="v1.3 英翻中：日期換算後相同、引文與程式碼內容不比，不報",
        ext="md",
        text="""# 修補說明

廠商在 2026 年 3 月 5 日發布 4.2 版，修補 17 個漏洞，其中包括 CVE-2026-12345。執行長表示「我們對這次的版本很有信心」，詳細內容見公告（https://example.org/advisory）。

```
# 先檢查設定
deploy --region tw
```
""",
        source="""# Patch notes

On March 5, 2026, the vendor released version 4.2 and patched 17 vulnerabilities, including CVE-2026-12345. The CEO said "we are confident in this release". Details are in the advisory (https://example.org/advisory).

```
# check the config first
deploy --region tw
```
""",
        source_ext="md",
        hit=[],
        miss=[("fact.missing", ""), ("fact.added", ""), ("fact.count", "")],
        why="SKILL.md〈檢查方式〉：原稿中文比例低於 30% 時當成英翻中，引文與程式碼區塊的內容不比，日期換算成同一種寫法再比",
    ),
    dict(
        name="v1.3 英翻中：數字譯錯要報",
        ext="md",
        text="這次掃描在 3 台伺服器上發現 16 個漏洞，其中 2 個屬於高風險。\n",
        source="The scan found 17 vulnerabilities on 3 servers, and 2 of them are high risk.\n",
        source_ext="md",
        hit=[("fact.missing", "17"), ("fact.added", "16")],
        why="SKILL.md〈檢查方式〉與待辦第三十一項：英翻中仍比數字",
    ),

    # ── 第三十六項：輸出第一行是各類總數 ─────────────────────
    dict(
        name="v1.3 第一行是總數，含強提示與分號的計數",
        ext="md",
        text="值得注意的是，這套系統在三個月內處理了五百件申請，審核時間從十天縮短到四天；客服人員接到的重複詢問也少了一半。\n",
        hit=[("_first", "總數："), ("_first", "強提示 1"), ("_first", "分號 1"), ("_first", "痕跡 0")],
        why="SKILL.md〈檢查方式〉：每個檔案的輸出第一行是各類提醒的總數，例如「AI 腔 1（強提示 1）｜標點 2（分號 1、引號 1）｜…｜痕跡 0」",
    ),
    dict(
        name="v1.3 第一行的總數包含痕跡",
        ext="md",
        text="本報告說明三台主機的\u200b設定檢查結果，並列出需要更新的項目。\n",
        hit=[("_first", "總數："), ("_first", "痕跡 1")],
        why="SKILL.md〈檢查方式〉：第一行總數的五類包含痕跡",
    ),

    # ── 第三十九項：分號規則的例外 ───────────────────────────
    dict(
        name="v1.3 並列的每一項已經有逗號時，分號提醒要建議改句號或條列",
        ext="md",
        text="掃描發現兩個問題：一台主機關閉了驗證，任何人都能登入；另一台的憑證已經過期，瀏覽器會顯示警告。\n",
        # 2026-11-25 維護者修改：使用者 2026-11-25 決定分號規則改成「自己寫的內文不用分號，重寫整句」，不再建議拆成句號，提醒文字跟著改，預期改成新的寫法。
        hit=[("punct.semicolon", "任何人都能登入；"), ("_out", "其中一項有逗號時把短的放前面")],
        why="（推論）SKILL.md 第一節與待辦第三十九項：每一項裡已經有逗號時，改成句號各寫一句或改成條列，不要降成逗號；"
            "分號提醒的說明應該反映這個例外（說明是分號那一類的標題，不在個別提醒裡，所以比對整份輸出）",
    ),
    dict(
        name="v1.3 敘事段落裡的分號列舉照報",
        ext="md",
        text="使用者回報的狀況很多：查詢說找不到；翻到第二頁就失效；同一個查詢時好時壞。\n",
        hit=[("punct.semicolon", "")],
        why="SKILL.md 第一節：敘事段落裡的一串列舉不算可以用分號的並列，要改寫成連貫的句子",
    ),
    dict(
        name="v1.3 圖說的「左：……；右：……」照報",
        ext="md",
        text="圖 2 比較兩種部署方式（左：單一機房集中部署；右：兩地機房分散部署）。\n",
        hit=[("punct.semicolon", "")],
        why="SKILL.md 第一節：圖說的「左：……；右：……」改成「左：……。右：……」",
    ),
    dict(
        name="v1.3 程式碼裡的分號不報",
        ext="md",
        text="""設定時在同一行執行兩個指令，例如 `cd /srv; make` 即可。

```
for (i = 0; i < n; i++) { total += i; }
```
""",
        hit=[],
        miss=[("punct.semicolon", "")],
        why="SKILL.md〈檢查方式〉：程式碼不檢查",
    ),
]


# ---------- v1.3.0（2026-11-25）：多個檔案、資料夾與 --source 的命令列 ----------
CLI_CASES = [
    dict(
        name="v1.3 一次檢查多個檔案，逐檔報告，最後印合計",
        files={
            "cover.html": "<html><body><h1>期末報告</h1>"
                          "<p>本報告整理兩項發現；第一項是設定錯誤，第二項是文件過時。</p></body></html>",
            "body.md": "# 內文\n\n團隊檢查了三台主機的設定，確認其中兩台需要更新憑證。\n",
            "appendix.txt": "附錄列出每台主機的檢查紀錄，以及檢查時使用的指令。\n",
        },
        args=["cover.html", "body.md", "appendix.txt"],
        hit=["cover.html", "body.md", "appendix.txt", "總數：", "合計", "分號"],
        miss=[],
        why="SKILL.md〈檢查方式〉與待辦第三十六項：接受多個檔案，逐檔報告，最後印出全部檔案的合計",
    ),
    dict(
        name="v1.3 資料夾只檢查 .html、.htm、.md、.txt，不含子資料夾",
        files={
            "a.md": "# 甲\n\n團隊檢查了三台主機的設定。\n",
            "b.htm": "<html><body><p>封面寫著期末報告的標題。</p></body></html>",
            "c.txt": "附錄列出每台主機的檢查紀錄。\n",
            "d.csv": "主機,狀態\n甲,正常\n",
            "sub/e.md": "# 子資料夾\n\n這份不該被檢查。\n",
        },
        args=["."],
        hit=["a.md", "b.htm", "c.txt", "合計"],
        miss=["d.csv", "e.md"],
        why="SKILL.md〈檢查方式〉：資料夾裡的 .html、.htm、.md、.txt（不含子資料夾）",
    ),
    dict(
        name="v1.3 只給一個檔案時不印合計",
        files={"only.md": "# 報告\n\n團隊檢查了三台主機的設定，確認其中兩台需要更新憑證。\n"},
        args=["only.md"],
        hit=["總數："],
        miss=["合計"],
        why="（推論）SKILL.md〈檢查方式〉：「一次檢查多個檔案，最後印出合計」，單一檔案沒有合計的必要",
    ),
    dict(
        name="v1.3 命令列 --source 會印出【與原稿比對】",
        files={
            "rewrite.md": "專案會議訂在 2026 年 3 月 5 日舉行，預算上限是 150 萬元。\n",
            "orig.md": "專案會議訂在 2026 年 3 月 5 日舉行，預算上限是 120 萬元。\n",
        },
        args=["rewrite.md"],
        source="orig.md",
        hit=["與原稿比對", "120", "150"],
        miss=[],
        why="SKILL.md〈檢查方式〉：加上 --source 原稿時，另外列出【與原稿比對】",
    ),
]
