# 字型設定

產出 HTML、PDF 或 Word 時再讀這份，純文字與 Markdown 用不到。中文文件預設使用 Noto Sans TC。

## HTML

- 字型已安裝在本機時（可用 `fc-list | grep -i "Noto Sans TC"` 確認），直接寫 `font-family: "Noto Sans TC", sans-serif;` 即可。實測 Chrome 對 Noto Sans TC 可變字重檔案的 300、400、500、700、900 都能正確顯示，不需要額外設定。
- 要給別人開啟的 HTML，或不確定對方有沒有安裝時，改用 Google Fonts 載入：
  ```html
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700&display=swap" rel="stylesheet">
  ```
- `font-family` 要把 Noto Sans TC 排在第一位。破折號「──」用的是 U+2500，Noto Sans TC 會把它畫滿整格，兩個連成一條線，如果西文字型排在前面，可能改由西文字型顯示成較短的線段，兩段之間出現空隙。

## PDF

- 用 headless Chrome 輸出 PDF 時加上 `--virtual-time-budget=8000`，讓字型載入完成再列印，如果用本機字型檔的 `@font-face`，再加 `--allow-file-access-from-files`。
- `pdffonts` 會把這個字型列成「NotoSansTC-Thin_Regular」，那只是可變字型檔的內部預設名稱，不代表印出來是細體，以實際畫面為準。

## Word

- 把中文字型（East Asian font）設為 Noto Sans TC。
