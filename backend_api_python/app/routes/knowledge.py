"""Knowledge pipeline HTTP routes (audit / faults / experiments / post-mortems / playbooks).

Boundaries (design §6.4, §8.3):
- These endpoints read persisted knowledge/audit data and register knowledge
  entries. They do **not** place orders, change positions, or accept risk-threshold
  parameters.
- Retrieved lessons are reference context only and are never consumed by a risk
  accept/reject decision.
- Reads are fail-open (empty list on DB failure); writes report ``written=False``
  instead of raising into the trading path.
"""
from __future__ import annotations

from flask import g, jsonify, request

from app.openapi.blueprint import HumanBlueprint as Blueprint
from app.services.knowledge_service import get_knowledge_service
from app.utils.auth import login_required

knowledge_blp = Blueprint("knowledge", __name__)


def _body() -> dict:
    return request.get_json(silent=True) or {}


def _ok(data):
    return jsonify({"code": 1, "msg": "success", "data": data})


def _bad(msg: str, status: int = 400):
    return jsonify({"code": 0, "msg": msg, "data": None}), status


# ----------------------------------------------------------------------
# Reads
# ----------------------------------------------------------------------
@knowledge_blp.route("/faults", methods=["GET"])
@login_required
def list_faults():
    """List verified fault-knowledge entries (baseline keyword + category filter)."""
    service = get_knowledge_service()
    data = service.list_faults(
        keyword=request.args.get("keyword", "").strip() or None,
        category=request.args.get("category", "").strip() or None,
        severity=request.args.get("severity", "").strip() or None,
        verified=_parse_bool(request.args.get("verified")),
        limit=request.args.get("limit", 20),
    )
    return _ok({"items": data, "total": len(data)})


@knowledge_blp.route("/experiments", methods=["GET"])
@login_required
def list_experiments():
    service = get_knowledge_service()
    data = service.list_experiments(
        strategy_id=request.args.get("strategy_id"),
        status=request.args.get("status", "").strip() or None,
        decision=request.args.get("decision", "").strip() or None,
        experiment_type=request.args.get("experiment_type", "").strip() or None,
        limit=request.args.get("limit", 20),
    )
    return _ok({"items": data, "total": len(data)})


@knowledge_blp.route("/playbooks", methods=["GET"])
@login_required
def list_playbooks():
    service = get_knowledge_service()
    data = service.list_playbooks(
        strategy_type=request.args.get("strategy_type", "").strip() or None,
        tag=request.args.get("tag", "").strip() or None,
        validated=_parse_bool(request.args.get("validated")),
        limit=request.args.get("limit", 20),
    )
    return _ok({"items": data, "total": len(data)})


@knowledge_blp.route("/stats", methods=["GET"])
@login_required
def knowledge_stats():
    return _ok(get_knowledge_service().get_stats())


@knowledge_blp.route("/lessons", methods=["GET"])
@login_required
def decision_lessons():
    """Decision-context lessons for a symbol/side/signal type (reference only)."""
    service = get_knowledge_service()
    lessons = service.get_lessons(
        symbol=request.args.get("symbol", "").strip(),
        side=request.args.get("side", "").strip(),
        signal_type=request.args.get("signal_type", "").strip(),
    )
    return _ok({"lessons": lessons})


# ----------------------------------------------------------------------
# Writes
# ----------------------------------------------------------------------
@knowledge_blp.route("/faults", methods=["POST"])
@login_required
def register_fault():
    body = _body()
    if not body.get("title") or not body.get("symptom"):
        return _bad("title and symptom are required")
    result = get_knowledge_service().register_fault(
        title=str(body.get("title")),
        symptom=str(body.get("symptom")),
        root_cause=str(body.get("root_cause", "")),
        solution=str(body.get("solution", "")),
        prevention=str(body.get("prevention", "")),
        category=str(body.get("category", "system")),
        severity=str(body.get("severity", "P2")),
        tags=body.get("tags") or [],
    )
    if not result.get("written"):
        return _bad(result.get("reason") or "fault registration failed", 500)
    return _ok(result)


