from __future__ import annotations

import argparse
import sys
import urllib.request
import webbrowser
from pathlib import Path


def bootstrap_src(root: Path) -> None:
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def main() -> None:
    parser = argparse.ArgumentParser(description="Export LangGraph visual bundle + interactive viewer")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="Project root of _GraphChat")
    parser.add_argument("--out", default="docs/graphs", help="Output dir relative to root")
    parser.add_argument("--data-dir", default="data", help="Runtime data dir relative to root")
    parser.add_argument("--default-graph", default="agent", help="Default graph id shown in viewer")
    parser.add_argument("--no-open", action="store_true", help="Do not auto-open viewer in browser")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    bootstrap_src(root)

    from graphchat import GraphChatRuntime
    from graphchat.application.graphs.graph_metadata import GRAPH_METADATA
    from graphchat.application.graphs.subgraphs.board_subgraph import BoardDeps, build_board_subgraph
    from graphchat.application.graphs.subgraphs.governance_subgraph import build_governance_subgraph
    from graphchat.application.graphs.subgraphs.retrieval_subgraph import RetrievalDeps, build_retrieval_subgraph
    from graphchat.application.graphs.subgraphs.silent_loop_subgraph import build_silent_loop_subgraph
    from graphchat.interfaces.ui.graph_bundle import (
        build_graph_bundle,
        build_graph_entry,
        write_bundle_html,
        write_graph_bundle,
    )

    runtime = GraphChatRuntime(base_dir=root / args.data_dir)

    sub_silent = build_silent_loop_subgraph()
    sub_retrieval = build_retrieval_subgraph(
        RetrievalDeps(tag_index=runtime.tag_index, vector_index=runtime.vector_index)
    )
    sub_board = build_board_subgraph(BoardDeps(board_store=runtime.board_store))
    sub_governance = build_governance_subgraph()

    entries = [
        build_graph_entry("world", runtime.world_graph, GRAPH_METADATA.get("world")),
        build_graph_entry("agent", runtime.agent_graph, GRAPH_METADATA.get("agent")),
        build_graph_entry("silent_loop_subgraph", sub_silent, GRAPH_METADATA.get("silent_loop_subgraph")),
        build_graph_entry("retrieval_subgraph", sub_retrieval, GRAPH_METADATA.get("retrieval_subgraph")),
        build_graph_entry("board_subgraph", sub_board, GRAPH_METADATA.get("board_subgraph")),
        build_graph_entry("governance_subgraph", sub_governance, GRAPH_METADATA.get("governance_subgraph")),
    ]

    out_dir = root / args.out
    vendor_dir = out_dir / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)

    vendor_mermaid = vendor_dir / "mermaid.esm.min.mjs"
    if not vendor_mermaid.exists():
        try:
            urllib.request.urlretrieve(
                "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs",
                vendor_mermaid,
            )
            print(f"vendor: {vendor_mermaid}")
        except Exception as e:  # pragma: no cover
            print(f"vendor_download_failed: {e}")

    bundle = build_graph_bundle(entries, root_graph_id=args.default_graph)
    bundle_path = write_graph_bundle(bundle, out_dir)
    html_path = write_bundle_html(bundle, out_dir)

    print(f"bundle: {bundle_path}")
    print(f"viewer: {html_path}")
    if not args.no_open:
        try:
            webbrowser.open(html_path.resolve().as_uri(), new=2)
            print("browser_opened: file viewer opened (if blank, use serve_graph_viewer.py)")
        except Exception as e:  # pragma: no cover
            print(f"browser_open_failed: {e}")


if __name__ == "__main__":
    main()
