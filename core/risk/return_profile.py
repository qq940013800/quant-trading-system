# -*- coding: utf-8 -*-
"""core.risk.return_profile —— 收益序列分布形态画像纯函数。

第一性原理（对照机构风险画像实践）：
    只看 Sharpe 会被偏度欺骗——一个右偏、小赚多次偶发大亏的策略，平均收益可能
    好看，但左尾才是爆仓来源。上线/放行前必须能还原收益分布的形态：偏度方向、
    下行/上行波动是否对称、左尾亏损占比与最差单笔。本模块只做可复算的统计量，
    不做需要分布校准阈值的分类标签（标签交上层适配器按 CLEAN 集分布注入阈值）。

边界与不变量：
- 纯函数：无 IO、无数据库、不发起下单或改仓；可被回测/研究/服务层复用。
- 纯 Python（仅 math），不引 numpy/pandas；统计口径在 docstring 注明，便于审计复算。
- 输入守卫：拒绝字符串/字节；元素必须可转有限浮点，非有限抛带上下文 ValueError。
- 空序列与退化序列返回中性描述，不抛；除零按 0 / None 兜底。

口径说明：
- 标准差、下行/上行半差为样本口径（ddof=1）；方向样本数 <2 时半差记 0。
- 偏度为 Fisher-Pearson 样本矩 g1 = m3/m2^1.5；超额峰度 g2 = m4/m2² - 3；
  不做小样本无偏修正。m2=0（常数列）时偏度/峰度记 0。
"""
from __future__ import annotations

import math
from typing import Any, Sequence


def _sample_std(values: list[float]) -> float:
    """样本标准差（ddof=1）；样本数 <2 或方差为 0 时记 0。"""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    var = sum((x - mean) ** 2 for x in values) / (n - 1)
    return math.sqrt(var) if var > 0 else 0.0


def describe_returns(returns: Sequence[Any]) -> dict[str, Any]:
    """计算收益序列的分布形态统计量。

    Args:
        returns: 单笔/序列收益（无量纲收益率或盈亏均可，口径由调用方保证一致）。

    Returns:
        dict 统计画像：``n`` 样本数；``mean`` 均值；``std`` 样本标准差；
        ``downside_deviation`` / ``upside_deviation`` 下行/上行半差；
        ``skewness`` 样本偏度；``excess_kurtosis`` 超额峰度；
        ``worst_return`` / ``best_return`` 最差/最佳单笔；``loss_share`` 亏损占比；
        ``downside_upside_ratio`` 下行/上行半差比（上行半差为 0 时记 None）。
        空序列返回全部中性值（n=0，统计量 0，ratio=None）。
    """
    if isinstance(returns, (str, bytes, dict)):
        raise ValueError(f"returns 必须为数值序列，收到 {type(returns).__name__}")

    try:
        series = [float(x) for x in returns]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"returns 含不可转为浮点的元素: {exc!r}") from exc

    for x in series:
        if not math.isfinite(x):
            raise ValueError(f"returns 含非有限值: {x!r}")

    n = len(series)
    if n == 0:
        return {
            "n": 0,
            "mean": 0.0,
            "std": 0.0,
            "downside_deviation": 0.0,
            "upside_deviation": 0.0,
            "skewness": 0.0,
            "excess_kurtosis": 0.0,
            "worst_return": 0.0,
            "best_return": 0.0,
            "loss_share": 0.0,
            "downside_upside_ratio": None,
        }

    mean = sum(series) / n
    downside = [x for x in series if x < 0]
    upside = [x for x in series if x > 0]
    down_dev = _sample_std(downside)
    up_dev = _sample_std(upside)

    if n >= 2:
        m2 = sum((x - mean) ** 2 for x in series) / n
        std = math.sqrt(sum((x - mean) ** 2 for x in series) / (n - 1))
        if m2 > 0:
            m3 = sum((x - mean) ** 3 for x in series) / n
            m4 = sum((x - mean) ** 4 for x in series) / n
            skewness = m3 / (m2 ** 1.5)
            excess_kurt = m4 / (m2 ** 2) - 3.0
        else:
            skewness = 0.0
            excess_kurt = 0.0
    else:
        std = 0.0
        skewness = 0.0
        excess_kurt = 0.0

    loss_share = len(downside) / n
    ratio = down_dev / up_dev if up_dev > 0 else None

    return {
        "n": n,
        "mean": mean,
        "std": std,
        "downside_deviation": down_dev,
        "upside_deviation": up_dev,
        "skewness": skewness,
        "excess_kurtosis": excess_kurt,
        "worst_return": min(series),
        "best_return": max(series),
        "loss_share": loss_share,
        "downside_upside_ratio": ratio,
    }
