"""Knowledge pipeline service — read/write facade over the audit/knowledge tables.

Scope and boundaries (aligned with ``docs/design/knowledge-pipeline-design.md`` §6, §8):

- Read endpoints expose only persisted audit/knowledge data; write endpoints register
  faults, experiments, post-mortems and playbooks. This service **does not** place
  orders, change positions, or accept risk-threshold parameters.
- Fail-open: reads return empty collections on DB failure; writes return
  ``written=False`` / ``None``. Failures are logged with context and are never
  propagated into a trading decision path (design §5.3, §6.1).
- The backend container does not ship the ``core`` package (verified:
  ``ModuleNotFoundError: No module named 'core'`` in ``qdpro-backend``), so this
  service talks to Postgres through the backend pool (``DATABASE_URL``) directly.
  Filtering/normalization semantics mirror ``core/audit`` (faults default to
  ``verified=true``; post-mortems default to ``status='closed'``); if ``core`` is
  later mounted into the backend image, the retrieval predicates should be
  reconciled against ``core/audit/knowledge_retriever.py``.

Tables touched are knowledge/audit tables only. Capital-flow ledgers
(``qd_quick_trades`` / ``qd_strategy_trades`` / ``qd_strategies_trading`` /
``ledger``) are intentionally out of scope.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from app.utils.db import get_db_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Allowed decision outcomes for an experiment (aligned with core/audit
# experiment_logger.py; decision-rule freeze is recorded at start).
_EXPERIMENT_DECISIONS = {"promote_to_production", "pivot", "abandon"}
_EXPERIMENT_TYPES = {
    "backtest", "ab_test", "parameter_tuning", "new_strategy",
    "feature_test", "parameter_search",
}
_FAULT_CATEGORIES = {"data", "code", "config", "network", "market", "exchange", "system"}
_SEVERITIES = {"P0", "P1", "P2", "P3"}
_PLAYBOOK_STATUSES = {"draft", "active", "archived"}


def _gen_uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _limit(value: Any, default: int = 20, cap: int = 100) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return min(max(n, 1), cap)


class KnowledgeService:
    """Read/write facade for the knowledge and audit pipeline."""

    def __init__(self):
        self._ensure_playbook_table()

    # ------------------------------------------------------------------
    # Schema bootstrap (idempotent; mirrors analysis_memory service pattern)
    # ------------------------------------------------------------------
    def _ensure_playbook_table(self) -> None:
        """Create the playbook table if missing (design §8.2b).

        Existing knowledge tables are reused as-is; this only provisions the
        playbook table, which has no CREATE DDL in ``migrations/init.sql``.
        """
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS qd_playbooks (
                        id BIGSERIAL PRIMARY KEY,
                        playbook_uid VARCHAR(64) UNIQUE NOT NULL,
                        title VARCHAR(255) NOT NULL,
                        strategy_type VARCHAR(64),
                        tags_json JSONB DEFAULT '[]'::jsonb,
                        trigger_conditions JSONB DEFAULT '{}'::jsonb,
                        preconditions_json JSONB DEFAULT '[]'::jsonb,
                        steps_json JSONB DEFAULT '[]'::jsonb,
                        risk_controls_json JSONB DEFAULT '[]'::jsonb,
                        source_refs_json JSONB DEFAULT '[]'::jsonb,
                        version INTEGER DEFAULT 1,
                        status VARCHAR(16) DEFAULT 'draft',
                        owner VARCHAR(64),
                        reproducibility_json JSONB DEFAULT '{}'::jsonb,
                        validated_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                    """
                )
                db.commit()
                cur.close()
        except Exception as exc:  # fail-open: table bootstrap is non-critical
            logger.warning("playbook table bootstrap skipped: %s", exc)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def list_faults(
        self,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        verified: Optional[bool] = None,
        limit: Any = 20,
    ) -> List[Dict[str, Any]]:
        sql = """
            SELECT fault_uid, title, symptom, root_cause, solution, prevention,
                   category, severity, occurrence_count, tags_json,
                   confidence_score, verified, updated_at
            FROM qd_fault_knowledge
            WHERE 1=1
        """
        params: List[Any] = []
        # Baseline retrieval mirrors core/audit: only verified faults by default.
        if verified is None:
            sql += " AND verified = TRUE"
        elif verified:
            sql += " AND verified = TRUE"
        else:
            sql += " AND verified = FALSE"

        if keyword:
            sql += """ AND (
                title ILIKE %s OR symptom ILIKE %s OR
                root_cause ILIKE %s OR solution ILIKE %s
            )"""
            like = f"%{keyword}%"
            params.extend([like, like, like, like])
        if category:
            sql += " AND category = %s"
            params.append(category)
        if severity:
            sql += " AND severity = %s"
            params.append(severity)

        sql += " ORDER BY confidence_score DESC, occurrence_count DESC LIMIT %s"
        params.append(_limit(limit))

        try:
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute(sql, tuple(params))
                rows = cur.fetchall() or []
                cur.close()
            return [self._normalize_fault(row) for row in rows]
        except Exception as exc:
            logger.warning("list_faults failed: %s", exc)
            return []

    def list_experiments(
        self,
        strategy_id: Any = None,
        status: Optional[str] = None,
        decision: Optional[str] = None,
        experiment_type: Optional[str] = None,
        limit: Any = 20,
    ) -> List[Dict[str, Any]]:
        sql = """
            SELECT experiment_uid, name, hypothesis, experiment_type,
                   control_group, treatment_group, metrics_json, sample_size,
                   duration_hours, p_value, effect_size, conclusion, decision,
                   result_json, trials_count, decision_rule_frozen, status, strategy_id,
                   created_at, completed_at
            FROM qd_experiment_logs
            WHERE 1=1
        """
        params: List[Any] = []
        if strategy_id is not None:
            sql += " AND strategy_id = %s"
            params.append(strategy_id)
        if status:
            sql += " AND status = %s"
            params.append(status)
        if decision:
            sql += " AND decision = %s"
            params.append(decision)
        if experiment_type:
            sql += " AND experiment_type = %s"
            params.append(experiment_type)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(_limit(limit))

        try:
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute(sql, tuple(params))
                rows = cur.fetchall() or []
                cur.close()
            return [self._normalize_experiment(row) for row in rows]
        except Exception as exc:
            logger.warning("list_experiments failed: %s", exc)
            return []

    def list_playbooks(
        self,
        strategy_type: Optional[str] = None,
        tag: Optional[str] = None,
        validated: Optional[bool] = None,
        limit: Any = 20,
    ) -> List[Dict[str, Any]]:
        sql = """
            SELECT playbook_uid, title, strategy_type, tags_json,
                   trigger_conditions, preconditions_json, steps_json,
                   risk_controls_json, source_refs_json, version, status,
                   owner, validated_at, created_at, updated_at
            FROM qd_playbooks
            WHERE 1=1
        """
        params: List[Any] = []
        if strategy_type:
            sql += " AND strategy_type = %s"
            params.append(strategy_type)
        if validated is None:
            sql += " AND validated_at IS NOT NULL"
        elif validated:
            sql += " AND validated_at IS NOT NULL"
        else:
            sql += " AND validated_at IS NULL"
        if tag:
            sql += " AND tags_json @> %s"
            params.append(json.dumps([tag]))
        sql += " ORDER BY updated_at DESC LIMIT %s"
        params.append(_limit(limit))

        try:
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute(sql, tuple(params))
                rows = cur.fetchall() or []
                cur.close()
            return [self._normalize_playbook(row) for row in rows]
        except Exception as exc:
            logger.warning("list_playbooks failed: %s", exc)
            return []

    def get_stats(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {
            "fault_knowledge": {"total": 0, "verified": 0},
            "post_mortems": {"total": 0, "closed": 0},
            "experiments": {"total": 0, "completed": 0},
            "playbooks": {"total": 0, "validated": 0},
        }
        queries = {
            "fault_total": "SELECT COUNT(*) FROM qd_fault_knowledge",
            "fault_verified": "SELECT COUNT(*) FROM qd_fault_knowledge WHERE verified = TRUE",
            "pm_total": "SELECT COUNT(*) FROM qd_post_mortems",
            "pm_closed": "SELECT COUNT(*) FROM qd_post_mortems WHERE status = 'closed'",
            "exp_total": "SELECT COUNT(*) FROM qd_experiment_logs",
            "exp_completed": "SELECT COUNT(*) FROM qd_experiment_logs WHERE status = 'completed'",
            "pb_total": "SELECT COUNT(*) FROM qd_playbooks",
            "pb_validated": "SELECT COUNT(*) FROM qd_playbooks WHERE validated_at IS NOT NULL",
        }
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                counts: Dict[str, int] = {}
                for key, sql in queries.items():
                    cur.execute(sql)
                    row = cur.fetchone()
                    counts[key] = int(row[0]) if row else 0
                cur.close()
            stats["fault_knowledge"] = {"total": counts["fault_total"], "verified": counts["fault_verified"]}
            stats["post_mortems"] = {"total": counts["pm_total"], "closed": counts["pm_closed"]}
            stats["experiments"] = {"total": counts["exp_total"], "completed": counts["exp_completed"]}
            stats["playbooks"] = {"total": counts["pb_total"], "validated": counts["pb_validated"]}
        except Exception as exc:
            logger.warning("get_stats failed: %s", exc)
        return stats

    def get_lessons(self, symbol: str = "", side: str = "", signal_type: str = "") -> List[Dict[str, Any]]:
        """Decision-context lessons: verified faults + closed post-mortems.

        Lessons are reference context only; they are never fed into a risk
        accept/reject decision (design §5.1 observation/decision separation).
        """
        keyword = " ".join(p for p in (symbol, side, signal_type) if p).strip()
        lessons: List[Dict[str, Any]] = []
        if not keyword:
            return lessons

        faults = self.list_faults(keyword=keyword, verified=True, limit=3)
        for fault in faults:
            lessons.append({
                "source": "fault",
                "uid": fault.get("fault_uid"),
                "summary": fault.get("title"),
                "solution": fault.get("solution"),
            })

        try:
            with get_db_connection() as db:
                cur = db.cursor()
                like = f"%{keyword}%"
                cur.execute(
                    """
                    SELECT post_mortem_uid, title, what_we_learned
                    FROM qd_post_mortems
                    WHERE status = 'closed'
                      AND (title ILIKE %s OR what_happened ILIKE %s OR what_we_learned ILIKE %s)
                    ORDER BY created_at DESC LIMIT %s
                    """,
                    (like, like, like, 2),
                )
                pms = cur.fetchall() or []
                cur.close()
            for pm in pms:
                lessons.append({
                    "source": "post_mortem",
                    "uid": pm.get("post_mortem_uid"),
                    "summary": pm.get("title"),
                    "solution": (pm.get("what_we_learned") or "")[:200],
                })
        except Exception as exc:
            logger.warning("get_lessons post-mortem lookup failed: %s", exc)
        return lessons

    # ------------------------------------------------------------------
    # Writes (idempotent on business uid; fail-open)
    # ------------------------------------------------------------------
    def register_fault(
        self,
        title: str,
        symptom: str,
        root_cause: str = "",
        solution: str = "",
        prevention: str = "",
        category: str = "system",
        severity: str = "P2",
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if not title or not symptom:
            return {"fault_uid": None, "written": False, "reason": "missing_title_or_symptom"}
        if category not in _FAULT_CATEGORIES:
            category = "system"
        if severity not in _SEVERITIES:
            severity = "P2"
        fault_uid = _gen_uid("fault")
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute(
                    """
                    INSERT INTO qd_fault_knowledge (
                        fault_uid, title, symptom, root_cause, solution, prevention,
                        category, severity, occurrence_count, tags_json,
                        verified, confidence_score
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s, FALSE, 0.5)
                    ON CONFLICT (fault_uid) DO NOTHING
                    """,
                    (fault_uid, title, symptom, root_cause, solution, prevention,
                     category, severity, tags_json),
                )
                db.commit()
                cur.close()
            logger.info("fault registered: %s", fault_uid)
            return {"fault_uid": fault_uid, "written": True}
        except Exception as exc:
            logger.warning("register_fault failed: %s", exc)
            return {"fault_uid": None, "written": False, "reason": str(exc)}

    def start_experiment(
        self,
        name: str,
        hypothesis: str,
        experiment_type: str = "backtest",
        control_group: Optional[str] = None,
        treatment_group: Optional[str] = None,
        sample_size: Any = None,
        duration_hours: Any = None,
        strategy_id: Any = None,
    ) -> Dict[str, Any]:
        if not name or not hypothesis:
            return {"experiment_uid": None, "written": False, "reason": "missing_name_or_hypothesis"}
        if experiment_type not in _EXPERIMENT_TYPES:
            experiment_type = "backtest"
        experiment_uid = _gen_uid("exp")
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute(
                    """
                    INSERT INTO qd_experiment_logs (
                        experiment_uid, name, hypothesis, experiment_type,
                        control_group, treatment_group, sample_size, duration_hours,
                        strategy_id, decision_rule_frozen, freeze_at, trials_count, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, NOW(), 1, 'running')
                    ON CONFLICT (experiment_uid) DO NOTHING
                    """,
                    (experiment_uid, name, hypothesis, experiment_type,
                     control_group, treatment_group, sample_size, duration_hours, strategy_id),
                )
                db.commit()
                cur.close()
            logger.info("experiment started: %s", experiment_uid)
            return {"experiment_uid": experiment_uid, "written": True}
        except Exception as exc:
            logger.warning("start_experiment failed: %s", exc)
            return {"experiment_uid": None, "written": False, "reason": str(exc)}

    def end_experiment(
        self,
        experiment_uid: str,
        metrics: Dict[str, Any],
        conclusion: str,
        decision: str,
        p_value: Any = None,
        effect_size: Any = None,
    ) -> Dict[str, Any]:
        if not experiment_uid:
            return {"written": False, "reason": "missing_experiment_uid"}
        if decision not in _EXPERIMENT_DECISIONS:
            return {"written": False, "reason": "invalid_decision"}
        metrics_json = json.dumps(metrics or {}, ensure_ascii=False)
        result_json = json.dumps({"final_metrics": metrics or {}}, ensure_ascii=False)
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                # Guard: promote is only allowed for a decision-rule-frozen
                # experiment (design §6.3, AGENTS rule 11). Re-read the frozen
                # flag on the existing row before closing the experiment.
                cur.execute(
                    "SELECT decision_rule_frozen, status FROM qd_experiment_logs "
                    "WHERE experiment_uid = %s",
                    (experiment_uid,),
                )
                row = cur.fetchone()
                if row is None:
                    cur.close()
                    return {"written": False, "reason": "experiment_not_found"}
                frozen = bool(row.get("decision_rule_frozen")) if isinstance(row, dict) else bool(row[0])
                if decision == "promote_to_production" and not frozen:
                    cur.close()
                    return {"written": False, "reason": "rule_not_frozen"}
                cur.execute(
                    """
                    UPDATE qd_experiment_logs
                    SET metrics_json = %s, result_json = %s, p_value = %s,
                        effect_size = %s, conclusion = %s, decision = %s,
                        status = 'completed', completed_at = NOW()
                    WHERE experiment_uid = %s
                    """,
                    (metrics_json, result_json, p_value, effect_size,
                     conclusion, decision, experiment_uid),
                )
                db.commit()
                cur.close()
            logger.info("experiment ended: %s decision=%s", experiment_uid, decision)
            return {"written": True}
        except Exception as exc:
            logger.warning("end_experiment failed: %s", exc)
            return {"written": False, "reason": str(exc)}

    def register_post_mortem(
        self,
        title: str,
        post_mortem_type: str,
        severity: str,
        what_happened: str,
        why_it_happened: str,
        what_we_learned: str,
        how_to_improve: str,
        how_to_harden: str = "",
        root_cause_category: str = "system",
        symbol: Optional[str] = None,
        strategy_id: Any = None,
        action_items: Optional[List[Dict[str, Any]]] = None,
        owner: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not title or not what_happened:
            return {"post_mortem_uid": None, "written": False, "reason": "missing_title_or_what_happened"}
        if severity not in _SEVERITIES:
            severity = "P2"
        pm_uid = _gen_uid("pm")
        action_items_json = json.dumps(action_items or [], ensure_ascii=False)
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute(
                    """
                    INSERT INTO qd_post_mortems (
                        post_mortem_uid, title, post_mortem_type, severity,
                        symbol, strategy_id, how_to_harden, action_items_json, owner,
                        root_cause_category, what_happened, why_it_happened,
                        what_we_learned, how_to_improve, status, occurred_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'open', NOW())
                    ON CONFLICT (post_mortem_uid) DO NOTHING
                    """,
                    (pm_uid, title, post_mortem_type, severity, symbol, strategy_id,
                     how_to_harden, action_items_json, owner, root_cause_category,
                     what_happened, why_it_happened, what_we_learned, how_to_improve),
                )
                db.commit()
                cur.close()
            logger.info("post-mortem registered: %s", pm_uid)
            return {"post_mortem_uid": pm_uid, "written": True}
        except Exception as exc:
            logger.warning("register_post_mortem failed: %s", exc)
            return {"post_mortem_uid": None, "written": False, "reason": str(exc)}

    def upsert_playbook(
        self,
        title: str,
        strategy_type: str = "",
        tags: Optional[List[str]] = None,
        trigger_conditions: Optional[Dict[str, Any]] = None,
        preconditions: Optional[List[Dict[str, Any]]] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
        risk_controls: Optional[List[Dict[str, Any]]] = None,
        source_refs: Optional[List[Dict[str, Any]]] = None,
        status: str = "draft",
        owner: Optional[str] = None,
        reproducibility: Optional[Dict[str, Any]] = None,
        playbook_uid: Optional[str] = None,
        validated: bool = False,
    ) -> Dict[str, Any]:
        if not title:
            return {"playbook_uid": None, "version": None, "written": False, "reason": "missing_title"}
        if status not in _PLAYBOOK_STATUSES:
            status = "draft"
        if not source_refs:
            return {"playbook_uid": None, "version": None, "written": False,
                    "reason": "missing_source_refs"}
        uid = playbook_uid or _gen_uid("pb")
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        trigger_json = json.dumps(trigger_conditions or {}, ensure_ascii=False)
        pre_json = json.dumps(preconditions or [], ensure_ascii=False)
        steps_json = json.dumps(steps or [], ensure_ascii=False)
        risk_json = json.dumps(risk_controls or [], ensure_ascii=False)
        refs_json = json.dumps(source_refs, ensure_ascii=False)
        repro_json = json.dumps(reproducibility or {}, ensure_ascii=False)
        validated_sql = "NOW()" if validated else "NULL"
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute(
                    f"""
                    INSERT INTO qd_playbooks (
                        playbook_uid, title, strategy_type, tags_json,
                        trigger_conditions, preconditions_json, steps_json,
                        risk_controls_json, source_refs_json, status, owner,
                        reproducibility_json, validated_at, version
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, {validated_sql}, 1)
                    ON CONFLICT (playbook_uid) DO UPDATE SET
                        title = EXCLUDED.title,
                        strategy_type = EXCLUDED.strategy_type,
                        tags_json = EXCLUDED.tags_json,
                        trigger_conditions = EXCLUDED.trigger_conditions,
                        preconditions_json = EXCLUDED.preconditions_json,
                        steps_json = EXCLUDED.steps_json,
                        risk_controls_json = EXCLUDED.risk_controls_json,
                        source_refs_json = EXCLUDED.source_refs_json,
                        status = EXCLUDED.status,
                        owner = EXCLUDED.owner,
                        reproducibility_json = EXCLUDED.reproducibility_json,
                        version = qd_playbooks.version + 1,
                        updated_at = NOW()
                    """,
                    (uid, title, strategy_type, tags_json, trigger_json, pre_json,
                     steps_json, risk_json, refs_json, status, owner, repro_json),
                )
                db.commit()
                cur.execute(
                    "SELECT version FROM qd_playbooks WHERE playbook_uid = %s",
                    (uid,),
                )
                version_row = cur.fetchone()
                cur.close()
            version = 1
            if version_row is not None:
                version = version_row.get("version") if isinstance(version_row, dict) else version_row[0]
            logger.info("playbook upserted: %s", uid)
            return {"playbook_uid": uid, "version": version, "written": True}
        except Exception as exc:
            logger.warning("upsert_playbook failed: %s", exc)
            return {"playbook_uid": None, "version": None, "written": False, "reason": str(exc)}

    # ------------------------------------------------------------------
    # Row normalization
    # ------------------------------------------------------------------
    @staticmethod
    def _load_json(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (list, dict)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value

    def _normalize_fault(self, row: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(row)
        out["tags"] = self._load_json(out.pop("tags_json", None)) or []
        return out

    def _normalize_experiment(self, row: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(row)
        out["metrics"] = self._load_json(out.pop("metrics_json", None))
        out["result"] = self._load_json(out.pop("result_json", None))
        return out

    def _normalize_playbook(self, row: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(row)
        out["tags"] = self._load_json(out.pop("tags_json", None)) or []
        out["trigger_conditions"] = self._load_json(out.pop("trigger_conditions", None))
        out["preconditions"] = self._load_json(out.pop("preconditions_json", None))
        out["steps"] = self._load_json(out.pop("steps_json", None))
        out["risk_controls"] = self._load_json(out.pop("risk_controls_json", None))
        out["source_refs"] = self._load_json(out.pop("source_refs_json", None))
        out["reproducibility"] = self._load_json(out.pop("reproducibility_json", None))
        out["validated"] = out.get("validated_at") is not None
        return out


_service_instance: Optional[KnowledgeService] = None


def get_knowledge_service() -> KnowledgeService:
    """Global knowledge-pipeline service singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = KnowledgeService()
    return _service_instance
