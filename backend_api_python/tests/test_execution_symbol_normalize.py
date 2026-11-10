from app.services.live_trading.execution import _normalize_symbol_for_order


def test_slash_symbol_passes_through():
    assert _normalize_symbol_for_order("ETH/USDT") == "ETH/USDT"


def test_concatenated_symbol_splits_to_slash():
    assert _normalize_symbol_for_order("ETHUSDT") == "ETH/USDT"


def test_swap_suffix_stripped_before_normalize():
    assert _normalize_symbol_for_order("ETH/USDT:USDT") == "ETH/USDT"


def test_hyphen_inst_id_normalizes_to_slash():
    # OKX instId 风格 BASE-QUOTE 不应残留前导 '-'（#298/#299 缝隙）。
    assert _normalize_symbol_for_order("ETH-USDT") == "ETH/USDT"


def test_hyphen_is_case_insensitive():
    assert _normalize_symbol_for_order("eth-usdt") == "ETH/USDT"


def test_unknown_quote_falls_back_to_usdt():
    assert _normalize_symbol_for_order("PI") == "PI/USDT"


def test_empty_and_none_pass_through():
    assert _normalize_symbol_for_order("") == ""
    assert _normalize_symbol_for_order(None) is None


def test_multi_segment_contract_code_not_mis_split():
    # 多段合约代码（ETH-USDT-SWAP）不得被拆成 base 残留 '-' 的形式；
    # 保持既有兜底，不产出 "ETH-/..." 这类错误对。
    out = _normalize_symbol_for_order("ETH-USDT-SWAP")
    assert "ETH-/" not in out
