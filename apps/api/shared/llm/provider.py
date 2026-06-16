"""Local-first LLM provider abstractions for WorkBuddy OSS."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import ssl
import time
import urllib.error
import urllib.request
from typing import Any, Protocol

from apps.api.core.config import get_settings


@dataclass(frozen=True)
class LLMRequest:
    """Provider-neutral request shape used for audit metadata."""

    task: str
    prompt: str
    variables: dict[str, Any] = field(default_factory=dict)
    json_mode: bool = True


@dataclass(frozen=True)
class LLMResponse:
    """Provider-neutral response shape.

    ``content`` is intentionally a dictionary in Phase 0 because the mock
    provider is rule-first and should feed structured AgentRun records directly.
    """

    provider: str
    model: str
    content: dict[str, Any]
    usage: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str
    model: str

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a structured result."""


class MockLLMProvider:
    """Deterministic local provider for demos and tests."""

    name = "mock"
    model = "workbuddy-mock-v0"

    def generate(self, request: LLMRequest) -> LLMResponse:
        text = str(request.variables.get("message_text", "")).lower()
        content: dict[str, Any]

        if request.task == "intent_classification":
            content = {
                "intent": "chat",
                "confidence": 0.42,
                "risk_level": "low",
                "requires_approval": False,
                "entities": {},
                "reason": "Mock fallback: no strong business intent matched.",
            }
            if any(word in text for word in ["refund", "complaint", "bug", "退款", "投诉", "报错"]):
                content.update(
                    {
                        "intent": "support_ticket",
                        "confidence": 0.72,
                        "risk_level": "high",
                        "requires_approval": True,
                        "reason": "Mock detected support-related keywords.",
                    }
                )
            elif any(word in text for word in ["price", "demo", "trial", "报价", "试用", "演示"]):
                content.update(
                    {
                        "intent": "sales_lead",
                        "confidence": 0.7,
                        "risk_level": "medium",
                        "requires_approval": True,
                        "reason": "Mock detected sales-related keywords.",
                    }
                )
        else:
            content = {
                "summary": "Mock provider did not call an external model.",
                "confidence": 0.5,
            }

        return LLMResponse(
            provider=self.name,
            model=self.model,
            content=content,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            raw={"mode": "demo"},
        )


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    """Settings for OpenAI-compatible chat completion providers."""

    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> "OpenAICompatibleConfig":
        settings = get_settings()
        return cls(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model or "gpt-4.1-mini",
            timeout_seconds=settings.llm_timeout_seconds,
        )


