-- 知识沉淀系统初始化SQL
-- 基于第一性原理：把运行时产生的经验转化为可复用的知识资产
-- 创建时间：2026-10-25

-- ============================================================
-- 1. 复盘记录表（Post-mortem）
-- ============================================================
CREATE TABLE IF NOT EXISTS qd_post_mortems (
    id BIGSERIAL PRIMARY KEY,
    post_mortem_uid VARCHAR(64) UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL,
    post_mortem_type VARCHAR(32) NOT NULL,  -- trade / weekly / monthly / incident / strategy_retirement
    severity VARCHAR(16),                   -- P0 / P1 / P2 / P3
    symbol VARCHAR(32),
    strategy_id BIGINT,
    related_decision_id BIGINT,              -- 关联 qd_ai_decisions.id
    related_trade_id BIGINT,                 -- 关联交易ID

    -- 五层次复盘
    what_happened TEXT,                      -- 发生了什么
    why_it_happened TEXT,                    -- 为什么发生（根因分析）
    what_we_learned TEXT,                    -- 学到了什么
    how_to_improve TEXT,                     -- 怎么改进
    how_to_harden TEXT,                      -- 怎么固化成规则

    -- 元数据
    root_cause_category VARCHAR(64),         -- data / signal / risk / execution / market / system
    action_items_json JSONB DEFAULT '[]',    -- 改进项
    status VARCHAR(16) DEFAULT 'open',        -- open / in_progress / closed
    owner VARCHAR(64),
    occurred_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_post_mortems_type ON qd_post_mortems(post_mortem_type);
CREATE INDEX IF NOT EXISTS idx_post_mortems_severity ON qd_post_mortems(severity);
CREATE INDEX IF NOT EXISTS idx_post_mortems_root_cause ON qd_post_mortems(root_cause_category);
CREATE INDEX IF NOT EXISTS idx_post_mortems_occurred ON qd_post_mortems(occurred_at DESC);

COMMENT ON TABLE qd_post_mortems IS '复盘记录表：交易复盘、周月复盘、故障复盘、策略退役复盘';

-- ============================================================
-- 2. 实验记录表（Experiment Log）
-- ============================================================
CREATE TABLE IF NOT EXISTS qd_experiment_logs (
    id BIGSERIAL PRIMARY KEY,
    experiment_uid VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    hypothesis TEXT NOT NULL,                -- 假设：我们相信X会导致Y

    -- 实验设计
    experiment_type VARCHAR(32),             -- ab_test / parameter_search / new_strategy / feature_test
    control_group TEXT,                       -- 对照组
    treatment_group TEXT,                     -- 实验组
    metrics_json JSONB DEFAULT '{}',          -- 评估指标
    sample_size INTEGER,
    duration_hours NUMERIC(10,2),

    -- 实验结果
    result_json JSONB DEFAULT '{}',          -- 结果数据
    p_value NUMERIC(8,6),                     -- 统计显著性
    effect_size NUMERIC(10,4),                -- 效应大小
    conclusion TEXT,                          -- 结论：显著/不显著/方向反了
    decision VARCHAR(32),                     -- rollout / iterate / abandon

    -- 防过拟合
    trials_count INTEGER DEFAULT 1,           -- 试验次数（包含失败）
    decision_rule_frozen BOOLEAN DEFAULT false,  -- 决策规则是否在实验前冻结
    freeze_at TIMESTAMP,

    -- 元数据
    status VARCHAR(16) DEFAULT 'running',    -- running / completed / abandoned
    strategy_id BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_experiments_status ON qd_experiment_logs(status);
CREATE INDEX IF NOT EXISTS idx_experiments_type ON qd_experiment_logs(experiment_type);
CREATE INDEX IF NOT EXISTS idx_experiments_decision ON qd_experiment_logs(decision);

COMMENT ON TABLE qd_experiment_logs IS '实验记录表：A/B测试、参数搜索、新策略验证，防过拟合';

-- ============================================================
-- 3. 故障知识库（Knowledge Base）
-- ============================================================
CREATE TABLE IF NOT EXISTS qd_fault_knowledge (
    id BIGSERIAL PRIMARY KEY,
    fault_uid VARCHAR(64) UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL,
    symptom TEXT NOT NULL,                    -- 故障现象
    root_cause TEXT,                          -- 根因
    solution TEXT,                            -- 解决方案
    prevention TEXT,                          -- 预防措施

    -- 分类
    category VARCHAR(64),                     -- data / code / config / network / market / exchange
    severity VARCHAR(16),                     -- P0 / P1 / P2 / P3
    occurrence_count INTEGER DEFAULT 1,       -- 发生次数
    tags_json JSONB DEFAULT '[]',              -- 标签

    -- 关联
    related_post_mortem_id BIGINT,
    related_decision_id BIGINT,

    -- 知识质量
    confidence_score NUMERIC(3,2) DEFAULT 0.5, -- 置信度 0-1
    verified BOOLEAN DEFAULT false,           -- 是否已验证
    status VARCHAR(16) DEFAULT 'active',     -- active / archived / deprecated

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_seen_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fault_kb_category ON qd_fault_knowledge(category);
CREATE INDEX IF NOT EXISTS idx_fault_kb_tags ON qd_fault_knowledge USING gin(tags_json);

COMMENT ON TABLE qd_fault_knowledge IS '故障知识库：故障现象→根因→解决方案，避免重复踩坑';

-- ============================================================
-- 4. 知识审计视图：统一查看所有决策、交易、复盘
-- ============================================================
CREATE OR REPLACE VIEW v_knowledge_audit AS
SELECT
    d.id,
    d.decision_uid AS record_uid,
    'decision' AS record_type,
    d.symbol,
    d.action,
    d.strategy_run_id AS strategy_id,
    d.confidence,
    d.allowed,
    d.reason AS summary,
    d.created_at AS recorded_at
FROM qd_ai_decisions d

UNION ALL

SELECT
    pm.id,
    pm.post_mortem_uid AS record_uid,
    'post_mortem' AS record_type,
    pm.symbol,
    pm.post_mortem_type AS action,
    pm.strategy_id,
    NULL::numeric AS confidence,
    true AS allowed,
    pm.title AS summary,
    pm.occurred_at AS recorded_at
FROM qd_post_mortems pm

UNION ALL

SELECT
    e.id,
    e.experiment_uid AS record_uid,
    'experiment' AS record_type,
    NULL AS symbol,
    e.decision AS action,
    e.strategy_id,
    e.p_value AS confidence,
    (e.decision = 'rollout') AS allowed,
    e.name AS summary,
    e.created_at AS recorded_at
FROM qd_experiment_logs e

UNION ALL

SELECT
    f.id,
    f.fault_uid AS record_uid,
    'fault' AS record_type,
    NULL AS symbol,
    f.category AS action,
    NULL::bigint AS strategy_id,
    f.confidence_score AS confidence,
    f.verified AS allowed,
    f.title AS summary,
    f.created_at AS recorded_at
FROM qd_fault_knowledge f

ORDER BY recorded_at DESC;

COMMENT ON VIEW v_knowledge_audit IS '知识审计视图：统一查看所有决策、复盘、实验、故障记录';

-- ============================================================
-- 5. 知识沉淀统计视图
-- ============================================================
CREATE OR REPLACE VIEW v_knowledge_stats AS
SELECT
    'decisions' AS knowledge_type,
    count(*) AS total_records,
    count(DISTINCT strategy_run_id) AS distinct_strategies,
    count(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') AS last_7d
FROM qd_ai_decisions

UNION ALL

SELECT
    'post_mortems',
    count(*),
    count(DISTINCT strategy_id),
    count(*) FILTER (WHERE occurred_at >= NOW() - INTERVAL '7 days')
FROM qd_post_mortems

UNION ALL

SELECT
    'experiments',
    count(*),
    count(DISTINCT strategy_id),
    count(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days')
FROM qd_experiment_logs

UNION ALL

SELECT
    'faults',
    count(*),
    NULL::bigint,
    count(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days')
FROM qd_fault_knowledge;

COMMENT ON VIEW v_knowledge_stats IS '知识沉淀统计：各类知识记录数量和活跃度';

-- ============================================================
-- 验证
-- ============================================================
-- 运行后验证：
-- \dt qd_*
-- SELECT * FROM v_knowledge_stats;
