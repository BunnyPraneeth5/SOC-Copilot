"""Batch A tests: log-format detection, brute-force aggregation, flow routing,
killswitch CLI, cp1252-safe status output."""

from __future__ import annotations

import io
import sys
from unittest.mock import Mock

import pytest

from soc_copilot.phase4.controller.app_controller import (
    AppController,
    BRUTE_FORCE_WINDOW_SECONDS,
)


@pytest.fixture
def controller() -> AppController:
    """Controller with no flow feature order → no flow routing to a mock pipeline."""
    c = AppController("unused")
    c._pipeline = Mock()
    c._text_log_classifier = None
    # Empty feature set → no text line is ever routed to the ML pipeline.
    c._flow_feature_names = set()
    return c


# ---------------------------------------------------------------------------
# _parse_raw_log
# ---------------------------------------------------------------------------

class TestParseRawLog:
    def test_sshd_failed_password(self, controller):
        e = controller._parse_raw_log(
            "Jan 18 02:56:01 server sshd[123]: Failed password for root "
            "from 45.67.89.101 port 22 ssh2"
        )
        assert e["event_type"] == "LoginAttempt"
        assert e["login_failed"] is True
        assert e["user"] == "root"
        assert e["src_ip"] == "45.67.89.101"
        # syslog timestamp parsed with current year
        assert e["timestamp"].startswith(f"{__import__('datetime').datetime.now().year}-01-18T02:56:01")

    def test_sshd_failed_invalid_user(self, controller):
        e = controller._parse_raw_log(
            "Jan 18 02:56:01 server sshd[123]: Failed password for invalid "
            "user admin from 45.67.89.101 port 22 ssh2"
        )
        assert e["event_type"] == "LoginAttempt"
        assert e["login_failed"] is True
        assert e["user"] == "admin"
        assert e["src_ip"] == "45.67.89.101"

    def test_invalid_user_line(self, controller):
        e = controller._parse_raw_log(
            "Jan 18 02:56:01 server sshd[123]: Invalid user bob from 45.67.89.101"
        )
        assert e["event_type"] == "LoginAttempt"
        assert e["login_failed"] is True
        assert e["user"] == "bob"
        assert e["src_ip"] == "45.67.89.101"

    def test_pam_authentication_failure(self, controller):
        e = controller._parse_raw_log(
            "Jan 18 02:56:01 server sshd[123]: pam_unix(sshd:auth): "
            "authentication failure; logname= uid=0 euid=0 tty=ssh "
            "ruser= rhost=45.67.89.101 user=carol"
        )
        assert e["event_type"] == "LoginAttempt"
        assert e["login_failed"] is True
        assert e["src_ip"] == "45.67.89.101"
        assert e["user"] == "carol"

    def test_sshd_accepted(self, controller):
        e = controller._parse_raw_log(
            "Jan 18 02:56:01 server sshd[123]: Accepted password for alice "
            "from 10.0.0.5 port 51234 ssh2"
        )
        assert e["event_type"] == "UserLogin"
        assert e["login_failed"] is False
        assert e["user"] == "alice"
        assert e["src_ip"] == "10.0.0.5"

    def test_windows_4625_failed_logon(self, controller):
        e = controller._parse_raw_log(
            "2026-01-18 02:56:01|EventID=4625|Level=Information|Message="
            "An account failed to log on. Subject: Security ID: S-1-0-0 "
            "Account Name: - Account Domain: - Logon Type: 3 "
            "Account For Which Logon Failed: Account Name: admin "
            "Failure Reason: Unknown user name or bad password. "
            "Source Network Address: 45.67.89.101"
        )
        assert e["event_type"] == "LoginAttempt"
        assert e["login_failed"] is True
        assert e["src_ip"] == "45.67.89.101"
        # last Account Name is the target account, not the subject "-"
        assert e["user"] == "admin"
        assert e["timestamp"] == "2026-01-18T02:56:01Z"

    def test_windows_4732_admin_group(self, controller):
        e = controller._parse_raw_log(
            "2026-01-18 02:56:01|EventID=4732|Level=Information|Message="
            "A member was added to a security-enabled local group. "
            "Subject: Account Name: SYSTEM "
            "Member: Security ID: S-1-5-21-x Account Name: bob "
            "Group: Security ID: S-1-5-32 Group Name: Administrators."
        )
        assert e["event_type"] == "PrivilegeEscalation"
        assert e["user"] == "bob"
        assert e["new_role"] == "admin"

    def test_custom_format_login_failed(self, controller):
        e = controller._parse_raw_log(
            "2026-01-18 02:56:01 LoginAttempt user=admin ip=45.67.89.101 "
            "success=false attempts=23"
        )
        assert e["event_type"] == "LoginAttempt"
        assert e["login_failed"] is True
        assert e["login_attempts"] == 23
        assert e["src_ip"] == "45.67.89.101"


