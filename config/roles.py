from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


_ROLES_DIR = Path(__file__).resolve().parent / "roles"


def load_role_profile(role: Optional[str]) -> Dict[str, Any]:
    role_key = (role or "default").lower()
    path = _ROLES_DIR / f"{role_key}.json"
    if not path.exists():
        path = _ROLES_DIR / "default.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("temperature", 1.0)
    return data


def role_prompt_description(role: Optional[str]) -> str:
    profile = load_role_profile(role)
    parts = [
        f"生理维度：{profile.get('physiology', '')}",
        f"心理维度：{profile.get('psychology', '')}",
        f"角色背景：{profile.get('background', '')}",
        f"知识卡：{profile.get('knowledge_card', '')}",
        f"语言语气：{profile.get('tone', '')}",
        f"擅长：{', '.join(profile.get('strengths', []) or [])}",
    ]
    return "\n".join(part for part in parts if part)


def role_temperature(role: Optional[str]) -> float:
    profile = load_role_profile(role)
    try:
        return float(profile.get("temperature", 1.0))
    except (TypeError, ValueError):
        return 1.0
