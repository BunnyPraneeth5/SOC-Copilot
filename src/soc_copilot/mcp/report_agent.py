"""ReportAgent — LLM-powered threat analysis and severity rating.

Aggregates outputs from ReconAgent, ReputationAgent, and ShodanAgent,
then calls the Anthropic Claude API to generate a structured
ThreatReport with severity classification.

.. note::
    This is a scaffold — full implementation is pending.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, ValidationError

from soc_copilot.mcp.base_agent import BaseAgent
from soc_copilot.mcp.exceptions import AgentLookupError, APIKeyMissingError
from soc_copilot.mcp.models import (
    AgentResult,
    AgentStatus,
    ThreatSeverity,
    ThreatReport,
)
from soc_copilot.security.network import online_enrichment_enabled


log = structlog.get_logger(__name__)


# Free-tier models are used for development and demos, so keep the prompt
# explicit about source limits and JSON shape. The production Claude adapter
# should use the same prompt contract when it is added.
REPORT_SYSTEM_PROMPT = (
    "You are a senior SOC analyst producing a structured threat assessment "
    "from machine-provided threat intelligence.\n\n"
    "Rules:\n"
    "- Use ONLY facts present in the provided JSON input.\n"
    "- Do NOT infer malware families, campaigns, exploitability, compromise, "
    "ownership, intent, or geolocation beyond the input.\n"
    "- If a source failed, timed out, or is partial, explicitly account for "
    "that uncertainty.\n"
    "- Never treat missing data from a failed source as evidence that the "
    "target is safe.\n"
    "- Return JSON only. Do not wrap it in Markdown.\n"
    "- Evidence entries must use field/value pairs copied from the Allowed "
    "evidence JSON provided in the user prompt.\n"
    "- Do not put concrete factual claims in evidence unless the same "
    "field/value pair appears in Allowed evidence.\n"
    "- The JSON must match this schema:\n"
    "{\n"
    '  "severity": "CRITICAL|HIGH|MEDIUM|LOW",\n'
    '  "summary": "string",\n'
    '  "recommendations": ["string", "..."],\n'
    '  "limitations": ["string", "..."],\n'
    '  "evidence": {\n'
    '    "recon": [{"field": "string", "value": "any JSON value"}],\n'
    '    "reputation": [{"field": "string", "value": "any JSON value"}],\n'
    '    "shodan": [{"field": "string", "value": "any JSON value"}]\n'
    "  }\n"
    "}"
)

REPORT_USER_PROMPT_TEMPLATE = """Assess the target below.

Target:
{target}

Agent results:
{agent_results_json}

Allowed evidence:
{allowed_evidence_json}

Severity guidance:
- CRITICAL: active evidence of severe exposure or malicious reputation, such as known exploited CVEs plus high malicious reputation.
- HIGH: strong malicious reputation, exposed risky services with CVEs, or multiple independent suspicious signals.
- MEDIUM: some suspicious reputation, exposed services without confirmed CVEs, or partial evidence requiring investigation.
- LOW: little or no suspicious evidence from successful sources.
- When key sources failed, include uncertainty in limitations and do not claim they found nothing.

Output requirements:
- Return JSON only.
- Use only evidence present in Agent results.
- Keep summary concise.
- Recommendations must be actionable SOC/IR next steps.
- Every evidence item must use a field/value pair from Allowed evidence under the matching source name.
"""


class EvidenceFact(BaseModel):
    """One structured source fact the LLM may cite."""

    model_config = ConfigDict(extra="forbid")

    field: str
    value: Any


class ReportEvidence(BaseModel):
    """Structured evidence selected by the LLM from allowed input facts."""

    model_config = ConfigDict(extra="forbid")

    recon: list[EvidenceFact]
    reputation: list[EvidenceFact]
    shodan: list[EvidenceFact]


class ReportLLMResponse(BaseModel):
    """Validated JSON shape expected from the report LLM."""

    model_config = ConfigDict(extra="forbid")

    severity: ThreatSeverity
    summary: str
    recommendations: list[str]
    limitations: list[str]
    evidence: ReportEvidence


class ReportLLMAdapter(Protocol):
    """Small provider interface used by ReportAgent.

    ReportAgent should depend only on this protocol. Free-tier adapters are
    intended for local development and demos; the production path is expected
    to use a Claude/Anthropic adapter added behind this same interface.
    """

    provider_name: str
    model: str

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return raw model text for the supplied chat prompts."""
        ...


