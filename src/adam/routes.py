"""WebSocket and REST routes.

WebSocket protocol (v1):
  Client → Server: { "v":1, "id":"<uuid>", "type":"command"|"ping"|"new_session"|"reset_pose", ... }
  Server → Client: { "v":1, "ref":"<id>", "type":"ack"|"thinking"|"motion"|"error"|"pong"|"session" }

Key behaviours:
  - Per-connection session (not global shared state)
  - Cancel-and-replace: new command cancels any in-flight LLM task
  - Server-side keepalive ping every 20 s
  - Motion cache checked before every LLM call
  - Exponential backoff reconnect hints surfaced via error codes
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from adam.cache import MotionCache
from adam.config import config
from adam.history import FileStore, MemoryStore, build_context
from adam.llm import complete_async, complete_streaming
from adam.models import Message, MotionPlan
from adam.state import Session

log = logging.getLogger("adam.routes")

router = APIRouter()

# ── Shared singletons ─────────────────────────────────────────────────────────
_store = (
    FileStore(config.history.history_dir)
    if config.history.persistent and config.history.history_dir
    else MemoryStore()
)
_cache = MotionCache(capacity=config.cache.capacity) if config.cache.enabled else None

log.info(
    "Store: %s  Cache: %s",
    type(_store).__name__,
    f"MotionCache(cap={config.cache.capacity})" if _cache else "disabled",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _v1(type_: str, ref: str | None = None, **kwargs) -> dict:
    msg: dict = {"v": 1, "type": type_}
    if ref:
        msg["ref"] = ref
    msg.update(kwargs)
    return msg


def _last_description(messages: list[Message]) -> str | None:
    for msg in reversed(messages):
        if msg.role == "assistant" and msg.motion_summary:
            try:
                return json.loads(msg.motion_summary).get("description")
            except Exception:
                pass
    return None


def _start_command_task(
    session: Session,
    websocket: WebSocket,
    command_text: str,
    msg_id: str,
) -> None:
    session.current_command = command_text
    session.active_task = asyncio.create_task(
        _run_command(session, websocket, command_text, msg_id)
    )
    session.active_task.add_done_callback(
        lambda _task: asyncio.create_task(_run_next_pending(session, websocket))
    )


async def _run_next_pending(session: Session, websocket: WebSocket) -> None:
    session.current_command = None
    if session.pending_command is None:
        return

    next_command = session.pending_command
    next_msg_id = session.pending_msg_id or ""
    session.pending_command = None
    session.pending_msg_id = None

    await _safe_send(websocket, _v1("thinking", next_msg_id, queued=True))
    _start_command_task(session, websocket, next_command, next_msg_id)


# ── LLM task (runs inside asyncio.Task, per command) ─────────────────────────

async def _run_command(
    session: Session,
    websocket: WebSocket,
    command_text: str,
    msg_id: str,
) -> None:
    messages = _store.load(session.id)
    last_desc = _last_description(messages)

    # Cache check
    if _cache:
        cached = _cache.get(command_text)
        if cached:
            log.info("Cache hit: %s", command_text[:60])
            _store.append(session.id, Message("user", command_text))
            _store.append(session.id, Message(
                "assistant", cached.description,
                motion_summary=cached.model_dump_json(),
            ))
            await websocket.send_json(_v1("motion", msg_id, motion=cached.model_dump()))
            return

    context = build_context(
        messages,
        config.history.max_history_tokens,
        config.history.max_history_messages,
        config.history.max_message_chars,
    )
    context.append({"role": "user", "content": command_text})

    plan: MotionPlan | None = None

    try:
        if config.llm.stream:
            async def _on_token(delta: str) -> None:
                try:
                    await websocket.send_json(_v1("token", msg_id, delta=delta))
                except Exception:
                    pass

            plan = await complete_streaming(context, _on_token, last_desc)
        else:
            plan = await complete_async(context, last_desc)

    except asyncio.CancelledError:
        log.info("LLM task cancelled (session %s)", session.id)
        return
    except Exception as exc:
        log.error("LLM error: %s", exc, exc_info=True)
        await _safe_send(websocket, _v1("error", msg_id, code="LLM_PROVIDER_ERROR", message="LLM request failed"))
        return

    if plan is None:
        await _safe_send(websocket, _v1("error", msg_id, code="LLM_PARSE_ERROR", message="Could not parse motion"))
        return

    # Persist
    _store.append(session.id, Message("user", command_text))
    _store.append(session.id, Message(
        "assistant", plan.description,
        motion_summary=plan.model_dump_json(),
    ))

    if _cache:
        _cache.put(command_text, plan)

    await _safe_send(websocket, _v1("motion", msg_id, motion=plan.model_dump()))


async def _safe_send(websocket: WebSocket, payload: dict) -> None:
    try:
        await websocket.send_json(payload)
    except Exception:
        pass


# ── Keepalive task ────────────────────────────────────────────────────────────

async def _keepalive(websocket: WebSocket) -> None:
    """Send a ping every 20 s. Runs until the connection closes."""
    try:
        while True:
            await asyncio.sleep(20)
            await websocket.send_json({"v": 1, "type": "ping"})
    except Exception:
        pass


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    session = Session()

    # Send session info + recent history to client
    prior = _store.load(session.id)
    await websocket.send_json(_v1("session", id=session.id, history=[
        {"role": m.role, "content": m.content, "ts": m.timestamp}
        for m in prior[-20:]
    ]))

    log.info("WS connected — session %s", session.id)
    keepalive_task = asyncio.create_task(_keepalive(websocket))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await _safe_send(websocket, _v1("error", code="WS_DECODE_ERROR", message="Invalid JSON frame"))
                continue

            msg_type = payload.get("type", "")
            msg_id = payload.get("id", "")

            if msg_type == "ping":
                await _safe_send(websocket, {"v": 1, "type": "pong"})
                continue

            if msg_type == "pong":
                continue

            if msg_type == "reset_pose":
                await _safe_send(websocket, _v1("ack", msg_id))
                continue

            if msg_type == "new_session":
                session = Session()
                await _safe_send(websocket, _v1("session", id=session.id, history=[]))
                continue

            if msg_type == "resume":
                resume_id = (payload.get("session_id") or "").strip()
                if resume_id:
                    if session.active_task and not session.active_task.done():
                        session.active_task.cancel()
                    session = Session(id=resume_id)
                    resumed = _store.load(session.id)
                    await _safe_send(websocket, _v1("session", id=session.id, history=[
                        {"role": m.role, "content": m.content, "ts": m.timestamp}
                        for m in resumed[-20:]
                    ]))
                continue

            if msg_type == "command":
                command_text = payload.get("command", "").strip()
                if not command_text:
                    continue

                log.info("WS command [%s]: %s", session.id[:8], command_text[:80])

                await _safe_send(websocket, _v1("ack", msg_id))

                if session.active_task and not session.active_task.done():
                    # Queue depth-1: keep only the latest pending command.
                    if command_text == session.current_command:
                        await _safe_send(websocket, _v1("queued", msg_id, message="Already processing this command"))
                        continue
                    session.pending_command = command_text
                    session.pending_msg_id = msg_id
                    await _safe_send(websocket, _v1("queued", msg_id, message="Command queued"))
                    continue

                await _safe_send(websocket, _v1("thinking", msg_id))
                _start_command_task(session, websocket, command_text, msg_id)

    except WebSocketDisconnect:
        log.info("WS disconnected — session %s", session.id)
    finally:
        keepalive_task.cancel()
        if session.active_task and not session.active_task.done():
            session.active_task.cancel()


# ── Session REST API ──────────────────────────────────────────────────────────

@router.get("/api/sessions")
async def list_sessions():
    if isinstance(_store, MemoryStore):
        return {"sessions": list(_store._store.keys())}
    if isinstance(_store, FileStore):
        files = list(_store._dir.glob("*.jsonl"))
        return {"sessions": [f.stem for f in files]}
    return {"sessions": []}


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    _store.delete(session_id)
    return {"deleted": session_id}


@router.post("/api/sessions/{session_id}/reset")
async def reset_session(session_id: str):
    _store.delete(session_id)
    return {"reset": session_id}

