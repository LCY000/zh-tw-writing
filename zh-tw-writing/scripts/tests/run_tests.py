#!/usr/bin/env python3
"""check_zh.py 的回歸測試。

用法：python3 scripts/tests/run_tests.py

每個測試是一小段文字，寫好「應該抓到」與「不應該抓到」的提醒。
改了 check_zh.py 或 references 裡的清單之後跑一次，全部通過才算改好。
修好一個誤報或漏抓時，把那句加進來，之後就不會再犯。

應該抓到：(類別, 片段)，該類別的某一則提醒要包含這個片段。
不應該抓到：(類別, 片段)，該類別的提醒都不能包含這個片段；類別寫 None 代表所有類別。
類別寫 "_out" 代表比對整份輸出文字，"_first" 代表輸出的第一行（各類總數）。
要測 --source 時，加上 source（原稿文字）與 source_ext（"md" 或 "html"）。

除了這個檔案裡的 CASES，同一個資料夾裡 cases_*.py 的 CASES 也會一起跑，
格式相同。cases_claude.py、cases_codex.py 是另外請獨立的子代理只看規範寫的，
不看 check_zh.py 的實作，避免「自己寫程式、自己出考題」。
"""
import glob
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_zh as cz  # noqa: E402

GOOD = "這個組織主要鎖定關鍵基礎設施，偏好使用系統內建工具，很少留下惡意程式，因此防禦方必須從行為下手。"

