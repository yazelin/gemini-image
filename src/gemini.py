"""Gemini 頁面互動 — 輸入 prompt、等待生成、擷取圖片"""
import asyncio
import logging
import time

from playwright.async_api import Page

from .selectors import SELECTORS

logger = logging.getLogger(__name__)

# 瀏覽器端 JS：將 img 元素轉為 base64
_IMG_TO_BASE64_JS = """
(img) => {
    return new Promise((resolve, reject) => {
        const canvas = document.createElement('canvas');
        const naturalImg = new Image();
        naturalImg.crossOrigin = 'anonymous';
        naturalImg.onload = () => {
            canvas.width = naturalImg.naturalWidth;
            canvas.height = naturalImg.naturalHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(naturalImg, 0, 0);
            resolve(canvas.toDataURL('image/png'));
        };
        naturalImg.onerror = () => reject('圖片載入失敗');
        naturalImg.src = img.src;
    });
}
"""

# 拒絕生圖的常見文字片段
_BLOCK_PHRASES = [
    "I can't generate",
    "I'm not able to",
    "無法生成",
    "I can't create",
    "isn't something I can",
    "against my safety",
    "violates my safety",
]


async def generate_image(page: Page, prompt: str, timeout: int = 60) -> dict:
    """在 Gemini 頁面輸入 prompt 並擷取生成的圖片

    Returns:
        {"success": True, "images": [...], "prompt": ..., "elapsed_seconds": ...}
        或 {"success": False, "error": ..., "message": ...}
    """
    start = time.time()

    try:
        # 1. 確認輸入框就緒
        input_el = await page.wait_for_selector(
            SELECTORS["input"], state="visible", timeout=10_000
        )
        if not input_el:
            return _error("browser_error", "找不到輸入框")

        # 2. 清空並輸入 prompt
        await input_el.click()
        await input_el.fill("")
        await page.keyboard.type(prompt, delay=20)
        await asyncio.sleep(0.5)

        # 3. 送出（按 Enter）
        await page.keyboard.press("Enter")
        logger.info("已送出 prompt：%s", prompt[:50])

        # 4. 等待回應完成
        #    策略：等待「停止生成」按鈕出現後再消失
        try:
            await page.wait_for_selector(
                SELECTORS["stop_generating"], state="visible", timeout=10_000
            )
        except Exception:
            pass  # 有時生成太快，按鈕瞬間出現又消失

        await page.wait_for_selector(
            SELECTORS["stop_generating"], state="hidden", timeout=timeout * 1000
        )
        # 額外等待確保圖片渲染完成
        await asyncio.sleep(2)

        # 5. 檢查是否被拒絕
        response_els = await page.query_selector_all(SELECTORS["response"])
        if response_els:
            last_response = response_els[-1]
            text = (await last_response.inner_text()).strip()
            for phrase in _BLOCK_PHRASES:
                if phrase.lower() in text.lower():
                    elapsed = round(time.time() - start, 1)
                    return {
                        "success": False,
                        "error": "content_blocked",
                        "message": text[:200],
                        "elapsed_seconds": elapsed,
                    }

        # 6. 擷取圖片
        img_els = await page.query_selector_all(SELECTORS["images"])
        if not img_els:
            # 可能回了文字而非圖片
            text = ""
            if response_els:
                text = (await response_els[-1].inner_text()).strip()
            elapsed = round(time.time() - start, 1)
            return {
                "success": False,
                "error": "no_image",
                "message": f"Gemini 未生成圖片。回應內容：{text[:200]}",
                "elapsed_seconds": elapsed,
            }

        # 7. 將圖片轉為 base64
        images = []
        for img_el in img_els:
            try:
                base64_data = await img_el.evaluate(_IMG_TO_BASE64_JS)
                if base64_data and base64_data.startswith("data:image"):
                    images.append(base64_data)
            except Exception as e:
                logger.warning("擷取圖片失敗：%s", e)

        elapsed = round(time.time() - start, 1)

        if not images:
            return _error("browser_error", "圖片元素存在但無法擷取", elapsed)

        return {
            "success": True,
            "images": images,
            "prompt": prompt,
            "elapsed_seconds": elapsed,
        }

    except asyncio.TimeoutError:
        elapsed = round(time.time() - start, 1)
        return _error("timeout", f"生成超時（{timeout}秒）", elapsed)
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        logger.exception("Gemini 互動發生錯誤")
        return _error("browser_error", str(e), elapsed)


async def new_chat(page: Page) -> bool:
    """點擊「新對話」重置 Gemini 狀態"""
    try:
        btn = await page.query_selector(SELECTORS["new_chat"])
        if btn:
            await btn.click()
            await asyncio.sleep(1)
            logger.info("已重置對話")
            return True
        # 備用：直接導航到 Gemini 首頁
        await page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        logger.info("已重新導航至 Gemini 首頁")
        return True
    except Exception as e:
        logger.warning("重置對話失敗：%s", e)
        return False


def _error(error: str, message: str, elapsed: float = 0) -> dict:
    return {
        "success": False,
        "error": error,
        "message": message,
        "elapsed_seconds": elapsed,
    }
