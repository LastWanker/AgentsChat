from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, List, Sequence


_STOP_TOKENS = {
    "的",
    "了",
    "是",
    "在",
    "和",
    "与",
    "或",
    "及",
    "一个",
    "我们",
    "你们",
    "他们",
    "她们",
    "它们",
    "我",
    "你",
    "他",
    "她",
    "它",
}

_STOP_PHRASES = {
    "各位好",
    "大家好",
    "你们好",
    "各位",
    "大家",
    "你们二位",
    "这次是个",
    "需要就",
    "谢谢",
    "感谢",
    "麻烦",
    "请问",
}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for match in re.finditer(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,6}", text):
        token = match.group(0).strip().lower()
        if not token or token in _STOP_TOKENS:
            continue
        if token in _STOP_PHRASES:
            continue
        if _CJK_RE.search(token) and len(token) < 2:
            continue
        tokens.append(token)
    return tokens


def generate_tags(
    *,
    text: str,
    fixed_prefix: Sequence[str] | None = None,
    max_tags: int = 6,
) -> List[str]:
    fixed = [t for t in (fixed_prefix or []) if t]
    seen = set(t.lower() for t in fixed)
    tags = list(fixed)
    for token, _ in Counter(_tokenize(text)).most_common():
        if token in seen:
            continue
        seen.add(token)
        tags.append(token)
        if len(tags) >= max_tags:
            break
    return tags


def extend_tags(existing: Iterable[str], extra: Iterable[str], max_tags: int = 9) -> List[str]:
    tags: List[str] = []
    seen = set()
    for tag in list(existing) + list(extra):
        if not tag:
            continue
        key = str(tag).lower()
        if key in seen:
            continue
        seen.add(key)
        tags.append(str(tag))
        if len(tags) >= max_tags:
            break
    return tags
