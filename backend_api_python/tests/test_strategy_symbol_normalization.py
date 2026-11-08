"""策略品种规范化与研究信号判定纯函数测试（#198）。"""

from app.services.strategy import (
    classify_strategy_symbol,
    is_research_only_strategy,
    normalize_strategy_symbol,
)


def test_normalize_crypto_concatenated_symbol():
    assert normalize_strategy_symbol("BTCUSDT") == "BTC/USDT"
    assert normalize_strategy_symbol("ETHUSDT") == "ETH/USDT"
    assert normalize_strategy_symbol("SOLUSDT") == "SOL/USDT"


def test_normalize_crypto_dash_and_quote_suffix():
    assert normalize_strategy_symbol("BTC-USDT") == "BTC/USDT"
    assert normalize_strategy_symbol("BTC/USDT:USDT") == "BTC/USDT"
    assert normalize_strategy_symbol("btcusdt") == "BTC/USDT"


def test_normalize_keeps_explicit_pair_unchanged():
    assert normalize_strategy_symbol("BTC/USDT") == "BTC/USDT"


def test_normalize_preserves_pool_and_equity_references():
    assert normalize_strategy_symbol("universe:POOL:sp500") == "universe:POOL:sp500"
    assert normalize_strategy_symbol("POOL:sp500") == "POOL:sp500"
    assert normalize_strategy_symbol("USStock:SPY") == "USStock:SPY"


def test_normalize_empty_symbol():
    assert normalize_strategy_symbol("") == ""
    assert normalize_strategy_symbol(None) == ""


def test_classify_symbol_kind():
    assert classify_strategy_symbol("BTC/USDT") == "crypto"
    assert classify_strategy_symbol("BTCUSDT") == "crypto"
    assert classify_strategy_symbol("universe:POOL:sp500") == "pool"
    assert classify_strategy_symbol("USStock:SPY") == "equity"
    assert classify_strategy_symbol("") == ""


def test_research_only_signal_or_pool():
    assert is_research_only_strategy(
        {"execution_mode": "signal", "symbol": "universe:POOL:sp500"}
    )
    # live 模式挂组合池仍不可在实盘通道成交
    assert is_research_only_strategy(
        {"execution_mode": "live", "symbol": "universe:POOL:sp500"}
    )
    # signal 模式即使挂单品种也只出信号，不进下单链路
    assert is_research_only_strategy({"execution_mode": "signal", "symbol": "BTC/USDT"})


def test_live_crypto_pair_not_research_only():
    assert not is_research_only_strategy(
        {"execution_mode": "live", "symbol": "BTC/USDT"}
    )