class OpenAICompatibleReportAdapter:
    """HTTP adapter for OpenAI-compatible chat-completions providers."""

    provider_name: str

    def __init__(
        self,
        *,
        provider_name: str,
        base_url: str,
        api_key_env: str,
        default_model: str,
        model_env: str,
        timeout: float,
    ) -> None:
        self.provider_name = provider_name
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.model = os.environ.get(model_env, default_model)
        self.timeout = timeout

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Call an OpenAI-compatible chat-completions endpoint."""
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise APIKeyMissingError(self.api_key_env)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()

            return body["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            detail = "HTTP 429 rate limit" if status == 429 else f"HTTP {status}"
            raise AgentLookupError(
                "ReportAgent", self.provider_name, detail
            ) from exc
        except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
            raise AgentLookupError(
                "ReportAgent", self.provider_name, str(exc)
            ) from exc


def build_report_llm_adapter(timeout: float) -> ReportLLMAdapter:
    """Build the configured LLM adapter for ReportAgent.

    ``REPORT_LLM_PROVIDER`` defaults to ``nvidia_nim`` so development and demos
    can use free-tier compatible providers. Production deployments should use a
    Claude/Anthropic adapter behind this same interface.
    """
    provider = os.environ.get("REPORT_LLM_PROVIDER", "nvidia_nim").lower()

    if provider == "nvidia_nim":
        return OpenAICompatibleReportAdapter(
            provider_name="nvidia_nim",
            base_url=os.environ.get(
                "NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"
            ),
            api_key_env="NVIDIA_API_KEY",
            default_model="meta/llama-3.1-8b-instruct",
            model_env="NVIDIA_NIM_MODEL",
            timeout=timeout,
        )

    if provider == "openrouter":
        return OpenAICompatibleReportAdapter(
            provider_name="openrouter",
            base_url=os.environ.get(
                "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
            ),
            api_key_env="OPENROUTER_API_KEY",
            default_model="meta-llama/llama-3.1-8b-instruct:free",
            model_env="OPENROUTER_MODEL",
            timeout=timeout,
        )

    raise AgentLookupError(
        "ReportAgent",
        "LLMProvider",
        f"Unsupported REPORT_LLM_PROVIDER '{provider}'",
    )


def _pydantic_to_plain(value: Any) -> Any:
    """Convert Pydantic models to JSON-serializable plain objects."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return value


def _is_default_fact_value(value: Any) -> bool:
    """Return whether a value looks like an empty/default lookup result."""
    return value in (None, "", [], {}, 0, 0.0, False)


def _append_fact(
    facts: list[EvidenceFact],
    field: str,
    value: Any,
    *,
    include_default_values: bool = True,
) -> None:
    """Append one evidence fact when the upstream value is meaningful."""
    if _is_default_fact_value(value) and not include_default_values:
        return
    if value in (None, "", [], {}):
        return
    facts.append(EvidenceFact(field=field, value=value))


def _agent_error_mentions(result: AgentResult | None, marker: str) -> bool:
    """Return whether an AgentResult error names a failed sub-source."""
    return result is not None and result.error is not None and marker in result.error


_INT_EVIDENCE_FIELDS = {
    "abuseipdb.confidence_score",
    "abuseipdb.total_reports",
    "cves_count",
    "hostnames_count",
    "open_ports",
    "open_ports_count",
    "services_count",
    "virustotal.harmless",
    "virustotal.malicious",
    "virustotal.suspicious",
    "virustotal.undetected",
}
_FLOAT_EVIDENCE_FIELDS = {"virustotal.detection_ratio"}
_BOOL_EVIDENCE_FIELDS = {"abuseipdb.is_whitelisted"}


def _normalize_fact_value(field: str, value: Any) -> Any:
    """Coerce known numeric/bool evidence fields before validation."""
    try:
        if field in _INT_EVIDENCE_FIELDS:
            return int(value)
        if field in _FLOAT_EVIDENCE_FIELDS:
            return float(value)
        if field in _BOOL_EVIDENCE_FIELDS:
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered == "true":
                    return True
                if lowered == "false":
                    return False
                raise ValueError(f"Expected boolean string, got {value!r}")
            return bool(value)
        return value
    except (TypeError, ValueError) as exc:
        raise AgentLookupError(
            "ReportAgent",
            "LLM",
            f"Invalid evidence value for field '{field}': {value!r}",
        ) from exc


