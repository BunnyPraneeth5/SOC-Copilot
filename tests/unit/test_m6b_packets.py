"""Milestone 6b step 5: packet animation along edges into running stages."""

import pytest
from PyQt6.QtCore import QPointF, QSettings
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from soc_copilot.phase4.controller.schemas import StageEvent
from soc_copilot.phase4.ui import pipeline_graph as graph_mod
from soc_copilot.phase4.ui.investigation_graph import INVESTIGATION_GRAPH
from soc_copilot.phase4.ui.pipeline_graph import PipelineGraphWidget
from soc_copilot.phase4.ui.theme import ThemeManager
from tests.qt_helpers import destroy


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def tm(qapp, tmp_path):
    manager = ThemeManager.instance()
    manager.load_preferences(QSettings(str(tmp_path / "t.ini"), QSettings.Format.IniFormat))
    yield manager
    manager._reduce_motion = False


@pytest.fixture()
def motion(monkeypatch):
    """Offscreen disables motion; force it on, keep Reduce motion live."""
    monkeypatch.setattr(
        graph_mod, "motion_enabled",
        lambda w=None: not ThemeManager.instance().reduce_motion and (w is None or w.isVisible()),
    )


def ev(stage, status, run="r1"):
    return StageEvent(batch_id=run, stage=stage, status=status)


def _graph(spec=None):
    widget = PipelineGraphWidget(spec=spec) if spec else PipelineGraphWidget()
    widget.resize(900, 200)
    widget.show()
    return widget


def _on_edge(packet):
    """Packet centre lies on its edge's path (within 1.5 scene px)."""
    best = min(
        (packet.edge.point_at(i / 400) - packet.pos()).manhattanLength() for i in range(401)
    )
    return best < 1.5


class TestWithMotion:
    def test_packet_on_edge_into_running_stage(self, tm, motion):
        g = _graph()
        g.apply_event(ev("ingest", "done"))
        g.apply_event(ev("text_detect", "active"))
        packets = g.visible_packets()
        assert len(packets) == 1 and g.packets_running
        assert packets[0].edge is next(e for s, d, e in g.edges if (s, d) == ("ingest", "text_detect"))
        assert _on_edge(packets[0])
        destroy(g)

    def test_packet_moves(self, tm, motion):
        g = _graph()
        g.apply_event(ev("ingest", "done"))
        g.apply_event(ev("flow_route", "active"))
        first = QPointF(g.visible_packets()[0].pos())
        QTest.qWait(200)
        g._tick_packets()
        assert g.visible_packets()[0].pos() != first
        assert _on_edge(g.visible_packets()[0])
        destroy(g)

    def test_parallel_agents_get_staggered_packets(self, tm, motion):
        g = _graph(INVESTIGATION_GRAPH)
        g.apply_event(ev("lookup", "done"))
        for agent in ("recon", "reputation", "shodan"):
            g.apply_event(ev(agent, "active"))
        packets = g.visible_packets()
        assert len(packets) == 3
        assert {p.edge for p in packets} == {e for s, d, e in g.edges if s == "lookup"}
        assert len({(round(p.pos().x()), round(p.pos().y())) for p in packets}) == 3
        destroy(g)

    def test_at_most_four_packets(self, tm, motion):
        from soc_copilot.phase4.ui.pipeline_graph import GraphSpec, StageSpec
        stages = tuple(StageSpec(k, k, "zap") for k in "abcdefg")
        spec = GraphSpec("Fan", stages, tuple(("a", k) for k in "bcdefg"),
                         {f"l{i}": i * 50 for i in range(6)},
                         {"a": (0, "l0"), **{k: (1, f"l{i}") for i, k in enumerate("bcdefg")}})
        g = _graph(spec)
        g.apply_event(ev("a", "done"))
        for k in "bcdefg":
            g.apply_event(ev(k, "active"))
        assert len(g.visible_packets()) == PipelineGraphWidget.MAX_PACKETS
        destroy(g)

    def test_stops_when_nothing_flows(self, tm, motion):
        g = _graph()
        g.apply_event(ev("ingest", "done"))
        g.apply_event(ev("text_detect", "active"))
        g.apply_event(ev("text_detect", "done"))
        assert g.visible_packets() == [] and not g.packets_running
        destroy(g)

    def test_skipped_target_has_no_packet(self, tm, motion):
        g = _graph()
        g.apply_event(ev("flow_route", "done"))
        g.apply_event(ev("preprocess", "skipped"))
        assert g.visible_packets() == []
        destroy(g)

    def test_pauses_when_hidden_and_resumes(self, tm, motion):
        g = _graph()
        g.apply_event(ev("ingest", "done"))
        g.apply_event(ev("text_detect", "active"))
        g.hide()
        assert not g.packets_running and g.visible_packets() == []
        g.show()
        assert g.packets_running and len(g.visible_packets()) == 1
        destroy(g)

    def test_reduce_motion_stops_running_animation(self, tm, motion):
        g = _graph()
        g.apply_event(ev("ingest", "done"))
        g.apply_event(ev("text_detect", "active"))
        tm.set_reduce_motion(True)  # no signal; next frame notices
        QTest.qWait(80)
        assert not g.packets_running and g.visible_packets() == []
        destroy(g)

    def test_collapsed_group_still_animates(self, tm, motion):
        g = _graph()
        g.set_ml_collapsed(True)
        g.apply_event(ev("flow_route", "done"))
        g.apply_event(ev("preprocess", "active"))
        packets = g.visible_packets()
        assert len(packets) == 1 and packets[0].edge.dst is g.ml_node
        destroy(g)

    def test_destroy_while_running_is_safe(self, tm, motion):
        g = _graph()
        g.apply_event(ev("ingest", "done"))
        g.apply_event(ev("text_detect", "active"))
        destroy(g)
        QTest.qWait(100)


def test_no_packets_without_motion(tm):
    """Offscreen / Reduce motion: the real motion_enabled is false."""
    g = _graph()
    g.apply_event(ev("ingest", "done"))
    g.apply_event(ev("text_detect", "active"))
    assert g.visible_packets() == [] and not g.packets_running
    destroy(g)
