"""Pure formatting helpers for investigation reports (UX-4).

No Qt imports — produces plain text / Markdown consumable by the
ReportDrawer widget and by clipboard/file export.
"""

from __future__ import annotations

from datetime import datetime


def _severity_value(report) -> str:
    sev = getattr(report, "severity", None)
    return getattr(sev, "value", sev) or "UNKNOWN"


def report_mode(report) -> str:
    """Classify a ThreatReport: 'AI report' | 'Partial' | 'Local-only'."""
    if getattr(report, "llm_model", None):
        return "AI report"
    if any(
        getattr(report, attr, None) is not None
        for attr in ("recon", "reputation", "shodan")
    ):
        return "Partial"
    return "Local-only"


def _fmt_generated(generated_at) -> str:
    if generated_at is None:
        return "Unknown"
    if isinstance(generated_at, datetime):
        return generated_at.strftime("%Y-%m-%d %H:%M:%S")
    return str(generated_at)


def report_to_markdown(report) -> str:
    """Render a ThreatReport as Markdown, skipping absent data."""
    if report is None:
        return "# Threat Report\n\nNo report was returned.\n"

    lines = [
        f"# Threat Report: {getattr(report, 'target', 'Unknown')}",
        "",
        f"**Severity:** {_severity_value(report)}",
        f"**Mode:** {report_mode(report)}",
        f"**Generated:** {_fmt_generated(getattr(report, 'generated_at', None))}",
    ]
    model = getattr(report, "llm_model", None)
    if model:
        lines.append(f"**Model:** {model}")
    lines.append("")

    lines.extend([
        "## Summary",
        "",
        getattr(report, "summary", "") or "No summary provided.",
        "",
    ])

    recommendations = getattr(report, "recommendations", None) or []
    if recommendations:
        lines.extend(["## Recommendations", ""])
        lines.extend(f"- {item}" for item in recommendations)
        lines.append("")

    recon = getattr(report, "recon", None)
    if recon is not None:
        block = _md_lines(_recon_fields(recon))
        if block:
            lines.extend(["## Recon", ""])
            lines.extend(block)
            lines.append("")

    reputation = getattr(report, "reputation", None)
    if reputation is not None:
        block = _md_lines(_reputation_fields(reputation))
        if block:
            lines.extend(["## Reputation", ""])
            lines.extend(block)
            lines.append("")

    shodan = getattr(report, "shodan", None)
    if shodan is not None:
        block = _md_lines(_shodan_fields(shodan))
        if block:
            lines.extend(["## Exposure (Shodan)", ""])
            lines.extend(block)
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _clean_fields(candidates) -> list[tuple[str, str]]:
    """Drop None/empty values; join list values. Returns (label, str) pairs."""
    out = []
    for label, value in candidates:
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(v) for v in value)
        out.append((label, str(value)))
    return out


def _md_lines(fields) -> list[str]:
    return [f"- **{label}:** {value}" for label, value in fields]


def _recon_fields(recon) -> list[tuple[str, str]]:
    whois = getattr(recon, "whois", None)
    dns = getattr(recon, "dns", None)
    asn = getattr(recon, "asn", None)
    geo = getattr(recon, "geo", None)

    return _clean_fields([
        ("WHOIS org", getattr(whois, "org", None)),
        ("WHOIS registrar", getattr(whois, "registrar", None)),
        ("WHOIS country", getattr(whois, "country", None)),
        ("Reverse DNS", getattr(dns, "hostname", None)),
        ("ASN", getattr(asn, "asn", None)),
        ("ASN name", getattr(asn, "asn_name", None)),
        ("ASN CIDR", getattr(asn, "asn_cidr", None)),
        ("ASN country", getattr(asn, "asn_country", None)),
        ("Geo city", getattr(geo, "city", None)),
        ("Geo region", getattr(geo, "region", None)),
        ("Geo country", getattr(geo, "country", None)),
        ("ISP", getattr(geo, "isp", None)),
    ])


def _reputation_fields(reputation) -> list[tuple[str, str]]:
    abuse = getattr(reputation, "abuseipdb", None)
    vt = getattr(reputation, "virustotal", None)

    fields = _clean_fields([
        ("AbuseIPDB confidence", getattr(abuse, "confidence_score", None)),
        ("AbuseIPDB total reports", getattr(abuse, "total_reports", None)),
        ("AbuseIPDB usage type", getattr(abuse, "usage_type", None)),
        ("AbuseIPDB ISP", getattr(abuse, "isp", None)),
        ("AbuseIPDB domain", getattr(abuse, "domain", None)),
    ])
    if vt is not None:
        fields.extend(_clean_fields([
            ("VirusTotal malicious", getattr(vt, "malicious", None)),
            ("VirusTotal suspicious", getattr(vt, "suspicious", None)),
            ("VirusTotal harmless", getattr(vt, "harmless", None)),
            ("VirusTotal undetected", getattr(vt, "undetected", None)),
        ]))
        ratio = getattr(vt, "detection_ratio", None)
        if ratio is not None:
            if isinstance(ratio, float):
                ratio = f"{ratio:.0%}"
            fields.append(("VirusTotal detection ratio", str(ratio)))
    return fields


def _shodan_fields(shodan) -> list[tuple[str, str]]:
    return _clean_fields([
        ("Open ports", getattr(shodan, "open_ports", None)),
        ("OS", getattr(shodan, "os", None)),
        ("Hostnames", getattr(shodan, "hostnames", None)),
        ("CVEs", getattr(shodan, "cves", None)),
    ])


# Back-compat: older callers/tests used the *_lines names.
def _recon_lines(recon) -> list[str]:
    return _md_lines(_recon_fields(recon))


def _reputation_lines(reputation) -> list[str]:
    return _md_lines(_reputation_fields(reputation))


def _shodan_lines(shodan) -> list[str]:
    return _md_lines(_shodan_fields(shodan))
