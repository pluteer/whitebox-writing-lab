from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Awaitable, Callable

import httpx

from .models import ProviderUsage


DeltaHandler = Callable[[str], Awaitable[None]]
MAX_PROVIDER_REQUEST_BYTES = 2 * 1024 * 1024
MAX_PROVIDER_CHUNK_BYTES = 1024 * 1024
MAX_PROVIDER_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_PROVIDER_CHUNKS = 10_000


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code

    def as_dict(self) -> dict:
        return {
            "message": str(self),
            "status_code": self.status_code,
            "code": self.code,
        }


@dataclass
class ProviderResult:
    text: str
    model: str
    request_id: str | None
    finish_reason: str | None
    usage: ProviderUsage
    request_payload: dict
    response_payload: dict


class OpenAICompatibleProvider:
    provider = "openai-compatible"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.deepseek.com",
        transport: httpx.AsyncBaseTransport | None = None,
        supports_deepseek_thinking: bool = False,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.supports_deepseek_thinking = supports_deepseek_thinking

    def configure(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
        if api_key is not None:
            self.api_key = api_key
        if base_url is not None:
            self.base_url = base_url.rstrip("/")

    def clear_api_key(self) -> None:
        self.api_key = None

    async def list_models(self) -> list[dict]:
        payload = await self._get_json("/models")
        models = payload.get("data", [])
        return sorted(
            [
                {
                    "id": item.get("id"),
                    "owned_by": item.get("owned_by"),
                    "object": item.get("object"),
                }
                for item in models
                if item.get("id")
            ],
            key=lambda item: item["id"],
        )

    async def get_balance(self) -> dict:
        payload = await self._get_json("/user/balance")
        return {
            "is_available": payload.get("is_available", False),
            "balance_infos": [
                {
                    "currency": item.get("currency"),
                    "total_balance": item.get("total_balance"),
                    "granted_balance": item.get("granted_balance"),
                    "topped_up_balance": item.get("topped_up_balance"),
                }
                for item in payload.get("balance_infos", [])
            ],
        }

    async def _get_json(self, path: str) -> dict:
        if not self.api_key:
            raise ProviderError("未配置供应商 API Key", code="missing_api_key")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(
            base_url=f"{self.base_url}/",
            timeout=httpx.Timeout(30, connect=10),
            transport=self.transport,
        ) as client:
            try:
                response = await client.get(path.lstrip("/"), headers=headers)
            except httpx.HTTPError as exc:
                raise ProviderError(f"模型供应商网络请求失败: {exc}", code="network_error") from exc
        if response.status_code >= 400:
            try:
                error = response.json().get("error", {})
                message = error.get("message", response.text[:1000])
                code = error.get("code")
            except (json.JSONDecodeError, ValueError):
                message = response.text[:1000]
                code = None
            raise ProviderError(message, status_code=response.status_code, code=code)
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise ProviderError("模型供应商返回了无效 JSON", code="invalid_json") from exc

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        thinking: bool,
        on_delta: DeltaHandler,
    ) -> ProviderResult:
        if not self.api_key:
            raise ProviderError("未配置供应商 API Key", code="missing_api_key")

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if self.supports_deepseek_thinking:
            payload["thinking"] = {"type": "enabled" if thinking else "disabled"}
        if len(json.dumps(payload, ensure_ascii=False).encode()) > MAX_PROVIDER_REQUEST_BYTES:
            raise ProviderError("模型请求载荷超过 2 MB 限制", code="request_too_large")
        chunks: list[dict] = []
        response_bytes = 0
        text_parts: list[str] = []
        finish_reason: str | None = None
        usage = ProviderUsage()
        request_id: str | None = None
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        timeout = httpx.Timeout(120, connect=15)
        async with httpx.AsyncClient(
            base_url=f"{self.base_url}/", timeout=timeout, transport=self.transport
        ) as client:
            try:
                async with client.stream(
                    "POST", "chat/completions", headers=headers, json=payload
                ) as response:
                    request_id = response.headers.get("x-request-id")
                    if response.status_code >= 400:
                        body = (await response.aread()).decode(errors="replace")[:2000]
                        code = None
                        message = body
                        try:
                            error = json.loads(body).get("error", {})
                            code = error.get("code")
                            message = error.get("message", body)
                        except json.JSONDecodeError:
                            pass
                        raise ProviderError(message, status_code=response.status_code, code=code)

                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].lstrip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError as exc:
                            raise ProviderError("模型供应商返回了无效的流式 JSON", code="invalid_stream") from exc
                        chunk_bytes = len(data.encode())
                        response_bytes += chunk_bytes
                        if chunk_bytes > MAX_PROVIDER_CHUNK_BYTES:
                            raise ProviderError("模型流式分块超过 1 MB 限制", code="chunk_too_large")
                        if len(chunks) >= MAX_PROVIDER_CHUNKS or response_bytes > MAX_PROVIDER_RESPONSE_BYTES:
                            raise ProviderError("模型流式响应超过大小限制", code="response_too_large")
                        chunks.append(chunk)
                        if not request_id:
                            request_id = chunk.get("id")
                        choices = chunk.get("choices") or []
                        if choices:
                            delta = choices[0].get("delta", {}).get("content") or ""
                            if delta:
                                text_parts.append(delta)
                                await on_delta(delta)
                            finish_reason = choices[0].get("finish_reason") or finish_reason
                        if chunk.get("usage"):
                            raw_usage = chunk["usage"]
                            usage = ProviderUsage(
                                prompt_tokens=raw_usage.get("prompt_tokens", 0),
                                completion_tokens=raw_usage.get("completion_tokens", 0),
                                total_tokens=raw_usage.get("total_tokens", 0),
                                prompt_cache_hit_tokens=raw_usage.get("prompt_cache_hit_tokens", 0),
                                prompt_cache_miss_tokens=raw_usage.get("prompt_cache_miss_tokens", 0),
                            )
            except httpx.HTTPError as exc:
                raise ProviderError(f"模型供应商网络请求失败: {exc}", code="network_error") from exc

        text = "".join(text_parts)
        if not text:
            raise ProviderError("模型供应商没有返回正文", code="empty_response")
        return ProviderResult(
            text=text,
            model=model,
            request_id=request_id,
            finish_reason=finish_reason,
            usage=usage,
            request_payload=payload,
            response_payload={"chunks": chunks},
        )


class DeepSeekProvider(OpenAICompatibleProvider):
    provider = "deepseek"

    def __init__(self, *args, **kwargs):
        if args and args[0] is None:
            args = (os.getenv("DEEPSEEK_API_KEY"), *args[1:])
        elif not args and kwargs.get("api_key") is None:
            kwargs["api_key"] = os.getenv("DEEPSEEK_API_KEY")
        kwargs["supports_deepseek_thinking"] = True
        super().__init__(*args, **kwargs)
