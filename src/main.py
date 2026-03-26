"""FastAPI 應用程式入口"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .browser import browser_manager
from .config import settings
from .gemini import generate_image, new_chat
from .queue import RequestQueue, QueueFullError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

request_queue = RequestQueue(max_size=settings.queue_max_size)
_start_time = time.time()


async def _handle_request(prompt: str, timeout: int) -> dict:
    """Worker handler：操作瀏覽器生圖 → 重置對話"""
    page = browser_manager.page
    if not page:
        return {"success": False, "error": "browser_error", "message": "瀏覽器未啟動"}

    result = await generate_image(page, prompt, timeout)
    # 每次生圖完重置對話
    await new_chat(page)
    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    """服務生命週期：啟動瀏覽器 + worker，結束時清理"""
    await browser_manager.start()
    worker_task = asyncio.create_task(request_queue.run_worker(_handle_request))
    logger.info("服務已啟動，port %d", settings.port)
    yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    await browser_manager.stop()


app = FastAPI(title="Gemini Image API", lifespan=lifespan)


# ── Request / Response 模型 ──


class GenerateRequest(BaseModel):
    prompt: str
    timeout: int = settings.default_timeout


# ── 端點 ──


@app.post("/api/generate")
async def api_generate(req: GenerateRequest):
    """生成圖片"""
    try:
        result = await request_queue.submit(req.prompt, timeout=req.timeout)
    except QueueFullError:
        raise HTTPException(status_code=429, detail="佇列已滿，請稍後再試")
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail=f"請求超時（{req.timeout}秒）")

    if not result.get("success"):
        error = result.get("error", "unknown")
        status_map = {
            "content_blocked": 200,  # 正常回應，只是被拒絕
            "no_image": 200,
            "timeout": 408,
            "browser_error": 502,
            "not_logged_in": 503,
        }
        status = status_map.get(error, 500)
        if status >= 400:
            raise HTTPException(status_code=status, detail=result.get("message", ""))
    return result


@app.get("/api/health")
async def api_health():
    """健康檢查"""
    alive = await browser_manager.is_alive()
    logged_in = await browser_manager.is_logged_in()
    status = "ok"
    if not alive:
        status = "down"
    elif not logged_in:
        status = "degraded"

    return {
        "status": status,
        "browser_alive": alive,
        "logged_in": logged_in,
        "queue_size": request_queue.size,
        "uptime_seconds": round(time.time() - _start_time),
    }


@app.post("/api/new-chat")
async def api_new_chat():
    """手動重置 Gemini 對話"""
    page = browser_manager.page
    if not page:
        raise HTTPException(status_code=503, detail="瀏覽器未啟動")
    ok = await new_chat(page)
    return {"success": ok}
