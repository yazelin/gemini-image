"""去水印 — 偵測並移除 Gemini 右下角 sparkle 水印"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _find_watermark(img) -> tuple[int, int, int, int] | None:
    """偵測水印位置（掃描右下角的亮色低飽和度區域）

    Returns:
        (x1, y1, x2, y2) 或 None
    """
    w, h = img.size
    # 水印在右下角，掃描範圍
    scan_w, scan_h = min(120, w // 4), min(80, h // 4)

    bright_xs = []
    bright_ys = []

    for y in range(h - scan_h, h):
        for x in range(w - scan_w, w):
            r, g, b = img.getpixel((x, y))[:3]
            avg = (r + g + b) / 3
            spread = max(r, g, b) - min(r, g, b)
            # 亮且低飽和度 = 白色半透明水印
            if avg > 200 and spread < 50:
                bright_xs.append(x)
                bright_ys.append(y)

    if len(bright_xs) < 10:
        return None

    x1 = min(bright_xs) - 2
    y1 = min(bright_ys) - 2
    x2 = max(bright_xs) + 2
    y2 = max(bright_ys) + 2

    wm_w = x2 - x1
    wm_h = y2 - y1

    # 水印大小合理性檢查（太大或太小都不是水印）
    if wm_w < 15 or wm_h < 15 or wm_w > 150 or wm_h > 150:
        return None

    return (x1, y1, x2, y2)


def remove_watermark(input_path: str, output_path: str | None = None) -> str:
    """移除圖片右下角 Gemini 水印（用高斯模糊 inpainting）

    Args:
        input_path: 輸入圖片路徑
        output_path: 輸出路徑（預設覆蓋原檔）

    Returns:
        輸出路徑（失敗時回傳原檔路徑）
    """
    if output_path is None:
        output_path = input_path

    try:
        from PIL import Image, ImageFilter, ImageDraw
    except ImportError:
        logger.warning("Pillow 未安裝，跳過去水印（pip install Pillow）")
        return input_path

    try:
        img = Image.open(input_path).convert("RGB")
        bbox = _find_watermark(img)

        if bbox is None:
            logger.info("未偵測到水印，跳過")
            return input_path

        x1, y1, x2, y2 = bbox
        logger.info("偵測到水印：(%d,%d) to (%d,%d), 大小 %dx%d", x1, y1, x2, y2, x2 - x1, y2 - y1)

        # 用周圍像素高斯模糊填充水印區域
        w, h = img.size
        pad = 10
        bx1 = max(0, x1 - pad)
        by1 = max(0, y1 - pad)
        bx2 = min(w, x2 + pad)
        by2 = min(h, y2 + pad)

        bg_region = img.crop((bx1, by1, bx2, by2))
        blurred = bg_region.filter(ImageFilter.GaussianBlur(radius=8))

        # 橢圓 mask 讓邊緣自然過渡
        mask = Image.new("L", bg_region.size, 0)
        draw = ImageDraw.Draw(mask)
        inner_x1 = x1 - bx1
        inner_y1 = y1 - by1
        inner_x2 = x2 - bx1
        inner_y2 = y2 - by1
        draw.ellipse([inner_x1, inner_y1, inner_x2, inner_y2], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=5))

        # 混合
        result = Image.composite(blurred, bg_region, mask)
        img.paste(result, (bx1, by1))

        # 儲存（保持原格式品質）
        ext = Path(input_path).suffix.lower()
        if ext in (".jpg", ".jpeg"):
            img.save(output_path, quality=95)
        else:
            img.save(output_path)

        logger.info("去水印完成：%s", output_path)
        return output_path

    except Exception as e:
        logger.warning("去水印失敗：%s", e)
        return input_path
