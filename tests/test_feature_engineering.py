"""特征工程模块单元测试。"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.models import feature_engineering as fe  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_TRAIN = ROOT / "data" / "raw" / "train_FD001.txt"


@pytest.fixture(scope="module")
def train_df():
    if not RAW_TRAIN.exists():
        pytest.skip("原始数据不存在，请先完成数据准备")
    df = fe.load_raw(RAW_TRAIN)
    return fe.compute_rul(df)


def test_load_raw_shape(train_df):
    # compute_rul 会新增 rul 列，因此为 27 列（26 原始列 + rul）
    assert len(train_df.columns) == 27
    assert train_df["unit"].nunique() == 100
    assert "sensor21" in train_df.columns
    assert "rul" in train_df.columns


def test_rul_range(train_df):
    assert train_df["rul"].max() <= fe.RUL_CAP
    assert (train_df["rul"] >= 0).all()


def test_select_sensors(train_df):
    cols = fe.select_sensors(train_df, threshold=0.5)
    assert len(cols) >= 5
    assert all(c.startswith("sensor") for c in cols)


def test_sequence_windows_shape(train_df):
    cols = fe.select_sensors(train_df, threshold=0.5)
    X, y, scaler = fe.make_sequence_windows(
        train_df, cols, window=30, stride=30
    )
    assert X.ndim == 3
    assert X.shape[1] == 30
    assert X.shape[2] == len(cols)
    assert len(X) == len(y)
    assert scaler is not None


def test_stat_features_shape(train_df):
    cols = fe.select_sensors(train_df, threshold=0.5)
    X, y = fe.make_stat_features(train_df, cols, window=30, stride=30)
    assert X.ndim == 2
    assert X.shape[1] == 4 * len(cols)
    assert len(X) == len(y)


def test_last_window_padding():
    # 构造不足窗口长度的单单元数据，验证补齐逻辑
    df = _make_short_df()
    cols = [c for c in df.columns if c.startswith("sensor")]
    scaler = {c: (0.0, 10.0) for c in cols}
    seq = fe.last_window_for_unit(df, cols, scaler, window=30)
    assert seq.shape == (30, len(cols))


def _make_short_df():
    import pandas as pd

    rows = []
    for cyc in range(1, 6):
        row = {"unit": 1, "cycle": cyc}
        for i in range(1, 22):
            row[f"sensor{i}"] = float(i) + cyc
        rows.append(row)
    return pd.DataFrame(rows)
