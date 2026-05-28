import json
import logging
import os
import asyncio
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from pydantic import BaseModel

# 1. Force load the .env file so the Hub can read EXPECTED_DESKTOP_API_KEY
load_dotenv()

logger = logging.getLogger(__name__)
router = APIRouter()

# registry of connected desktop spokes
connected_spokes: dict[str, WebSocket] = {}
_ws_device_map: dict[WebSocket, str] = {}

@router.websocket("/desktop")
async def desktop_websocket(websocket: WebSocket):
    # 2. ALWAYS accept the connection first to prevent ASGI handshake timeouts
    await websocket.accept()

    # 3. Authentication Phase
    client_api_key = websocket.headers.get("Authorization")
    device_id = websocket.headers.get("X-Device-ID")
    expected_key = f"Bearer {os.getenv('EXPECTED_DESKTOP_API_KEY')}"
    

    # Verify the API key
    if client_api_key != expected_key or not device_id:
        logger.warning(f"Rejected WebSocket connection: Invalid API Key or missing Device ID.")
        # Gracefully close the established connection with a Policy Violation
        await websocket.close(code=1008)  
        return

    # 4. Registration
    connected_spokes[device_id] = websocket
    _ws_device_map[websocket] = device_id
    logger.info(f"Desktop spoke connected: {device_id}")

    try:
        # listen for messages from the spoke
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "command_result":
                request_id = data.get("request_id")
                logger.info(f"Command result from {device_id}: exit_code={data.get('exit_code')}")
                
                # Resolve the pending future so send_command_to_spoke can return
                if request_id:
                    resolve_result(request_id, data)

            elif msg_type == "heartbeat":
                # Acknowledge the heartbeat so the spoke knows we are alive
                await websocket.send_json({"type": "heartbeat_ack"})

            elif msg_type == "index_complete":
                logger.info(f"Indexing complete from {device_id}: {data.get('indexed')} files indexed")

    except WebSocketDisconnect:
        logger.info(f"Desktop spoke disconnected: {device_id}")
    except Exception as e:
        logger.exception(f"WebSocket error for {device_id}: {e}")
    finally:
        # Cleanup when the connection drops
        if device_id and device_id in connected_spokes:
            del connected_spokes[device_id]
        if websocket in _ws_device_map:
            del _ws_device_map[websocket]


async def send_command_to_spoke(
    device_id: str,
    command: str,
    working_dir: str = None,
    timeout_s: int = 30,
    require_confirm: bool = False,
) -> dict:
    websocket = connected_spokes.get(device_id)
    if not websocket:
        return {
            "status": "offline",
            "message": f"Desktop spoke '{device_id}' is not connected."
        }

    import uuid
    from hub.auth.hmac_signer import sign_payload

    request_id = str(uuid.uuid4())
    payload = {
        "type": "exec_request",
        "request_id": request_id,
        "command": command,
        "working_dir": working_dir,
        "timeout_s": timeout_s,
        "require_confirm": require_confirm,
    }
    payload = sign_payload(payload)

    # 3. FIXED: Register the future *before* firing the message over the network
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    _pending_results[request_id] = future

    await websocket.send_json(payload)

    # wait for result with timeout
    try:
        result = await asyncio.wait_for(future, timeout=timeout_s + 5)
        return result
    except asyncio.TimeoutError:
        return {
            "status": "timeout",
            "message": "Desktop spoke did not respond in time"
        }
    finally:
        # Always clean up the registry to prevent memory leaks
        _pending_results.pop(request_id, None)

# pending results registry
_pending_results: dict[str, asyncio.Future] = {}

async def wait_for_result(request_id: str):
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    _pending_results[request_id] = future
    try:
        return await future
    finally:
        _pending_results.pop(request_id, None)

def resolve_result(request_id: str, result: dict):
    future = _pending_results.get(request_id)
    if future and not future.done():
        future.set_result(result)


class TestCommandRequest(BaseModel):
    command: str
    device_id: str = "windows_laptop_001"

@router.post("/test-desktop-command")
async def test_desktop_command(req: TestCommandRequest):
    # This calls the function we wrote earlier!
    result = await send_command_to_spoke(
        device_id=req.device_id,
        command=req.command,
        timeout_s=10
    )
    return result