CASES = [
    # ---------- 既有行為（v1.1.1 已經抓得到的） ----------
    dict(name="README 改寫前的範例", ext="md",
         text="值得注意的是，Microsoft在2023年首次公開這個組織。它是國家支持的駭客組織。它的目標是關鍵基礎設施。"
              "它主要使用系統內建工具；很難被偵測——防禦方必須從行為下手。\n",
         hit=[("ai.strong", "值得注意的是"), ("punct.semicolon", "；"), ("punct.dash_form", "——"),
              ("punct.cjk_space", "Microsoft在2023"), ("rhythm.short_run", "它是國家支持")]),
    dict(name="README 改寫後的範例不報標點與套話", ext="md",
         text="Microsoft 在 2023 年首次公開這個國家支持的駭客組織，它的攻擊目標是關鍵基礎設施，主要使用系統內建工具，"
              "由於很難被偵測，因此防禦方必須從行為下手。\n",
         miss=[("ai.strong", ""), ("punct.semicolon", ""), ("punct.cjk_space", ""), ("punct.dash_form", "")]),
    dict(name="引號裡的用語不檢查", ext="md",
         text="他在訪談中說「這個軟件很好用」，我們照原文引用，不另外修改內容。\n",
         miss=[("term.direct", "軟件")]),
    dict(name="引號外的中國用語要抓", ext="md",
         text="我們把軟件安裝在伺服器上，再確認服務正常啟動，最後記錄版本號碼。\n",
         hit=[("term.direct", "軟件")]),
    dict(name="台與臺混用", ext="md",
         text="台灣的資安產業正在成長，臺北的新創公司也越來越多，政府持續投入預算。\n",
         hit=[("term.taitai", "混用")]),

    # ---------- 第一項：YAML frontmatter ----------
    dict(name="略過 YAML frontmatter", ext="md",
         text="---\ntitle: 測試報告,v1\ntags: [資安, 研究]\nsummary: 本研究說明novaguard的定位,並比較三種方案\n---\n\n"
              "## 一、背景\n\n本研究說明系統的定位，並比較三種方案的差異，作為後續規劃的依據。\n",
         miss=[(None, "novaguard"), (None, "測試報告"), (None, "資安, 研究")]),
    dict(name="frontmatter 後面的內文照常檢查", ext="md",
         text="---\ntitle: 報告\n---\n\n本研究說明novaguard的定位，並比較三種方案的差異，作為後續規劃的依據。\n",
         hit=[("punct.cjk_space", "說明novaguard")]),

    # ---------- 第二項：粗體後面必要的空格 ----------
    dict(name="「**粗體句。** 內文」的空格不報", ext="md",
         text="**買方怎麼花錢。** SANS 2025 年的調查顯示，多數企業把預算放在偵測，回應的投入相對少。\n\n"
              "使用者常說 **「零信任」** 是趨勢，但做法差很多，導入前要先盤點資產。\n",
         miss=[("punct.fw_space", "")]),
    dict(name="一般的全形標點旁空格照報", ext="md",
         text="這是錯的。 後面多了空格，要提醒使用者修正這個問題，不能放過。\n",
         hit=[("punct.fw_space", "錯的。 後面")]),

    # ---------- 第三項：中文字之間的半形空格 ----------
    dict(name="中文字之間多了空格", ext="md",
         text="本研究在 第 7.1 節說明架構，並比較三種方案的優缺點，最後提出建議。\n",
         hit=[("punct.cjk_gap", "在 第")]),
    dict(name="引號內的空格不報", ext="md",
         text="原文寫成「本研究 在第七節說明」，這是從 PDF 抽出的文字，我們照原文保留。\n",
         miss=[("punct.cjk_gap", "")]),
    dict(name="Markdown 表格分隔不算", ext="md",
         text="| 項目 | 說明 |\n|---|---|\n| 偵測 | 依據行為判斷 |\n",
         miss=[("punct.cjk_gap", "")]),
    dict(name="HTML 原始碼換行不算空格", ext="html",
         text="<html><body><p>這是一段正常的內文，作者在原始碼裡換行\n繼續寫下去，讀者看到的是同一段文字。</p></body></html>",
         miss=[("punct.cjk_gap", "")]),

    # ---------- 第四項：數字與英文單位 ----------
    dict(name="數字與單位沒空格", ext="md",
         text="電網容量為 5MW，單櫃功率 30kW，匯流排電壓 800VDC，頻寬 10Gbps，儲能 2MWh。\n",
         hit=[("punct.unit", "5MW"), ("punct.unit", "30kW"), ("punct.unit", "800VDC"),
              ("punct.unit", "10Gbps"), ("punct.unit", "2MWh")]),
    dict(name="不是單位的英數字不報", ext="md",
         text="營收成長 15%，使用 5G 網路與 x86 架構，搭配 H100 晶片、3D 列印與 2FA 驗證，功率為 5 MW。\n",
         miss=[("punct.unit", "")]),

    # ---------- 第五項：「**粗體標籤：**說明」條列 ----------
    dict(name="三項以上的粗體標籤條列", ext="md",
         text="- **背景：**說明這次研究的起因與範圍。\n- **方法：**說明資料來源與分析方式。\n"
              "- **結果**：說明主要發現與限制。\n",
         hit=[("ai.bold_label", "背景")]),
    dict(name="只有兩項不報", ext="md",
         text="- **背景：**說明這次研究的起因與範圍。\n- **方法：**說明資料來源與分析方式。\n",
         miss=[("ai.bold_label", "")]),
    dict(name="HTML 的粗體標籤條列", ext="html",
         text="<html><body><ul><li><strong>背景：</strong>說明起因。</li><li><b>方法：</b>說明資料。</li>"
              "<li><strong>結果</strong>：說明發現。</li></ul></body></html>",
         hit=[("ai.bold_label", "背景")]),

    # ---------- 第六項：HTML 抽取範圍與涵蓋率 ----------
    dict(name="表格、圖說與 div 卡片的內文也要檢查", ext="html",
         text="<html><body><h2>三、觀察</h2><table><tr><td>使用線程池處理請求；另外記錄每次的結果。</td></tr></table>"
              "<figure><img src='a.png'><figcaption>左：軟件介面；右：設定畫面</figcaption></figure>"
              "<div class='card'><div>這個查詢不是找不到，而是語法寫錯了，所以要重新檢查。</div>"
              "<div>另一個問題不是漏抓，而是被過濾掉，所以要調整規則。</div></div></body></html>",
         hit=[("punct.semicolon", "線程池"), ("term.direct", "線程"), ("term.direct", "軟件"),
              ("ai.contrast", "不是找不到"), ("_out", "涵蓋")]),
    dict(name="略過目錄、mono 與程式碼", ext="html",
         text="<html><body><nav class='toc'><a>第一章背景1</a><a>第二章方法5</a></nav>"
              "<div class='toc'>第三章結果9</div>"
              "<table><tr><td class='mono'>\"會議紀錄\" site:gov.tw</td><td>用引號查詢完整詞組，結果比較精準。</td></tr></table>"
              "<pre>for i in range(3): print(\"軟件\")</pre>"
              "<p>這段正文說明查詢方式，並比較兩種寫法的差異，結果一致。</p></body></html>",
         miss=[(None, "第一章"), (None, "第三章"), ("punct.quotes", ""), ("term.direct", "軟件")]),
    dict(name="涵蓋率太低要警告", ext="html",
         text="<html><body><pre>" + "x = compute(data)\n" * 40 + "</pre>"
              "<p>這段正文說明查詢方式，並比較兩種寫法的差異，結果一致。</p></body></html>",
         hit=[("_out", "涵蓋率偏低")]),

    # ---------- 第七項：最低段落與分節比例 ----------
    dict(name="列出比例最低的段落與各節比例", ext="md",
         text="## 一、背景\n\n" + GOOD * 5 + "\n\n## 二、心得\n\n"
              "這次作業很難。我花了很多時間。查詢一直失敗。後來才找到原因。最後終於完成。\n",
         hit=[("rhythm.low_para", "這次作業很難"), ("rhythm.section", "二、心得")]),

    # ---------- 第十項：位置資訊 ----------
    dict(name="提醒附上行號與章節", ext="md",
         text="# 報告\n\n## 二、方法\n\n我們把軟件安裝在伺服器上，再確認服務正常啟動，最後記錄版本。\n",
         hit=[("term.direct", "第 5 行"), ("term.direct", "二、方法")]),
    dict(name="HTML 提醒附上行號", ext="html",
         text="<html><body>\n<h2>二、方法</h2>\n<p>我們把軟件安裝在伺服器上，再確認服務正常啟動，最後記錄版本。</p>\n</body></html>",
         hit=[("term.direct", "第 3 行"), ("term.direct", "二、方法")]),

    # ---------- 第十一項：誤報 ----------
    dict(name="網域名稱與演算法不誤報", ext="md",
         text="我們設定網域名稱，並偵測網域產生演算法的流量，確認沒有誤判的情況。\n",
         miss=[("term.direct", "域名"), ("term.direct", "算法")]),
    dict(name="單獨的算法仍然要抓", ext="md",
         text="這個算法的速度很快，但記憶體用量偏高，需要再調整參數。\n",
         hit=[("term.direct", "算法")]),
    dict(name="英文引文不算長句", ext="md",
         text="報告原文寫道：「" + "The actor used living-off-the-land techniques to blend in with normal administrative "
              "activity, which made detection difficult for defenders who relied on signatures. " * 2 + "」\n",
         miss=[("rhythm.long", "")]),
    dict(name="真正的長句照報", ext="md",
         text="這個組織" + "，偏好使用系統內建工具" * 8 + "。\n",
         hit=[("rhythm.long", "")]),

    # ---------- 用三份舊報告重跑時發現的誤報（2026-11-12） ----------
    dict(name="「只讀取」「只讀公開報告」不是唯讀", ext="md",
         text="全程被動查詢，只讀取公開紀錄與已發表的報告，也只讀公開報告與 RDAP 註冊資料，不連線到任何主機。\n",
         miss=[("term.direct", "只讀")]),
    dict(name="「直接口徑」不是接口", ext="md",
         text="方法一採用分析機構的直接口徑，2025 年的市場規模約為 42 億美元，作為主要數字。\n",
         miss=[("term.direct", "接口")]),
    dict(name="真正的接口仍然要抓", ext="md",
         text="這個服務透過 REST 接口提供資料，前端每五秒呼叫一次，回傳最新的告警清單。\n",
         hit=[("term.direct", "接口")]),
    dict(name="並排的 span 標籤與內容不黏在一起", ext="html",
         text="<html><body><div class='row'><span class='k'>我的問題</span><span>dnstwist 是什麼？它能找出哪些仿冒網域？</span></div>"
              "<div class='row'><span class='k'>AI 回答重點</span>\n<span>Pivoting 是把查到的線索當成下一步的條件，繼續往下追查。</span></div>"
              "</body></html>",
         miss=[("punct.cjk_space", "問題dnstwist"), ("punct.cjk_space", "重點Pivoting")]),
    dict(name="一般行內 span 照常接成同一句", ext="html",
         text="<html><body><p>我們用<span class='hl'>Python</span>寫腳本，再把結果整理成表格，最後交給組員確認。</p></body></html>",
         hit=[("punct.cjk_space", "用Python")]),

    # ---------- Codex 審查發現的問題（2026-11-12） ----------
    dict(name="一般段落裡相鄰的 span 照樣接成同一句", ext="html",
         text="<html><body><p>我們使用<span>軟</span><span>件處理資料，並確認系統正常運作，再交給組員。</span></p></body></html>",
         hit=[("term.direct", "軟件")]),
    dict(name="省略結束標籤的 li 不讓 mono 延伸到下一項", ext="html",
         text="<html><body><ul><li class='mono'>print(x)<li>這個軟件需要更新，請在週五前完成。</ul></body></html>",
         hit=[("term.direct", "軟件")]),
    dict(name="省略結束標籤的 td 不讓 mono 延伸到下一格", ext="html",
         text="<html><body><table><tr><td class='mono'>print(x)<td>這個軟件需要更新，請在週五前完成。</table></body></html>",
         hit=[("term.direct", "軟件")]),
    dict(name="程式碼區塊裡的粗體標籤不算", ext="md",
         text="範例如下，這是要避免的寫法，不是本文的內容。\n\n```markdown\n- **背景：**說明。\n- **方法：**說明。\n"
              "- **結果：**說明。\n```\n",
         miss=[("ai.bold_label", "")]),
    dict(name="HTML pre 裡的粗體標籤不算", ext="html",
         text="<html><body><p>範例如下，這是要避免的寫法，不是本文的內容。</p><pre><li><b>背景：</b>說明。</li>"
              "<li><b>方法：</b>說明。</li><li><b>結果：</b>說明。</li></pre></body></html>",
         miss=[("ai.bold_label", "")]),
    dict(name="單位前面是中文字也要抓", ext="md",
         text="功率為5MW，電壓是800VDC，容量達2TB，都要在數字與單位之間加空格。\n",
         hit=[("punct.unit", "5MW"), ("punct.unit", "800VDC"), ("punct.unit", "2TB")]),
    # 前 5 處附前後文，其餘列行號：同一個詞在長報告裡可能出現上百處，全部附前後文會讓輸出無法閱讀
    dict(name="看語意判斷的詞超過五處，其餘列出行號", ext="md",
         text="".join(f"第{n}份文件需要檢查，請在週五前交回。\n\n" for n in "一二三四五六"),
         hit=[("_out", "第五份文件"), ("_out", "其餘 1 處在第 11 行")]),
    dict(name="「回調」「棧」台灣也有正常用法，不直接替換", ext="md",
         text="價格回調後恢復穩定，貨棧旁的棧橋也完成整修，預計下個月開放。\n",
         miss=[("term.direct", "回調"), ("term.direct", "棧")], hit=[("term.context", "回調")]),
    dict(name="波浪號圍住的程式碼區塊不檢查", ext="md",
         text="以下是範例程式，說明變數的命名方式。\n\n~~~python\n軟件 = \"數組\"\n~~~\n",
         miss=[("term.direct", "軟件"), ("term.direct", "數組"), ("punct.quotes", "")]),
    dict(name="只有一節也列出各節比例", ext="md",
         text="## 心得\n\n這次作業很難。我花了很多時間。查詢一直失敗。後來才找到原因。最後終於完成。\n",
         hit=[("_out", "各節")]),

    # ---------- Claude 審查發現的問題（2026-11-12） ----------
    dict(name="新詞剛好是台灣常用詞的一部分，不誤報", ext="md",
         text="多數組織把中文檔案放在國內核能研究所，收集成果後在地圖標示位置，並用螢光標籤分類。"
              "團隊列出正常量測與指標量化的方法，增加載客量的方案不勝枚舉，許多任務都要看文字段落，"
              "會議也討論比特犬、布爾喬亞與間接口徑的定義。\n",
         miss=[("term.direct", "")]),
    dict(name="數組、本地化、主板、個性化、插件台灣也常用，改成看語意判斷", ext="md",
         text="學生分成數組討論，軟體本地化由廠商負責，公司在上市主板掛牌，推出個性化推薦，工廠也有插件產線。\n",
         miss=[("term.direct", "")],
         hit=[("term.context", "數組"), ("term.context", "本地化"), ("term.context", "主板"),
              ("term.context", "個性化"), ("term.context", "插件")]),
    dict(name="Markdown 提醒的行號是命中那一行", ext="md",
         text="# 報告\n\n第一行說明背景，\n第二行說明方法，\n第三行用了軟件處理資料。\n",
         hit=[("term.direct", "第 5 行")]),
    dict(name="HTML 提醒的行號是命中那一行", ext="html",
         text="<html><body>\n<p>\n   第一行說明背景，\n   第二行用了軟件處理資料。</p>\n</body></html>",
         hit=[("term.direct", "第 4 行")]),
    dict(name="開頭是 --- 分隔線不是 frontmatter", ext="md",
         text="---\n\n# 報告\n\n第一段內文用了軟件，需要修正。\n\n---\n\n第二段內文說明後續的處理方式。\n",
         hit=[("term.direct", "軟件")]),
    dict(name="程式碼多但內文都有檢查，不警告涵蓋率", ext="html",
         text="<html><body><pre>" + "x = compute(data)\n" * 40 + "</pre>"
              "<p>這段正文說明查詢方式，並比較兩種寫法的差異，結果一致。</p></body></html>",
         miss=[("_out", "⚠")], hit=[("_out", "略過的大多是程式碼")]),
    dict(name="內文被 mono 或目錄吃掉時要警告涵蓋率", ext="html",
         text="<html><body><div class='mono'>" + "這段其實是內文，卻被放進 mono 樣式裡，所以沒有被檢查。" * 5 + "</div>"
              "<p>這段正文說明查詢方式，並比較兩種寫法的差異，結果一致。</p></body></html>",
         hit=[("_out", "涵蓋率偏低")]),
    dict(name="5W1H 不是單位，負電壓要抓", ext="md",
         text="我們採用 5W1H 與 4P 分析問題，系統的直流電壓為 -48VDC，需要加上空格。\n",
         miss=[("punct.unit", "5W1H")], hit=[("punct.unit", "-48VDC")]),
    dict(name="div 段落句子中間相鄰的 span 不拆開", ext="html",
         text="<html><body><div>這是<span>軟</span><span>件的說明</span>，後面繼續說明處理方式與結果。</div></body></html>",
         hit=[("term.direct", "軟件")]),
    dict(name="全形空格不當成半形空格", ext="html",
         text="<html><body><p>全形　空格的寫法：　這裡測試，確認腳本不會把它當成半形空格。</p></body></html>",
         miss=[("punct.fw_space", ""), ("punct.cjk_gap", "")]),
    dict(name="引文裡的單位照原文，不報", ext="md",
         text="年報原文寫道「整合甲公司液冷型 3.4MW 功率調節系統」，我們照原文引用，不另外修改。\n",
         miss=[("punct.unit", "")]),
    dict(name="直接改用超過上限時，其餘列出行號", ext="md",
         text="".join(f"第{n}台伺服器的軟件需要更新，請在週五前完成。\n\n" for n in range(1, 18)),
         hit=[("_out", "其餘 2 處在第 31、33 行")]),
    dict(name="HTML 標題本身的提醒顯示自己的節名", ext="html",
         text="<html><body><h2>一、背景</h2><p>這段正文說明查詢方式，並比較兩種寫法的差異，結果一致。</p>"
              "<h2>二、軟件設定</h2><p>這段正文說明設定方式，並比較兩種寫法的差異，結果一致。</p></body></html>",
         hit=[("term.direct", "〈二、軟件設定〉")]),
    dict(name="id 是 toc 的目錄也略過", ext="html",
         text="<html><body><div id='toc'>第一章背景1</div><p>這段正文說明查詢方式，並比較兩種寫法的差異，結果一致。</p></body></html>",
         miss=[(None, "第一章")]),

    # ---------- Claude 第二輪複查發現的問題（2026-11-12） ----------
    dict(name="長引文不影響「不是…而是…」的計算", ext="md",
         text="問題不是「這個工具在第二頁之後就完全失效而且沒有任何錯誤訊息可以參考」，而是我們沒有先驗證。\n\n"
              "另一個問題不是漏抓，而是被過濾掉，所以要調整規則。\n",
         hit=[("ai.contrast", "問題不是")]),
    dict(name="前後文跳過引文後仍顯示後面的字", ext="md",
         text="值得注意的是「這個工具在第二頁之後就完全失效而且沒有任何錯誤訊息」，我們後來改用別的方法查詢。\n",
         hit=[("ai.strong", "」，我們")]),
    dict(name="比例最低的段落超過 8 段時，其餘列出行號", ext="md",
         text="".join(f"第{n}週完成一件事。結果還可以。下週繼續處理。\n\n" for n in "一二三四五六七八九十"),
         hit=[("_out", "其餘 2 段在第 17、19 行")]),
    dict(name="巢狀引號裡的單位也照原文", ext="md",
         text="年報寫道「甲公司表示「系統」已擴充，容量達5MW / 7.68MWh」，我們照原文引用，不另外修改。\n",
         miss=[("punct.unit", "")]),

    # ---------- Codex 第二輪複查發現的問題（2026-11-12） ----------
    dict(name="四個反引號的區塊裡有三個反引號，仍然整塊略過", ext="md",
         text="範例如下，說明程式碼區塊的寫法。\n\n````markdown\n```\n軟件 = 數組\n```\n軟件 = 數組\n````\n",
         miss=[("term.direct", "")]),
    dict(name="縮排四格的程式碼不檢查", ext="md",
         text="範例如下，說明程式碼的寫法。\n\n    軟件 = \"數組\"\n\n後面是正常的內文，說明處理方式。\n",
         miss=[("term.direct", ""), ("punct.quotes", "")]),
    dict(name="清單項目的縮排續行不是程式碼", ext="md",
         text="- 第一項說明背景，內容比較長，\n\n    續行用了軟件，需要修正。\n",
         hit=[("term.direct", "軟件")]),
    dict(name="沒關閉的程式碼區塊一路略過到檔尾", ext="md",
         text="範例如下，說明程式碼的寫法。\n\n```\n軟件 = 數組\n",
         miss=[("term.direct", "")]),
    dict(name="省略結束標籤的 tr 不讓 mono 延伸到下一列", ext="html",
         text="<html><body><table>\n<tr class='mono'><td>print(x)\n<tr><td>這個軟件需要更新，請在週五前完成。\n</table></body></html>",
         hit=[("term.direct", "第 3 行")]),
    dict(name="長書名不影響外面的套話", ext="md",
         text="隨著《這是一個很長而且不能隨意修改的技術名稱》的快速發展，我們完成相關工作。\n",
         hit=[("ai.strong", "隨著")]),
    dict(name="長的『』引文不影響「不是…而是…」", ext="md",
         text="問題不是『這個工具在第二頁之後就完全失效而且沒有任何錯誤訊息可以參考』而是我們沒有先驗證。\n\n"
              "另一個問題不是『這個查詢語法在不同的瀏覽器裡面會得到完全不一樣的搜尋結果』而是快取。\n",
         hit=[("ai.contrast", "問題不是")]),
    dict(name="粗體標籤不掃 frontmatter", ext="md",
         text="---\ntitle: 報告\nsummary: |\n  - **背景：**說明。\n  - **方法：**說明。\n  - **結果：**說明。\n---\n\n"
              "這是正常的內文段落，說明研究的背景與方法。\n",
         miss=[("ai.bold_label", "")]),
    dict(name="粗體標籤不掃 HTML 註解與導覽", ext="html",
         text="<html><body><!--\n<ul><li><b>背景：</b>說明。</li><li><b>方法：</b>說明。</li><li><b>結果：</b>說明。</li></ul>\n-->"
              "<nav><ul><li><b>背景：</b>說明。</li><li><b>方法：</b>說明。</li><li><b>結果：</b>說明。</li></ul></nav>"
              "<p>這是正常的內文段落，說明研究的背景與方法。</p></body></html>",
         miss=[("ai.bold_label", "")]),
    dict(name="檔名裡的數字與單位不報", ext="md",
         text="請保留檔名 30kW.txt 與路徑 data/5MW，這是我們用來測試的檔案名稱，不要修改其中的數字或字母。\n",
         miss=[("punct.unit", "")]),
    dict(name="HTML 的換行實體不增加行號", ext="html",
         text="<html><body><p>目前正常。&#10;這個軟件需要更新，請在週五前完成。</p></body></html>",
         hit=[("term.direct", "第 1 行")]),

    # ---------- Codex 第三輪確認發現的問題（2026-11-12） ----------
    dict(name="清單項目裡縮排的程式碼不檢查", ext="md",
         text="- 項目說明如下\n\n      軟件 = \"數組\"\n\n正常的內文用了軟件，需要修正。\n",
         hit=[("term.direct", "第 5 行")], miss=[("term.direct", "第 3 行"), ("punct.quotes", "")]),
    dict(name="清單項目裡的程式碼區塊不檢查，後面的內文照常檢查", ext="md",
         text="- ```python\n  軟件 = 數組\n  ```\n\n正常的內文用了軟件，需要修正。\n",
         hit=[("term.direct", "第 5 行")], miss=[("term.direct", "第 2 行")]),
    dict(name="縮排程式碼裡的 ``` 不是程式碼區塊開頭", ext="md",
         text="    ```\n    軟件 = 數組\n\n正常的內文用了軟件，需要修正。\n",
         hit=[("term.direct", "第 4 行")], miss=[("term.direct", "第 2 行")]),
    dict(name="清單結束後的粗體段落不算粗體標籤", ext="html",
         text="<html><body><ul><li> </li></ul>\n<p><b>背景：</b>正常說明。</p>\n<ul><li> </li></ul>\n"
              "<p><b>方法：</b>正常說明。</p>\n<ul><li> </li></ul>\n<p><b>結果：</b>正常說明。</p>\n</body></html>",
         miss=[("ai.bold_label", "")]),

    # ---------- v1.3.0 第二十八項：複合詞與補充的用語 ----------
    dict(name="視頻通話、打印機報成完整的台灣說法，不拆成兩半", ext="md",
         text="我們用視頻通話開會，再用激光打印機印出清單，另一台打印機放在二樓。\n",
         hit=[("term.direct", "「視頻通話」→「視訊通話」"), ("term.direct", "「激光打印機」→「雷射印表機」"),
              ("term.direct", "「打印機」→「印表機」")],
         miss=[("term.direct", "「視頻」→"), ("term.direct", "「激光」→"), ("term.direct", "「打印」→")]),
    dict(name="補充的中國用語", ext="md",
         text="請把賬號、二維碼與手機號寄到郵箱，筆記本電腦宕機後再用光盤重裝，便利店也能繳費。\n",
         hit=[("term.direct", "賬號"), ("term.direct", "二維碼"), ("term.direct", "「手機號」→"), ("term.direct", "郵箱"),
              ("term.direct", "筆記本電腦"), ("term.direct", "宕機"), ("term.direct", "光盤"), ("term.direct", "便利店")]),
    dict(name="補充的用語不誤報台灣的正常說法", ext="md",
         text="這款手機號稱續航兩天，手機號碼要填完整，賭博主要發生在夜間，致死機率很低，批發貨品先入庫，"
              "日本周邊的景點很多，基本周期為三天，他是本科系畢業。\n",
         miss=[("term.direct", ""), ("term.context", "本周"), ("term.context", "本科")]),
    dict(name="周末、工資、渠道放在看語意判斷", ext="md",
         text="員工的工資在周末發放，業務透過三個渠道銷售，下周再檢討。\n",
         miss=[("term.direct", "")],
         hit=[("term.context", "「周末」"), ("term.context", "「工資」"), ("term.context", "「渠道」"), ("term.context", "「下周」")]),

    # ---------- v1.3.0 第二十九項：台灣慣用字形 ----------
    dict(name="台灣不用的字形", ext="md",
         text="這裏的綫路爲了穩定，内容要説明清楚，着手處理户政資料。\n",
         hit=[("term.glyph", "「裏」→「裡」"), ("term.glyph", "「綫」→「線」"), ("term.glyph", "「爲」→「為」"),
              ("term.glyph", "「内」→「內」"), ("term.glyph", "「説」→「說」"), ("term.glyph", "「着」→「著」"),
              ("term.glyph", "「户」→「戶」")]),
    dict(name="台灣字形與引文裡的字形不報", ext="md",
         text="這裡的線路為了穩定，內容要說明清楚。原文寫「這裏的綫路」，我們照原文引用。\n",
         miss=[("term.glyph", "")]),

    # ---------- v1.3.0 第三十項：痕跡 ----------
    dict(name="零寬空格與不換行空格", ext="md",
         text="這段文字\u200b夾了零寬空格，這裡\u00a0也有不換行空格，需要清掉。\n",
         hit=[("trace.invisible", "零寬空格（U+200B）"), ("trace.invisible", "不換行空格（U+00A0）")]),
    dict(name="檔首 BOM 與表情符號的零寬連字不報", ext="md",
         text="\ufeff這份文件開頭有 BOM，表情符號👨\u200d💻是一個組合字，不算隱形字元。\n",
         miss=[("trace.invisible", "")]),
    dict(name="HTML 的 &nbsp; 實體不報", ext="html",
         text="<html><body><p>這段文字用了實體&nbsp;空格，是作者刻意寫的排版，不算夾帶的字元。</p></body></html>",
         miss=[("trace.invisible", "")]),
    dict(name="連結網址裡的 utm 參數與檢索標記", ext="html",
         text="<html><body><p>詳見<a href='https://example.com/a?utm_source=chatgpt.com'>這份公告</a>，"
              "也可以參考 turn0search0 的說明。</p></body></html>",
         hit=[("trace.tool", "utm_source=chatgpt.com"), ("trace.tool", "turn0search0")]),
    dict(name="Gemini 與 ChatGPT 的引用標記", ext="md",
         text="該漏洞影響 3.2 版以前的所有版本 [cite: 1, 3]，廠商已發布修補程式【4:0†source】。\n",
         hit=[("trace.tool", "[cite: 1, 3]"), ("trace.tool", "【4:0†source】")]),
    dict(name="程式碼裡的痕跡與 TODO 不報", ext="md",
         text="範例如下，說明如何移除追蹤參數。\n\n```python\nurl = url.replace('utm_source=chatgpt.com', '')  # TODO\n```\n\n"
              "行內的 `turn0search0` 也是範例。\n",
         miss=[("trace.tool", ""), ("trace.placeholder", "")]),
    dict(name="沒填的佔位文字", ext="md",
         text="聯絡人：【請在此處填寫】，預算 TBD，負責單位 XXX，其餘待討論。\n\n| 項目 | 狀態 |\n|---|---|\n| 測試 | TODO |\n",
         hit=[("trace.placeholder", "【請在此處填寫】"), ("trace.placeholder", "TBD"), ("trace.placeholder", "XXX"),
              ("trace.placeholder", "TODO")]),
    dict(name="引文裡的佔位文字與英文單字裡的 X 不報", ext="md",
         text="範本原文寫「預算 TBD」，我們照原文引用，另外 XXXL 是衣服尺寸，TODOS 是產品名稱。\n",
         miss=[("trace.placeholder", "")]),

    # ---------- v1.3.0 第三十六項：輸出開頭先印總數 ----------
    dict(name="輸出第一行是各類總數", ext="md",
         text="值得注意的是，甲單位負責審核；乙單位負責追蹤，這是我們的分工方式。\n",
         hit=[("_first", "總數："), ("_first", "AI 腔 1（強提示 1）"), ("_first", "標點 1（分號 1）")]),
    dict(name="沒有中文內容時也有總數，痕跡照樣檢查", ext="md",
         text="This document is written in English.\u200b See https://a.example/?utm_source=openai for details.\n",
         hit=[("_first", "找不到中文內容"), ("trace.invisible", "零寬空格"), ("trace.tool", "utm_source=openai")]),

    # ---------- v1.3.0 第三十九項：分號規則的例外 ----------
    dict(name="分號提醒寫出其中一項有逗號時怎麼重寫", ext="md",
         text="掃描發現兩個問題：一台主機關閉了驗證，任何人都能登入；另一台的憑證已經過期，瀏覽器會顯示警告。\n",
         hit=[("_out", "其中一項有逗號時把短的放前面")]),

    # ---------- v1.3.0 第三十一項：--source 事實比對 ----------
    dict(name="潤稿：遺失與新增的數字、代碼、網址、程式碼", ext="md",
         source="2026 年 3 月 5 日上線，共 3,200 筆資料，版本 v1.2.0，代碼 CVE-2024-3400，詳見 https://example.com/a 。\n\n"
                "```\nprint(1)\n```\n", source_ext="md",
         text="系統在2026年3月5日上線，共 3,200 筆資料，版本 v1.2.0，代碼 CVE-2024-3401，效率提升 42%。\n",
         hit=[("fact.missing", "代碼「CVE-2024-3400」"), ("fact.missing", "網址「https://example.com/a」"),
              ("fact.missing", "程式碼區塊"), ("fact.added", "代碼「CVE-2024-3401」"), ("fact.added", "數字「42%」"),
              ("fact.count", "程式碼區塊：原稿 1 個，改寫稿 0 個"), ("_out", "比對模式：潤稿")],
         miss=[("fact.missing", "3,200"), ("fact.missing", "2026"), ("fact.missing", "1.2.0"), ("fact.added", "3200")]),
    dict(name="潤稿：引文改了一個字要報", ext="md",
         source="負責人說「我們會在 9 月改版」，請大家配合。\n", source_ext="md",
         text="負責人說「我們將在 9 月改版」，請大家配合。\n",
         hit=[("fact.missing", "引文「我們會在 9 月改版」"), ("fact.added", "引文「我們將在 9 月改版」")]),
    # 潤稿要一字不動，所以比原文寫法：數值相同但寫法改了也要報，只有空格不算（兩位審查者都指出）
    dict(name="潤稿：數字與日期的寫法改了要報，只差空格不報", ext="md",
         source="這項計畫的費用為 350 萬元，共 3,200 筆，2026 年 3 月 5 日上線。\n", source_ext="md",
         text="這項計畫花費 3.5 百萬元，共 3200 筆，2026/3/5 上線。\n",
         hit=[("fact.missing", "數字「350 萬」"), ("fact.added", "數字「3.5 百萬」"), ("fact.missing", "數字「3,200」"),
              ("fact.missing", "日期「2026 年 3 月 5 日」"), ("fact.added", "日期「2026/3/5」")]),
    dict(name="潤稿：只補了空格不算改", ext="md",
         source="這項計畫的費用為350萬元，2026年3月5日上線，版本v1.2.0。\n", source_ext="md",
         text="這項計畫的費用為 350 萬元，2026 年 3 月 5 日上線，版本 v1.2.0。\n",
         miss=[("fact.missing", ""), ("fact.added", "")], hit=[("_out", "沒有發現遺失或新增")]),
    dict(name="英翻中：只寫月份的英文月名不把「3 月」的 3 當成新增", ext="md",
         source="The service launched in March and was redesigned in September.\n", source_ext="md",
         text="服務在 3 月上線，9 月改版。\n",
         miss=[("fact.missing", ""), ("fact.added", "")]),
    dict(name="HTML 裡的識別字不算佔位文字", ext="html",
         text="<html><body><p>TODO_LIST 與 FIXME_v2 是系統裡的變數名稱，照原樣保留。</p></body></html>",
         miss=[("trace.placeholder", "")]),
    dict(name="比例偏低的段落超過 8 段時，總數算進全部", ext="md",
         text="".join(f"第{n}週完成一件事。結果還可以。下週繼續處理。\n\n" for n in "一二三四五六七八九十"),
         hit=[("_first", "比例偏低的段落 10")]),
    dict(name="英翻中：日期、金額、網址、信箱換寫法不報", ext="md",
         source="The system went live on March 5, 2026 with 3,200 records. It cost 3.5 million dollars. "
                "See https://example.com/a and contact admin@example.com. Version v1.2.0 fixed CVE-2024-3400.\n",
         source_ext="md",
         text="系統在 2026 年 3 月 5 日上線，共有 3,200 筆紀錄，花費 350 萬美元，詳見 https://example.com/a，"
              "或聯絡 admin@example.com。1.2.0 版修正了 CVE-2024-3400。\n",
         miss=[("fact.missing", ""), ("fact.added", "")], hit=[("_out", "比對模式：英翻中")]),
    dict(name="英翻中：漏譯的數字與多出來的推算要報，引文不比", ext="md",
         source="The service launched in March and was redesigned in September. About 40% of users \"loved it\".\n",
         source_ext="md",
         text="服務在 3 月上線，上線 6 個月後改版，使用者都說「很喜歡」。\n",
         hit=[("fact.missing", "數字「40%」"), ("fact.added", "數字「6」")],
         # Claude 審查指出：原稿的 in March 譯成「3 月」不能報成新增的數字
         # （這題沒寫 miss 所以之前沒發現），September 沒譯出來，要報遺失
         # 2026-11-25 補上

         miss=[("fact.missing", "引文"), ("fact.added", "引文")]),
    dict(name="HTML 改寫稿對照 Markdown 原稿：標題與連結數量", ext="html",
         source="# 報告\n\n## 背景\n\n詳見 [公告](https://example.com/a)。\n\n## 方法\n\n說明方法。\n", source_ext="md",
         text="<html><body><h1>報告</h1><h2>背景</h2><p>詳見<a href='https://example.com/a'>公告</a>。</p>"
              "<p>說明方法。</p></body></html>",
         hit=[("fact.count", "標題：原稿 3 個，改寫稿 2 個")],
         miss=[("fact.missing", "網址"), ("fact.count", "連結")]),

    # ---------- Codex 第一輪審查發現的問題（2026-11-25） ----------
    dict(name="程式碼區塊裡的空格與全形數字照原樣比", ext="md",
         source="範例如下，說明輸出格式。\n\n```python\nprint(\"a b\")\nprint(\"１\")\n```\n", source_ext="md",
         text="範例如下，說明輸出格式。\n\n```python\nprint(\"a  b\")\nprint(\"1\")\n```\n",
         hit=[("fact.missing", "程式碼區塊"), ("fact.added", "程式碼區塊")]),
    dict(name="負號與百分比改掉要報", ext="md",
         source="溫度為 -5 度，成功率為 50%，範圍是第 5-10 頁。\n", source_ext="md",
         text="溫度為 5 度，成功率為 50，範圍是第 5-10 頁。\n",
         hit=[("fact.missing", "數字「-5」"), ("fact.missing", "數字「50%」"), ("fact.added", "數字「5」")],
         miss=[("fact.missing", "10"), ("fact.added", "10")]),
    dict(name="HTML 行內標籤與實體不切斷數字", ext="html",
         source="<html><body><p>數量為 123 筆，另有 45 筆待確認。</p></body></html>", source_ext="html",
         text="<html><body><p>數量為 1<strong>23</strong> 筆，另有 &#52;5 筆待確認。</p></body></html>",
         miss=[("fact.missing", ""), ("fact.added", "")]),
    dict(name="相鄰的兩個程式碼區塊合成一個要報", ext="md",
         source="範例如下。\n\n```\na\n```\n```\nb\n```\n", source_ext="md",
         text="範例如下。\n\n```\na\nb\n```\n",
         hit=[("fact.count", "程式碼區塊：原稿 2 個，改寫稿 1 個")]),
    dict(name="沒有引號的 href 與顯示網址的連結都只算一次", ext="html",
         source="詳見 <https://example.com/a>，另見 [公告](https://example.com/b)。\n", source_ext="md",
         text="<html><body><p>詳見 <a href=https://example.com/a>https://example.com/a</a>，"
              "另見<a href='https://example.com/b'>公告</a>。</p></body></html>",
         miss=[("fact.missing", ""), ("fact.added", ""), ("fact.count", "")]),
    dict(name="很長的數字改了最後一位也要報", ext="md",
         source="編號 123456789012345678901234567890 已登記。\n", source_ext="md",
         text="編號 123456789012345678901234567891 已登記。\n",
         hit=[("fact.missing", "123456789012345678901234567890")]),
    dict(name="不是組合表情符號的零寬連字要報", ext="md",
         text="中文😀\u200d文字夾帶痕跡，要清掉這個字元。\n",
         hit=[("trace.invisible", "零寬連字")]),
    dict(name="台灣的「應聘」也指接受聘請，放在看語意判斷", ext="md",
         text="他應聘回國任教，下學期開始授課。\n",
         miss=[("term.direct", "應聘")], hit=[("term.context", "應聘")]),
    dict(name="教育部正字「脣」不算台灣不用的字形", ext="md",
         text="這是脣顎裂的衛教文件，請家長詳閱。\n",
         miss=[("term.glyph", "")]),

    # ---------- Codex 第二輪審查發現的問題（2026-11-25） ----------
    dict(name="程式碼的行尾空白也照原樣比", ext="md",
         source="範例如下。\n\n```python\ns = \"\"\"a  \nb\"\"\"\n```\n", source_ext="md",
         text="範例如下。\n\n```python\ns = \"\"\"a\nb\"\"\"\n```\n",
         hit=[("fact.missing", "程式碼區塊")]),
    dict(name="四個反引號裡的三個反引號是內容，不拆開", ext="md",
         source="範例如下。\n\n````markdown\n```python\nprint(1)\n```\n````\n", source_ext="md",
         text="範例如下。\n\n````markdown\n```javascript\nprint(1)\n```\n````\n",
         hit=[("fact.missing", "程式碼區塊「```python…」")], miss=[("fact.count", "")]),
    dict(name="連結文字包含網址但目標不同，照樣比對目標", ext="html",
         source="<html><body><p>見<a href='https://example.org/a'>https://example.org/abc</a>。</p></body></html>",
         source_ext="html",
         text="<html><body><p>見<a href='https://example.org/ab'>https://example.org/abc</a>。</p></body></html>",
         hit=[("fact.missing", "https://example.org/a」"), ("fact.added", "https://example.org/ab」")]),
    dict(name="潤稿：全形數字改成半形也要報", ext="md",
         source="共１２３筆，２０３１年３月５日上線。\n", source_ext="md",
         text="共 123 筆，2031 年 3 月 5 日上線。\n",
         hit=[("fact.missing", "數字「１２３」"), ("fact.added", "數字「123」")]),
    dict(name="HTML 屬性引號裡的 > 不讓屬性變成正文", ext="html",
         source="<html><body><p title=\"1 > 2\">總數為 100 筆。</p></body></html>", source_ext="html",
         text="<html><body><p title=\"2 > 1\">總數為 100 筆。</p></body></html>",
         miss=[("fact.missing", ""), ("fact.added", "")]),
    dict(name="Markdown 裡底線開頭或結尾的識別字不算佔位文字", ext="md",
         text="變數 TODO_LIST、MAX_XXX_ID 與 _TODO 是程式裡的名稱，照原樣保留。\n",
         miss=[("trace.placeholder", "")]),
    dict(name="英翻中：情態動詞 May 不當成月份", ext="md",
         source="May I send 3 files to the team?\n", source_ext="md",
         text="我可以把 3 個檔案寄給團隊嗎？\n",
         miss=[("fact.missing", ""), ("fact.added", "")]),

    # ---------- Claude 第二輪審查發現的問題（2026-11-25） ----------
    dict(name="潤稿：引文裡只補了中英空格，不算改了引文", ext="md",
         source="主管說「我們今年用AI處理了3200件客訴」，請大家參考。\n", source_ext="md",
         text="主管說「我們今年用 AI 處理了 3200 件客訴」，請大家參考。\n",
         miss=[("fact.missing", ""), ("fact.added", "")]),
    dict(name="網址後面緊接的中文與全形冒號不算進網址", ext="md",
         source="詳見https://example.com/x的說明，或https://example.com/y：請見附錄。\n", source_ext="md",
         text="詳見 https://example.com/x 的說明，或 https://example.com/y：請見附錄。\n",
         miss=[("fact.missing", ""), ("fact.added", "")]),
    dict(name="英文術語多的中文技術文件不當成英翻中", ext="md",
         source="Kubernetes 的 Deployment 透過 ReplicaSet 管理 Pod，預設保留 3,200 筆 revision history，"
                "詳見 https://kubernetes.example.org/docs/concepts/workloads/controllers/deployment 。\n", source_ext="md",
         text="Kubernetes 的 Deployment 透過 ReplicaSet 管理 Pod，預設保留 3200 筆 revision history，"
              "詳見 https://kubernetes.example.org/docs/concepts/workloads/controllers/deployment 。\n",
         hit=[("_out", "比對模式：潤稿"), ("fact.missing", "數字「3,200」")]),
    dict(name="比例最低的段落超過 8 段時，標題寫出總段數", ext="md",
         text="".join(f"第{n}週完成一件事。結果還可以。下週繼續處理。\n\n" for n in "一二三四五六七八九十"),
         hit=[("_out", "共 10 段，列出最低的 8 段")]),
    dict(name="「光盤點」不算光盤", ext="md",
         text="倉庫用燈光盤點庫存，每週一次，結果交給主管確認。\n",
         miss=[("term.direct", "光盤")]),

    # ---------- 行為 eval 發現的誤報（2026-11-25） ----------
    dict(name="潤稿：名稱從「」改成《》不算引文遺失", ext="md",
         source="本計畫依「資料開放規範」辦理，並於 3 月公告。\n", source_ext="md",
         text="本計畫依《資料開放規範》辦理，並於 3 月公告。\n",
         miss=[("fact.missing", ""), ("fact.added", "")]),

    # ---------- v1.3.0 定案前的調整（2026-11-25） ----------
    dict(name="HTML 的 blockquote 和 Markdown 的 > 一樣略過，外面的照常檢查", ext="html",
         text="<html><body><blockquote><p>受訪者說：軟件更新後；登入就失敗。</p></blockquote>"
              "<p>這段正文提到軟件更新，另外記錄每次的結果；結果一致。</p></body></html>",
         hit=[("term.direct", "正文提到軟件"), ("punct.semicolon", "結果；結果")],
         miss=[("term.direct", "受訪者"), ("punct.semicolon", "登入")]),
    dict(name="分號提醒寫的是重寫整句，不再叫人改成句號", ext="md",
         text="甲單位負責審核申請；乙單位負責追蹤進度，兩邊每週對一次結果。\n",
         hit=[("_out", "自己寫的內文不用分號"), ("punct.semicolon", "審核申請")],
         miss=[("_out", "改用句號分開")]),

    # ---------- 第十三項：看語意判斷要附前後文 ----------
    dict(name="看語意判斷的詞附前後文", ext="md",
         text="請把文件存到共用資料夾，再把結果整理成表格，最後確認格式正確。\n",
         hit=[("term.context", "存到共用")]),
]


