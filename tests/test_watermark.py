"""去水印模組測試"""
import pytest
from pathlib import Path
from PIL import Image, ImageDraw
from src.watermark import remove_watermark, _find_watermark


def _create_test_image(path: str, w: int = 1024, h: int = 559, add_watermark: bool = True):
    """建立測試圖片，可選加入模擬水印"""
    img = Image.new("RGB", (w, h), (120, 80, 50))  # 深色背景
    if add_watermark:
        # 在右下角畫一個白色半透明 sparkle 模擬水印
        draw = ImageDraw.Draw(img)
        wm_x, wm_y = w - 50, h - 50
        draw.ellipse([wm_x, wm_y, wm_x + 40, wm_y + 40], fill=(230, 230, 230))
    img.save(path)
    return path


class TestFindWatermark:
    def test_finds_watermark(self, tmp_path):
        """應偵測到右下角水印"""
        path = str(tmp_path / "test.png")
        _create_test_image(path, add_watermark=True)
        img = Image.open(path)
        bbox = _find_watermark(img)
        assert bbox is not None
        x1, y1, x2, y2 = bbox
        assert x1 > 900  # 在右邊
        assert y1 > 450  # 在下面

    def test_no_watermark(self, tmp_path):
        """無水印圖片應回傳 None"""
        path = str(tmp_path / "clean.png")
        _create_test_image(path, add_watermark=False)
        img = Image.open(path)
        bbox = _find_watermark(img)
        assert bbox is None


class TestRemoveWatermark:
    def test_removes_watermark(self, tmp_path):
        """有水印的圖片應成功處理"""
        input_path = str(tmp_path / "input.png")
        output_path = str(tmp_path / "output.png")
        _create_test_image(input_path, add_watermark=True)
        result = remove_watermark(input_path, output_path)
        assert result == output_path
        assert Path(output_path).exists()

    def test_no_watermark_returns_original(self, tmp_path):
        """無水印圖片直接回傳原檔"""
        input_path = str(tmp_path / "clean.png")
        _create_test_image(input_path, add_watermark=False)
        result = remove_watermark(input_path)
        assert result == input_path

    def test_default_overwrites(self, tmp_path):
        """不指定 output 時覆蓋原檔"""
        input_path = str(tmp_path / "test.png")
        _create_test_image(input_path, add_watermark=True)
        original_size = Path(input_path).stat().st_size
        result = remove_watermark(input_path)
        assert result == input_path
        # 檔案應該被修改過
        assert Path(input_path).exists()

    def test_nonexistent_file(self):
        """不存在的檔案回傳原路徑"""
        result = remove_watermark("/tmp/nonexistent_image.png")
        assert result == "/tmp/nonexistent_image.png"

    def test_jpeg_output(self, tmp_path):
        """JPEG 格式應正確儲存"""
        input_path = str(tmp_path / "test.jpg")
        img = Image.new("RGB", (1024, 559), (120, 80, 50))
        draw = ImageDraw.Draw(img)
        draw.ellipse([974, 509, 1014, 549], fill=(230, 230, 230))
        img.save(input_path, quality=95)
        result = remove_watermark(input_path)
        assert result == input_path
        # 確認還是合法 JPEG
        reopened = Image.open(input_path)
        assert reopened.size == (1024, 559)
