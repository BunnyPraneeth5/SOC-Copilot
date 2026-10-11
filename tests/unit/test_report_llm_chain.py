"""Report LLM fallback chain: primary model, its fallback, optional provider.

No network: adapters are fakes, HTTP is a MockTransport.
"""

import asyncio
import json
import time

import httpx
import pytest

from soc_copilot.mcp import report_agent as ra
from soc_copilot.mcp.exceptions import AgentLookupError
from soc_copilot.mcp.models import AgentResult, AgentStatus
from soc_copilot.mcp.report_agent import (
    DEFAULT_NVIDIA_FALLBACK_MODEL,
    DEFAULT_NVIDIA_MODEL,
    OpenAICompatibleReportAdapter,
    ReportAgent,
    build_report_llm_chain,
)

VALID = json.dumps({
    "severity": "HIGH",
    "summary": "Tor exit node with abuse reports.",
    "recommendations": ["Block the address"],
    "limitations": [],
    "evidence": {"recon": [], "reputation": [], "shodan": []},
})


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", "true")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    for var in ("REPORT_LLM_PROVIDER", "NVIDIA_NIM_MODEL", "NVIDIA_NIM_FALLBACK_MODEL",
                "REPORT_LLM_FALLBACK_PROVIDER", "OPENROUTER_MODEL", "OPENROUTER_FALLBACK_MODEL"):
        monkeypatch.delenv(var, raising=False)


class Fake:
    provider_name = "nvidia_nim"

    def __init__(self, model, answer=VALID, exc=None, delay=0.0):
        self.model, self.answer, self.exc, self.delay = model, answer, exc, delay
        self.calls = 0

    async def complete(self, system_prompt, user_prompt):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc
        return self.answer


def _agent(adapters, timeout=10.0, attempt_timeout=5.0):
    return ReportAgent(timeout=timeout, attempt_timeout=attempt_timeout, llm_adapters=adapters,
                       recon=AgentResult(agent_name="ReconAgent", status=AgentStatus.FAILED),
                       reputation=AgentResult(agent_name="ReputationAgent", status=AgentStatus.FAILED),
                       shodan=AgentResult(agent_name="ShodanAgent", status=AgentStatus.FAILED))


def _run(agent):
    return asyncio.run(agent.execute("example.com"))


class TestChain:
    def test_primary_used_when_it_works(self):
        primary, fallback = Fake("primary"), Fake("fallback")
        result = _run(_agent([primary, fallback]))
        assert result.status == AgentStatus.SUCCESS
        assert result.data.llm_model == "primary"
        assert fallback.calls == 0

    def test_http_error_falls_back(self):
        primary = Fake("primary", exc=AgentLookupError("ReportAgent", "nvidia_nim", "HTTP 410"))
        result = _run(_agent([primary, Fake("fallback")]))
        assert result.status == AgentStatus.SUCCESS
        assert result.data.llm_model == "fallback"

    def test_timeout_falls_back_within_budget(self):
        primary = Fake("slow", delay=5.0)
        t = time.monotonic()
        result = _run(_agent([primary, Fake("fallback")], timeout=10.0, attempt_timeout=0.3))
        assert result.status == AgentStatus.SUCCESS
        assert result.data.llm_model == "fallback"
        assert time.monotonic() - t < 2.0

    def test_rejected_answer_falls_back(self):
        """Invented evidence or bad JSON counts as a failed attempt."""
        bad = json.dumps({"severity": "HIGH", "summary": "x", "recommendations": ["y"], "limitations": [],
                          "evidence": {"recon": [{"field": "made.up", "value": "z"}],
                                       "reputation": [], "shodan": []}})
        result = _run(_agent([Fake("liar", answer=bad), Fake("not-json", answer="hello"),
                              Fake("good")]))
        assert result.status == AgentStatus.SUCCESS
        assert result.data.llm_model == "good"

    def test_all_fail_names_every_attempt(self):
        result = _run(_agent([
            Fake("a", exc=AgentLookupError("ReportAgent", "nvidia_nim", "HTTP 404")),
            Fake("b", answer="no json here"),
        ]))
        assert result.status == AgentStatus.FAILED
        assert "a: " in result.error and "HTTP 404" in result.error
        assert "b: " in result.error

    def test_total_budget_stops_the_chain(self):
        first = Fake("first", delay=5.0)
        second = Fake("second")
        result = _run(_agent([first, second], timeout=1.2, attempt_timeout=5.0))
        assert result.status == AgentStatus.FAILED
        assert second.calls == 0
        assert "no time left" in result.error

    def test_missing_key_falls_back(self):
        from soc_copilot.mcp.exceptions import APIKeyMissingError
        result = _run(_agent([Fake("p", exc=APIKeyMissingError("X_KEY")), Fake("f")]))
        assert result.data.llm_model == "f"

    def test_single_adapter_still_supported(self):
        agent = ReportAgent(llm_adapter=Fake("only"))
        assert [a.model for a in agent._llm_adapters] == ["only"]


