-- 更新策略1: ML增强趋势策略 (source_version_id=15, source_id=8)
UPDATE qd_strategies_trading 
SET trading_config = '{"script_source_id": 8, "script_source_version_id": 15}'::jsonb
WHERE id = 1;

-- 更新策略2: 均值回归策略 (source_version_id=11, source_id=7)
UPDATE qd_strategies_trading 
SET trading_config = '{"script_source_id": 7, "script_source_version_id": 11}'::jsonb
WHERE id = 2;

-- 更新策略3: 突破策略 (source_version_id=19, source_id=10)
UPDATE qd_strategies_trading 
SET trading_config = '{"script_source_id": 10, "script_source_version_id": 19}'::jsonb
WHERE id = 3;

-- 验证结果
SELECT id, strategy_name, source_version_id, trading_config FROM qd_strategies_trading;
