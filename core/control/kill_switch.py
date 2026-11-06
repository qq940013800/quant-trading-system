# -*- coding: utf-8 -*-
"""core.control.kill_switch —— 独立的紧急停止开关（fail-closed）。

为什么需要它（而不是在策略里加一个 if）：
    - 策略进程崩溃、卡死、被重启时，策略内的标志位会一起消失；
    - 人工、对账、回撤、数据过期等多个来源都要能触发同一个开关；
    - 触发/复位本身必须是可审计事件（谁、何时、为什么）。

设计契约：
1. **状态落盘**：JSON 文件 + 原子替换（os.replace），进程崩溃不丢状态；
2. **跨进程可见**：每次读取都读文件，不做内存缓存；
3. **失败关闭**：状态文件损坏、或状态文件缺失但审计日志存在（疑似被删除绕过）时，
   一律视为已触发（armed=True）；
4. **幂等**：重复 trigger 不覆盖首次触发原因；重复 reset 不报错；
5. **复位需授权**：reset 必须提供非空 operator 与 reason，并写审计；
6. **不依赖策略层**：本模块不 import core.strategies / core.risk / core.execution。

用法：
    ks = KillSwitch("runtime/kill_switch.json")
    if ks.is_armed():
        ...  # 禁止新开仓，只允许减仓
    ks.trigger(reason="drawdown 12% > 10%", source="risk.circuit")
    ks.reset(operator="ops-01", reason="incident reviewed")
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


class KillSwitchError(RuntimeError):
    """KillSwitch 的操作非法（参数错误/IO 失败），携带上下文。"""

    def __init__(self, detail: str, **context: Any):
        self.context = {"layer": "control.kill_switch", "detail": detail, **context}
        super().__init__(f"KillSwitchError: {self.context}")


class KillSwitchArmed(KillSwitchError):
    """守卫模式下开关已触发：调用方必须停止新开仓。"""

    def __init__(self, state: "KillSwitchState"):
        self.state = state
        super().__init__(
            "kill switch armed; new positions are forbidden",
            reason=state.reason,
            source=state.source,
            triggered_at=state.triggered_at,
        )


@dataclass(frozen=True)
class KillSwitchState:
    """开关状态的持久化快照（不可变）。"""

    armed: bool
    reason: str
    source: str
    triggered_at: str | None
    reset_at: str | None
    version: int
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KillSwitch:
    """文件持久化的紧急停止开关（详见模块 docstring）。"""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        state_path: str | os.PathLike[str],
        audit_path: str | os.PathLike[str] | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = Path(state_path)
        self._audit_path = (
            Path(audit_path) if audit_path is not None
            else self._path.with_suffix(".audit.jsonl")
        )
        self._lock = threading.Lock()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._ensure_initialized()

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------
    def is_armed(self) -> bool:
        """只读检查；任何读取失败都返回 True（fail-closed）。"""
        state = self._read_state()
        if state is None:
            return True
        return state.armed

    def state(self) -> KillSwitchState:
        """返回当前状态；文件损坏/缺失时返回合成的 armed 状态（不抛异常）。"""
        state = self._read_state()
        if state is not None:
            return state
        now = self._now_iso()
        return KillSwitchState(
            armed=True, reason="state unreadable or missing (fail-closed)",
            source="kill_switch", triggered_at=now, reset_at=None,
            version=self.SCHEMA_VERSION, updated_at=now,
        )

    def trigger(
        self,
        reason: str,
        source: str,
        *,
        ts_utc: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> KillSwitchState:
        """触发开关（幂等：已触发时保留首次原因，仅记录审计）。"""
        _require_nonempty(reason, "reason")
        _require_nonempty(source, "source")
        with self._lock:
            current = self._read_state()
            if current is not None and current.armed:
                self._append_audit("trigger_ignored", current, metadata=metadata)
                return current
            now = ts_utc or self._now_iso()
            new_state = KillSwitchState(
                armed=True, reason=reason, source=source,
                triggered_at=now, reset_at=None,
                version=self.SCHEMA_VERSION, updated_at=now,
            )
            self._write_state(new_state)
            self._append_audit("trigger", new_state, metadata=metadata)
            return new_state

    def reset(
        self, operator: str, reason: str, *,
        ts_utc: str | None = None,
    ) -> KillSwitchState:
        """人工复位：必须给出操作者与原因（写审计），否则拒绝。"""
        _require_nonempty(operator, "operator")
        _require_nonempty(reason, "reason")
        with self._lock:
            current = self._read_state()
            now = ts_utc or self._now_iso()
            if current is not None and not current.armed:
                self._append_audit("reset_noop", current, operator=operator,
                                   metadata={"reason": reason})
                return current
            new_state = KillSwitchState(
                armed=False, reason=reason, source=operator,
                triggered_at=None, reset_at=now,
                version=self.SCHEMA_VERSION, updated_at=now,
            )
            self._write_state(new_state)
            self._append_audit("reset", new_state, operator=operator)
            return new_state

    def guard(self) -> None:
        """守卫：已触发则抛 KillSwitchArmed；否则无副作用。"""
        if self.is_armed():
            raise KillSwitchArmed(self.state())

    # ------------------------------------------------------------------
    # 内部：状态读写
    # ------------------------------------------------------------------
    def _ensure_initialized(self) -> None:
        """首次构造：缺状态文件时创建；但有审计日志说明状态被删除 → 失败关闭。"""
        if self._path.exists():
            state = self._read_state()
            if state is None:
                # 文件存在但损坏：重写为 armed（fail-closed）
                now = self._now_iso()
                broken = KillSwitchState(
                    armed=True, reason="state file corrupted (fail-closed)",
                    source="kill_switch", triggered_at=now, reset_at=None,
                    version=self.SCHEMA_VERSION, updated_at=now,
                )
                self._write_state(broken)
                self._append_audit("fail_closed_corrupt", broken)
            return

        now = self._now_iso()
        audit_exists = self._audit_path.exists() and self._audit_path.stat().st_size > 0
        if audit_exists:
            state = KillSwitchState(
                armed=True,
                reason="state file missing while audit log exists (possible tampering)",
                source="kill_switch", triggered_at=now, reset_at=None,
                version=self.SCHEMA_VERSION, updated_at=now,
            )
            self._write_state(state)
            self._append_audit("fail_closed_missing_state", state)
            return

        state = KillSwitchState(
            armed=False, reason="initialized", source="kill_switch",
            triggered_at=None, reset_at=None,
            version=self.SCHEMA_VERSION, updated_at=now,
        )
        self._write_state(state)
        self._append_audit("init", state)

    def _read_state(self) -> KillSwitchState | None:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError:
            return None
        try:
            data = json.loads(raw)
            return KillSwitchState(
                armed=bool(data["armed"]),
                reason=str(data["reason"]),
                source=str(data["source"]),
                triggered_at=data.get("triggered_at"),
                reset_at=data.get("reset_at"),
                version=int(data.get("version", self.SCHEMA_VERSION)),
                updated_at=str(data["updated_at"]),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None

    def _write_state(self, state: KillSwitchState) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state.to_dict(), ensure_ascii=False, separators=(",", ":"))
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self._path.parent), prefix=".kill_switch-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self._path)  # Windows/POSIX 均为原子替换
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        # 目录项落盘（POSIX 语义；Windows 上是 no-op）
        try:
            dir_fd = os.open(str(self._path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass

    def _append_audit(
        self, action: str, state: KillSwitchState,
        *, operator: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "ts": self._now_iso(),
            "action": action,
            "armed": state.armed,
            "reason": state.reason,
            "source": state.source,
            "triggered_at": state.triggered_at,
            "version": state.version,
        }
        if operator:
            entry["operator"] = operator
        if metadata:
            entry["metadata"] = dict(metadata)
        line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self._audit_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def _now_iso(self) -> str:
        dt = self._clock()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()


def _require_nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise KillSwitchError(f"{name} must be a non-empty string", field=name)
