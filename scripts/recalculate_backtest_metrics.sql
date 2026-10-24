-- 手动计算回测指标并更新数据库
-- 基于权益曲线计算总收益率、最大回撤等指标

-- 1. 查看最新和最旧的权益点
SELECT 
    run_id,
    MIN(timestamp) as start_time,
    MAX(timestamp) as end_time,
    (SELECT equity FROM qd_backtest_equity_points WHERE run_id = 5 ORDER BY timestamp ASC LIMIT 1) as start_equity,
    (SELECT equity FROM qd_backtest_equity_points WHERE run_id = 5 ORDER BY timestamp DESC LIMIT 1) as end_equity;

-- 2. 计算总收益率
-- 总收益率 = (期末权益 - 初始权益) / 初始权益

-- 3. 计算最大回撤
-- 最大回撤 = max((peak - trough) / peak)

-- 4. 更新数据库
-- UPDATE qd_backtest_runs 
-- SET total_return = ..., win_rate = ..., max_drawdown = ...
-- WHERE id = 5;
