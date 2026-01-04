"""
legacy/interpreter.py

早期版本的解释器（v0.1），接口与语义均已被 agents/interpreter.py::IntentInterpreter 取代。
保留此实现仅供测试或历史对比，Router 与正式逻辑禁止引用。
"""

from typing import Any, Dict, List
import yaml


class InterpretationError(Exception):
    """与旧版保持兼容的异常类型。"""


class LegacyInterpreter:
    """
    v0.1 的 Interpreter：直接返回批准/压制结果，不支持约束/可供性升级。

    ⚠️ legacy 组件，仅用于测试验证，其他模块请统一使用 IntentInterpreter。
    """
    def __init__(self, constraint_path: str = "intent_constraint.yaml"):
        with open(constraint_path, "r", encoding="utf-8") as f:
            self.policy = yaml.safe_load(f)

        self.kinds = self.policy.get("kinds", {})

    # ---------- 公共入口 ----------
    def interpret(self, intention: Dict[str, Any], agent, world) -> Dict[str, Any]:
        kind = intention.get("kind")

        if kind not in self.kinds:
            return self._suppress("forbid", f"Unknown intention kind: {kind}")

        ruleset = self.kinds[kind]
        violations: List[Dict[str, str]] = []

        # require 先检查
        for violation in self._check_require(ruleset.get("require"), intention, agent, world):
            violations.append(violation)

        # forbid 再检查
        for violation in self._check_forbid(ruleset.get("forbid"), intention, agent, world):
            violations.append(violation)

        if violations:
            return {"status": "suppressed", "violations": violations}

        return {"status": "approved", "violations": []}

    # ---------- require ----------
    def _check_require(self, require, intention, agent, world):
        if not require:
            return []

        violations = []

        # require.fields
        fields = require.get("fields", [])
        for field in fields:
            if not self._has_field(intention, field):
                violations.append({
                    "kind": "require",
                    "rule": f"missing field {field}",
                    "detail": field,
                })

        # require.references
        ref_req = require.get("references")
        if ref_req:
            refs = intention.get("references", [])
            if not refs:
                violations.append({"kind": "require", "rule": "missing references", "detail": "references"})
            else:
                types = ref_req.get("event_types", [])
                if types:
                    if not self._references_match_types(refs, types, world):
                        violations.append({
                            "kind": "require",
                            "rule": "reference type mismatch",
                            "detail": str(types),
                        })

        return violations

    # ---------- forbid ----------
    def _check_forbid(self, forbid, intention, agent, world):
        if not forbid:
            return []

        violations = []

        for expr in forbid:
            if self._eval_expr(expr, intention, agent, world):
                violations.append({"kind": "forbid", "rule": expr, "detail": "expression matched"})

        return violations

    # ---------- 工具函数 ----------
    def _has_field(self, intention, dotted_path: str) -> bool:
        parts = dotted_path.split(".")
        cur = intention
        for p in parts:
            if not isinstance(cur, dict) or p not in cur:
                return False
            cur = cur[p]
        return True

    def _references_match_types(self, refs, allowed_types, world) -> bool:
        for ref in refs:
            event = world.get_event(ref)
            if event and event.get("type") in allowed_types:
                return True
        return False

    def _eval_expr(self, expr: str, intention, agent, world) -> bool:
        """
        极简表达式执行器（v0）。
        expr 示例：
          intention.completed == true
          intention.scope != public
        """
        # 可控执行环境
        env = {
            "intention": intention,
            "agent": agent,
            "world": world,
            "true": True,
            "false": False,
            "public": "public",
        }

        try:
            return bool(eval(expr, {}, env))
        except Exception:
            # 表达式错误，一律当作不命中
            return False

    def _suppress(self, kind, reason):
        return {"status": "suppressed", "violations": [{"kind": kind, "rule": reason, "detail": ""}]}