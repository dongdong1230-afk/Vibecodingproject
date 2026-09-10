"""模糊综合评价 FCE 服务(技术模块 3): 对多套替代方案五指标打分排序

指标集 U = {性能匹配度, 工艺兼容性, 采购成本, 供货交期, 历史故障率}
评语集 V = {优, 良, 中, 差}, 分值向量 C = [100, 80, 60, 40]

流程:
  1) 归一化(候选集内 min-max): 成本型 r=(max-x)/(max-min), 效益型 r=(x-min)/(max-min);
     全等时 r=1(无差异即最优)
  2) 隶属度: 半梯形/三角形隶属函数(参数见 knowledge/fce_config.json),
     四隶属度之和≈1(覆盖归一化论域)
  3) 权重: AHP 判断矩阵(特征向量法+一致性检验 CR<0.1) × 熵权法 乘法合成归一化,
     mode 可切换 ahp/entropy/combined
  4) 模糊合成: 加权平均型 M(·,+): b_j = Σ_i w_i·μ_ij; 综合得分 S = Σ_j b_j·c_j(百分制);
     等级按最大隶属度原则
  5) 排序: S 降序; 并列时采购成本低者优先
"""
import json
import math
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
from app.config import FCE_CONFIG_FILE


@lru_cache(maxsize=1)
def load_config() -> dict:
    return json.loads(FCE_CONFIG_FILE.read_text(encoding="utf-8"))


# ---------- 隶属度函数 ----------
def trapmf(x: float, a: float, b: float, c: float, d: float) -> float:
    if x < a or x > d:
        return 0.0
    if x == a:
        return 1.0 if a == b else 0.0   # 左端点: 半梯形(a==b)时隶属度为 1
    if x == d:
        return 1.0 if c == d else 0.0   # 右端点: 半梯形(c==d)时隶属度为 1
    if x < b:
        return (x - a) / (b - a) if b > a else 1.0
    if x <= c:
        return 1.0
    return (d - x) / (d - c) if d > c else 1.0


def trimf(x: float, a: float, b: float, c: float) -> float:
    if x <= a or x >= c:
        return 0.0
    if x <= b:
        return (x - a) / (b - a) if b > a else 1.0
    return (c - x) / (c - b) if c > b else 1.0


def membership_vector(r: float, config: dict) -> list[float]:
    """归一化值 r ∈ [0,1] -> 四级隶属度向量 [μ优, μ良, μ中, μ差]"""
    mfs = config["membership"]
    order = ["优", "良", "中", "差"]
    vec = []
    for g in order:
        mf = mfs[g]
        if mf["type"] == "trapmf":
            vec.append(trapmf(r, *mf["params"]))
        else:
            vec.append(trimf(r, *mf["params"]))
    return vec


# ---------- 权重 ----------
def ahp_weights(matrix: list[list[float]], max_iter: int = 200, tol: float = 1e-9) -> tuple[list[float], float]:
    """AHP 特征向量法(幂法迭代): 返回 (权重, 一致性比率 CR)"""
    n = len(matrix)
    w = [1.0 / n] * n
    for _ in range(max_iter):
        nw = [sum(matrix[i][j] * w[j] for j in range(n)) for i in range(n)]
        total = sum(nw)
        nw = [v / total for v in nw]
        if max(abs(nw[i] - w[i]) for i in range(n)) < tol:
            w = nw
            break
        w = nw
    # λmax = 平均 (Aw/w)
    aw = [sum(matrix[i][j] * w[j] for j in range(n)) for i in range(n)]
    lam = sum(aw[i] / w[i] for i in range(n)) / n
    config = load_config()
    ri = config["ri"].get(str(n), 1.12)
    cr = ((lam - n) / (n - 1)) / ri if n > 2 else 0.0
    return w, cr


def entropy_weights(rows: list[list[float]]) -> list[float]:
    """熵权法: rows 为各候选(行)×各指标(列)的归一化效益型值 r∈[0,1]"""
    n = len(rows)
    if n == 0:
        return []
    m = len(rows[0])
    k = 1.0 / math.log(n) if n > 1 else 1.0
    weights = []
    for j in range(m):
        col = [max(rows[i][j], 1e-9) for i in range(n)]
        total = sum(col)
        p = [v / total for v in col]
        e = -k * sum(pi * math.log(pi) for pi in p if pi > 0)
        weights.append(1.0 - e)
    s = sum(weights)
    if s == 0:
        return [1.0 / m] * m
    return [w / s for w in weights]


