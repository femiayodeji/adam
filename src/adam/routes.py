import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from adam.history import save_history, get_or_create_active_session
from adam.llm import complete
from adam.state import AppState

log = logging.getLogger("adam.routes")

router = APIRouter()
app_state = AppState()


class CommandRequest(BaseModel):
    command: str


@router.post("/api/command")
async def command(req: CommandRequest):
    log.info("REST command: %s", req.command)
    result = complete([{"role": "user", "content": req.command}])
    return result


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session = get_or_create_active_session(app_state)
    conversation_history: list[dict] = list(session.messages)
    log.info("WS connected — session %s (%d prior msgs)", session.id, len(conversation_history))

    try:
        while True:
            try:
                data = await websocket.receive_text()
                payload = json.loads(data)
                command_text = payload.get("command", "")
                log.info("WS command: %s", command_text)

                conversation_history.append({"role": "user", "content": command_text})

                await websocket.send_json({"type": "thinking", "message": "Processing..."})

                result = complete(conversation_history)

                conversation_history.append({"role": "assistant", "content": result["raw"]})
                save_history(app_state, conversation_history)

                if result["ok"]:
                    await websocket.send_json({"type": "motion", "motion": result["motion"]})
                else:
                    await websocket.send_json(
                        {"type": "error", "message": "Failed to parse motion JSON"}
                    )
            except Exception as e:
                log.error("WS error: %s", e, exc_info=True)
                try:
                    await websocket.send_json({"type": "error", "message": f"Internal error: {str(e)}"})
                except Exception:
                    # If sending error fails, break the loop
                    break
    except WebSocketDisconnect:
        log.info("WS disconnected — session %s", session.id)
