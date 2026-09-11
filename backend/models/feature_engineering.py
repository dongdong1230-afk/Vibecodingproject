"""特征工程模块：传感器筛选、滑动窗口特征构造、归一化。

对应课程技术方向：数据预处理与特征工程。
提供两类输出：
1. 序列输入（供 LSTM）：选定传感器在滑动窗口内的归一化原始值序列；
2. 统计特征（供随机森林基线）：窗口内的均值/标准差/斜率/最大值等统计量。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# C-MAPSS FD001 列名（26 列：单元号、循环号、3 个工况参数、21 个传感器）
CMAPSS_COLUMNS = (
    ["unit", "cycle"]
    + [f"setting{i}" for i in range(1, 4)]
    + [f"sensor{i}" for i in range(1, 22)]
)

# 用于训练的默认窗口长度（飞行循环数）
DEFAULT_WINDOW = 30
# RUL 上限截断值（防止训练初期大 RUL 主导损失）
RUL_CAP = 125
# 传感器筛选相关阈值
CORR_THRESHOLD = 0.5


def load_raw(path: str) -> pd.DataFrame:
    """读取 C-MAPSS 原始 txt 数据并命名列。"""
    df = pd.read_csv(path, sep=r"\s+", header=None, names=CMAPSS_COLUMNS)
    return df


def compute_rul(df: pd.DataFrame) -> pd.DataFrame:
    """为训练数据计算每个循环的剩余寿命 RUL = 该单元最大循环 - 当前循环。"""
    df = df.copy()
    max_cycle = df.groupby("unit")["cycle"].transform("max")
    df["rul"] = max_cycle - df["cycle"]
    df["rul"] = df["rul"].clip(upper=RUL_CAP)
    return df


def select_sensors(df: pd.DataFrame, threshold: float = CORR_THRESHOLD) -> list[str]:
    """基于与 RUL 的 Pearson 相关系数筛选有效传感器。

    训练数据需已包含 rul 列。返回 |corr| >= threshold 的传感器列名。
    """
    if "rul" not in df.columns:
        raise ValueError("训练数据必须包含 rul 列，请先调用 compute_rul")
    sensor_cols = [c for c in df.columns if c.startswith("sensor")]
    corr = df[sensor_cols].corrwith(df["rul"]).abs()
    selected = corr[corr >= threshold].index.tolist()
    if not selected:
        # 兜底：保留相关性最高的 10 个传感器
        selected = corr.sort_values(ascending=False).head(10).index.tolist()
    return selected


def make_sequence_windows(
    df: pd.DataFrame,
    sensor_cols: list[str],
    window: int = DEFAULT_WINDOW,
    stride: int = 1,
    scaler: dict | None = None,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """构造 LSTM 的滑动窗口序列样本。

    参数:
        df: 含 unit/cycle/sensor 列的数据（训练数据应含 rul）
        sensor_cols: 选定传感器列
        window: 窗口长度
        stride: 步长
        scaler: 已拟合的归一化参数 {col: (min, max)}，None 表示就地拟合
    返回:
        (X, y, scaler): X 形状 (n, window, n_sensor)，y 为窗口末端 RUL
    """
    df = df.copy()
    if scaler is None:
        scaler = {
            c: (float(df[c].min()), float(df[c].max())) for c in sensor_cols
        }
    for c in sensor_cols:
        lo, hi = scaler[c]
        denom = hi - lo if hi > lo else 1.0
        df[c] = (df[c] - lo) / denom

    X, y = [], []
    for _, grp in df.groupby("unit", sort=False):
        vals = grp[sensor_cols].to_numpy()
        ruls = grp["rul"].to_numpy() if "rul" in grp.columns else None
        n = len(vals)
        for start in range(0, n - window + 1, stride):
            X.append(vals[start : start + window])
            if ruls is not None:
                y.append(ruls[start + window - 1])
    X = np.asarray(X, dtype=np.float32)
    y = np.asarray(y, dtype=np.float32) if y else None
    return X, y, scaler


def make_stat_features(
    df: pd.DataFrame,
    sensor_cols: list[str],
    window: int = DEFAULT_WINDOW,
    stride: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """构造随机森林基线的窗口统计特征。

    每个窗口输出：每个传感器的 [末值, 均值, 标准差, 斜率]。
    """
    rows, y = [], []
    for _, grp in df.groupby("unit", sort=False):
        vals = grp[sensor_cols].to_numpy()
        ruls = grp["rul"].to_numpy() if "rul" in grp.columns else None
        cycles = grp["cycle"].to_numpy()
        n = len(vals)
        for start in range(0, n - window + 1, stride):
            w = vals[start : start + window]
            feat = []
            for j in range(w.shape[1]):
                col = w[:, j]
                slope = np.polyfit(cycles[start : start + window], col, 1)[0]
                feat.extend([col[-1], col.mean(), col.std(), slope])
            rows.append(feat)
            if ruls is not None:
                y.append(ruls[start + window - 1])
    X = np.asarray(rows, dtype=np.float32)
    return X, (np.asarray(y, dtype=np.float32) if y else None)


def last_window_for_unit(
    df: pd.DataFrame,
    sensor_cols: list[str],
    scaler: dict,
    window: int = DEFAULT_WINDOW,
) -> np.ndarray:
    """取单个单元最后 window 个循环的归一化序列，供推理使用。"""
    df = df.copy()
    for c in sensor_cols:
        lo, hi = scaler[c]
        denom = hi - lo if hi > lo else 1.0
        df[c] = (df[c] - lo) / denom
    vals = df[sensor_cols].to_numpy()
    if len(vals) < window:
        # 数据不足窗口时，用首行重复填充补齐
        pad = np.repeat(vals[:1], window - len(vals), axis=0)
        vals = np.concatenate([pad, vals], axis=0)
    return vals[-window:].astype(np.float32)
