# Worker Pool 多瀏覽器並行設計

## 背景

gemini-web 目前只有一個 Chromium instance，所有請求序列處理。當多個服務同時呼叫 API（如 catime 的多 stage pipeline），後面的請求會在 queue 中等到 timeout。

## 目標

- 支援多個 Chromium instance 並行處理請求
- 每個 worker 使用獨立的 Google 帳號和 profile 目錄
- 對外 API 完全不變，消費者零改動
- 向後相容：`WORKER_COUNT=1` 等同現有行為

## 架構

```
                         ┌─────────────────────────┐
                         │       FastAPI App        │
                         │                          │
Request ──► Queue ──►    │   WorkerPool             │
                         │    ├── Worker 0          │
                         │    │   BrowserManager    │
                         │    │   profiles/         │
                         │    │   Account A         │
                         │    ├── Worker 1          │
                         │    │   BrowserManager    │
                         │    │   profiles-1/       │
                         │    │   Account B         │
                         │    └── Worker 2          │
                         │        BrowserManager    │
                         │        profiles-2/       │
                         │        Account C         │
                         └─────────────────────────┘
```

## 設定

### .env 新增

```
WORKER_COUNT=3
```

預設值為 1（向後相容）。

### Profile 目錄結構

```
~/.gemini-web/
├── profiles/          ← worker-0（現有目錄，不用重新登入）
├── profiles-1/        ← worker-1
└── profiles-2/        ← worker-2
```

命名規則：`profiles/` 為 worker-0，`profiles-{N}/` 為 worker-N（N >= 1）。

## 登入流程

```bash
gemini-web login --worker 0    # 或不帶參數，向後相容
gemini-web login --worker 1
gemini-web login --worker 2
```

每個 worker 只需登入一次，session 持久化到對應 profile 目錄。

## 請求分配策略

不使用 round-robin，改用**空閒優先**分配：

```python
class WorkerPool:
    workers: list[Worker]  # 每個 Worker 含 BrowserManager + asyncio.Lock

    async def dispatch(kind, prompt, model, timeout):
        # 1. 找第一個空閒的 worker（Lock 未被持有）
        # 2. 如果都忙，等最快完成的那個
        # 3. 分配給該 worker 執行
```

行為：
- N 個 worker → 最多同時處理 N 個請求
- 第 N+1 個請求開始排隊等待
- 排隊超過 `QUEUE_MAX_SIZE` 時回 429
- 每個 worker 用 `asyncio.Lock` 確保同一時間只操作一個瀏覽器

## Health Check 擴充

`GET /api/health` 回應：

```json
{
  "status": "ok",
  "workers": [
    {"id": 0, "alive": true, "logged_in": true, "busy": false},
    {"id": 1, "alive": true, "logged_in": true, "busy": true},
    {"id": 2, "alive": true, "logged_in": false, "busy": false}
  ],
  "workers_available": 2,
  "workers_total": 3,
  "queue_waiting": 0,
  "uptime_seconds": 3600
}
```

Status 判斷：
- 全部 alive + logged_in = `"ok"`
- 部分可用 = `"degraded"`
- 全掛 = `"down"`

## 需要修改的檔案

| 檔案 | 改動 |
|------|------|
| `src/config.py` | 新增 `worker_count` 設定 |
| `src/browser.py` | `BrowserManager` 支援指定 profile 目錄；新增 `WorkerPool` 類別 |
| `src/queue.py` | 改為多 worker 分配（空閒優先 + 溢出排隊） |
| `src/main.py` | 啟動 WorkerPool 取代單一 browser_manager；擴充 health check |
| `src/cli.py` | `login` 指令加 `--worker` 參數 |

## 向後相容

- API 端點完全不變
- `WORKER_COUNT=1` = 現有行為
- 現有 `profiles/` 目錄自動成為 worker-0
- CLI `gemini-web login` 不帶 `--worker` = `--worker 0`
- 消費者零改動

## 資源估算

- 每個 Chromium instance: ~300-500MB RAM
- 伺服器：16GB RAM / 20 核 i5-13500
- 3 個 worker: ~1.2-1.5GB RAM，安全範圍內
- 最多建議 5 個 worker（~2-2.5GB）

## 風險

- Google 風控：不同帳號降低風險，但同 IP 多帳號仍需注意
- Gemini 限流：每個帳號有獨立額度，分散後單帳號壓力更小
- 記憶體：需監控，Chromium 記憶體可能隨時間增長（心跳機制已有）