def run_case(c):
    src = (c["source"], c.get("source_ext") == "html") if "source" in c else None
    rep = cz.analyze(c["text"], html_mode=(c["ext"] == "html"), source=src)
    out = "\n".join(rep.lines)
    errors = []

    def pool(key):
        if key == "_out":
            return [out]
        if key == "_first":
            return rep.lines[:1]
        if key is None:
            return [h for hs in rep.hits.values() for h in hs]
        return rep.hits.get(key, [])

    for key, frag in c.get("hit", []):
        if not any(frag in h for h in pool(key)):
            errors.append(f"該抓沒抓到：{key}「{frag}」")
    for key, frag in c.get("miss", []):
        bad = [h for h in pool(key) if frag in h]
        if bad:
            errors.append(f"不該抓卻抓到：{key}「{frag}」→ {bad[0]}")
    return errors, out


SPACING = [
    # (說明, 是否 HTML, 原文, 預期結果)
    ("Markdown 不動 frontmatter 與行內程式碼", False,
     "---\ntitle: 報告v1\n---\n\n使用Python寫`a=1中文`的程式。\n",
     "---\ntitle: 報告v1\n---\n\n使用 Python 寫 `a=1中文` 的程式。\n"),
    ("``` 區塊裡出現 ~~~ 時不提早結束保護", False,
     "使用Python。\n\n```\n中文Python\n~~~\n中文Python\n```\n", "使用 Python。\n\n```\n中文Python\n~~~\n中文Python\n```\n"),
    ("清單項目裡的程式碼不補空格", False,
     "- 項目\n\n      中文Python\n\n- ```python\n  中文Python\n  ```\n\n正常中文Python。\n",
     "- 項目\n\n      中文Python\n\n- ```python\n  中文Python\n  ```\n\n正常中文 Python。\n"),
    ("縮排程式碼裡的 ``` 不會一路保護到檔尾", False,
     "    ```\n    中文Python\n\n正常中文Python。\n", "    ```\n    中文Python\n\n正常中文 Python。\n"),
    ("縮排四格的程式碼不補空格", False,
     "使用Python。\n\n    x=1中文Python\n", "使用 Python。\n\n    x=1中文Python\n"),
    # 以下 14 個情況來自 Codex 第四輪確認，預期結果依 CommonMark 實際渲染：程式碼裡的不動，內文的補空格
    ("CommonMark：清單裡縮排不足四格的是內文", False, '- 項目\n\n    中文Python\n', '- 項目\n\n    中文 Python\n'),
    ("CommonMark：巢狀清單退回外層後的縮排程式碼", False, '- 外層\n  - 內層\n\n  外層續段\n\n      中文Python\n', '- 外層\n  - 內層\n\n  外層續段\n\n      中文Python\n'),
    ("CommonMark：巢狀清單退回外層後的一般內文", False, '- 外層\n  - 內層\n\n  外層續段\n\n    一般中文Python。\n', '- 外層\n  - 內層\n\n  外層續段\n\n    一般中文 Python。\n'),
    ("CommonMark：清單裡沒關閉的圍欄在清單結束時結束", False, '- ```\n  中文Python\n\n正常中文Python。\n', '- ```\n  中文Python\n\n正常中文 Python。\n'),
    ("CommonMark：縮排太深的 ``` 不是結尾圍欄", False, '```\n    ```\n中文Python\n```\n', '```\n    ```\n中文Python\n```\n'),
    ("CommonMark：清單符號後五格空白是縮排程式碼", False, '-     中文Python\n', '-     中文Python\n'),
    ("CommonMark：同一行巢狀清單的圍欄", False, '- - ```\n    中文Python\n    ```\n\n正常中文Python。\n', '- - ```\n    中文Python\n    ```\n\n正常中文 Python。\n'),
    ("CommonMark：tab 縮排的清單程式碼", False, '-\t項目\n\n\t\t中文Python\n', '-\t項目\n\n\t\t中文Python\n'),
    ("CommonMark：編號清單的縮排程式碼", False, '123. 項目\n\n         中文Python\n', '123. 項目\n\n         中文Python\n'),
    ("CommonMark：懶惰續行後的縮排程式碼", False, '- 項目\n懶惰續行\n\n      中文Python\n', '- 項目\n懶惰續行\n\n      中文Python\n'),
    ("CommonMark：清單後的段落與縮排程式碼", False, '- 項目\n\n正常中文Python。\n\n    中文Python\n', '- 項目\n\n正常中文 Python。\n\n    中文Python\n'),
    ("CommonMark：內層懶惰續行後縮排不足的是內文", False, '- 外層\n  - 內層\n外層懶惰續行\n\n      中文Python\n', '- 外層\n  - 內層\n外層懶惰續行\n\n      中文 Python\n'),
    ("CommonMark：空清單項目後的縮排程式碼", False, '-\n\n      中文Python\n', '-\n\n      中文Python\n'),
    ("CommonMark：資訊字串含反引號的不是圍欄", False, '```foo`bar\n正常中文Python。\n', '```foo`bar\n正常中文 Python。\n'),
    ("Markdown 不動波浪號程式碼區塊", False,
     "使用Python。\n\n~~~\nx=1中文\n~~~\n", "使用 Python。\n\n~~~\nx=1中文\n~~~\n"),
    ("HTML 不動屬性、註解與程式碼，數字照補", True,
     "<html><body><p class=\"x1\" title=\"中A\">使用Python。</p><!-- 中B --><p>2026年報告<code>a中</code>完成</p>"
     "<pre>x=1中文</pre></body></html>",
     "<html><body><p class=\"x1\" title=\"中A\">使用 Python。</p><!-- 中B --><p>2026 年報告 <code>a中</code>完成</p>"
     "<pre>x=1中文</pre></body></html>"),
]


