# -*- coding: utf-8 -*-
"""
tests/test_agent_config.py —— Agent 配置的静态校验
目的：把"最小权限""字段合法""无 MCP 幻觉字段"从口头约定变成 CI 门禁。
运行：python tests/test_agent_config.py  或  pytest -q tests/test_agent_config.py
"""
from __future__ import annotations
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT / ".github" / "agents"
INSTR_DIR = ROOT / ".github" / "instructions"

# 已知工具别名（按 VS Code .agent.md 规范维护；未知工具会静默失效）。MCP 工具写为 <server>/*。
KNOWN_TOOLS = {"read", "search", "edit", "execute", "web", "todo", "agent"}
WRITE_TOOLS = {"edit"}
EXEC_TOOLS = {"execute"}
DELEGATE_TOOLS = {"agent"}

# frontmatter 允许的键；拼写错误（如 user-invokable）会静默失效
KNOWN_KEYS = {
    "name", "description", "tools", "model", "argument-hint", "agents",
    "user-invocable", "disable-model-invocation", "handoffs", "hooks",
}

# 只读 Agent 名单：必须不含写/执行/委派权限
READONLY_AGENTS = {"causal-guard", "mql5-reviewer", "research-factory"}
# 必须禁止模型自动调用的 Agent（涉及预算/资金/风控）
MANUAL_ONLY_AGENTS = {"research-factory"}

MAX_BODY_CHARS = 30000  # 与平台提示长度上限对齐


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """极简 frontmatter 解析（避免引入 pyyaml 依赖）。"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        raise ValueError("缺少 frontmatter")
    meta_raw, body = m.group(1), m.group(2)
    meta: dict = {}
    for line in meta_raw.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v.startswith("[") and v.endswith("]"):
            meta[k] = [t.strip().strip("'\"") for t in v[1:-1].split(",") if t.strip()]
        elif v.lower() in ("true", "false"):
            meta[k] = (v.lower() == "true")
        else:
            meta[k] = v.strip("'\"")
    return meta, body


def test_agents_exist():
    assert AGENTS_DIR.is_dir(), f"缺少目录 {AGENTS_DIR}"
    files = list(AGENTS_DIR.glob("*.agent.md"))
    assert len(files) >= 4, f"Agent 数量异常：{len(files)}"


def test_agent_fields_and_permissions():
    problems = []
    for f in sorted(AGENTS_DIR.glob("*.agent.md")):
        meta, body = parse_frontmatter(f.read_text(encoding="utf-8"))
        stem = f.name[: -len(".agent.md")]

        # 1) name 与文件名一致（省略时默认取文件名，显式写更稳）
        if meta.get("name", stem) != stem:
            problems.append(f"{f.name}: name 与文件名不一致")

        # 1b) frontmatter 键必须合法（防拼写静默失效）
        bad_keys = set(meta) - KNOWN_KEYS
        if bad_keys:
            problems.append(f"{f.name}: 未知 frontmatter 键 {sorted(bad_keys)}")

        # 2) description 必填且含触发线索
        desc = meta.get("description", "")
        if len(desc) < 20:
            problems.append(f"{f.name}: description 过短，自动委派命中率会低")

        # 3) tools 必须是已知集合的子集（防拼写静默失效）；MCP 写为 <server>/*
        tools = meta.get("tools", [])
        if isinstance(tools, str):
            tools = [tools]
        unknown = {t for t in tools if t not in KNOWN_TOOLS and not t.endswith("/*")}
        if unknown:
            problems.append(f"{f.name}: 未知工具 {sorted(unknown)}")

        # 4) 只读 Agent 不得持有写/执行/委派权限
        if stem in READONLY_AGENTS:
            if set(tools) & (WRITE_TOOLS | EXEC_TOOLS | DELEGATE_TOOLS):
                problems.append(f"{f.name}: 只读 Agent 持有写/执行/委派权限 {sorted(tools)}")
            if meta.get("agents") != []:
                problems.append(f"{f.name}: 只读 Agent 必须设置 agents: []")

        # 5) 敏感 Agent 必须禁止模型自动调用
        if stem in MANUAL_ONLY_AGENTS and meta.get("disable-model-invocation") is not True:
            problems.append(f"{f.name}: 必须设置 disable-model-invocation: true")

        # 6) 不得在 agent 文件里配 MCP（多数 IDE 不消费该字段，易造成"以为生效"）
        if "mcp-servers" in meta or "mcpServers" in meta:
            problems.append(f"{f.name}: 不要在 agent 文件配置 MCP，请用 .vscode/mcp.json")

        # 7) 正文长度与非空
        if len(body) > MAX_BODY_CHARS:
            problems.append(f"{f.name}: 正文超过 {MAX_BODY_CHARS} 字符")
        if "停止条件" not in body:
            problems.append(f"{f.name}: 缺少『停止条件』段落")

    assert not problems, "Agent 配置校验失败：\n  - " + "\n  - ".join(problems)


def test_instructions_have_applyto():
    if not INSTR_DIR.is_dir():
        return
    for f in sorted(INSTR_DIR.glob("*.instructions.md")):
        meta, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        assert meta.get("applyTo"), f"{f.name}: 缺少 applyTo，指令不会按模式生效"


def test_agents_md_hard_rules_present():
    p = ROOT / "AGENTS.md"
    assert p.is_file(), "缺少 AGENTS.md"
    text = p.read_text(encoding="utf-8")
    for kw in ["前视守卫", "集合分离", "止损单调", "停止条件", "禁止删除"]:
        assert kw in text, f"AGENTS.md 缺少关键条款：{kw}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn(); print(f"PASS {fn.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {fn.__name__}: {e}")
    sys.exit(1 if failed else 0)
