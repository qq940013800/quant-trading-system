# MCP Setup

QuantDinger's MCP server wraps the Agent Gateway and keeps the REST API as the source of truth.

## Install

```bash
pip install "quantdinger-mcp==0.5.0"
```

For repository development, use `pip install -e ./mcp_server` instead.

Set these environment variables in the MCP client process:

```text
QUANTDINGER_BASE_URL=http://localhost:8888
QUANTDINGER_AGENT_TOKEN=qd_agent_xxx
```

Run `quantdinger-mcp` for the default `stdio` transport. For network use, set `QUANTDINGER_MCP_TRANSPORT=sse` or `streamable-http`, plus optional `QUANTDINGER_MCP_HOST` and `QUANTDINGER_MCP_PORT`.

Non-loopback network listeners are denied by default unless `QUANTDINGER_MCP_AUTH_TOKEN` is set to a distinct secret of at least 32 characters. Configure `QUANTDINGER_MCP_PUBLIC_URL` to the externally reachable HTTPS base URL and send the inbound token as a Bearer token from the MCP client. The inbound token protects the MCP listener; `QUANTDINGER_AGENT_TOKEN` remains the separate upstream tenant credential.

## Client configuration

A typical stdio client entry is:

```json
{
  "mcpServers": {
    "quantdinger": {
      "command": "quantdinger-mcp",
      "env": {
        "QUANTDINGER_BASE_URL": "http://localhost:8888",
        "QUANTDINGER_AGENT_TOKEN": "qd_agent_xxx"
      }
    }
  }
}
```

Keep the configuration private. Prefer an environment-secret facility when the client supports one.

## Minimal mounting and approval boundary

- **Mount only the tools a task truly needs.** Every attached MCP server and tool both consumes context (tool schema/description injected each turn) and widens the attack surface; do not enable read-only research tools alongside trading/write tools in the same session unless the task requires both.
- **Dangerous operations go through ask/approval first.** Restoring source versions, cancelling jobs, deleting alerts, delivering notifications, stopping runtime state, emergency-stopping trading, or placing any order require explicit human confirmation before execution; the agent does not self-approve mutating or irreversible actions.
- Prefer read-only tools for discovery and inspection; expose write/execution tools behind separate review and an allowlist (see `AGENT_ENVIRONMENT_DESIGN.md` Layer 3).
- **审批判定落点（core 纯函数，已固化）**：`core/control/approval_gate.py::evaluate_approval` 按风险等级（read / write_draft / write_config / runtime_control / trading）判定是否放行；未确认、权限不足、实盘条件不满足均 fail-closed 拒绝，结果与输入写入 audit。权限 scope、实盘开关、是否模拟单由适配器取数注入，纯函数不读库不触网。
- **接线状态（未验证 / 第二步）**：纯函数尚未接到执行路由。现状勘察：`kill-switch` 已校验 `confirm is True`；但下单路由 `agent_v1/quick_trade.py::place_order` 未强制校验注册表声明的 `confirm_order` 显式确认标志（元数据 safety 承诺与执行强制不一致）。后续适配器接线：各写/交易/控制路由在执行前调用 `evaluate_approval`，把 body 的 `confirm_*` 标志、token scope、paper/live 条件注入，拒绝按现有 400/501 错误映射返回；审批回调与留痕落库留第二步。

## Expected workflow

- Use market tools for discovery and OHLCV reads.
- Use universe, factor, and watchlist tools for research workspace inputs.
- Use indicator tools only for chart artifacts.
- Compile Strategy API V2 code before saving it.
- Save private Strategy API V2 sources and inspect version history.
- Create stopped deployments from saved V2 source IDs.
- Use bounded job polling or SSE streaming for backtest results.
- Use broker and execution observation tools only for reads; credential secrets are never exposed.
- Use N-scope signal-alert tools for notification automation.
- Supply a unique `idempotency_key` to every mutating W/B/N/T tool.
- Require explicit confirmation before restoring source versions, cancelling jobs, deleting alerts, delivering notifications, stopping runtime state, emergency-stopping trading, or placing any order.

The strategy manifest owns market, instrument, frequency, warmup, dependency, and leverage scope. Do not pass those as alternate backtest fields.

For the exact tool signatures, see [the MCP package README](../../mcp_server/README.md) and [Agent OpenAPI](agent-openapi.json).
