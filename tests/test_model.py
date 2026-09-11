"""模型模块测试：LSTM 网络结构、推理，随机森林推理。"""
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.models.lstm_model import LstmPredictor, RulLSTM  # noqa: E402
from backend.models.ml_baseline import RfPredictor  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "backend" / "models"


def test_lstm_forward_shape():
    model = RulLSTM(n_features=14, hidden=32, layers=2)
    x = torch.randn(4, 30, 14)
    out = model(x)
    assert out.shape == (4,)


def test_lstm_predictor_ready():
    if not (MODEL_DIR / "lstm_fd001.pt").exists():
        pytest.skip("模型未训练，请先运行 scripts/train.py")
    predictor = LstmPredictor("lstm_fd001")
    seq = np.random.rand(predictor.window, len(predictor.sensor_cols)).astype(np.float32)
    rul = predictor.predict(seq)
    assert rul >= 0
    assert isinstance(rul, float)


def test_rf_predictor_ready():
    if not (MODEL_DIR / "rf_fd001.joblib").exists():
        pytest.skip("模型未训练，请先运行 scripts/train.py")
    rf = RfPredictor("rf_fd001")
    feat = np.random.rand(rf.model.n_features_in_).astype(np.float32)
    rul = rf.predict(feat)
    assert rul >= 0
