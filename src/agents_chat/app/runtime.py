from __future__ import annotations

from .bootstrap import RuntimeConfig, build_runtime


def run_session(cfg: RuntimeConfig):
    runtime = build_runtime(cfg)
    runtime.engine.run()
    if getattr(runtime.controller, "memory", None):
        runtime.controller.memory.wait_for_maintenance()
        runtime.controller.memory.shutdown()
    if runtime.ui_server:
        runtime.ui_server.shutdown()
        runtime.ui_server.server_close()
    return runtime

