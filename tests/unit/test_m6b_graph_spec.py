"""Milestone 6b step 1: the pipeline graph widget is driven by a GraphSpec."""

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from soc_copilot.phase4.controller.schemas import PIPELINE_STAGES, StageEvent
from soc_copilot.phase4.ui.pipeline_graph import (
    ANALYSIS_GRAPH,
    EDGES,
    ML_STAGES,
    STAGES,
    GraphSpec,
    PipelineGraphWidget,
    StageSpec,
)
from soc_copilot.phase4.ui.theme import ThemeManager
from tests.qt_helpers import destroy

SMALL = GraphSpec(
    name="Small graph",
    stages=(StageSpec("a", "Alpha", "upload"), StageSpec("b", "Beta", "zap"),
            StageSpec("c", "Gamma", "database")),
    edges=(("a", "b"), ("a", "c")),
    lanes={"top": 0, "bottom": 60},
    layout={"a": (0, "top"), "b": (1, "top"), "c": (1, "bottom")},
)


@pytest.fixture()
def qapp():
    # keep a reference: an unreferenced QApplication is deleted at once
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def tm(qapp, tmp_path):
    manager = ThemeManager.instance()
    manager.load_preferences(QSettings(str(tmp_path / "t.ini"), QSettings.Format.IniFormat))
    return manager


def ev(stage, status, batch="r1"):
    return StageEvent(batch_id=batch, stage=stage, status=status)


def test_analysis_spec_is_the_default(tm):
    widget = PipelineGraphWidget()
    assert widget.spec is ANALYSIS_GRAPH
    assert [s.key for s in ANALYSIS_GRAPH.stages] == list(PIPELINE_STAGES)
    assert ANALYSIS_GRAPH.stages == STAGES and ANALYSIS_GRAPH.edges == EDGES
    assert ANALYSIS_GRAPH.group.members == ML_STAGES
    assert widget.accessibleName() == "Pipeline graph"
    assert widget.group_frame.label == "ML pipeline"
    destroy(widget)


class TestSpecWithoutGroup:
    @pytest.fixture()
    def graph(self, tm):
        widget = PipelineGraphWidget(spec=SMALL, ml_collapsed=True)
        widget.resize(400, 160)
        yield widget
        destroy(widget)

    def test_builds_nodes_and_edges_from_spec(self, graph):
        assert set(graph.nodes) == {"a", "b", "c"}
        assert [(s, d) for s, d, _ in graph.edges] == [("a", "b"), ("a", "c")]
        assert graph.accessibleName() == "Small graph"

    def test_has_no_group(self, graph):
        assert graph.ml_node is None and graph.group_frame is None
        assert not graph.ml_collapsed  # ignored without a group
        graph.set_ml_collapsed(True)
        assert not graph.ml_collapsed

    def test_layout_follows_spec(self, graph):
        assert graph.nodes["b"].pos().y() == graph.nodes["a"].pos().y()
        assert graph.nodes["c"].pos().y() > graph.nodes["b"].pos().y()
        assert graph.nodes["b"].pos().x() > graph.nodes["a"].pos().x()

    def test_events_and_description(self, graph):
        graph.apply_event(ev("a", "done"))
        graph.apply_event(ev("b", "active"))
        assert graph.status("a") == "done" and graph.status("b") == "active"
        assert "Alpha done; Beta running; Gamma idle" == graph.accessibleDescription()
        assert not graph.is_fading()

    def test_paints(self, graph):
        graph.apply_event(ev("c", "failed"))
        graph.show()
        assert not graph.grab().isNull()