def combine_weights(w_ahp: list[float], w_ent: list[float]) -> list[float]:
    """乘法合成归一化: w = w_ahp·w_ent / Σ(w_ahp·w_ent)"""
    prod = [a * b for a, b in zip(w_ahp, w_ent)]
    s = sum(prod)
    return [p / s for p in prod]


# ---------- 归一化 ----------
def normalize(values: list[float], ind_type: str) -> list[float]:
    """候选集内 min-max 归一化; 全等 -> 1.0"""
    vmax, vmin = max(values), min(values)
    if vmax == vmin:
        return [1.0] * len(values)
    if ind_type == "cost":
        return [(vmax - v) / (vmax - vmin) for v in values]
    return [(v - vmin) / (vmax - vmin) for v in values]


# ---------- 评价入口 ----------
def evaluate(items: list[dict], mode: str | None = None,
             config: dict | None = None) -> dict:
    """对候选方案做五指标模糊综合评价

    Args:
        items: [{"code", "name", "raw": {"perf_match": .., "process_compat": ..,
                "cost": .., "lead_time": .., "failure_rate": ..}}, ...]
        mode: ahp / entropy / combined(默认取配置)
    Returns:
        {ranked: [按得分降序的完整结果], weights, mode, ahp_cr}
    """
    config = config or load_config()
    mode = mode or config.get("mode", "combined")
    indicators = config["indicators"]
    grades = config["grades"]
    if not items:
        return {"ranked": [], "weights": [], "mode": mode, "ahp_cr": None}

    # 1) 归一化矩阵(行=候选, 列=指标)
    norm_matrix = []
    for j, ind in enumerate(indicators):
        col = normalize([it["raw"][ind["key"]] for it in items], ind["type"])
        for i, v in enumerate(col):
            if len(norm_matrix) <= i:
                norm_matrix.append([None] * len(indicators))
            norm_matrix[i][j] = v

    # 2) 权重
    w_ahp, cr = ahp_weights(config["ahp_matrix"])
    w_ent = entropy_weights(norm_matrix)
    if mode == "ahp":
        weights = w_ahp
    elif mode == "entropy":
        weights = w_ent
    else:
        weights = combine_weights(w_ahp, w_ent)

    # 3) 隶属度 + M(·,+) 合成 + 综合得分
    ranked = []
    for i, it in enumerate(items):
        ind_detail = []
        b = [0.0] * 4
        for j, ind in enumerate(indicators):
            r = norm_matrix[i][j]
            mu = membership_vector(r, config)
            for k in range(4):
                b[k] += weights[j] * mu[k]
            ind_detail.append({
                "key": ind["key"], "name": ind["name"], "type": ind["type"],
                "unit": ind["unit"],
                "raw": it["raw"][ind["key"]],
                "norm": round(r, 4),
                "membership": [round(x, 4) for x in mu],
                "weight": round(weights[j], 4),
                "weighted": [round(weights[j] * x, 4) for x in mu],
            })
        score = sum(b[k] * grades[list(grades)[k]] for k in range(4))
        grade = list(grades)[max(range(4), key=lambda k: b[k])]
        ranked.append({
            "code": it["code"], "name": it["name"],
            "score": round(score, 2), "grade": grade,
            "membership": [round(x, 4) for x in b],
            "indicators": ind_detail,
            **{k: v for k, v in it.items() if k not in ("code", "name", "raw")},
        })
    # 4) 排序: 得分降序, 并列时成本低者优先
    def _cost(x):
        for ind in x["indicators"]:
            if ind["key"] == "cost":
                return ind["raw"]
        return 0.0

    ranked.sort(key=lambda x: (-x["score"], _cost(x)))
    return {
        "ranked": ranked,
        "weights": {ind["key"]: round(w, 4)
                    for ind, w in zip(indicators, weights)},
        "mode": mode,
        "ahp_cr": round(cr, 4) if cr is not None else None,
    }