class TestBuildChain:
    def _models(self):
        return [(a.provider_name, a.model) for a in build_report_llm_chain(30.0)]

    def test_defaults(self):
        assert self._models() == [("nvidia_nim", DEFAULT_NVIDIA_MODEL),
                                  ("nvidia_nim", DEFAULT_NVIDIA_FALLBACK_MODEL)]
        assert DEFAULT_NVIDIA_MODEL != "meta/llama-3.1-8b-instruct"  # retired (HTTP 410)

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_NIM_MODEL", "vendor/a")
        monkeypatch.setenv("NVIDIA_NIM_FALLBACK_MODEL", "vendor/b")
        assert self._models() == [("nvidia_nim", "vendor/a"), ("nvidia_nim", "vendor/b")]

    def test_empty_fallback_disables_it(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_NIM_FALLBACK_MODEL", "")
        assert self._models() == [("nvidia_nim", DEFAULT_NVIDIA_MODEL)]

    def test_same_model_not_repeated(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_NIM_FALLBACK_MODEL", DEFAULT_NVIDIA_MODEL)
        assert self._models() == [("nvidia_nim", DEFAULT_NVIDIA_MODEL)]

    def test_other_provider_only_when_asked(self, monkeypatch):
        assert all(p == "nvidia_nim" for p, _ in self._models())
        monkeypatch.setenv("REPORT_LLM_FALLBACK_PROVIDER", "openrouter")
        models = self._models()
        assert models[-1][0] == "openrouter" and len(models) == 3
        assert "REPORT_LLM_PROVIDER" not in __import__("os").environ  # restored

    def test_unknown_fallback_provider_ignored(self, monkeypatch):
        monkeypatch.setenv("REPORT_LLM_FALLBACK_PROVIDER", "nope")
        assert len(self._models()) == 2


class TestHttpErrors:
    @pytest.fixture()
    def http(self, monkeypatch):
        def install(status):
            transport = httpx.MockTransport(lambda request: httpx.Response(status, json={}))
            real = httpx.AsyncClient
            monkeypatch.setattr(ra.httpx, "AsyncClient",
                                lambda **kw: real(transport=transport, **kw))
        return install

    def _adapter(self):
        return OpenAICompatibleReportAdapter(
            provider_name="nvidia_nim", base_url="https://example.invalid/v1",
            api_key_env="NVIDIA_API_KEY", default_model="vendor/old",
            model_env="NVIDIA_NIM_MODEL", timeout=5.0)

    def test_410_says_model_retired(self, http):
        http(410)
        with pytest.raises(AgentLookupError, match="retired.*NVIDIA_NIM_MODEL"):
            asyncio.run(self._adapter().complete("s", "u"))

    def test_404_says_not_available_to_key(self, http):
        http(404)
        with pytest.raises(AgentLookupError, match="not available to this API key"):
            asyncio.run(self._adapter().complete("s", "u"))
