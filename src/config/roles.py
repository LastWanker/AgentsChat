from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


_ROLES_DIR = Path(__file__).resolve().parent / "roles"


def _resolve_role_path(role: Optional[str]) -> Path:
    if not role:
        return _ROLES_DIR / "default.json"

    role_key = str(role).strip()
    direct_path = _ROLES_DIR / f"{role_key}.json"
    if direct_path.exists():
        return direct_path

    lower_key = role_key.lower()
    lower_path = _ROLES_DIR / f"{lower_key}.json"
    if lower_path.exists():
        return lower_path

    for candidate in _ROLES_DIR.iterdir():
        if candidate.suffix != ".json":
            continue
        if candidate.stem.lower() == lower_key:
            return candidate

    return _ROLES_DIR / "default.json"


def load_role_profile(role: Optional[str]) -> Dict[str, Any]:
    path = _resolve_role_path(role)
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
