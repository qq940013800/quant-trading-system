# -*- coding: utf-8 -*-
"""tests.test_audit.test_attribution —— 归因拆分纯函数测试。"""
from __future__ import annotations

import inspect
import math

import pytest

from core.audit.attribution import (
    AttributionError,
    aggregate_attribution,
    split_trade_outcome,
)


class TestSplitTradeOutcome:
    def test_long_flat_benchmark_all_pnl_is_alpha(self):
        # 基准零波动：被动敞口不赚钱，扣费前盈亏全部归残差
        res = split_trade_outcome(
            pnl=100.0, side="buy", entry_price=2000.0, exit_price=2010.0,
            benchmark_return=0.0, notional=20000.0, cost=20.0,
        )
        assert res.gross_pnl == pytest.approx(120.0)
        assert res.market_component == pytest.approx(0.0)
        assert res.alpha_component == pytest.approx(120.0)
        assert res.cost_component == pytest.approx(-20.0)
        assert res.decomposition_residual() == pytest.approx(0.0, abs=1e-9)

    def test_long_positive_benchmark_splits_beta_and_alpha(self):
        # 基准 +1%，notional 20000 → 贝塔 200；gross 250 → alpha 50
        res = split_trade_outcome(
            pnl=230.0, side="buy", entry_price=2000.0, exit_price=2012.0,
            benchmark_return=0.01, notional=20000.0, cost=20.0,
        )
        assert res.market_component == pytest.approx(200.0)
        assert res.alpha_component == pytest.approx(50.0)
        assert res.gross_pnl == pytest.approx(250.0)
        assert res.pnl == pytest.approx(
            res.market_component + res.alpha_component + res.cost_component)

    def test_short_market_component_sign_flips(self):
        # 空头：基准下跌 -1% 时被动做空赚 200；基准上涨时被动做空亏 200
        short_down = split_trade_outcome(
            pnl=0.0, side="sell", entry_price=1800.0, exit_price=1782.0,
            benchmark_return=-0.01, notional=20000.0,
        )
        assert short_down.market_component == pytest.approx(200.0)

        short_up = split_trade_outcome(
            pnl=0.0, side="sell", entry_price=1800.0, exit_price=1818.0,
            benchmark_return=0.01, notional=20000.0,
        )
        assert short_up.market_component == pytest.approx(-200.0)

    def test_own_directional_return_long_and_short(self):
        res_long = split_trade_outcome(
            pnl=0.0, side="buy", entry_price=100.0, exit_price=102.0,
            benchmark_return=0.0, notional=1000.0,
        )
        assert res_long.own_directional_return == pytest.approx(0.02)

        res_short = split_trade_outcome(
            pnl=0.0, side="sell", entry_price=100.0, exit_price=102.0,
            benchmark_return=0.0, notional=1000.0,
        )
        assert res_short.own_directional_return == pytest.approx(-0.02)

    def test_shares_zero_gross_guarded(self):
        res = split_trade_outcome(
            pnl=0.0, side="buy", entry_price=100.0, exit_price=100.0,
            benchmark_return=0.0, notional=1000.0,
        )
        shares = res.shares()
        assert shares == {"market": 0.0, "alpha": 0.0, "cost": 0.0}

    def test_invalid_side_raises_with_context(self):
        with pytest.raises(AttributionError) as exc:
            split_trade_outcome(
                pnl=1.0, side="long", entry_price=100.0, exit_price=101.0,
                benchmark_return=0.0, notional=1000.0,
            )
        assert "side" in exc.value.context

    def test_negative_cost_raises(self):
        with pytest.raises(AttributionError):
            split_trade_outcome(
                pnl=1.0, side="buy", entry_price=100.0, exit_price=101.0,
                benchmark_return=0.0, notional=1000.0, cost=-5.0,
            )

    def test_non_finite_benchmark_raises(self):
        with pytest.raises(AttributionError):
            split_trade_outcome(
                pnl=1.0, side="buy", entry_price=100.0, exit_price=101.0,
                benchmark_return=math.nan, notional=1000.0,
            )

    def test_entry_price_must_be_positive(self):
        with pytest.raises(AttributionError):
            split_trade_outcome(
                pnl=1.0, side="buy", entry_price=0.0, exit_price=1.0,
                benchmark_return=0.0, notional=1000.0,
            )


class TestAggregateAttribution:
    def test_totals_and_alpha_share(self):
        r1 = split_trade_outcome(
            pnl=100.0, side="buy", entry_price=100.0, exit_price=101.0,
            benchmark_return=0.01, notional=10000.0, cost=10.0,
        )
        r2 = split_trade_outcome(
            pnl=-40.0, side="buy", entry_price=100.0, exit_price=99.0,
            benchmark_return=-0.01, notional=10000.0, cost=10.0,
        )
        agg = aggregate_attribution([r1, r2])
        assert agg["n_trades"] == 2
        assert agg["pnl_total"] == pytest.approx(60.0)
        assert agg["alpha_total"] == pytest.approx(
            r1.alpha_component + r2.alpha_component)
        assert 0.0 <= agg["alpha_positive_share"] <= 1.0

    def test_empty_aggregate_guarded(self):
        agg = aggregate_attribution([])
        assert agg["n_trades"] == 0
        assert agg["pnl_total"] == 0.0


class TestNoExternalDependency:
    def test_module_source_has_no_db_or_network_imports(self):
        from core.audit import attribution as mod
        src = inspect.getsource(mod)
        for banned in ("psycopg", "requests", "socket", "db_writer",
                       "sqlalchemy", "httpx", "urllib.request"):
            assert banned not in src, f"attribution.py 引入了外部依赖: {banned}"
