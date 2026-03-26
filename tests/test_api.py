"""API 端點測試"""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

# mock 瀏覽器，避免測試時真的啟動 Chromium
@pytest.fixture(autouse=True)
def mock_browser():
    with patch("src.main.browser_manager") as mock:
        mock.start = AsyncMock()
        mock.stop = AsyncMock()
        mock.is_alive = AsyncMock(return_value=True)
        mock.is_logged_in = AsyncMock(return_value=True)
        mock.page = AsyncMock()
        yield mock


@pytest.fixture
def mock_queue():
    with patch("src.main.request_queue") as mock:
        mock.size = 0
        yield mock


@pytest.mark.asyncio
async def test_health_endpoint(mock_browser, mock_queue):
    """GET /api/health 應回傳狀態"""
    from src.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["browser_alive"] is True
    assert data["logged_in"] is True


@pytest.mark.asyncio
async def test_generate_missing_prompt():
    """POST /api/generate 沒有 prompt 應回 422"""
    from src.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/generate", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_generate_success(mock_browser, mock_queue):
    """POST /api/generate 成功時回傳圖片"""
    mock_queue.submit = AsyncMock(return_value={
        "success": True,
        "images": ["data:image/png;base64,abc"],
        "prompt": "test",
        "elapsed_seconds": 1.0,
    })
    from src.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/generate", json={"prompt": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["images"]) == 1