@knowledge_blp.route("/experiments/start", methods=["POST"])
@login_required
def start_experiment():
    body = _body()
    if not body.get("name") or not body.get("hypothesis"):
        return _bad("name and hypothesis are required")
    result = get_knowledge_service().start_experiment(
        name=str(body.get("name")),
        hypothesis=str(body.get("hypothesis")),
        experiment_type=str(body.get("experiment_type", "backtest")),
        control_group=body.get("control_group"),
        treatment_group=body.get("treatment_group"),
        sample_size=body.get("sample_size"),
        duration_hours=body.get("duration_hours"),
        strategy_id=body.get("strategy_id"),
    )
    if not result.get("written"):
        return _bad(result.get("reason") or "experiment start failed", 500)
    return _ok(result)


@knowledge_blp.route("/experiments/<experiment_uid>/end", methods=["POST"])
@login_required
def end_experiment(experiment_uid: str):
    body = _body()
    if not body.get("decision"):
        return _bad("decision is required")
    result = get_knowledge_service().end_experiment(
        experiment_uid=experiment_uid,
        metrics=body.get("metrics") or {},
        conclusion=str(body.get("conclusion", "")),
        decision=str(body.get("decision")),
        p_value=body.get("p_value"),
        effect_size=body.get("effect_size"),
    )
    if not result.get("written"):
        return _bad(result.get("reason") or "experiment end failed", 400)
    return _ok(result)


@knowledge_blp.route("/post-mortems", methods=["POST"])
@login_required
def register_post_mortem():
    body = _body()
    if not body.get("title") or not body.get("what_happened"):
        return _bad("title and what_happened are required")
    result = get_knowledge_service().register_post_mortem(
        title=str(body.get("title")),
        post_mortem_type=str(body.get("post_mortem_type", "incident")),
        severity=str(body.get("severity", "P2")),
        what_happened=str(body.get("what_happened")),
        why_it_happened=str(body.get("why_it_happened", "")),
        what_we_learned=str(body.get("what_we_learned", "")),
        how_to_improve=str(body.get("how_to_improve", "")),
        how_to_harden=str(body.get("how_to_harden", "")),
        root_cause_category=str(body.get("root_cause_category", "system")),
        symbol=body.get("symbol"),
        strategy_id=body.get("strategy_id"),
        action_items=body.get("action_items") or [],
        owner=body.get("owner"),
    )
    if not result.get("written"):
        return _bad(result.get("reason") or "post-mortem registration failed", 500)
    return _ok(result)


@knowledge_blp.route("/playbooks", methods=["POST"])
@login_required
def upsert_playbook():
    body = _body()
    if not body.get("title"):
        return _bad("title is required")
    if not body.get("source_refs"):
        return _bad("source_refs must reference at least one post-mortem/experiment/fault")
    result = get_knowledge_service().upsert_playbook(
        title=str(body.get("title")),
        strategy_type=str(body.get("strategy_type", "")),
        tags=body.get("tags") or [],
        trigger_conditions=body.get("trigger_conditions") or {},
        preconditions=body.get("preconditions") or [],
        steps=body.get("steps") or [],
        risk_controls=body.get("risk_controls") or [],
        source_refs=body.get("source_refs"),
        status=str(body.get("status", "draft")),
        owner=body.get("owner"),
        reproducibility=body.get("reproducibility") or {},
        playbook_uid=body.get("playbook_uid"),
        validated=bool(body.get("validated", False)),
    )
    if not result.get("written"):
        return _bad(result.get("reason") or "playbook upsert failed", 400)
    return _ok(result)


def _parse_bool(raw: str | None):
    if raw is None or raw == "":
        return None
    return str(raw).strip().lower() in ("1", "true", "yes", "y", "on")