# ---------------------------------------------------------------------------
# Cross-line brute-force aggregation
# ---------------------------------------------------------------------------

def _sshd_fail(ip: str, user: str = "root") -> dict:
    return {
        "raw_line": (
            f"Jan 18 02:56:01 server sshd[123]: Failed password for {user} "
            f"from {ip} port 22 ssh2"
        )
    }


class TestBruteForceAggregation:
    def test_five_failed_lines_external_alert(self, controller):
        result = controller.process_batch(
            [_sshd_fail("45.67.89.101") for _ in range(5)]
        )
        agg = [a for a in result.alerts if a.alert_id.startswith("RULE-BFAGG-")]
        assert len(agg) == 1
        assert agg[0].classification == "BruteForce"
        assert agg[0].priority == "P0-Critical"
        assert agg[0].source_ip == "45.67.89.101"
        assert result.stats.classification_distribution["BruteForce"] == 1

    def test_four_lines_no_alert(self, controller):
        result = controller.process_batch(
            [_sshd_fail("45.67.89.101") for _ in range(4)]
        )
        assert not [
            a for a in result.alerts if a.alert_id.startswith("RULE-BFAGG-")
        ]

    def test_no_duplicate_within_cooldown(self, controller):
        controller.process_batch(
            [_sshd_fail("45.67.89.101") for _ in range(5)]
        )
        result = controller.process_batch([_sshd_fail("45.67.89.101")])
        assert not [
            a for a in result.alerts if a.alert_id.startswith("RULE-BFAGG-")
        ]

    def test_new_alert_after_window(self, controller):
        t = [1000.0]
        controller._clock = lambda: t[0]
        controller.process_batch(
            [_sshd_fail("45.67.89.101") for _ in range(5)]
        )
        t[0] += BRUTE_FORCE_WINDOW_SECONDS + 1
        result = controller.process_batch(
            [_sshd_fail("45.67.89.101") for _ in range(5)]
        )
        agg = [a for a in result.alerts if a.alert_id.startswith("RULE-BFAGG-")]
        assert len(agg) == 1

    def test_internal_ip_lower_priority(self, controller):
        result = controller.process_batch(
            [_sshd_fail("192.168.1.50") for _ in range(5)]
        )
        agg = [a for a in result.alerts if a.alert_id.startswith("RULE-BFAGG-")]
        assert len(agg) == 1
        assert agg[0].priority == "P1-High"

    def test_single_failed_logins_skip_text_classifier(self, controller):
        """Per-line failed logins go to aggregation, not the text ML."""
        stub = Mock()
        stub.classify.return_value = (
            "Suspicious",
            0.9,
            {"Suspicious": 0.9, "Benign": 0.1},
        )
        controller._text_log_classifier = stub

        result = controller.process_batch(
            [_sshd_fail("45.67.89.101") for _ in range(6)]
        )

        assert len(result.alerts) == 1
        assert result.alerts[0].alert_id.startswith("RULE-BFAGG-")
        assert result.alerts[0].classification == "BruteForce"
        stub.classify.assert_not_called()

    def test_custom_high_attempt_line_reaches_classifier(self, controller):
        """Lines with attempts >= threshold still go through text ML."""
        stub = Mock()
        stub.classify.return_value = (
            "BruteForce",
            0.95,
            {"BruteForce": 0.95, "Benign": 0.05},
        )
        controller._text_log_classifier = stub

        result = controller.process_batch([{
            "raw_line": (
                "2026-01-18 02:56:01 LoginAttempt user=admin "
                "ip=45.67.89.101 success=false attempts=23"
            )
        }])

        assert stub.classify.call_count == 1
        assert any(
            a.classification == "BruteForce" for a in result.alerts
        )