def run_spacing():
    errors = []
    for name, html_mode, src, want in SPACING:
        try:
            got = cz.spaced(src, html_mode=html_mode)
        except Exception as e:  # noqa: BLE001
            got = f"當掉：{e!r}"
        if got != want:
            errors.append(f"--fix-spacing（{name}）結果不對：\n   得到 {got!r}\n   預期 {want!r}")
    return errors


def all_cases():
    cases = [dict(c, src="run_tests") for c in CASES]
    here = os.path.dirname(os.path.abspath(__file__))
    for path in sorted(glob.glob(os.path.join(here, "cases_*.py"))):
        spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cases += [dict(c, src=os.path.basename(path)[6:-3]) for c in mod.CASES]
    return cases


INVISIBLE_SRC = set("\u200b\u200c\u200d\ufeff\u2060\u00a0\u2009\u202f")


def run_source_check():
    """check_zh.py 與測試檔裡不能有看不見的字元（零寬空格、BOM、不換行空格、Unicode 私用區），
    要用 \\u 跳脫或 chr() 產生。這類字元在編輯或複製時很容易消失或被換掉，
    v1.2.0 開發時發生過兩次，v1.3.0 新增痕跡檢查時，寫進去的跳脫字元也被編輯工具換成了字元本身。"""
    here = os.path.dirname(os.path.abspath(__file__))
    paths = [os.path.join(here, "..", "check_zh.py")] + sorted(glob.glob(os.path.join(here, "*.py")))
    errors = []
    for path in paths:
        bad = [i for i, line in enumerate(open(path, encoding="utf-8"), 1)
               if any(c in INVISIBLE_SRC or "\ue000" <= c <= "\uf8ff" for c in line)]
        if bad:
            errors.append(f"{os.path.basename(path)} 第 {', '.join(map(str, bad))} 行有看不見的字元，請改用 \\u 跳脫或 chr() 產生")
    return errors


