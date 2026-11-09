# -*- coding: utf-8 -*-
"""core.audit.data_manifest —— 数据集 manifest 与内容指纹纯底座。

蓝图 G6：模型/策略版本卡需记录训练/回测数据窗口、行数、列清单与数据指纹，
便于事后还原"这个模型是用哪份数据训出来的"（不变量 2：决策可审计）。

边界与不变量：
- 纯函数：不读文件、不触库、不联网；数据规模与内容哈希由调用方取数注入。
- fingerprint 由元数据 + 可选 content_digest 派生；元数据相同且无内容哈希时指纹稳定。
- 阈值/列清单不做绩效寻优；本模块只做记录与指纹，不判断数据好坏。
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Optional, Sequence


class ManifestError(Exception):
    """manifest 构造/校验异常，携带上下文（硬规则 9）。"""

    def __init__(self, detail: str, layer: str = "audit.data_manifest"):
        self.context = {"layer": layer, "detail": detail}
        super().__init__(f"ManifestError: {self.context}")


def _nonempty_str(name: str, val: object) -> str:
    if not isinstance(val, str) or not val.strip():
        raise ManifestError(f"{name} 必须为非空字符串，收到 {val!r}")
    return val.strip()


def _opt_str(name: str, val: Optional[object]) -> Optional[str]:
    if val is None:
        return None
    if not isinstance(val, str):
        raise ManifestError(f"{name} 必须为字符串或 None，收到 {val!r}")
    return val


def _nonneg_int(name: str, val: object) -> int:
    if isinstance(val, bool) or not isinstance(val, int):
        raise ManifestError(f"{name} 必须为整数，收到 {val!r}")
    if val < 0:
        raise ManifestError(f"{name} 必须 >= 0，收到 {val}")
    return val


def _columns(val: object) -> tuple[str, ...]:
    if not isinstance(val, Sequence) or isinstance(val, (str, bytes)):
        raise ManifestError(f"columns 必须为字符串序列，收到 {val!r}")
    seen: list[str] = []
    for col in val:
        if not isinstance(col, str) or not col.strip():
            raise ManifestError(f"columns 元素必须为非空字符串，收到 {col!r}")
        c = col.strip()
        if c not in seen:
            seen.append(c)
    if not seen:
        raise ManifestError("columns 不能为空")
    return tuple(seen)


def _fingerprint(
    dataset_name: str,
    symbol: str,
    timeframe: str,
    n_bars: int,
    columns: tuple[str, ...],
    first_bar_time: Optional[str],
    last_bar_time: Optional[str],
    source: Optional[str],
    content_digest: Optional[str],
) -> str:
    payload = "|".join([
        dataset_name, symbol, timeframe, str(n_bars),
        ",".join(columns),
        first_bar_time or "", last_bar_time or "",
        source or "", content_digest or "",
    ])
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()


@dataclass(frozen=True)
class DatasetManifest:
    """数据集元数据快照（纯结果，含可序列化指纹）。"""

    dataset_name: str
    symbol: str
    timeframe: str
    n_bars: int
    columns: tuple[str, ...]
    first_bar_time: Optional[str]
    last_bar_time: Optional[str]
    source: Optional[str]
    content_digest: Optional[str]
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "n_bars": self.n_bars,
            "columns": list(self.columns),
            "first_bar_time": self.first_bar_time,
            "last_bar_time": self.last_bar_time,
            "source": self.source,
            "content_digest": self.content_digest,
            "fingerprint": self.fingerprint,
        }


def build_manifest(
    *,
    dataset_name: str,
    symbol: str,
    timeframe: str,
    n_bars: int,
    columns: Sequence[str],
    first_bar_time: Optional[str] = None,
    last_bar_time: Optional[str] = None,
    source: Optional[str] = None,
    content_digest: Optional[str] = None,
) -> DatasetManifest:
    """构造数据集 manifest 并派生内容指纹。

    Args:
        dataset_name: 数据集名称（非空）。
        symbol: 标的代码（非空）。
        timeframe: 周期（非空）。
        n_bars: bar 根数（非负整数）。
        columns: 列清单（非空字符串序列；去重保序）。
        first_bar_time: 首根 bar 时间戳（可选，字符串）。
        last_bar_time: 末根 bar 时间戳（可选，字符串）。
        source: 数据来源/文件名（可选）。
        content_digest: 调用方注入的内容/文件哈希（可选；如 sha256 摘要）。

    Returns:
        ``DatasetManifest``；``fingerprint`` 由上述元数据与可选内容哈希派生。
    """
    name = _nonempty_str("dataset_name", dataset_name)
    sym = _nonempty_str("symbol", symbol)
    tf = _nonempty_str("timeframe", timeframe)
    bars = _nonneg_int("n_bars", n_bars)
    cols = _columns(columns)
    first = _opt_str("first_bar_time", first_bar_time)
    last = _opt_str("last_bar_time", last_bar_time)
    src = _opt_str("source", source)
    digest = _opt_str("content_digest", content_digest)

    fp = _fingerprint(name, sym, tf, bars, cols, first, last, src, digest)
    return DatasetManifest(
        dataset_name=name,
        symbol=sym,
        timeframe=tf,
        n_bars=bars,
        columns=cols,
        first_bar_time=first,
        last_bar_time=last,
        source=src,
        content_digest=digest,
        fingerprint=fp,
    )
