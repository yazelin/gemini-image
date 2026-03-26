# Gemini Image API

使用 Playwright 自動化 Gemini 網頁版生成含繁體中文文字的圖片，提供 HTTP API 供內部系統呼叫。

## 快速開始

### 1. 安裝

```bash
uv sync --extra dev
uv run playwright install chromium
cp .env.example .env
```

### 2. 首次啟動（手動登入 Google）

```bash
# HEADLESS=false 會開啟瀏覽器視窗
HEADLESS=false uv run uvicorn src.main:app --port 8070
```

在彈出的瀏覽器中登入 Google 帳號，確認進入 Gemini 頁面。

### 3. 正式運行

修改 `.env` 中 `HEADLESS=true`，然後：

```bash
uv run uvicorn src.main:app --host 0.0.0.0 --port 8070
```

### 4. 安裝為 systemd 服務（可選）

```bash
sudo bash scripts/install-service.sh
```

## API

### POST /api/generate

生成圖片。

```bash
curl -X POST http://localhost:8070/api/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "畫一張台北101海報，標題寫「歡迎來到台北」"}'
```

回傳：

```json
{
  "success": true,
  "images": ["data:image/png;base64,..."],
  "prompt": "...",
  "elapsed_seconds": 12.3
}
```

### GET /api/health

健康檢查。

### POST /api/new-chat

手動重置 Gemini 對話。

## 環境變數

見 `.env.example`。

## 已知限制

- 一次只能處理一個生圖請求（其他排隊）
- Google 登入過期需手動重新登入
- Gemini 改版可能導致 DOM selector 失效，需手動更新 `src/selectors.py`
- 違反 Google 服務條款，帳號有被封風險
