# Siftlet 安裝說明（v2.4.1）

Siftlet 是一個用來過濾系統日誌的命令列工具，支援 Linux 與 macOS。安裝前請先確認電腦已安裝 Python 3.11 以上的版本，如果公司配發的電腦沒有管理員權限，也請先向資訊組申請安裝許可。

1. 下載安裝檔：https://downloads.example.org/siftlet/siftlet-2.4.1.tar.gz
2. 解壓縮後，在終端機執行 `pip install ./siftlet-2.4.1`。
3. 把設定檔 `sieve.toml` 放到家目錄的 `.config/siftlet/` 資料夾裡。
4. 執行 `siftlet --check` 確認安裝成功，螢幕上會出現「OK: 3 rules loaded」。

## 注意事項

- 若出現「ModuleNotFoundError」，代表 Python 版本不相容，請升級後重新安裝。
- 預設規則檔只包含 3 條規則，如需自訂規則，請參考 https://docs.example.org/siftlet/rules。
- 本工具目前為測試版本，問題請回報至 siftlet-team@example.org。
