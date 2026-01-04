# agents/interpreter.py
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional

# import yaml
try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - 环境无 PyYAML 时退化为空策略
    yaml = None

try:
    # 如果你有 events/types.py 的 Decision，就用它
    from events.types import Decision
except Exception:
    Decision = None  # type: ignore


def _to_dict(obj: Any) -> Dict[str, Any]:
    """把 dataclass / dict 都统一成 dict，方便规则检查。"""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if is_dataclass(obj):
        return asdict(obj)
    # 普通对象：尽量用 __dict__
    return getattr(obj, "__dict__", {}) or {}


class IntentInterpreter:
    """
    v0：只做裁决（approved / suppressed），不 rewrite、不 downgrade。
    规则来自 intent_constraint.yaml（kinds: ...）。
    """

    def __init__(self, constraint_path: str):
        if yaml is None:
            # 没有 PyYAML 时，退化为空策略（全部 approved）
            self.policy = {}
        else:
            with open(constraint_path, "r", encoding="utf-8") as f:
                self.policy = yaml.safe_load(f) or {}

        # with open(constraint_path, "r", encoding="utf-8") as f:
        #     self.policy = yaml.safe_load(f) or {}

        self.kinds = self.policy.get("kinds", {}) or {}

    # ===== 这就是 Router 要的适配层方法 =====
    def interpret_intention(self, intention, agent, world, store) -> Any:
        """
        返回 Decision（若可用）或 dict:
          {"status": "...", "violations": [...]}
        """
        it = _to_dict(intention)
        ag = _to_dict(agent)

        kind = it.get("kind")
        if not kind:
            return self._decision(
                "suppressed",
                [{"kind": "require", "rule": "missing kind", "detail": "intention.kind"}],
            )

        ruleset = self.kinds.get(kind)
        if not ruleset:
            # 没有任何规则时，默认放行，保证 demo 可运行
            if not self.kinds:
                return self._decision("approved", [])
            return self._decision(
                "suppressed",
                [{"kind": "forbid", "rule": f"unknown kind {kind}", "detail": kind}],
            )

        violations: List[Dict[str, str]] = []

        # 1) require
        violations.extend(self._check_require(ruleset.get("require"), it, ag, world, store))

        # 2) forbid
        violations.extend(self._check_forbid(ruleset.get("forbid"), it, ag, world, store))

        if violations:
            return self._decision("suppressed", violations)

        return self._decision("approved", [])

    # ---------------- require ----------------
    def _check_require(self, require_block: Optional[Dict[str, Any]], it, ag, world, store):
        if not require_block:
            return []

        violations: List[Dict[str, str]] = []

        # require.fields: ["payload.text", ...]
        fields = require_block.get("fields", []) or []
        for path in fields:
            if not self._has_path(it, path):
                violations.append({"kind": "require", "rule": f"missing field {path}", "detail": path})

        # require.references: { min?, event_types? }
        ref_req = require_block.get("references")
        if ref_req:
            refs = it.get("references") or []
            if not refs:
                violations.append({"kind": "require", "rule": "missing references", "detail": "references"})
            else:
                min_n = ref_req.get("min")
                if isinstance(min_n, int) and len(refs) < min_n:
                    violations.append({"kind": "require", "rule": f"references < {min_n}", "detail": str(len(refs))})

                allowed_types = ref_req.get("event_types") or []
                if allowed_types:
                    if not self._any_ref_type_in(refs, allowed_types, store):
                        violations.append(
                            {"kind": "require", "rule": "reference type mismatch", "detail": str(allowed_types)}
                        )

        return violations

    # ---------------- forbid ----------------
    def _check_forbid(self, forbid_list: Optional[List[Any]], it, ag, world, store):
        if not forbid_list:
            return []

        violations: List[Dict[str, str]] = []

        # v0：forbid 条件用非常小的表达式执行（先跑通闭环）
        for expr in forbid_list:
            if not isinstance(expr, str):
                # 不认识的 forbid 结构，先当作不命中（以后升级 DSL 再严格）
                continue

            hit = self._eval_expr(expr, it, ag, world, store)
            if hit:
                violations.append({"kind": "forbid", "rule": expr, "detail": "matched"})
        return violations

    # ---------------- helpers ----------------
    def _decision(self, status: str, violations: List[Dict[str, str]]):
        payload = {"status": status, "violations": violations}
        if Decision is not None:
            return Decision(status=status, violations=violations)
        return payload

    def _has_path(self, root: Dict[str, Any], dotted: str) -> bool:
        cur: Any = root
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return False
            cur = cur[part]
        return True

    def _any_ref_type_in(self, refs: List[str], allowed_types: List[str], store) -> bool:
        for rid in refs:
            ev = store.get(rid) if store else None
            if not ev:
                continue
            # ev 可能是 dataclass，也可能是 dict
            evd = _to_dict(ev)
            if evd.get("type") in allowed_types:
                return True
        return False

    def _eval_expr(self, expr: str, it, ag, world, store) -> bool:
        """
        v0 表达式执行：先支持你 YAML 里那种简单写法。
        允许用：
          intention.xxx
          agent.xxx
          referenced_event.scope   （取第一个 reference 对应的 event）
          true/false/public
          == != < > and or not abs()

        先跑通闭环。后面再换成 DSL（把 eval 干掉）。
        """
        referenced_event = None
        refs = it.get("references") or []
        if refs and store:
            referenced_event = store.get(refs[0])
        rev = _to_dict(referenced_event)

        # 小心：这里用 eval 是“工程推进版”，不是终局。
        env = {
            "intention": it,
            "agent": ag,
            "referenced_event": rev,
            "world": world,
            "store": store,
            "true": True,
            "false": False,
            "public": "public",
            "abs": abs,
        }

        try:
            # 让 intention.completed 这种访问可用：用 dict 会变成 intention["completed"] 不方便
            # 所以我们要求 expr 写成 intention.get("completed") ? 不现实。
            # 简单处理：把 intention.xxx 重写成 intention["xxx"]
            rewritten = self._rewrite_dot_access(expr)
            return bool(eval(rewritten, {"__builtins__": {}}, env))
        except Exception:
            return False

    def _rewrite_dot_access(self, expr: str) -> str:
        """
        把 intention.completed 变成 intention["completed"]
        把 agent.scope 变成 agent["scope"]
        把 referenced_event.scope 变成 referenced_event["scope"]

        v0：非常粗暴但够用（只处理一层点号）。
        """
        for prefix in ("intention.", "agent.", "referenced_event."):
            # 逐个替换：prefix + name（name 只认字母数字下划线）
            out = []
            i = 0
            while i < len(expr):
                j = expr.find(prefix, i)
                if j == -1:
                    out.append(expr[i:])
                    break
                out.append(expr[i:j])
                k = j + len(prefix)
                name = []
                while k < len(expr) and (expr[k].isalnum() or expr[k] == "_"):
                    name.append(expr[k])
                    k += 1
                if name:
                    base = prefix[:-1]  # "intention"
                    out.append(f'{base}["{"".join(name)}"]')
                    i = k
                else:
                    # 没抓到字段名，原样放回
                    out.append(prefix)
                    i = k
            expr = "".join(out)
        return expr
