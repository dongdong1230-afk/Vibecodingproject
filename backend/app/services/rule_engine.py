"""JSON 规则表达式求值器(无 eval): 风险判定与本体推理共用

表达式语法(嵌套 JSON, 数据化规则, 可解释可导出):
  - 字面量: 数字/字符串/布尔 直接返回值
  - {"op": "ref", "path": "mat.stock_qty"}: 取变量路径值(逐级 dict 取值)
  - {"op": "eq|neq|gt|gte|lt|lte|in", "left": ..., "right": ...}: 二元比较
  - {"op": "and|or", "args": [...]}: 逻辑组合; {"op": "not", "args": [x]}: 取反
  - {"op": "mul|add", "args": [a, b]}: 数值运算(用于阈值计算, 如 2×阈值)
  涉及 None 的比较(路径缺失)一律返回 False(neq 返回 True), 保证规则不误触发。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

_CMP_OPS = {
    "eq": lambda a, b: a == b,
    "neq": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and b is not None and a > b,
    "gte": lambda a, b: a is not None and b is not None and a >= b,
    "lt": lambda a, b: a is not None and b is not None and a < b,
    "lte": lambda a, b: a is not None and b is not None and a <= b,
    "in": lambda a, b: a in (b or []),
}


def resolve_path(data: dict, path: str):
    """逐级取值: "mat.stock_qty" / "cand.attrs.power_w"; 缺失返回 None"""
    cur = data
    for part in str(path).split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _val(x, data: dict):
    """操作数求值: dict 为子表达式; 含 '.' 的字符串视为变量路径, 其余为字面量"""
    if isinstance(x, dict):
        return eval_expr(x, data)
    if isinstance(x, str) and "." in x:
        return resolve_path(data, x)
    return x


def eval_expr(expr, data: dict):
    """递归求值表达式; data 为变量根 dict(如 {"mat": {...}, "cond": {...}, "cfg": {...}})"""
    if isinstance(expr, dict):
        op = expr.get("op")
        if op == "ref":
            return resolve_path(data, expr.get("path", ""))
        if op == "and":
            return all(eval_expr(a, data) for a in expr.get("args", []))
        if op == "or":
            return any(eval_expr(a, data) for a in expr.get("args", []))
        if op == "not":
            return not eval_expr(expr["args"][0], data)
        if op in ("mul", "add"):
            a = _val(expr["args"][0], data)
            b = _val(expr["args"][1], data)
            if a is None or b is None:
                return None
            return a * b if op == "mul" else a + b
        # 二元比较
        if op in _CMP_OPS:
            left = _val(expr.get("left"), data)
            right = _val(expr.get("right"), data)
            if op == "eq" and left is None and right is None:
                return True
            return _CMP_OPS[op](left, right)
        raise ValueError(f"未知操作符: {op}")
    return expr


def eval_rule(rule: dict, data: dict) -> tuple[bool, dict]:
    """求值单条风险/适配规则: 返回 (是否命中, 级别信息或 {})"""
    cond = rule.get("condition")
    if cond is None:
        return True, rule
    return eval_expr(cond, data), rule
