"""Tests for Milestone 6a: PipelineGraphWidget (static statuses, ML group)."""

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from soc_copilot.phase4.controller.schemas import PIPELINE_STAGES, StageEvent
from soc_copilot.phase4.ui.pipeline_graph import (
    ML_STAGES,
    STAGES,
    EdgeItem,
    PipelineGraphWidget,
    aggregate_status,
)
from soc_copilot.phase4.ui.theme import ThemeManager
from tests.qt_helpers import destroy


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def tm(qapp, tmp_path):
    manager = ThemeManager.instance()
    manager.load_preferences(
        QSettings(str(tmp_path / "t.ini"), QSettings.Format.IniFormat)
    )
    yield manager
    manager.set_theme("dark")


@pytest.fixture()
def graph(tm):
    widget = PipelineGraphWidget()
    widget.resize(1000, 200)
    yield widget
    destroy(widget)


def ev(stage, status, detail="", batch="b1"):
    return StageEvent(batch_id=batch, stage=stage, status=status, detail=detail)


def _edge(graph, src, dst) -> EdgeItem:
    return next(e for s, d, e in graph.edges if (s, d) == (src, dst))


class TestStructure:
    def test_one_node_per_controller_stage(self, graph):
        assert [s.key for s in STAGES] == list(PIPELINE_STAGES)
        assert set(graph.nodes) == set(PIPELINE_STAGES)

    def test_starts_idle_and_expanded(self, graph):
        assert all(graph.status(s) == "idle" for s in PIPELINE_STAGES)
        assert graph.batch_id is None
        assert not graph.ml_collapsed
        assert graph.group_frame.isVisible()
        assert not graph.ml_node.isVisible()

    def test_never_scrolls(self, graph):
        from PyQt6.QtCore import Qt
        off = Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        assert graph.horizontalScrollBarPolicy() == off
        assert graph.verticalScrollBarPolicy() == off


class TestEvents:
    def test_apply_event_sets_status_and_tooltip(self, graph):
        graph.apply_event(ev("flow_route", "done", "120 flow records, 0 other"))
        node = graph.nodes["flow_route"]
        assert graph.status("flow_route") == "done"
        assert graph.detail("flow_route") == "120 flow records, 0 other"
        assert "Routing: Done" in node.toolTip()
        assert "120 flow records" in node.toolTip()
        assert graph.batch_id == "b1"

    def test_new_batch_resets_previous_run(self, graph):
        graph.apply_event(ev("store", "done", batch="b1"))
        graph.apply_event(ev("ingest", "active", batch="b2"))
        assert graph.status("store") == "idle"
        assert graph.status("ingest") == "active"
        assert graph.batch_id == "b2"

    def test_unknown_stage_or_status_ignored(self, graph):
        graph.apply_event(ev("nope", "done"))
        graph.apply_event(ev("ingest", "exploded"))
        graph.apply_event(object())
        assert all(graph.status(s) == "idle" for s in PIPELINE_STAGES)
        assert graph.batch_id is None

    def test_reset(self, graph):
        graph.apply_event(ev("ingest", "done"))
        graph.reset()
        assert graph.status("ingest") == "idle"
        assert graph.batch_id is None

    def test_accessible_description_tracks_status(self, graph):
        graph.apply_event(ev("ingest", "blocked", "Kill switch active"))
        assert "Ingest blocked" in graph.accessibleDescription()
        assert "Store idle" in graph.accessibleDescription()


class TestEdges:
    def test_running_edge_is_accent(self, graph):
        graph.apply_event(ev("ingest", "done"))
        graph.apply_event(ev("flow_route", "active"))
        assert _edge(graph, "ingest", "flow_route").style()[0] == "accent"

    def test_finished_edge_is_success(self, graph):
        graph.apply_event(ev("alerts", "done"))
        graph.apply_event(ev("store", "done"))
        assert _edge(graph, "alerts", "store").style()[0] == "success"

    def test_skipped_edge_is_dashed(self, graph):
        graph.apply_event(ev("flow_route", "done"))
        graph.apply_event(ev("preprocess", "skipped"))
        assert _edge(graph, "flow_route", "preprocess").style()[2] is True

    def test_idle_edge_is_neutral(self, graph):
        assert _edge(graph, "ingest", "text_detect").style() == ("border", 1.0, False)


