# -*- coding: utf-8 -*-
"""tests/test_selector_walkforward_smoke.py —— 元层验证核心逻辑冒烟。

小合成数据（600 bar）4 折跑通 run_selection_experiment，断言：
- 返回结构含 regime_blend 行 + 四个单一策略基线行；
- 每行 metrics dict 齐全（OOS 交易数 / 最大回撤 / Sharpe / whipsaw 字段）；
- 审计文件（若给定）存在且可被 read_selections 读回。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.selector.audit import read_selections
from scripts.run_strategy_selection import (SelectionConfig,
                                            run_selection_experiment)

EXPECTED_ROWS = {"regime_blend", "trend_breakout", "mean_reversion",
                 "structure_break", "supply_demand"}


def test_smoke_runs_folds_and_report_structure(tmp_path):
    audit = tmp_path / "selection.jsonl"
    cfg = SelectionConfig(seed=7, n_bars=600, n_splits=4,
                          use_gmm=False,           # 加速 smoke（规则软映射路径）
                          audit_out=str(audit))
    result = run_selection_experiment(cfg)

    assert result["n_folds"] >= 1
    assert set(result["summary"].keys()) == EXPECTED_ROWS

    for name, s in result["summary"].items():
        for k in ("n_folds", "oos_trades_total", "mean_max_drawdown",
                  "mean_sharpe", "mean_dir_flips", "mean_loss_runs",
                  "mean_cost_usd", "mean_win_rate"):
            assert k in s, f"{name} summary missing {k}"
        assert s["n_folds"] == result["n_folds"]

    # 每折行结构齐全
    for name, rows in result["fold_rows"].items():
        assert len(rows) == result["n_folds"]
        for r in rows:
            for k in ("max_drawdown", "sharpe", "dir_flips", "loss_runs",
                      "est_cost_usd", "oos_trades", "fold"):
                assert k in r, f"{name} fold row missing {k}"

    # 审计落盘且可回放
    assert audit.exists()
    recs = read_selections(str(audit))
    assert len(recs) >= 1
    assert recs[0].strategy_weights


def test_smoke_gmm_path_runs(tmp_path):
    """GMM 可用时同一路径也应跑通（不可用则降级，不要求必然激活）。"""
    cfg = SelectionConfig(seed=3, n_bars=600, n_splits=4, use_gmm=True)
    result = run_selection_experiment(cfg)
    assert set(result["summary"].keys()) == EXPECTED_ROWS
    assert result["n_folds"] >= 1