# ---------------------------------------------------------------------------
# Flow routing
# ---------------------------------------------------------------------------

class TestFlowRouting:
    def test_flow_record_detected(self, controller):
        controller._flow_feature_names = {
            "destination_port", "flow_duration", "total_fwd_packets",
            "total_backward_packets", "flow_bytes_s", "flow_packets_s",
            "fwd_packet_length_mean", "bwd_packet_length_mean",
            "flow_iat_mean", "flow_iat_std",
        }
        entry = {
            "Destination Port": 80,
            "Flow Duration": 1200,
            " Total Fwd Packets": 10,
            " Total Backward Packets": 8,
            "Flow Bytes/s": 500.0,
            "Flow Packets/s": 2.5,
            "Fwd Packet Length Mean": 300.0,
            "Bwd Packet Length Mean": 250.0,
            "Flow IAT Mean": 100.0,
            "Flow IAT Std": 10.0,
        }
        assert controller._is_flow_record(entry) is True

    def test_text_line_not_flow(self, controller):
        controller._flow_feature_names = {
            "destination_port", "flow_duration", "total_fwd_packets",
        }
        entry = controller._parse_raw_log(
            "Jan 18 02:56:01 server sshd[123]: Failed password for root "
            "from 45.67.89.101 port 22 ssh2"
        )
        assert controller._is_flow_record(entry) is False

    def test_text_only_batch_never_calls_pipeline(self, controller):
        controller._flow_feature_names = {"destination_port", "flow_duration"}
        result = controller.process_batch([_sshd_fail("45.67.89.101")])
        assert controller._pipeline.analyze_file.call_count == 0
        assert result.stats.total_records == 1
        assert controller._non_flow_records == 1
        assert controller._flow_records_routed == 0

    def test_get_stats_counters(self, controller):
        stats = controller.get_stats()
        assert stats["flow_records_routed"] == 0
        assert stats["non_flow_records"] == 0


# ---------------------------------------------------------------------------
# killswitch CLI
# ---------------------------------------------------------------------------

class TestKillswitchCli:
    def test_on_status_off_roundtrip(self, tmp_path, monkeypatch, capsys):
        import soc_copilot.phase4.kill_switch as ks_mod
        from soc_copilot import cli

        real_cls = ks_mod.KillSwitch
        monkeypatch.setattr(
            ks_mod, "KillSwitch", lambda *a, **k: real_cls(tmp_path)
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["cli", "killswitch", "on"])

        assert cli.main() == 0
        assert (tmp_path / ".kill").exists()
        assert "Emergency analysis stop: ACTIVE" in capsys.readouterr().out

        monkeypatch.setattr(sys, "argv", ["cli", "killswitch", "status"])
        assert cli.main() == 0
        assert "Emergency analysis stop: ACTIVE" in capsys.readouterr().out

        monkeypatch.setattr(sys, "argv", ["cli", "killswitch", "off"])
        assert cli.main() == 0
        assert not (tmp_path / ".kill").exists()
        assert "Emergency analysis stop: inactive" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# cp1252-safe status output
# ---------------------------------------------------------------------------

def test_status_safe_on_cp1252(monkeypatch):
    from soc_copilot import cli

    fake_out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    fake_err = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", fake_out)
    monkeypatch.setattr(sys, "stderr", fake_err)
    monkeypatch.setattr(sys, "argv", ["cli", "status"])

    cli.main()  # must not raise UnicodeEncodeError
    fake_out.flush()
    fake_err.flush()
