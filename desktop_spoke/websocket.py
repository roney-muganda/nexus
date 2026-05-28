import asyncio
import json
import logging
import websockets
from datetime import datetime

from desktop_spoke.config import HUB_WS_URL, DEVICE_ID, API_KEY
from desktop_spoke.executor import execute_command, verify_hmac
from desktop_spoke.notifier import show_notification

logger = logging.getLogger("nexus-desktop")
RECONNECT_DELAY = 5

async def handle_message(websocket, message: dict):
    """Processes incoming JSON commands from the Hub."""
    msg_type = message.get("type")

    if msg_type == "exec_request":
        request_id = message.get("request_id")
        command = message.get("command", "")
        working_dir = message.get("working_dir")
        timeout_s = message.get("timeout_s", 30)
        require_confirm = message.get("require_confirm", False)
        signature = message.get("signature", "")

        # verify HMAC signature
        if not verify_hmac(message, signature):
            logger.warning(f"Invalid HMAC signature for request {request_id}")
            await websocket.send(json.dumps({
                "type": "command_result",
                "request_id": request_id,
                "status": "rejected",
                "reason": "Invalid signature",
                "exit_code": -1,
            }))
            return

        # confirmation gate for destructive commands
        if require_confirm:
            show_notification("NEXUS", f"Command requires confirmation: {command[:60]}")
            logger.info(f"Command requires confirmation: {command}")

        # execute the command safely
        result = execute_command(
            command=command,
            working_dir=working_dir,
            timeout_s=timeout_s,
        )
        result["type"] = "command_result"
        result["request_id"] = request_id

        await websocket.send(json.dumps(result))
        logger.info(f"Command executed: '{command}' → exit_code={result.get('exit_code')}")

        if result.get("status") == "success":
            show_notification("NEXUS — Complete", f"{command[:50]}\nExit: {result.get('exit_code')}")

    elif msg_type == "notification":
        show_notification(message.get("title", "NEXUS"), message.get("body", ""))

    elif msg_type == "heartbeat":
        await websocket.send(json.dumps({"type": "heartbeat_ack"}))


async def connect_to_hub():
    """Maintains the persistent WebSocket connection with auto-reconnect."""
    logger.info(f"NEXUS Desktop Agent starting — Device: {DEVICE_ID}")
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "X-Device-ID": DEVICE_ID
    }

    while True:
        try:
            async with websockets.connect(
                "ws://127.0.0.1:8000/ws/desktop",
                additional_headers=headers,
                ping_interval=30,
                ping_timeout=10,
            ) as websocket:
                
                logger.info("✓ Connected to NEXUS Hub")
                show_notification("NEXUS Agent", "Connected to Hub")

                # Heartbeat background task
                async def send_heartbeat():
                    while True:
                        await asyncio.sleep(30)
                        try:
                            await websocket.send(json.dumps({
                                "type": "heartbeat",
                                "device_id": DEVICE_ID,
                                "timestamp": datetime.utcnow().isoformat()
                            }))
                        except Exception:
                            break

                heartbeat_task = asyncio.create_task(send_heartbeat())

                try:
                    async for raw_message in websocket:
                        try:
                            message = json.loads(raw_message)
                            await handle_message(websocket, message)
                        except json.JSONDecodeError:
                            logger.warning("Invalid JSON received.")
                        except Exception as e:
                            logger.exception(f"Error handling message: {e}")
                finally:
                    heartbeat_task.cancel()

        except websockets.exceptions.InvalidStatus as e:
            logger.error(f"Hub rejected connection: HTTP {e.response.status_code}. Verify API_KEY.")
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"Connection closed: {e}. Reconnecting...")
        except ConnectionRefusedError:
            logger.warning(f"Hub offline at {HUB_WS_URL}. Retrying...")
        except Exception as e:
            logger.exception(f"Unexpected error: {e}. Retrying...")

        await asyncio.sleep(RECONNECT_DELAY)