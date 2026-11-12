#!/usr/bin/env python3
"""check_zh.py 的回歸測試。

用法：python3 scripts/tests/run_tests.py

每個測試是一小段文字，寫好「應該抓到」與「不應該抓到」的提醒。
改了 check_zh.py 或 references 裡的清單之後跑一次，全部通過才算改好。
修好一個誤報或漏抓時，把那句加進來，之後就不會再犯。

應該抓到：(類別, 片段)，該類別的某一則提醒要包含這個片段。
不應該抓到：(類別, 片段)，該類別的提醒都不能包含這個片段；類別寫 None 代表所有類別。
類別寫 "_out" 代表比對整份輸出文字。

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

    # ---------- 第十三項：看語意判斷要附前後文 ----------
    dict(name="看語意判斷的詞附前後文", ext="md",
         text="請把文件存到共用資料夾，再把結果整理成表格，最後確認格式正確。\n",
         hit=[("term.context", "存到共用")]),
]


def run_case(c):
    rep = cz.analyze(c["text"], html_mode=(c["ext"] == "html"))
    out = "\n".join(rep.lines)
    errors = []

    def pool(key):
        if key == "_out":
            return [out]
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


def run_source_check():
    """check_zh.py 裡不能有看不見的字元（BOM、Unicode 私用區），要用 chr() 產生。
    這類字元在編輯或複製時很容易消失，v1.2.0 開發時就發生過兩次。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "check_zh.py")
    bad = [i for i, line in enumerate(open(path, encoding="utf-8"), 1)
           if any(c == "\ufeff" or "\ue000" <= c <= "\uf8ff" for c in line)]
    return [f"check_zh.py 第 {', '.join(map(str, bad))} 行有看不見的字元，請改用 chr() 產生"] if bad else []


def main():
    verbose = "-v" in sys.argv
    failed = 0
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
    errors = run_source_check()
    print(("✗ " if errors else "✓ ") + "check_zh.py 沒有看不見的字元")
    for e in errors:
        print("   " + e)
    failed += bool(errors)
    total = len(cases) + 2
    print(f"\n{total - failed}/{total} 通過")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
