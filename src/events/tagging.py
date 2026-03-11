from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence


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


def generate_tags_with_llm(
    *,
    text: str,
    fixed_prefix: Sequence[str] | None = None,
    max_tags: int = 6,
    llm_client: Optional[Any] = None,
    llm_mode: str = "sync",
    tag_pool: Optional[Dict[str, Any]] = None,
) -> Optional[List[str]]:
    if llm_client is None:
        return None
    from llm.client import LLMRequestOptions
    from llm.prompts import build_tag_generation_prompt
    from llm.schemas import parse_tag_generation

    messages = build_tag_generation_prompt(
        text=text,
        max_tags=max_tags,
        fixed_prefix=list(fixed_prefix or []),
        tag_pool=tag_pool,
    )
    options = LLMRequestOptions(temperature=0.2, max_tokens=96)
    if llm_mode == "async":
        import asyncio

        content = asyncio.run(llm_client.acomplete(messages, options=options))
    elif llm_mode == "stream":
        content = "".join(llm_client.stream(messages, options=options))
    else:
        content = llm_client.complete(messages, options=options)
    try:
        data = parse_tag_generation(content)
    except Exception:
        return None
    raw_tags = data.get("tags") if isinstance(data, dict) else None
    return _normalize_llm_tags(raw_tags, fixed_prefix, max_tags)


async def generate_tags_with_llm_async(
    *,
    text: str,
    fixed_prefix: Sequence[str] | None = None,
    max_tags: int = 6,
    llm_client: Optional[Any] = None,
    tag_pool: Optional[Dict[str, Any]] = None,
    semaphore: Optional[Any] = None,
) -> Optional[List[str]]:
    if llm_client is None:
        return None
    from llm.client import LLMRequestOptions
    from llm.prompts import build_tag_generation_prompt
    from llm.schemas import parse_tag_generation

    messages = build_tag_generation_prompt(
        text=text,
        max_tags=max_tags,
        fixed_prefix=list(fixed_prefix or []),
        tag_pool=tag_pool,
    )
    options = LLMRequestOptions(temperature=0.2, max_tokens=96)
    if semaphore is None:
        content = await llm_client.acomplete(messages, options=options)
    else:
        async with semaphore:
            content = await llm_client.acomplete(messages, options=options)
    try:
        data = parse_tag_generation(content)
    except Exception:
        return None
    raw_tags = data.get("tags") if isinstance(data, dict) else None
    return _normalize_llm_tags(raw_tags, fixed_prefix, max_tags)


def _normalize_llm_tags(
    raw_tags: Optional[Sequence[Any]],
    fixed_prefix: Sequence[str] | None,
    max_tags: int,
) -> Optional[List[str]]:
    if not raw_tags:
        return None
    fixed = [str(t) for t in (fixed_prefix or []) if t]
    seen = set()
    tags: List[str] = []
    for tag in fixed + list(raw_tags):
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


def select_tags_from_pool(text: str, pool_tags: Iterable[str], max_tags: int = 9) -> List[str]:
    lowered = text.lower()
    selected: List[str] = []
    seen = set()
    for tag in pool_tags:
        tag_text = str(tag)
        if not tag_text:
            continue
        key = tag_text.lower()
        if key in seen:
            continue
        if key in lowered:
            seen.add(key)
            selected.append(tag_text)
            if len(selected) >= max_tags:
                break
    return selected


def generate_extra_tags_with_llm(
    *,
    text: str,
    existing_tags: Sequence[str] | None = None,
    max_new_tags: int = 3,
    llm_client: Optional[Any] = None,
    llm_mode: str = "sync",
) -> List[str]:
    if llm_client is None:
        return _filter_new_tags(generate_tags(text=text, max_tags=max_new_tags), existing_tags, max_new_tags)
    from llm.client import LLMRequestOptions
    from llm.prompts import build_tag_enrichment_prompt
    from llm.schemas import parse_tag_generation

    messages = build_tag_enrichment_prompt(
        text=text,
        existing_tags=list(existing_tags or []),
        max_tags=max_new_tags,
    )
    options = LLMRequestOptions(temperature=0.2, max_tokens=96)
    if llm_mode == "async":
        import asyncio

        content = asyncio.run(llm_client.acomplete(messages, options=options))
    elif llm_mode == "stream":
        content = "".join(llm_client.stream(messages, options=options))
    else:
        content = llm_client.complete(messages, options=options)
    try:
        data = parse_tag_generation(content)
    except Exception:
        return _filter_new_tags(generate_tags(text=text, max_tags=max_new_tags), existing_tags, max_new_tags)
    raw_tags = data.get("tags") if isinstance(data, dict) else None
    return _filter_new_tags(raw_tags, existing_tags, max_new_tags)


async def generate_extra_tags_with_llm_async(
    *,
    text: str,
    existing_tags: Sequence[str] | None = None,
    max_new_tags: int = 3,
    llm_client: Optional[Any] = None,
    semaphore: Optional[Any] = None,
) -> List[str]:
    if llm_client is None:
        return _filter_new_tags(generate_tags(text=text, max_tags=max_new_tags), existing_tags, max_new_tags)
    from llm.client import LLMRequestOptions
    from llm.prompts import build_tag_enrichment_prompt
    from llm.schemas import parse_tag_generation

    messages = build_tag_enrichment_prompt(
        text=text,
        existing_tags=list(existing_tags or []),
        max_tags=max_new_tags,
    )
    options = LLMRequestOptions(temperature=0.2, max_tokens=96)
    if semaphore is None:
        content = await llm_client.acomplete(messages, options=options)
    else:
        async with semaphore:
            content = await llm_client.acomplete(messages, options=options)
    try:
        data = parse_tag_generation(content)
    except Exception:
        return _filter_new_tags(generate_tags(text=text, max_tags=max_new_tags), existing_tags, max_new_tags)
    raw_tags = data.get("tags") if isinstance(data, dict) else None
    return _filter_new_tags(raw_tags, existing_tags, max_new_tags)


def _filter_new_tags(
    raw_tags: Optional[Sequence[Any]],
    existing_tags: Sequence[str] | None,
    max_new_tags: int,
) -> List[str]:
    if not raw_tags:
        return []
    existing = {str(tag).lower() for tag in (existing_tags or []) if tag}
    seen = set(existing)
    filtered: List[str] = []
    for tag in raw_tags:
        if not tag:
            continue
        key = str(tag).lower()
        if key in seen:
            continue
        seen.add(key)
        filtered.append(str(tag))
        if len(filtered) >= max_new_tags:
            break
    return filtered
