"""后端 API 接口测试（使用 FastAPI TestClient）。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app import app  # noqa: E402
from backend import database  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample_upload.csv"

from fastapi.testclient import TestClient  # noqa: E402

database.init_db()  # TestClient 不触发 startup 事件，需显式建表
client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "PHM" in r.text


def test_predict_with_sample():
    if not SAMPLE.exists():
        pytest.skip("样例数据不存在")
    if not (ROOT / "backend" / "models" / "lstm_fd001.pt").exists():
        pytest.skip("模型未训练，请先运行 scripts/train.py")
    with open(SAMPLE, "rb") as f:
        r = client.post(
            "/api/predict",
            files={"file": ("sample.csv", f, "text/csv")},
            data={"unit_id": "test-001"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["predicted_rul"] >= 0
    assert data["health_level"] in ("健康", "退化", "危险", "失效风险")
    assert "trend" in data
    assert data["unit_id"] == "test-001"


def test_predict_empty_file():
    r = client.post(
        "/api/predict",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert r.status_code == 400


def test_history():
    r = client.get("/api/history")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