def run_cli():
    """多個檔案、資料夾與 --source 的參數組合，用暫存檔測 cz.run()。"""
    import tempfile
    errors = []
    with tempfile.TemporaryDirectory() as d:
        def w(name, text):
            p = os.path.join(d, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            return p
        cover = w("1_cover.html", "<html><body><p>重點：甲單位負責審核；乙單位負責追蹤，兩邊每週開會。</p></body></html>")
        body = w("2_body.md", "值得注意的是，這份報告說明系統的架構與測試結果，並提出改善建議。\n")
        w("notes.bak", "這個檔案不是 .md，不能被檢查。值得注意的是。\n")
        out = cz.run([cover, body])
        for frag in ("━━━━ " + cover, "━━━━ " + body, "全部 2 個檔案合計", "標點 1（分號 1）", "AI 腔 1（強提示 1）",
                     "1_cover.html：逗號比例"):
            if frag not in out:
                errors.append(f"多個檔案：輸出缺少「{frag}」")
        out = cz.run([d])
        if "全部 2 個檔案合計" not in out or "notes.bak" in out:
            errors.append("資料夾：應該只檢查 .html、.md 兩個檔案")
        out = cz.run([cover, body], source=body)
        if "只能搭配一個" not in out:
            errors.append("--source 搭配多個檔案時要提示")
        out = cz.run([body], source=w("src.md", "值得注意的是，這份報告說明系統的架構與 3 項測試結果。\n"))
        if "數字「3」" not in out or not out.startswith("總數："):
            errors.append("--source：單一檔案的輸出要從總數開始，並列出遺失的數字")
        os.mkdir(os.path.join(d, "nested.md"))
        if "讀不到" in cz.run([d]):
            errors.append("資料夾：副檔名是 .md 的子資料夾不能當成檔案")
        for bad in (os.path.join(d, "missing.md"), d):
            out = cz.run([body], source=bad)
            if not out.startswith("讀不到原稿"):
                errors.append(f"--source 讀不到原稿時要提示，不能當掉：{out[:40]}")
        fixme = w("fix.md", "使用Python寫程式，再把結果整理成表格。\n")
        out = cz.run([fixme], fix=True)
        if not out.startswith("總數：") or "已補上中英空格" not in out:
            errors.append("--fix-spacing：第一行仍要是總數，補空格的訊息放在後面")
        out = cz.run([body, os.path.join(d, "missing.md")])
        if "missing.md：讀不到" not in out.split("━━━━")[0]:
            errors.append("多個檔案：讀不到的檔案也要列在開頭的總數清單")
        empty = os.path.join(d, "empty")
        os.mkdir(empty)
        if "沒有 .html" not in cz.run([empty]):
            errors.append("空資料夾要提示")
    return errors


def run_cli_cases():
    """cases_*.py 裡的 CLI_CASES：用暫存資料夾測多個檔案、資料夾與 --source。
    格式：dict(name=..., files={"檔名": "內容"}, args=["檔名", ...]（"." 代表整個暫存資料夾）,
              source="檔名"（可省略）, hit=["片段"], miss=["片段"])，hit、miss 比對 cz.run() 的整份輸出。"""
    import tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    results = []
    for path in sorted(glob.glob(os.path.join(here, "cases_*.py"))):
        spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for c in getattr(mod, "CLI_CASES", []):
            errors = []
            with tempfile.TemporaryDirectory() as d:
                for name, text in c["files"].items():
                    os.makedirs(os.path.dirname(os.path.join(d, name)) or d, exist_ok=True)
                    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                        f.write(text)
                args = [d if a == "." else os.path.join(d, a) for a in c["args"]]
                src = os.path.join(d, c["source"]) if c.get("source") else None
                try:
                    out = cz.run(args, source=src).replace(d + os.sep, "")
                except Exception as e:  # noqa: BLE001
                    out = f"當掉：{e!r}"
                    errors.append(out)
            errors += [f"該抓沒抓到：「{x}」" for x in c.get("hit", []) if x not in out]
            errors += [f"不該抓卻抓到：「{x}」" for x in c.get("miss", []) if x in out]
            results.append((os.path.basename(path)[6:-3], c["name"], errors, out))
    return results


def main():
    verbose = "-v" in sys.argv
    failed = 0
    total_cli = [0]
    cases = all_cases()
    for c in cases:
        errors, out = run_case(c)
        if errors:
            failed += 1
            print(f"✗ [{c['src']}] {c['name']}")
            for e in errors:
                print("   " + e)
            if verbose:
                print("   ---- 輸出 ----\n   " + out.replace("\n", "\n   "))
        else:
            print(f"✓ [{c['src']}] {c['name']}")
    errors = run_spacing()
    print(("✗ " if errors else "✓ ") + f"--fix-spacing 的 {len(SPACING)} 個情況")
    for e in errors:
        print("   " + e)
    failed += bool(errors)
    for src, name, errors, out in run_cli_cases():
        failed += bool(errors)
        print(("✗ " if errors else "✓ ") + f"[{src}] {name}")
        for e in errors:
            print("   " + e)
        if errors and verbose:
            print("   ---- 輸出 ----\n   " + out.replace("\n", "\n   "))
        total_cli[0] += 1
    errors = run_cli()
    print(("✗ " if errors else "✓ ") + "多個檔案、資料夾與 --source 的參數")
    for e in errors:
        print("   " + e)
    failed += bool(errors)
    errors = run_source_check()
    print(("✗ " if errors else "✓ ") + "check_zh.py 與測試檔沒有看不見的字元")
    for e in errors:
        print("   " + e)
    failed += bool(errors)
    total = len(cases) + total_cli[0] + 3
    print(f"\n{total - failed}/{total} 通過")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