def _fact_key(fact: EvidenceFact | dict[str, Any]) -> tuple[str, str]:
    """Return a stable comparable key for one structured evidence fact."""
    if isinstance(fact, EvidenceFact):
        field = fact.field
        value = fact.value
    else:
        field = str(fact["field"])
        value = fact["value"]
    value = _normalize_fact_value(field, value)
    return field, json.dumps(value, sort_keys=True, separators=(",", ":"))


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    """Extract a JSON object from raw LLM text, including fenced responses."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = json.loads(_first_balanced_json_object(text))

    if not isinstance(parsed, dict):
        raise AgentLookupError(
            "ReportAgent", "LLM", "LLM response JSON must be an object"
        )
    return parsed


def _first_balanced_json_object(text: str) -> str:
    """Return the first balanced JSON object substring from mixed LLM text."""
    start = text.find("{")
    if start == -1:
        raise AgentLookupError("ReportAgent", "LLM", "No JSON object found")

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    raise AgentLookupError("ReportAgent", "LLM", "Unbalanced JSON object")


class ReportAgent(BaseAgent):
    """LLM-powered threat report generator.

    Consumes :class:`AgentResult` outputs from the three data-gathering agents
    and calls a configured LLM provider to produce a final :class:`ThreatReport`.

    Attributes:
        name:    ``"ReportAgent"``
        timeout: Per-agent deadline in seconds (default 30 s — LLM calls
                 are slower than network lookups).
    """

    name: str = "ReportAgent"
    timeout: float = 30.0

    def __init__(
        self,
        timeout: float = 30.0,
        recon: AgentResult | None = None,
        reputation: AgentResult | None = None,
        shodan: AgentResult | None = None,
        llm_adapter: ReportLLMAdapter | None = None,
    ) -> None:
        self.timeout = timeout
        self._recon = recon
        self._reputation = reputation
        self._shodan = shodan
        self._llm_adapter = llm_adapter or build_report_llm_adapter(timeout)

    def _agent_result_for_prompt(
        self, result: AgentResult | None, agent_name: str
    ) -> dict[str, Any]:
        """Normalize one upstream AgentResult for prompt input."""
        if result is None:
            return {
                "agent_name": agent_name,
                "status": AgentStatus.FAILED.value,
                "error": "AgentResult was not provided to ReportAgent.",
                "data": None,
            }

        if result.agent_name != agent_name:
            raise AgentLookupError(
                self.name,
                "InputValidation",
                f"Expected {agent_name}, got {result.agent_name}",
            )

        return {
            "agent_name": result.agent_name,
            "status": result.status.value,
            "error": result.error,
            "data": _pydantic_to_plain(result.data),
        }

    def _combined_agent_results_for_prompt(self) -> dict[str, Any]:
        """Build the source-of-truth JSON object sent to the LLM."""
        return {
            "ReconAgent": self._agent_result_for_prompt(
                self._recon, "ReconAgent"
            ),
            "ReputationAgent": self._agent_result_for_prompt(
                self._reputation, "ReputationAgent"
            ),
            "ShodanAgent": self._agent_result_for_prompt(
                self._shodan, "ShodanAgent"
            ),
        }

    def _allowed_evidence_for_prompt(self) -> dict[str, list[dict[str, Any]]]:
        """Build structured evidence facts the LLM is allowed to cite."""
        return {
            "recon": [
                fact.model_dump(mode="json") for fact in self._recon_evidence()
            ],
            "reputation": [
                fact.model_dump(mode="json")
                for fact in self._reputation_evidence()
            ],
            "shodan": [
                fact.model_dump(mode="json") for fact in self._shodan_evidence()
            ],
        }

    def _recon_evidence(self) -> list[EvidenceFact]:
        """Extract allowed evidence facts from ReconAgent data."""
        if self._recon is None or self._recon.status in (
            AgentStatus.FAILED,
            AgentStatus.TIMEOUT,
        ):
            return []

        include_defaults = self._recon.status == AgentStatus.SUCCESS
        data = _pydantic_to_plain(self._recon.data) or {}
        facts: list[EvidenceFact] = []
        _append_fact(
            facts,
            "ip",
            data.get("ip"),
            include_default_values=include_defaults,
        )

        # TODO: Replace error-text markers with structured sub-source statuses
        # on ReconResult/ReputationResult in a future milestone. While an agent
        # is PARTIAL, we suppress zero/default/false values unless the whole
        # agent succeeded. This may omit legitimate confirmed-clean zero scores,
        # but avoids presenting a failed sub-lookup's default model as evidence.
        if not _agent_error_mentions(self._recon, "WHOIS:"):
            whois = data.get("whois") or {}
            _append_fact(
                facts,
                "whois.registrar",
                whois.get("registrar"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "whois.org",
                whois.get("org"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "whois.country",
                whois.get("country"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "whois.description",
                whois.get("description"),
                include_default_values=include_defaults,
            )

        if not _agent_error_mentions(self._recon, "DNS:"):
            dns = data.get("dns") or {}
            _append_fact(
                facts,
                "dns.hostname",
                dns.get("hostname"),
                include_default_values=include_defaults,
            )
            for alias in dns.get("aliases") or []:
                _append_fact(
                    facts,
                    "dns.aliases",
                    alias,
                    include_default_values=include_defaults,
                )
            for address in dns.get("addresses") or []:
                _append_fact(
                    facts,
                    "dns.addresses",
                    address,
                    include_default_values=include_defaults,
                )

        if not _agent_error_mentions(self._recon, "ASN:"):
            asn = data.get("asn") or {}
            _append_fact(
                facts,
                "asn.asn",
                asn.get("asn"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "asn.asn_name",
                asn.get("asn_name"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "asn.asn_cidr",
                asn.get("asn_cidr"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "asn.asn_country",
                asn.get("asn_country"),
                include_default_values=include_defaults,
            )

        if not _agent_error_mentions(self._recon, "GeoIP:"):
            geo = data.get("geo") or {}
            _append_fact(
                facts,
                "geo.country",
                geo.get("country"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "geo.region",
                geo.get("region"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "geo.city",
                geo.get("city"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "geo.isp",
                geo.get("isp"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "geo.org",
                geo.get("org"),
                include_default_values=include_defaults,
            )
        return facts

    def _reputation_evidence(self) -> list[EvidenceFact]:
        """Extract allowed evidence facts from ReputationAgent data."""
        if (
            self._reputation is None
            or self._reputation.status
            in (AgentStatus.FAILED, AgentStatus.TIMEOUT)
        ):
            return []

        include_defaults = self._reputation.status == AgentStatus.SUCCESS
        data = _pydantic_to_plain(self._reputation.data) or {}
        facts: list[EvidenceFact] = []
        _append_fact(
            facts,
            "ip",
            data.get("ip"),
            include_default_values=include_defaults,
        )

        if not _agent_error_mentions(self._reputation, "AbuseIPDB:"):
            abuseipdb = data.get("abuseipdb") or {}
            _append_fact(
                facts,
                "abuseipdb.confidence_score",
                abuseipdb.get("confidence_score"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "abuseipdb.total_reports",
                abuseipdb.get("total_reports"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "abuseipdb.usage_type",
                abuseipdb.get("usage_type"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "abuseipdb.isp",
                abuseipdb.get("isp"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "abuseipdb.is_whitelisted",
                abuseipdb.get("is_whitelisted"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "abuseipdb.domain",
                abuseipdb.get("domain"),
                include_default_values=include_defaults,
            )

        if not _agent_error_mentions(self._reputation, "VirusTotal:"):
            virustotal = data.get("virustotal") or {}
            _append_fact(
                facts,
                "virustotal.malicious",
                virustotal.get("malicious"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "virustotal.suspicious",
                virustotal.get("suspicious"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "virustotal.harmless",
                virustotal.get("harmless"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "virustotal.undetected",
                virustotal.get("undetected"),
                include_default_values=include_defaults,
            )
            _append_fact(
                facts,
                "virustotal.detection_ratio",
                virustotal.get("detection_ratio"),
                include_default_values=include_defaults,
            )
        return facts

    def _shodan_evidence(self) -> list[EvidenceFact]:
        """Extract allowed evidence facts from ShodanAgent data."""
        if self._shodan is None or self._shodan.status in (
            AgentStatus.FAILED,
            AgentStatus.TIMEOUT,
        ):
            return []

        include_defaults = self._shodan.status == AgentStatus.SUCCESS
        data = _pydantic_to_plain(self._shodan.data) or {}
        facts: list[EvidenceFact] = []
        _append_fact(
            facts,
            "ip",
            data.get("ip"),
            include_default_values=include_defaults,
        )
        if include_defaults:
            _append_fact(
                facts,
                "open_ports_count",
                len(data.get("open_ports") or []),
                include_default_values=True,
            )
            _append_fact(
                facts,
                "cves_count",
                len(data.get("cves") or []),
                include_default_values=True,
            )
            _append_fact(
                facts,
                "hostnames_count",
                len(data.get("hostnames") or []),
                include_default_values=True,
            )
            _append_fact(
                facts,
                "services_count",
                len(data.get("services") or []),
                include_default_values=True,
            )
        for port in data.get("open_ports") or []:
            _append_fact(
                facts,
                "open_ports",
                port,
                include_default_values=include_defaults,
            )
        for cve in data.get("cves") or []:
            _append_fact(
                facts,
                "cves",
                cve,
                include_default_values=include_defaults,
            )
        _append_fact(
            facts,
            "os",
            data.get("os"),
            include_default_values=include_defaults,
        )
        for hostname in data.get("hostnames") or []:
            _append_fact(
                facts,
                "hostnames",
                hostname,
                include_default_values=include_defaults,
            )
        for service in data.get("services") or []:
            if isinstance(service, dict):
                service_summary = {
                    key: service.get(key)
                    for key in ("port", "transport", "product", "version", "title")
                    if service.get(key) is not None
                }
                _append_fact(
                    facts,
                    "services",
                    service_summary,
                    include_default_values=include_defaults,
                )
        return facts

    def _build_user_prompt(self, target: str) -> str:
        """Build the exact user prompt for the configured LLM provider."""
        agent_results_json = json.dumps(
            self._combined_agent_results_for_prompt(),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        allowed_evidence_json = json.dumps(
            self._allowed_evidence_for_prompt(),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return REPORT_USER_PROMPT_TEMPLATE.format(
            target=target,
            agent_results_json=agent_results_json,
            allowed_evidence_json=allowed_evidence_json,
        )

    def _parse_llm_response(self, raw_text: str) -> ReportLLMResponse:
        """Parse and validate the JSON response returned by the LLM."""
        try:
            return ReportLLMResponse.model_validate(
                _extract_json_object(raw_text)
            )
        except ValidationError as exc:
            raise AgentLookupError(
                self.name, "LLM", f"Response schema validation failed: {exc}"
            ) from exc

    def _validate_evidence(self, response: ReportLLMResponse) -> None:
        """Reject evidence claims that were not present in allowed input facts."""
        allowed = self._allowed_evidence_for_prompt()
        actual = response.evidence.model_dump()
        for source_name, items in actual.items():
            allowed_items = {
                _fact_key(fact) for fact in allowed[source_name]
            }
            unsupported = [
                item for item in items if _fact_key(item) not in allowed_items
            ]
            if unsupported:
                raise AgentLookupError(
                    self.name,
                    "LLM",
                    (
                        f"Unsupported {source_name} evidence: "
                        + json.dumps(unsupported, default=str)
                    ),
                )

    async def execute(self, target: str) -> AgentResult:
        """Generate a ThreatReport via the configured LLM provider.

        Args:
            target: IP address or domain under investigation.

        Returns:
            AgentResult wrapping a :class:`ThreatReport`.
        """
        if not online_enrichment_enabled():
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.FAILED,
                error=(
                    "Online enrichment is disabled. Set "
                    "SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT=true to enable external lookups."
                ),
            )

        log.info(
            "report_start",
            target=target,
            provider=self._llm_adapter.provider_name,
            model=self._llm_adapter.model,
        )

        try:
            user_prompt = self._build_user_prompt(target)
            raw_response = await self._llm_adapter.complete(
                REPORT_SYSTEM_PROMPT, user_prompt
            )
            llm_response = self._parse_llm_response(raw_response)
            self._validate_evidence(llm_response)

            report = ThreatReport(
                target=target,
                severity=llm_response.severity,
                summary=llm_response.summary,
                recommendations=llm_response.recommendations,
                recon=self._recon.data if self._recon else None,
                reputation=self._reputation.data if self._reputation else None,
                shodan=self._shodan.data if self._shodan else None,
                llm_model=self._llm_adapter.model,
            )

            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.SUCCESS,
                data=report,
            )
        except AgentLookupError as exc:
            log.warning("report_lookup_failed", target=target, error=str(exc))
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.FAILED,
                data=None,
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            log.error(
                "report_unexpected_error",
                target=target,
                error=str(exc),
                exc_info=True,
            )
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.FAILED,
                data=None,
                error=str(exc),
            )
