# agents/interpreter.py
from __future__ import annotations

import ast
import re
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional, Tuple, cast

from events.references import ref_event_id

_ALLOWED_CALLS = {"abs", "len", "is_empty", "get"}


def is_empty(x: Any) -> bool:
    if x is None:
        return True
    if isinstance(x, (str, list, dict, tuple, set)):
        return len(x) == 0
    return False


def get_value(d: Any, key: Any, default: Any = None) -> Any:
    if isinstance(d, dict):
        return d.get(key, default)
    return default


_LOGIC_WORDS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bAND\b"), "and"),
    (re.compile(r"\bOR\b"), "or"),
    (re.compile(r"\bNOT\b"), "not"),
    (re.compile(r"\bTRUE\b"), "true"),
    (re.compile(r"\bFALSE\b"), "false"),
]


class _SafeEval(ast.NodeVisitor):
    def __init__(self, env: Dict[str, Any]):
        self.env = env

    def visit_Expression(self, node: ast.Expression):
        return self.visit(cast(ast.AST, node.body))

    def visit_Name(self, node: ast.Name):
        if node.id in self.env:
            return self.env[node.id]
        raise NameError(node.id)

    def visit_Constant(self, node: ast.Constant):
        return node.value

    def visit_BoolOp(self, node: ast.BoolOp):
        vals = [bool(self.visit(cast(ast.AST, v))) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(vals)
        if isinstance(node.op, ast.Or):
            return any(vals)
        raise ValueError("boolop")

    def visit_UnaryOp(self, node: ast.UnaryOp):
        v = self.visit(cast(ast.AST, node.operand))
        if isinstance(node.op, ast.Not):
            return not bool(v)
        if isinstance(node.op, ast.USub):
            return -v
        raise ValueError("unary")

    def visit_Compare(self, node: ast.Compare):
        left = self.visit(cast(ast.AST, node.left))
        for op, comp in zip(node.ops, node.comparators):
            right = self.visit(cast(ast.AST, comp))
            ok = None
            if isinstance(op, ast.Eq):
                ok = left == right
            elif isinstance(op, ast.NotEq):
                ok = left != right
            elif isinstance(op, ast.Lt):
                ok = left < right
            elif isinstance(op, ast.LtE):
                ok = left <= right
            elif isinstance(op, ast.Gt):
                ok = left > right
            elif isinstance(op, ast.GtE):
                ok = left >= right
            elif isinstance(op, ast.In):
                ok = left in right
            elif isinstance(op, ast.NotIn):
                ok = left not in right
            else:
                raise ValueError("compare-op")
            if not ok:
                return False
            left = right
        return True

    def visit_Subscript(self, node: ast.Subscript):
        base = self.visit(cast(ast.AST, node.value))
        slice_node = cast(ast.AST, node.slice.value if isinstance(node.slice, ast.Index) else node.slice)
        sl = self.visit(slice_node)
        return base[sl]

    def visit_Attribute(self, node: ast.Attribute):
        base = self.visit(cast(ast.AST, node.value))
        if isinstance(base, dict):
            return base.get(node.attr)
        return getattr(base, node.attr)

    def visit_Call(self, node: ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("call-func")
        fn = node.func.id
        if fn not in _ALLOWED_CALLS:
            raise ValueError(f"call-not-allowed:{fn}")
        args = [self.visit(cast(ast.AST, a)) for a in node.args]
        if fn == "abs":
            return abs(*args)
        if fn == "len":
            return len(*args)
        if fn == "is_empty":
            return is_empty(*args)
        if fn == "get":
            return get_value(*args)
        raise ValueError("call")

    def generic_visit(self, node):  # pragma: no cover - 防御性兜底
        raise ValueError(f"node-not-allowed:{type(node).__name__}")


def _safe_bool_expr(expr: str, env: Dict[str, Any]) -> bool:
    for pat, rep in _LOGIC_WORDS:
        expr = pat.sub(rep, expr)
    tree = ast.parse(expr, mode="eval")
    return bool(_SafeEval(env).visit(tree))


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

    def __init__(self, constraint_path: str, *, allow_empty_policy: bool = False, allow_unknown_kind: Optional[bool] = None):
        self.allow_empty_policy = allow_empty_policy
        # with open(constraint_path, "r", encoding="utf-8") as f:
        #     self.policy = yaml.safe_load(f) or {}
        if yaml is None:
            if not allow_empty_policy:
                raise RuntimeError("PyYAML 未安装，无法加载策略；请 pip install pyyaml")
            self.policy = {}
        else:
            with open(constraint_path, "r", encoding="utf-8") as f:
                self.policy = yaml.safe_load(f) or {}

        self.kinds = self.policy.get("kinds", {}) or {}
        if allow_unknown_kind is None:
            self.allow_unknown_kind = not bool(self.kinds)
        else:
            self.allow_unknown_kind = allow_unknown_kind
        if not self.kinds and not allow_empty_policy:
            raise RuntimeError("未配置任何意向规则，请检查策略文件或开启 allow_empty_policy")
        print(
            f"[agents/interpreter.py] 📖 装载策略 {constraint_path} 完成，定义了 {len(self.kinds)} 种意向规则。"
        )

    # ===== 这就是 Router 要的适配层方法 =====
    def interpret_intention(self, intention, agent, world, store) -> Any:
        """
        返回 Decision（若可用）或 dict:
          {"status": "...", "violations": [...]}
        """
        it = _to_dict(intention)
        ag = _to_dict(agent)
        print(
            f"[agents/interpreter.py] 🔎 开始审查意向 {it.get('intention_id', '<no-id>')} 类型 {it.get('kind', '<unknown>')}"
            f"，来自 {ag.get('name', ag.get('id', '<unknown>'))}。"
        )

        kind = it.get("kind")
        if not kind:
            decision = self._decision(
                "suppressed",
                [{"kind": "require", "rule": "missing kind", "detail": "intention.kind"}],
            )
            print(
                f"[agents/interpreter.py] ⚠️ 意向缺少 kind 字段，直接压制：{decision}."
            )
            return decision

        ruleset = self.kinds.get(kind)
        if not ruleset:
            if not self.allow_unknown_kind:
                decision = self._decision(
                    "suppressed",
                    [{"kind": "forbid", "rule": f"unknown kind {kind}", "detail": kind}],
                )
                print(
                    f"[agents/interpreter.py] ❔ 未找到 {kind} 的规则，压制：{decision}."
                )
                return decision

            decision = self._decision(
                "approved",
                [{"kind": "warn", "rule": f"unknown kind {kind}", "detail": kind}],
            )
            print(
                f"[agents/interpreter.py] ⚠️ 未找到 {kind} 的规则，但允许未知类型通过：{decision}."
            )
            return decision

        violations: List[Dict[str, str]] = []

        # 1) require
        violations.extend(self._check_require(ruleset.get("require"), it, ag, world, store))

        # 2) forbid
        violations.extend(self._check_forbid(ruleset.get("forbid"), it, ag, world, store))

        if violations:
            decision = self._decision("suppressed", violations)
            print(
                f"[agents/interpreter.py] 🚫 意向 {it.get('intention_id', '<no-id>')} 未通过：{violations}."
            )
            return decision

        decision = self._decision("approved", [])
        print(
            f"[agents/interpreter.py] ✅ 意向 {it.get('intention_id', '<no-id>')} 通过审查。"
        )
        return decision

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
                    try:
                        ok = self._any_ref_type_in(refs, allowed_types, store)
                    except Exception:
                        violations.append(
                            {
                                "kind": "require",
                                "rule": "store_missing",
                                "detail": "references.event_types needs store",
                            }
                        )
                    else:
                        if not ok:
                            violations.append(
                                {
                                    "kind": "require",
                                    "rule": "reference type mismatch",
                                    "detail": str(allowed_types),
                                }
                            )

        return violations

    # ---------------- forbid ----------------
    def _check_forbid(self, forbid_list: Optional[List[Any]], it, ag, world, store):
        if not forbid_list:
            return []

        violations: List[Dict[str, str]] = []

        # forbid 条件用安全的表达式解释器执行
        for expr in forbid_list:
            if not isinstance(expr, str):
                # 不认识的 forbid 结构，先当作不命中（以后升级 DSL 再严格）
                continue

            try:
                hit = self._eval_expr(expr, it, ag, world, store)
            except Exception as e:  # pragma: no cover - 运行时防御
                violations.append(
                    {"kind": "forbid", "rule": "expr_error", "detail": f"{expr} :: {type(e).__name__}:{e}"}
                )
                continue

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

    def _any_ref_type_in(self, refs: List, allowed_types: List[str], store) -> bool:
        if store is None:
            raise RuntimeError("store missing")
        for ref in refs:
            ev = store.get(ref_event_id(ref))
            if not ev:
                continue
            # ev 可能是 dataclass，也可能是 dict
            evd = _to_dict(ev)
            if evd.get("type") in allowed_types:
                return True
        return False

    def _eval_expr(self, expr: str, it, ag, world, store) -> bool:
        referenced_event = None
        refs = it.get("references") or []
        if refs and store:
            referenced_event = store.get(ref_event_id(refs[0]))
        rev = _to_dict(referenced_event)

        globals_block = (self.policy.get("globals") or {}) if hasattr(self, "policy") else {}
        escalation_threshold = globals_block.get("escalation_threshold", 0.75)

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
            "len": len,
            "is_empty": is_empty,
            "get": get_value,
            "escalation_threshold": escalation_threshold,
        }

        return _safe_bool_expr(expr, env)