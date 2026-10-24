# -*- coding: utf-8 -*-
"""scripts/score_agent_eval.py —— 为 Agent A/B 评测打分（不调用任何 Agent）。

用法：
    python scripts/score_agent_eval.py --key tests/fixtures/causal_guard/answer_key.json \
        --results A=reports/ab_A.json B=reports/ab_B.json

结果文件格式：{"<case_id>": {"<check_no>": "PASS|FAIL|UNKNOWN"}}
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

VALID_VERDICTS = {"PASS", "FAIL", "UNKNOWN"}


def load_json(path: Path) -> dict[str, dict[str, str]]:
    """读取并校验 {case: {check: verdict}} 结构。

    输入约束：文件存在且为 UTF-8 JSON；verdict 取值于 VALID_VERDICTS。
    不变量：返回值只包含合法 verdict，不做任何修正或补全。
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 {path}: {exc}") from exc
    for case, checks in data.items():
        for check, verdict in checks.items():
            if verdict not in VALID_VERDICTS:
                raise ValueError(f"{path}: {case}/{check} 的 verdict 非法：{verdict!r}")
    return data


def score(key: dict[str, dict[str, str]], results: dict[str, dict[str, str]]) -> dict[str, float | int]:
    """按答案键统计检出率、误报率、UNKNOWN 率与缺失数。

    输入约束：key 的取值仅为 PASS/FAIL；未在 key 中的 (case, check) 不计分。
    不变量：缺失项计入 missing，且不当作 PASS；UNKNOWN 不算检出也不算误报。
    """
    tp = fn = fp = tn = unknown = missing = 0
    for case, checks in key.items():
        for check, expected in checks.items():
            got = results.get(case, {}).get(check)
            if got is None:
                missing += 1
            elif got == "UNKNOWN":
                unknown += 1
            elif expected == "FAIL":
                tp, fn = (tp + 1, fn) if got == "FAIL" else (tp, fn + 1)
            else:
                fp, tn = (fp + 1, tn) if got == "FAIL" else (fp, tn + 1)
    positives = sum(1 for c in key.values() for e in c.values() if e == "FAIL")
    negatives = sum(1 for c in key.values() for e in c.values() if e == "PASS")
    total = positives + negatives
    return {
        "tp": tp, "fn": fn, "fp": fp, "tn": tn, "unknown": unknown, "missing": missing,
        "detection_rate": tp / positives if positives else float("nan"),
        "false_positive_rate": fp / negatives if negatives else float("nan"),
        "unknown_rate": unknown / total if total else float("nan"),
    }


def main() -> int:
    """命令行入口；返回进程退出码。"""
    parser = argparse.ArgumentParser(description="Agent A/B 评测打分")
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--results", nargs="+", required=True, help="NAME=path 形式，可多个")
    args = parser.parse_args()
    key = load_json(args.key)
    for item in args.results:
        name, _, raw_path = item.partition("=")
        if not raw_path:
            print(f"参数格式错误（应为 NAME=path）：{item}", file=sys.stderr)
            return 2
        print(name, json.dumps(score(key, load_json(Path(raw_path))), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
