譯文已完成，可以直接轉給開發團隊。

確定程度照原文
- we estimate that about 1,900 → 「我們估計約有 1,900 個」。
- may break without code changes → 「如果沒有修改程式碼，可能會無法運作」。
- is expected to take most teams between two and five working days → 「預計多數團隊需要兩到五個工作天」，timelines may vary → 「可能……而有所不同」。
- We plan to send → 「我們計畫……寄送」，The schedule is subject to change → 「上述時程可能調整」。

標點與用詞
- 原文成對的破折號「Version 2—available since January 2030—」改成一般敘述「v2 版自 2030 年 1 月起即已推出」，不需要破折號。
- token 譯「權杖」，第一次出現附上原文（token），之後統一用「權杖」。static API keys 譯「靜態 API 金鑰」，endpoints 譯「端點」，rate limits 譯「速率限制」，support tickets 譯「支援工單」。
- HTTP 410、OAuth 2.0、LL-MIGRATE 與網址照原文。
- 為了讓段落連貫，「v2 速率限制維持每個權杖每分鐘 600 次請求」移到第一段介紹 v2 的地方，內容沒變。

沒有推算
- 沒有幫團隊算距離停用還剩多久，也沒有把兩到五個工作天換算成週數。

檢查腳本結果（--source 比對原稿）
總數：逗號比例 2.33（偏低）｜句子節奏 1（比例偏離的節 1）｜AI 腔 0｜標點 0｜台灣用語 1（需確認用語 1）｜痕跡 0｜與原稿比對 8（可能遺失 4、可能新增 3、數量不同 1）
- 逗號比例 2.33：公告每句交代一件獨立的事（停用日期、移轉估計、提醒時程、提問管道），讀起來不碎，不再硬併。
- 需確認用語「用戶」：在「用戶端應用程式」（client applications），台灣通用。
- 日期 July 1／September 1, 2031 與「2031 年 7 月 1 日」「9 月 1 日」：原文寫成「July 1 and September 1, 2031」，年份同時適用兩個日期，譯文是同樣的寫法，只是年份放在前面，腳本無法對應。
- 數字 1、2 與 v1、v2：原文的「version 1」「Version 2」譯成「v1 版」「v2 版」，所以數字少了、v1 v2 多了。
- 標題數量不同：公告標題做成 Markdown 標題。