class TestAggregateStatus:
    @pytest.mark.parametrize("statuses,expected", [
        (["idle", "idle", "idle"], "idle"),
        (["done", "done", "done"], "done"),
        (["done", "skipped", "skipped"], "done"),
        (["skipped", "skipped", "skipped"], "skipped"),
        (["done", "active", "idle"], "active"),
        (["done", "idle", "idle"], "active"),  # between sub-stages
        (["done", "failed", "skipped"], "failed"),
        (["active", "failed", "idle"], "failed"),
    ])
    def test_cases(self, statuses, expected):
        assert aggregate_status(statuses) == expected


class TestMlGroup:
    def test_collapse_hides_ml_stages_and_internal_edges(self, graph):
        received = []
        graph.mlCollapsedChanged.connect(received.append)
        graph.set_ml_collapsed(True)

        assert graph.ml_collapsed and received == [True]
        assert graph.ml_node.isVisible()
        assert not graph.group_frame.isVisible()
        assert not any(graph.nodes[s].isVisible() for s in ML_STAGES)
        assert not _edge(graph, "preprocess", "features").isVisible()
        into = _edge(graph, "flow_route", "preprocess")
        out = _edge(graph, "detect", "alerts")
        assert into.isVisible() and into.dst is graph.ml_node
        assert out.isVisible() and out.src is graph.ml_node

    def test_set_same_value_does_not_emit(self, graph):
        received = []
        graph.mlCollapsedChanged.connect(received.append)
        graph.set_ml_collapsed(False)
        assert received == []

    def test_clicks_toggle(self, graph):
        graph.group_frame._on_click()
        assert graph.ml_collapsed
        graph.ml_node._on_click()
        assert not graph.ml_collapsed
        assert all(graph.nodes[s].isVisible() for s in ML_STAGES)

    def test_collapsed_node_shows_current_sub_stage(self, graph):
        graph.set_ml_collapsed(True)
        graph.apply_event(ev("preprocess", "done", "120 of 120 records kept"))
        graph.apply_event(ev("features", "active"))
        assert graph.status("ml") == "active"
        assert graph.ml_node.status_text() == "Running · Features"
        assert "Preprocess: Done (120 of 120 records kept)" in graph.detail("ml")

    def test_collapsed_node_never_hides_failure(self, graph):
        graph.set_ml_collapsed(True)
        graph.apply_event(ev("preprocess", "done"))
        graph.apply_event(ev("features", "failed", "boom"))
        graph.apply_event(ev("detect", "skipped"))
        assert graph.status("ml") == "failed"
        assert graph.ml_node.status_text() == "Failed · Features"

    def test_collapsed_layout_is_narrower(self, graph):
        wide = graph.scene().sceneRect().width()
        graph.set_ml_collapsed(True)
        assert graph.scene().sceneRect().width() < wide

    def test_starts_collapsed_when_asked(self, tm):
        widget = PipelineGraphWidget(ml_collapsed=True)
        assert widget.ml_node.isVisible()
        destroy(widget)


class TestRendering:
    @pytest.mark.parametrize("theme", ["dark", "light"])
    def test_paints_every_status(self, tm, graph, theme):
        tm.set_theme(theme)
        for stage, status in zip(
            PIPELINE_STAGES,
            ["done", "done", "done", "done", "done", "failed", "skipped",
             "active", "blocked"],
        ):
            graph.apply_event(ev(stage, status))
        graph.show()
        assert not graph.grab().isNull()
        graph.set_ml_collapsed(True)
        assert not graph.grab().isNull()

    def test_theme_change_after_destroy_is_safe(self, tm):
        widget = PipelineGraphWidget()
        destroy(widget)
        tm.set_theme("light")
        tm.set_theme("dark")

    def test_height_for_scene_follows_width(self, graph):
        assert graph.heightForScene(600) < graph.heightForScene(1000)
