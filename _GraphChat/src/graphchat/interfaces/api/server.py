from __future__ import annotations

from contextlib import asynccontextmanager
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse

from graphchat import GraphChatRuntime
from graphchat.interfaces.api.app import GraphChatAPI
from graphchat.interfaces.api.schemas import (
    DirectChatRequest,
    MessageRequest,
    ResolveApprovalRequest,
    WorldCommandsRequest,
)
from graphchat.interfaces.api.settings import APISettings

LOGGER = logging.getLogger("graphchat.api")
CONSOLE_HTML = Path(__file__).resolve().parents[1] / "ui" / "internal_console.html"


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "req_unknown"))


def _error_payload(
    request: Request,
    *,
    code: str,
    message: str,
    detail: object | None = None,
) -> dict:
    payload: dict = {
        "error": {
            "code": code,
            "message": message,
            "request_id": _request_id(request),
        }
    }
    if detail is not None:
        payload["error"]["detail"] = detail
    return payload


def _sse(event: str, data: dict) -> str:
    body = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {body}\n\n"


def configure_logging(settings: APISettings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    log_dir = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "graphchat_api.log"
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    root.addHandler(stream_handler)
    root.addHandler(file_handler)
    LOGGER.info("logging configured: level=%s file=%s", settings.log_level, log_file)


def get_settings(request: Request) -> APISettings:
    return request.app.state.settings


def get_api(request: Request) -> GraphChatAPI:
    api: GraphChatAPI | None = getattr(request.app.state, "api", None)
    if api is None:
        raise HTTPException(status_code=503, detail="runtime_not_ready")
    return api


def require_api_token(request: Request, settings: APISettings = Depends(get_settings)) -> None:
    expected = settings.api_token.strip()
    if not expected:
        return
    auth_header = request.headers.get("authorization", "").strip()
    token = ""
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.headers.get("x-api-token", "").strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


def create_app(
    *,
    settings: APISettings | None = None,
    runtime: GraphChatRuntime | None = None,
) -> FastAPI:
    cfg = settings or APISettings.from_env()

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI):
        if fastapi_app.state.runtime is None:
            fastapi_app.state.runtime = GraphChatRuntime(
                base_dir=cfg.data_dir,
                checkpointer_backend=cfg.checkpointer_backend,
            )
        fastapi_app.state.api = GraphChatAPI(fastapi_app.state.runtime)
        try:
            yield
        finally:
            if fastapi_app.state.runtime_owner and fastapi_app.state.runtime is not None:
                fastapi_app.state.runtime.close()
            fastapi_app.state.api = None
            if fastapi_app.state.runtime_owner:
                fastapi_app.state.runtime = None

    app = FastAPI(title="GraphChat Internal API", version="0.1.0", lifespan=lifespan)

    app.state.settings = cfg
    app.state.runtime = runtime
    app.state.runtime_owner = runtime is None
    app.state.api = GraphChatAPI(runtime) if runtime is not None else None

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id") or f"req_{uuid4().hex[:12]}"
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        response.headers["x-request-id"] = _request_id(request)
        LOGGER.info(
            "%s %s -> %s (%.2fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=400,
            content=_error_payload(request, code="bad_request", message=str(exc)),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                request,
                code="validation_error",
                message="invalid request payload",
                detail=exc.errors(),
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        message = str(exc.detail) if exc.detail else "http_error"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(request, code="http_error", message=message),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        LOGGER.exception("unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content=_error_payload(request, code="internal_error", message="internal server error"),
        )

    @app.get("/healthz")
    def healthz(request: Request) -> dict:
        return {
            "status": "ok",
            "service": "graphchat-api",
            "request_id": _request_id(request),
        }

    @app.get("/readyz")
    def readyz(request: Request) -> dict:
        ready = app.state.runtime is not None and app.state.api is not None
        if not ready:
            raise HTTPException(status_code=503, detail="runtime_not_ready")
        return {"status": "ready", "request_id": _request_id(request)}

    @app.get("/")
    def index() -> RedirectResponse:
        return RedirectResponse(url="/internal-console", status_code=307)

    @app.get("/internal-console")
    def internal_console() -> FileResponse:
        if not CONSOLE_HTML.exists():
            raise HTTPException(status_code=404, detail="internal_console_not_found")
        return FileResponse(CONSOLE_HTML, media_type="text/html")

    router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_token)])

    @router.post("/sessions/{session_id}/messages")
    def post_message(
        session_id: str,
        body: MessageRequest,
        api: GraphChatAPI = Depends(get_api),
    ) -> dict:
        events = api.post_message(
            session_id=session_id,
            text=body.text,
            world_scope=body.world_scope,
            actor_id=body.actor_id,
        )
        return {"session_id": session_id, "events": events}

    @router.get("/sessions/{session_id}/stream")
    def stream_message(
        session_id: str,
        request: Request,
        text: str = Query(min_length=1),
        world_scope: str = Query(default="group:main"),
        actor_id: str = Query(default="user"),
        api: GraphChatAPI = Depends(get_api),
    ) -> StreamingResponse:
        def event_stream():
            yield _sse("meta", {"session_id": session_id, "request_id": _request_id(request)})
            for item in api.stream_message(
                session_id=session_id,
                text=text,
                world_scope=world_scope,
                actor_id=actor_id,
            ):
                event = str(item.get("type", "message"))
                yield _sse(event, item)
            yield _sse("done", {"session_id": session_id})

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/sessions/{session_id}/world-commands")
    def post_world_commands(
        session_id: str,
        body: WorldCommandsRequest,
        api: GraphChatAPI = Depends(get_api),
    ) -> dict:
        commands = list(body.commands)
        if body.command is not None:
            commands.insert(0, body.command)
        if not commands:
            raise ValueError("world-commands requires `command` or `commands`")
        return api.post_world_commands(
            session_id=session_id,
            commands=commands,
            created_by=body.created_by,
            world_running=body.world_running,
            max_world_ticks_per_run=body.max_world_ticks_per_run,
        )

    @router.get("/approvals")
    def list_approvals(
        session_id: str | None = None,
        status: str | None = "pending",
        api: GraphChatAPI = Depends(get_api),
    ) -> dict:
        items = api.list_approvals(session_id=session_id, status=status)
        return {"count": len(items), "items": items}

    @router.post("/approvals/{request_id}/resolve")
    def resolve_approval(
        request_id: str,
        body: ResolveApprovalRequest,
        api: GraphChatAPI = Depends(get_api),
    ) -> dict:
        return api.resolve_approval(
            request_id=request_id,
            decision=body.decision,
            reviewer=body.reviewer,
            note=body.note,
        )

    @router.post("/sessions/{session_id}/direct-chat")
    def direct_chat(
        session_id: str,
        body: DirectChatRequest,
        api: GraphChatAPI = Depends(get_api),
    ) -> dict:
        event = api.direct_chat(
            session_id=session_id,
            agent_id=body.agent_id,
            text=body.text,
            scope=body.scope,
            actor_id=body.actor_id,
        )
        if event is None:
            raise HTTPException(status_code=404, detail="agent_not_found_or_disabled")
        return {"session_id": session_id, "event": event}

    @router.get("/sessions/{session_id}/observability")
    def get_observability(
        session_id: str,
        api: GraphChatAPI = Depends(get_api),
    ) -> dict:
        return api.get_observability(session_id=session_id)

    @router.get("/sessions/{session_id}/events")
    def list_session_events(
        session_id: str,
        limit: int = Query(default=120, ge=1, le=1000),
        api: GraphChatAPI = Depends(get_api),
    ) -> dict:
        items = api.list_session_events(session_id=session_id, limit=limit)
        return {"session_id": session_id, "count": len(items), "events": items}

    app.include_router(router)
    return app


def main() -> None:
    settings = APISettings.from_env()
    configure_logging(settings)
    app = create_app(settings=settings)
    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("uvicorn is required to run GraphChat API server") from exc
    uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level)


if __name__ == "__main__":
    main()
