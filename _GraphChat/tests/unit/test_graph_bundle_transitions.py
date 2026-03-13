from __future__ import annotations

from graphchat import GraphChatRuntime
from graphchat.application.graphs.graph_metadata import GRAPH_METADATA
from graphchat.interfaces.ui.graph_bundle import build_graph_bundle, build_graph_entry, write_bundle_html


def test_graph_bundle_should_include_transition_metadata(tmp_path) -> None:
    runtime = GraphChatRuntime(base_dir=tmp_path / "data", checkpointer_backend="memory")
    entry = build_graph_entry("world", runtime.world_graph, GRAPH_METADATA.get("world"))
    agent_entry = build_graph_entry("agent", runtime.agent_graph, GRAPH_METADATA.get("agent"))
    runtime.close()

    assert entry.transitions
    assert any(item.get("type") == "send" for item in entry.transitions)
    assert any(item.get("type") == "loop" for item in entry.transitions)
    assert all("rendered" in item for item in entry.transitions)
    assert any(
        item.get("source") == "action_parallel_subgraph" and item.get("target") == "skill_execution_subgraph"
        for item in agent_entry.transitions
    )


def test_graph_bundle_html_should_include_language_switch(tmp_path) -> None:
    runtime = GraphChatRuntime(base_dir=tmp_path / "data", checkpointer_backend="memory")
    try:
        world_entry = build_graph_entry("world", runtime.world_graph, GRAPH_METADATA.get("world"))
        agent_entry = build_graph_entry("agent", runtime.agent_graph, GRAPH_METADATA.get("agent"))
        bundle = build_graph_bundle([world_entry, agent_entry], root_graph_id="agent")
        html_path = write_bundle_html(bundle, tmp_path / "graphs")
        html = html_path.read_text(encoding="utf-8")
    finally:
        runtime.close()

    assert "<title>Graph 可视化</title>" in html
    assert "id=\"langSelect\"" in html
    assert "graph_viewer_lang" in html
