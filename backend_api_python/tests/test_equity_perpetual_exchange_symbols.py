from app.services.live_trading.symbols import (
    to_binance_futures_symbol,
    to_bitget_um_symbol,
    to_bybit_symbol,
    to_gate_currency_pair,
    to_htx_contract_code,
    to_okx_spot_inst_id,
    to_okx_swap_inst_id,
)


def test_equity_perpetual_native_instrument_ids_for_six_exchanges():
    symbol = "AAPL/USDT"

    assert to_binance_futures_symbol(symbol) == "AAPLUSDT"
    assert to_bitget_um_symbol(symbol) == "AAPLUSDT"
    assert to_bybit_symbol(symbol) == "AAPLUSDT"
    assert to_okx_swap_inst_id(symbol) == "AAPL-USDT-SWAP"
    assert to_gate_currency_pair(symbol) == "AAPL_USDT"
    assert to_htx_contract_code(symbol) == "AAPL-USDT"


def test_hyphen_inst_id_matches_slash_and_concat_outputs():
    # 连字符 instId 风格（ETH-USDT）应与斜杠/拼接归一到同一交易所标识（#299）。
    for src in ("ETH-USDT", "ETH/USDT", "ETHUSDT"):
        assert to_okx_spot_inst_id(src) == "ETH-USDT"
        assert to_okx_swap_inst_id(src) == "ETH-USDT-SWAP"
        assert to_binance_futures_symbol(src) == "ETHUSDT"
        assert to_bitget_um_symbol(src) == "ETHUSDT"
        assert to_bybit_symbol(src) == "ETHUSDT"
        assert to_gate_currency_pair(src) == "ETH_USDT"
        assert to_htx_contract_code(src) == "ETH-USDT"


def test_multi_segment_contract_code_not_mis_split():
    # 多段合约代码不得被拆出残留 '-' 的 base（如 ETH--USDT-SWAP）。
    assert to_okx_spot_inst_id("ETH-USDT-SWAP") == "ETH-USDT-SWAP"
    assert to_okx_swap_inst_id("ETH-USDT-SWAP") == "ETH-USDT-SWAP"
