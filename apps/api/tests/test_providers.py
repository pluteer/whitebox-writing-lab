import asyncio
import json

import httpx

from whitebox.providers import DeepSeekProvider, OpenAICompatibleProvider, ProviderError


def test_deepseek_stream_contract_and_usage() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["authorization"]
        captured["payload"] = json.loads(request.content)
        stream = "\n\n".join(
            [
                'data: {"id":"req-1","choices":[{"delta":{"content":"雨夜"},"finish_reason":null}],"usage":null}',
                'data: {"id":"req-1","choices":[{"delta":{"content":"戏楼"},"finish_reason":"stop"}],"usage":{"prompt_tokens":12,"completion_tokens":4,"total_tokens":16,"prompt_cache_hit_tokens":2,"prompt_cache_miss_tokens":10}}',
                "data: [DONE]",
            ]
        )
        return httpx.Response(200, text=stream, headers={"x-request-id": "header-req-1"})

    provider = DeepSeekProvider(api_key="test-secret", transport=httpx.MockTransport(handler))
    deltas = []

    async def execute():
        async def on_delta(delta: str) -> None:
            deltas.append(delta)

        return await provider.stream_chat(
            model="deepseek-v4-flash",
            messages=[{"role": "user", "content": "写作"}],
            temperature=0.8,
            max_tokens=100,
            thinking=False,
            on_delta=on_delta,
        )

    result = asyncio.run(execute())

    assert result.text == "雨夜戏楼"
    assert deltas == ["雨夜", "戏楼"]
    assert result.request_id == "header-req-1"
    assert result.usage.total_tokens == 16
    assert captured["authorization"] == "Bearer test-secret"
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert "authorization" not in result.request_payload


def test_deepseek_error_is_normalized_without_key_leak() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "Authentication Fails", "code": "invalid_request_error"}},
        )

    provider = DeepSeekProvider(api_key="test-secret", transport=httpx.MockTransport(handler))

    async def execute():
        async def on_delta(_: str) -> None:
            pass

        return await provider.stream_chat(
            model="deepseek-v4-flash",
            messages=[{"role": "user", "content": "写作"}],
            temperature=0.8,
            max_tokens=100,
            thinking=False,
            on_delta=on_delta,
        )

    try:
        asyncio.run(execute())
        raise AssertionError("expected ProviderError")
    except ProviderError as exc:
        assert exc.status_code == 401
        assert exc.code == "invalid_request_error"
        assert "test-secret" not in str(exc)


def test_deepseek_lists_models_and_balance() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/models":
            return httpx.Response(200, json={"data": [
                {"id": "deepseek-v4-pro", "owned_by": "deepseek"},
                {"id": "deepseek-v4-flash", "owned_by": "deepseek"},
            ]})
        return httpx.Response(200, json={
            "is_available": True,
            "balance_infos": [{
                "currency": "USD", "total_balance": "1.20",
                "granted_balance": "0.20", "topped_up_balance": "1.00",
            }],
        })

    provider = DeepSeekProvider(api_key="test-secret", transport=httpx.MockTransport(handler))
    models = asyncio.run(provider.list_models())
    balance = asyncio.run(provider.get_balance())

    assert [item["id"] for item in models] == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert balance["is_available"] is True
    assert balance["balance_infos"][0]["currency"] == "USD"


def test_generic_openai_compatible_request_omits_deepseek_specific_fields() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, text=(
            'data: {"id":"generic-1","choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}],'
            '"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}\n\n'
            'data: [DONE]\n\n'
        ))

    provider = OpenAICompatibleProvider(
        api_key="generic-secret", base_url="https://generic.example/v1",
        transport=httpx.MockTransport(handler),
    )

    async def execute():
        async def on_delta(_: str) -> None: pass
        return await provider.stream_chat(
            model="generic-model", messages=[{"role": "user", "content": "hi"}],
            temperature=0.5, max_tokens=10, thinking=True, on_delta=on_delta,
        )

    asyncio.run(execute())
    assert "thinking" not in captured


def test_generic_provider_does_not_inherit_deepseek_key(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-env-secret")

    assert OpenAICompatibleProvider().api_key is None
    assert DeepSeekProvider().api_key == "deepseek-env-secret"


def test_openai_compatible_preserves_v1_and_accepts_sse_without_space() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, text=(
            'data:{"id":"generic-1","choices":[{"delta":{"content":"ok"},'
            '"finish_reason":"stop"}]}\n\ndata:[DONE]\n\n'
        ))

    provider = OpenAICompatibleProvider(
        api_key="secret", base_url="https://generic.example/v1/",
        transport=httpx.MockTransport(handler),
    )

    async def execute():
        async def on_delta(_: str) -> None:
            pass

        return await provider.stream_chat(
            model="model", messages=[], temperature=0.2, max_tokens=10,
            thinking=False, on_delta=on_delta,
        )

    assert asyncio.run(execute()).text == "ok"
    assert captured["path"] == "/v1/chat/completions"
