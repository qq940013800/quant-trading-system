-- 交易日志与绩效归因系统
-- 基于第一性原理：没有归因的交易系统 = 盲人骑瞎马

-- ============================================================
-- 1. 交易日志表
-- ============================================================
CREATE TABLE IF NOT EXISTS qd_trade_journal (
    id BIGSERIAL PRIMARY KEY,
    trade_uid VARCHAR(64) UNIQUE NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    side VARCHAR(16) NOT NULL,              -- buy / sell

    -- 时间
    entry_time TIMESTAMP NOT NULL,
    exit_time TIMESTAMP,
    holding_hours NUMERIC(10,2),

    -- 价格
    entry_price NUMERIC(18,8) NOT NULL,
    exit_price NUMERIC(18,8),
    quantity NUMERIC(18,8) NOT NULL,
    stop_loss NUMERIC(18,8),
    take_profit NUMERIC(18,8),

    -- 盈亏
    gross_pnl NUMERIC(18,8),
    commission NUMERIC(18,8) DEFAULT 0,
    slippage_cost NUMERIC(18,8) DEFAULT 0,
    net_pnl NUMERIC(18,8),
    return_pct NUMERIC(10,4),
    r_multiple NUMERIC(10,4),               -- 盈亏/初始风险

    -- 决策信息
    strategy_id BIGINT,
    decision_id VARCHAR(64),                 -- 关联 qd_ai_decisions
    market_regime VARCHAR(32),               -- trend / range / volatile
    entry_reason VARCHAR(255),
    exit_reason VARCHAR(255),
    confidence NUMERIC(5,2),

    -- 归因
    attributed_to VARCHAR(64),              -- 归因类别
    lesson_learned TEXT,
    post_mortem_id BIGINT,

    status VARCHAR(16) DEFAULT 'open',      -- open / closed
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trade_journal_symbol ON qd_trade_journal(symbol);
CREATE INDEX IF NOT EXISTS idx_trade_journal_status ON qd_trade_journal(status);
CREATE INDEX IF NOT EXISTS idx_trade_journal_entry_time ON qd_trade_journal(entry_time DESC);
CREATE INDEX IF NOT EXISTS idx_trade_journal_strategy ON qd_trade_journal(strategy_id);

COMMENT ON TABLE qd_trade_journal IS '交易日志：每笔交易的完整记录与归因';

-- ============================================================
-- 2. 绩效归因视图
-- ============================================================
CREATE OR REPLACE VIEW v_performance_summary AS
SELECT
    COUNT(*) AS total_trades,
    COUNT(*) FILTER (WHERE status = 'closed') AS closed_trades,
    COUNT(*) FILTER (WHERE net_pnl > 0 AND status = 'closed') AS winning_trades,
    COUNT(*) FILTER (WHERE net_pnl <= 0 AND status = 'closed') AS losing_trades,
    ROUND(
        COUNT(*) FILTER (WHERE net_pnl > 0 AND status = 'closed')::numeric /
        NULLIF(COUNT(*) FILTER (WHERE status = 'closed'), 0) * 100,
        2
    ) AS win_rate_pct,
    ROUND(AVG(net_pnl) FILTER (WHERE net_pnl > 0 AND status = 'closed'), 2) AS avg_win,
    ROUND(AVG(net_pnl) FILTER (WHERE net_pnl <= 0 AND status = 'closed'), 2) AS avg_loss,
    ROUND(
        AVG(net_pnl) FILTER (WHERE net_pnl > 0 AND status = 'closed') /
        NULLIF(ABS(AVG(net_pnl) FILTER (WHERE net_pnl <= 0 AND status = 'closed')), 0),
        2
    ) AS profit_factor,
    ROUND(SUM(net_pnl) FILTER (WHERE status = 'closed'), 2) AS total_net_pnl,
    ROUND(AVG(r_multiple) FILTER (WHERE status = 'closed'), 2) AS avg_r_multiple,
    ROUND(MAX(r_multiple) FILTER (WHERE status = 'closed'), 2) AS best_r_multiple,
    ROUND(MIN(r_multiple) FILTER (WHERE status = 'closed'), 2) AS worst_r_multiple
FROM qd_trade_journal;

COMMENT ON VIEW v_performance_summary IS '绩效汇总：胜率、盈亏比、Profit Factor、R倍数统计';

-- ============================================================
-- 3. 按品种归因视图
-- ============================================================
CREATE OR REPLACE VIEW v_symbol_attribution AS
SELECT
    symbol,
    COUNT(*) AS trades,
    COUNT(*) FILTER (WHERE net_pnl > 0) AS wins,
    ROUND(COUNT(*) FILTER (WHERE net_pnl > 0)::numeric / COUNT(*) * 100, 1) AS win_rate_pct,
    ROUND(SUM(net_pnl), 2) AS total_pnl,
    ROUND(AVG(r_multiple), 2) AS avg_r,
    ROUND(SUM(commission + slippage_cost), 2) AS total_costs
FROM qd_trade_journal
WHERE status = 'closed'
GROUP BY symbol
ORDER BY total_pnl DESC;

COMMENT ON VIEW v_symbol_attribution IS '按品种归因：哪个品种贡献收益，哪个在亏钱';

-- ============================================================
-- 4. 按市场状态归因视图
-- ============================================================
CREATE OR REPLACE VIEW v_regime_attribution AS
SELECT
    market_regime,
    COUNT(*) AS trades,
    ROUND(COUNT(*) FILTER (WHERE net_pnl > 0)::numeric / COUNT(*) * 100, 1) AS win_rate_pct,
    ROUND(AVG(r_multiple), 2) AS avg_r_multiple,
    ROUND(SUM(net_pnl), 2) AS total_pnl
FROM qd_trade_journal
WHERE status = 'closed' AND market_regime IS NOT NULL
GROUP BY market_regime;

COMMENT ON VIEW v_regime_attribution IS '按市场状态归因：策略在趋势/震荡市表现如何';

-- ============================================================
-- 5. 成本归因视图
-- ============================================================
CREATE OR REPLACE VIEW v_cost_attribution AS
SELECT
    COUNT(*) AS total_trades,
    ROUND(SUM(gross_pnl), 2) AS total_gross_pnl,
    ROUND(SUM(commission), 2) AS total_commission,
    ROUND(SUM(slippage_cost), 2) AS total_slippage,
    ROUND(SUM(commission + slippage_cost), 2) AS total_costs,
    ROUND(SUM(net_pnl), 2) AS total_net_pnl,
    ROUND(
        SUM(commission + slippage_cost)::numeric /
        NULLIF(SUM(ABS(gross_pnl)), 0) * 100,
        2
    ) AS cost_ratio_pct
FROM qd_trade_journal
WHERE status = 'closed';

COMMENT ON VIEW v_cost_attribution IS '成本归因：交易成本占毛收益的比例';

-- ============================================================
-- 验证
-- ============================================================
-- SELECT * FROM v_performance_summary;
-- SELECT * FROM v_symbol_attribution;
-- SELECT * FROM v_regime_attribution;
-- SELECT * FROM v_cost_attribution;
