# -*- coding: utf-8 -*-
"""core.audit.knowledge_normalize —— 经验条目结构化与标签归一（纯逻辑）。

第一性原理：
    沉淀进知识库的经验，来源形态五花八门（自由文本、半成品字典、日志摘录）。
    入库前必须归一到同一套字段与标签口径，否则检索时同义不同名、
    大小写/空白不一致，知识无法复用。

纯逻辑约束：
    - 同义词映射、严重度/状态映射都是模块内纯数据；
    - 不依赖 DB 连接、网络、向量库或文件系统；
    - 标签小写、去空白、分隔符归一、同义词折叠；
    - 未知取值走默认值并在 warnings 里留痕，便于事后审计。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence, Union

# ------------------------------------------------------------------
# 纯数据：标签同义词映射（别名 → 规范标签）
# ------------------------------------------------------------------
SYNONYM_TAGS: dict[str, str] = {
    # 连接 / 网络
    "connection": "connection",
    "connect": "connection",
    "conn": "connection",
    "network": "connection",
    "连接": "connection",
    "连接失败": "connection",
    "连接问题": "connection",
    "断线": "connection",
    # 超时 / 延迟
    "timeout": "timeout",
    "timed out": "timeout",
    "time out": "timeout",
    "latency": "latency",
    "延迟": "latency",
    "延迟高": "latency",
    "超时": "timeout",
    # 下单 / 订单
    "order": "order",
    "trade": "order",
    "下单": "order",
    "订单": "order",
    "成交": "order",
    # 风控 / 止损 / 滑点
    "risk": "risk",
    "margin": "risk",
    "风控": "risk",
    "风险": "risk",
    "stop_loss": "stop_loss",
    "stop loss": "stop_loss",
    "stoploss": "stop_loss",
    "止损": "stop_loss",
    "slippage": "slippage",
    "滑点": "slippage",
    # 数据
    "data": "data",
    "empty": "data",
    "missing": "data",
    "数据": "data",
    "空值": "data",
    # 配置 / 权限 / 系统
    "config": "config",
    "setting": "config",
    "配置": "config",
    "permission": "permission",
    "denied": "permission",
    "forbidden": "permission",
    "权限": "permission",
    "system": "system",
    "bug": "system",
    "crash": "system",
    "系统": "system",
    # 接口 / 数据库
    "api": "api",
    "http": "api",
    "接口": "api",
    "db": "db",
    "database": "db",
    "postgres": "db",
    "数据库": "db",
}

# 严重度归一（别名 → P0/P1/P2/P3）
SEVERITY_MAP: dict[str, str] = {
    "p0": "P0", "critical": "P0", "紧急": "P0", "致命": "P0",
    "p1": "P1", "high": "P1", "高": "P1", "严重": "P1",
    "p2": "P2", "medium": "P2", "中": "P2", "一般": "P2",
    "p3": "P3", "low": "P3", "info": "P3", "低": "P3", "提示": "P3",
}
DEFAULT_SEVERITY = "P3"

# 状态归一（别名 → open/investigating/closed/verified）
STATUS_MAP: dict[str, str] = {
    "open": "open", "pending": "open", "待处理": "open", "未开始": "open",
    "investigating": "investigating", "in_progress": "investigating",
    "处理中": "investigating", "分析中": "investigating",
    "closed": "closed", "resolved": "closed", "fixed": "closed",
    "已关闭": "closed", "已修复": "closed", "已解决": "closed",
    "verified": "verified", "confirmed": "verified",
    "已验证": "verified", "已确认": "verified",
}
DEFAULT_STATUS = "open"

# 条目字段别名（dict 键 → 规范字段）
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "entry_id": ("id", "entry_id", "uid", "fault_uid", "post_mortem_uid"),
    "title": ("title", "name", "标题", "名称"),
    "symptom": ("symptom", "what_happened", "症状", "现象", "故障现象"),
    "root_cause": ("root_cause", "rootcause", "why_it_happened", "根因", "原因", "根本原因"),
    "solution": ("solution", "how_to_improve", "fix", "方案", "解决方案", "修复方案", "改进措施"),
    "tags": ("tags", "labels", "category", "标签", "分类"),
    "severity": ("severity", "level", "严重度", "等级"),
    "status": ("status", "状态"),
}

_PUNCT_SPLIT_RE = re.compile(r"[、,，;；/]+")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_WS_RE = re.compile(r"\s+")


def normalize_text(raw: Any) -> str:
    """文本归一：去控制符、折叠空白、小写。"""
    if raw is None:
        return ""
    text = str(raw)
    text = _CONTROL_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip().lower()


def normalize_tag(raw: Any) -> str:
    """单个标签归一：小写、去空白、分隔符折叠、同义词折叠。"""
    tag = normalize_text(raw)
    if not tag:
        return ""
    if tag in SYNONYM_TAGS:
        return SYNONYM_TAGS[tag]
    tag = tag.replace("-", "_").replace(" ", "_")
    tag = re.sub(r"_+", "_", tag).strip("_")
    return SYNONYM_TAGS.get(tag, tag)


def _chunk_candidates(chunk: str) -> list[str]:
    """标点分隔后的块：整词命中同义词则保留整词，否则按空白拆。"""
    words = [w for w in _WS_RE.split(chunk.strip()) if w]
    if len(words) > 1:
        whole = " ".join(words)
        if whole in SYNONYM_TAGS:
            return [whole]
    return words


def normalize_tags(raw: Union[str, Sequence[Any], None]) -> list[str]:
    """标签列表归一：拆分分隔符、逐个归一、保序去重、丢弃空标签。"""
    if raw is None:
        return []
    chunks: list[str]
    if isinstance(raw, str):
        chunks = [p for p in _PUNCT_SPLIT_RE.split(raw) if p]
    elif isinstance(raw, Sequence):
        chunks = []
        for part in raw:
            if part is not None:
                chunks.extend(p for p in _PUNCT_SPLIT_RE.split(str(part)) if p)
    else:
        chunks = [str(raw)]

    out: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        for item in _chunk_candidates(chunk):
            canon = normalize_tag(item)
            if canon and canon not in seen:
                seen.add(canon)
                out.append(canon)
    return out


def normalize_severity(raw: Any) -> tuple[str, Optional[str]]:
    """严重度归一；未知取值回退默认值并返回告警说明。"""
    key = normalize_text(raw)
    if key in SEVERITY_MAP:
        return SEVERITY_MAP[key], None
    return DEFAULT_SEVERITY, f"未知严重度 {raw!r}，回退 {DEFAULT_SEVERITY}"


def normalize_status(raw: Any) -> tuple[str, Optional[str]]:
    """状态归一；未知取值回退默认值并返回告警说明。"""
    key = normalize_text(raw)
    if key in STATUS_MAP:
        return STATUS_MAP[key], None
    return DEFAULT_STATUS, f"未知状态 {raw!r}，回退 {DEFAULT_STATUS}"


def generate_id(title: str) -> str:
    """由标题生成确定性短 id（纯哈希，不依赖外部资源）。"""
    digest = hashlib.blake2b(normalize_text(title).encode("utf-8"), digest_size=8)
    return digest.hexdigest()


@dataclass(frozen=True)
class NormalizedEntry:
    """规范化经验条目（供检索/匹配/入库前复用）。"""

    entry_id: str
    title: str
    symptom: str
    root_cause: str
    solution: str
    tags: list[str] = field(default_factory=list)
    severity: str = DEFAULT_SEVERITY
    status: str = DEFAULT_STATUS
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "title": self.title,
            "symptom": self.symptom,
            "root_cause": self.root_cause,
            "solution": self.solution,
            "tags": list(self.tags),
            "severity": self.severity,
            "status": self.status,
            "warnings": list(self.warnings),
        }


def _pick(d: dict[str, Any], field_name: str) -> Any:
    for alias in FIELD_ALIASES[field_name]:
        if alias in d and d[alias] is not None:
            return d[alias]
    return None


def normalize_entry(raw: Union[dict[str, Any], str]) -> NormalizedEntry:
    """把原始 dict / 自由文本归一为 :class:`NormalizedEntry`。

    Args:
        raw: 经验条目。dict 按字段别名取值；str 视为症状/标题自由文本。

    Returns:
        规范化条目；无法识别的取值进入 warnings，不抛异常（除非 dict/str 外）。
    """
    warnings: list[str] = []

    if isinstance(raw, str):
        text = normalize_text(raw)
        if not text:
            raise ValueError("raw text entry must not be empty")
        first_line = text.split(". ", 1)[0][:120]
        entry_id = generate_id(text)
        return NormalizedEntry(
            entry_id=entry_id,
            title=first_line,
            symptom=text,
            root_cause="",
            solution="",
            tags=[],
            severity=DEFAULT_SEVERITY,
            status=DEFAULT_STATUS,
            warnings=["自由文本条目缺少结构化字段（标题/根因/方案/标签）。"],
        )

    if not isinstance(raw, dict):
        raise TypeError(f"entry must be dict or str, got {type(raw).__name__}")

    entry_id = _pick(raw, "entry_id")
    title = normalize_text(_pick(raw, "title"))
    symptom = normalize_text(_pick(raw, "symptom"))
    root_cause = normalize_text(_pick(raw, "root_cause"))
    solution = normalize_text(_pick(raw, "solution"))
    tags = normalize_tags(_pick(raw, "tags"))

    severity, sev_warn = normalize_severity(_pick(raw, "severity"))
    if sev_warn:
        warnings.append(sev_warn)
    status, st_warn = normalize_status(_pick(raw, "status"))
    if st_warn:
        warnings.append(st_warn)

    if not title and not symptom:
        warnings.append("条目同时缺少标题与症状，归一后信息不足。")

    if entry_id is None or str(entry_id).strip() == "":
        entry_id = generate_id(title or symptom)
    else:
        entry_id = str(entry_id).strip()

    return NormalizedEntry(
        entry_id=entry_id,
        title=title,
        symptom=symptom,
        root_cause=root_cause,
        solution=solution,
        tags=tags,
        severity=severity,
        status=status,
        warnings=warnings,
    )
