"""去水印模組測試"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.watermark import remove_watermark, _find_gwt, _get_platform, _get_exe_name


class TestPlatformDetection:
    @patch("src.watermark.platform.system", return_value="Linux")
    def test_linux(self, mock):
        assert _get_platform() == "linux"

    @patch("src.watermark.platform.system", return_value="Darwin")
    def test_macos(self, mock):
        assert _get_platform() == "darwin"

    @patch("src.watermark.platform.system", return_value="Windows")
    def test_windows(self, mock):
        assert _get_platform() == "windows"

    @patch("src.watermark.platform.system", return_value="Windows")
    def test_exe_name_windows(self, mock):
        assert _get_exe_name() == "GeminiWatermarkTool.exe"

    @patch("src.watermark.platform.system", return_value="Linux")
    def test_exe_name_linux(self, mock):
        assert _get_exe_name() == "GeminiWatermarkTool"


class TestFindGwt:
    def test_returns_string_or_none(self):
        result = _find_gwt()
        assert result is None or isinstance(result, str)

    @patch("src.watermark._download_gwt", return_value="/tmp/gwt")
    @patch("src.watermark.shutil.which", return_value=None)
    def test_fallback_to_download(self, mock_which, mock_download, tmp_path):
        import src.watermark as wm
        orig = wm._CACHE_DIR
        wm._CACHE_DIR = tmp_path / "nonexistent"
        try:
            result = _find_gwt()
            mock_download.assert_called_once()
        finally:
            wm._CACHE_DIR = orig


class TestRemoveWatermark:
    @patch("src.watermark._find_gwt", return_value=None)
    def test_no_tool_returns_original(self, mock_find):
        result = remove_watermark("/tmp/test.png")
        assert result == "/tmp/test.png"

    @patch("src.watermark.subprocess.run")
    @patch("src.watermark._find_gwt", return_value="/usr/bin/GeminiWatermarkTool")
    def test_success(self, mock_find, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = remove_watermark("/tmp/input.png", "/tmp/output.png")
        assert result == "/tmp/output.png"
        args = mock_run.call_args[0][0]
        assert "--input" in args
        assert "--output" in args
        assert "--remove" in args
        assert "--denoise" in args

    @patch("src.watermark.subprocess.run")
    @patch("src.watermark._find_gwt", return_value="/usr/bin/GeminiWatermarkTool")
    def test_failure_returns_original(self, mock_find, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="No watermark found")
        result = remove_watermark("/tmp/input.png", "/tmp/output.png")
        assert result == "/tmp/input.png"

    @patch("src.watermark.subprocess.run")
    @patch("src.watermark._find_gwt", return_value="/usr/bin/GeminiWatermarkTool")
    def test_timeout_returns_original(self, mock_find, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="gwt", timeout=60)
        result = remove_watermark("/tmp/input.png")
        assert result == "/tmp/input.png"

    @patch("src.watermark.subprocess.run")
    @patch("src.watermark._find_gwt", return_value="/usr/bin/GeminiWatermarkTool")
    def test_default_output_overwrites(self, mock_find, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        remove_watermark("/tmp/input.png")
        args = mock_run.call_args[0][0]
        input_idx = args.index("--input")
        output_idx = args.index("--output")
        assert args[input_idx + 1] == "/tmp/input.png"
        assert args[output_idx + 1] == "/tmp/input.png"
