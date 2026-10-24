# -*- coding: utf-8 -*-
"""tests/test_models_walkforward.py —— walk-forward 实验入口冒烟 + meta-label/drift。

泄漏自检：martingale 上 OOS 精度不应显著偏离先验（显著偏离提示前视泄漏）。
"""
from __future__ import annotations

import numpy as np
import pytest

from _tp_bootstrap import ROOT  # noqa: F401
from scripts.run_walkforward import WFConfig, run_walkforward
from core.models.meta_label import MetaLabeler
from core.models.baseline import LogisticBaseline
from core.models.drift import psi, rolling_hit_rate


def _cfg(**kw):
    base = dict(seed=7, n_bars=800, n_splits=3, max_holding_bars=12,
                warmup_bars=96)
    base.update(kw)
    return WFConfig(**base)


def test_walkforward_runs_and_returns_metrics():
    m = run_walkforward(_cfg())
    assert m["n_folds"] == 3
    assert 0.0 <= m["oos_acc_mean"] <= 1.0
    assert set(m) >= {"kind", "n_bars", "n_folds", "oos_acc_mean",
                      "oos_prec_mean", "label_distribution"}


def test_walkforward_deterministic():
    a = run_walkforward(_cfg())
    b = run_walkforward(_cfg())
    assert a["oos_acc_mean"] == b["oos_acc_mean"]


def test_martingale_no_magical_accuracy():
    """泄漏自检：纯随机游走 OOS 精度不应出现"预言机"式高分。"""
    m = run_walkforward(_cfg(kind="martingale"))
    assert 0.30 <= m["oos_acc_mean"] <= 0.80


def test_meta_label_p_k_unit_interval():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(400, 3))
    y = (X[:, 0] > 0.5).astype(float)
    ml = MetaLabeler(LogisticBaseline()).fit(X, y)
    p, k = ml.predict(X)
    assert p.shape == (400,)
    assert np.all(k >= 0) and np.all(k <= 1)
    assert ml.version.startswith("meta-")


def test_psi_stable_vs_shifted():
    rng = np.random.default_rng(0)
    ref = rng.normal(size=1000)
    cur = rng.normal(size=1000)
    cur_shifted = rng.normal(loc=2.0, size=1000)
    assert psi(ref, cur) < psi(ref, cur_shifted)  # 同分布 < 偏移分布


def test_rolling_hit_rate_causal():
    rates = rolling_hit_rate(np.ones(10), window=5)
    assert rates[4] == 1.0   # 前 4 个样本窗口不足 → NaN 之后全 1
    assert np.isnan(rates[:4]).all()
