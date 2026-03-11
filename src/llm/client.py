from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional
from urllib import request
from urllib.error import HTTPError, URLError


@dataclass(frozen=True)
class LLMTimeouts:
    connect: float = 5.0
    read: float = 60.0
    stream_first_packet: float = 10.0
    stream_total: float = 120.0


@dataclass(frozen=True)
class LLMRetryPolicy:
    max_retries: int = 2
    backoff_base: float = 0.5
    backoff_factor: float = 2.0
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)


@dataclass
class LLMRequestOptions:
    temperature: float = 0.7
    max_tokens: int = 512
    stream: bool = False
    timeouts: LLMTimeouts = field(default_factory=LLMTimeouts)
    retry_policy: LLMRetryPolicy = field(default_factory=LLMRetryPolicy)


class LLMClient:
    """抽象客户端：同步 / 异步 / 流式三套玩法。"""

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        options: Optional[LLMRequestOptions] = None,
    ) -> str:
        raise NotImplementedError

    async def acomplete(
        self,
        messages: List[Dict[str, str]],
        *,
        options: Optional[LLMRequestOptions] = None,
    ) -> str:
        return await asyncio.to_thread(self.complete, messages, options=options)

    def stream(
        self,
        messages: List[Dict[str, str]],
        *,
        options: Optional[LLMRequestOptions] = None,
    ) -> Iterable[str]:
        yield self.complete(messages, options=options)

    async def astream(
        self,
        messages: List[Dict[str, str]],
        *,
        options: Optional[LLMRequestOptions] = None,
    ) -> AsyncIterator[str]:
        for chunk in self.stream(messages, options=options):
            yield chunk


class OpenAICompatibleClient(LLMClient):
    """适配 OpenAI 风格的 chat/completions API（DeepSeek 兼容）。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        default_options: Optional[LLMRequestOptions] = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.default_options = default_options or LLMRequestOptions()

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        options: Optional[LLMRequestOptions] = None,
    ) -> str:
        opts = options or self.default_options
        payload = self._build_payload(messages, opts, stream=False)
        data = self._request_with_retries(payload, opts)
        return self._extract_content(data)

    def stream(
        self,
        messages: List[Dict[str, str]],
        *,
        options: Optional[LLMRequestOptions] = None,
    ) -> Iterable[str]:
        opts = options or self.default_options
        payload = self._build_payload(messages, opts, stream=True)
        for chunk in self._request_stream_with_retries(payload, opts):
            if chunk:
                yield chunk

    def _build_payload(
        self,
        messages: List[Dict[str, str]],
        options: LLMRequestOptions,
        *,
        stream: bool,
    ) -> Dict[str, Any]:
        return {
            "model": self.model,
            "messages": messages,
            "temperature": options.temperature,
            "max_tokens": options.max_tokens,
            "stream": stream,
        }

    def _request_with_retries(
        self, payload: Dict[str, Any], options: LLMRequestOptions
    ) -> Dict[str, Any]:
        retry_policy = options.retry_policy
        last_exc: Optional[Exception] = None
        for attempt in range(retry_policy.max_retries + 1):
            try:
                return self._request(payload, options)
            except Exception as exc:  # noqa: BLE001 - 需要统一重试入口
                last_exc = exc
                if not self._should_retry(exc, retry_policy, attempt):
                    raise
                delay = retry_policy.backoff_base * (retry_policy.backoff_factor ** attempt)
                time.sleep(delay)
        if last_exc:
            raise last_exc
        raise RuntimeError("LLM 请求失败且未捕获异常")

    def _request_stream_with_retries(
        self, payload: Dict[str, Any], options: LLMRequestOptions
    ) -> Iterable[str]:
        retry_policy = options.retry_policy
        last_exc: Optional[Exception] = None
        for attempt in range(retry_policy.max_retries + 1):
            try:
                yield from self._request_stream(payload, options)
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if not self._should_retry(exc, retry_policy, attempt):
                    raise
                delay = retry_policy.backoff_base * (retry_policy.backoff_factor ** attempt)
                time.sleep(delay)
        if last_exc:
            raise last_exc

    def _request(self, payload: Dict[str, Any], options: LLMRequestOptions) -> Dict[str, Any]:
        url = f"{self.base_url}/v1/chat/completions"
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Content-Type", "application/json")
        timeout = max(options.timeouts.connect, options.timeouts.read)
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
        return json.loads(body)

    def _request_stream(
        self, payload: Dict[str, Any], options: LLMRequestOptions
    ) -> Iterable[str]:
        url = f"{self.base_url}/v1/chat/completions"
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Content-Type", "application/json")
        timeout = max(options.timeouts.connect, options.timeouts.stream_total)
        start_time = time.monotonic()
        got_first_packet = False
        with request.urlopen(req, timeout=timeout) as resp:
            while True:
                elapsed = time.monotonic() - start_time
                if not got_first_packet and elapsed > options.timeouts.stream_first_packet:
                    raise TimeoutError("LLM 流式首包超时")
                if elapsed > options.timeouts.stream_total:
                    raise TimeoutError("LLM 流式输出超时")
                line = resp.readline()
                if not line:
                    break
                got_first_packet = True
                decoded = line.decode("utf-8").strip()
                if not decoded or not decoded.startswith("data:"):
                    continue
                payload_text = decoded.replace("data:", "", 1).strip()
                if payload_text == "[DONE]":
                    break
                try:
                    data_json = json.loads(payload_text)
                except json.JSONDecodeError:
                    continue
                delta = self._extract_stream_delta(data_json)
                if delta:
                    yield delta

    @staticmethod
    def _extract_content(data: Dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return message.get("content") or choices[0].get("text") or ""

    @staticmethod
    def _extract_stream_delta(data: Dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        delta = choices[0].get("delta") or {}
        return delta.get("content") or ""

    @staticmethod
    def _should_retry(exc: Exception, policy: LLMRetryPolicy, attempt: int) -> bool:
        if attempt >= policy.max_retries:
            return False
        if isinstance(exc, HTTPError):
            return exc.code in policy.retry_statuses
        if isinstance(exc, (URLError, TimeoutError)):
            return True
        return False


def build_openai_client_from_settings(settings: Any) -> Optional[OpenAICompatibleClient]:
    if not getattr(settings, "llm_enabled", False):
        return None
    api_key = getattr(settings, "llm_api_key", None)
    if not api_key:
        print("[llm/client.py] ⚠️ 未检测到 LLM API Key，无法创建客户端。")
        return None
    timeouts = LLMTimeouts(
        connect=settings.llm_timeout_connect,
        read=settings.llm_timeout_read,
        stream_first_packet=settings.llm_timeout_stream_first,
        stream_total=settings.llm_timeout_stream_total,
    )
    retry_policy = LLMRetryPolicy(
        max_retries=settings.llm_retries,
        backoff_base=settings.llm_retry_backoff_base,
    )
    options = LLMRequestOptions(
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        stream=False,
        timeouts=timeouts,
        retry_policy=retry_policy,
    )
    return OpenAICompatibleClient(
        api_key=api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        default_options=options,
    )