class OpenAICompatibleProvider:
    """OpenAI-compatible chat completion provider.

    DeepSeek, OpenAI, Qwen, Moonshot and other compatible services can use the
    same base_url/api_key/model contract.
    """

    name = "openai_compatible"

    def __init__(self, config: OpenAICompatibleConfig | None = None) -> None:
        self.config = config or OpenAICompatibleConfig.from_env()
        self.model = self.config.model

    def generate(self, request: LLMRequest) -> LLMResponse:
        if not self.config.api_key or not self.config.base_url:
            return LLMResponse(
                provider=self.name,
                model=self.model,
                content={
                    "intent": "chat",
                    "confidence": 0.0,
                    "risk_level": "low",
                    "requires_approval": False,
                    "entities": {},
                    "reason": "OpenAI-compatible provider is selected but LLM_API_KEY or LLM_BASE_URL is missing.",
                },
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                raw={"configured": False, "network_call": False},
            )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Return compact JSON only. Do not wrap the response in markdown.",
                },
                {
                    "role": "user",
                    "content": request.prompt,
                },
            ],
            "temperature": 0.2,
        }
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            body = self._post_chat_completions(payload)
            choice = (body.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            content = parse_json_content(str(message.get("content") or "{}"))
            usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
            return LLMResponse(
                provider=self.name,
                model=str(body.get("model") or self.model),
                content=content,
                usage={
                    "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                    "completion_tokens": int(usage.get("completion_tokens") or 0),
                    "total_tokens": int(usage.get("total_tokens") or 0),
                },
                raw={"configured": True, "network_call": True, "finish_reason": choice.get("finish_reason")},
            )
        except Exception as exc:  # noqa: BLE001 - keep Agent routing available when model calls fail.
            return LLMResponse(
                provider=self.name,
                model=self.model,
                content={
                    "intent": "chat",
                    "confidence": 0.0,
                    "risk_level": "low",
                    "requires_approval": False,
                    "entities": {},
                    "reason": f"OpenAI-compatible provider call failed: {exc}",
                },
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                raw={"configured": True, "network_call": False, "error": str(exc)},
            )

    def _post_chat_completions(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds, context=default_ssl_context()) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("Provider returned a non-object JSON payload.")
        return parsed


def smoke_test_llm(
    provider: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    selected = (provider or settings.llm_provider or "mock").strip().lower()
    started = time.perf_counter()
    if selected in {"", "mock", "demo", "local"}:
        response = MockLLMProvider().generate(
            LLMRequest(
                task="smoke_test",
                prompt='Return {"ok": true, "message": "mock provider ready"} as JSON.',
                variables={},
            )
        )
        return {
            "ok": True,
            "provider": "mock",
            "model": response.model,
            "mode": "mock",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "message": "Mock provider is ready. No external model call was made.",
            "advice": "切换到真实 Provider 并填写 Base URL/API Key/Model 后，可验证真实模型。",
            "usage": response.usage,
        }

    merged = OpenAICompatibleConfig(
        base_url=(base_url if base_url is not None else settings.llm_base_url).strip(),
        api_key=api_key if api_key is not None else settings.llm_api_key,
        model=(model if model is not None else settings.llm_model).strip() or "workbuddy-demo",
        timeout_seconds=timeout_seconds if timeout_seconds is not None else settings.llm_timeout_seconds,
    )
    if not merged.base_url or not merged.api_key or not merged.model:
        return {
            "ok": False,
            "provider": selected,
            "model": merged.model,
            "mode": "real",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "message": "模型配置不完整。",
            "error_type": "missing_config",
            "advice": "请补齐 Base URL、API Key 和 Model。API Key 留空只会沿用已保存密钥。",
            "base_url_configured": bool(merged.base_url),
            "api_key_configured": bool(merged.api_key),
        }

    payload = {
        "model": merged.model,
        "messages": [
            {"role": "system", "content": "Return compact JSON only."},
            {"role": "user", "content": 'Return {"ok": true, "message": "WorkBuddy smoke test passed"} as JSON.'},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    try:
        body = OpenAICompatibleProvider(merged)._post_chat_completions(payload)
        choice = (body.get("choices") or [{}])[0]
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        return {
            "ok": True,
            "provider": selected,
            "model": str(body.get("model") or merged.model),
            "mode": "real",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "message": "模型 smoke test 调用成功。",
            "finish_reason": choice.get("finish_reason"),
            "usage": {
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
            },
            "certificate": certificate_status(),
        }
    except Exception as exc:  # noqa: BLE001 - smoke test should return actionable diagnostics.
        return {
            "ok": False,
            "provider": selected,
            "model": merged.model,
            "mode": "real",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "message": "模型 smoke test 调用失败。",
            "error": str(exc),
            "error_type": classify_llm_error(exc),
            "advice": llm_error_advice(exc),
            "certificate": certificate_status(),
        }


def default_ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi
    except Exception:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def certificate_status() -> dict[str, Any]:
    try:
        import certifi
    except Exception as exc:
        return {
            "certifi_available": False,
            "ca_bundle": None,
            "advice": f"certifi 未安装或不可用：{exc}",
        }
    return {
        "certifi_available": True,
        "ca_bundle": certifi.where(),
    }


def classify_llm_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "certificate_verify_failed" in text or "self-signed certificate" in text or "ssl" in text:
        return "ssl_certificate"
    if "timed out" in text or "timeout" in text:
        return "timeout"
    if "http 401" in text or "unauthorized" in text:
        return "auth"
    if "http 404" in text or "not found" in text or "model names" in text or "model name" in text:
        return "endpoint_or_model"
    if "http 429" in text or "rate limit" in text:
        return "rate_limit"
    if "http " in text:
        return "http_error"
    return "network_or_provider"


def llm_error_advice(exc: Exception) -> str:
    error_type = classify_llm_error(exc)
    if error_type == "ssl_certificate":
        return "当前请求已尝试使用 certifi CA 证书包。若仍失败，请检查公司代理/自签根证书，或把可信 CA 合并进 Python 运行环境的证书链。"
    if error_type == "auth":
        return "请检查 API Key 是否正确、是否有模型访问权限。"
    if error_type == "endpoint_or_model":
        return "请检查 Base URL 是否以兼容接口根路径结尾，例如 https://api.example.com/v1，并确认模型名存在。"
    if error_type == "timeout":
        return "请检查网络连通性，或在配置中心适当调大超时时间。"
    if error_type == "rate_limit":
        return "供应商返回限流，请稍后再试或更换 Key/模型。"
    return "请检查 Base URL、模型名、网络代理和供应商兼容接口返回。"


def parse_json_content(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return LLMResponse(
            provider="parser",
            model="json",
            content={"summary": content, "confidence": 0.0},
        ).content
    if not isinstance(parsed, dict):
        return {"summary": parsed, "confidence": 0.0}
    return parsed


def get_llm_provider(mode: str | None = None) -> LLMProvider:
    """Return the configured provider, defaulting to deterministic mock mode."""

    settings = get_settings()
    selected = (mode or settings.llm_provider or "mock").strip().lower()
    if selected in {"openai", "openai_compatible", "deepseek", "qwen", "dashscope", "moonshot"}:
        return OpenAICompatibleProvider()
    return MockLLMProvider()
