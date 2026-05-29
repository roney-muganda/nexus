import asyncio
import json
import logging
import websockets
import ctypes
from datetime import datetime

from desktop_spoke.config import HUB_WS_URL, DEVICE_ID, API_KEY
from desktop_spoke.executor import execute_command, verify_hmac
from desktop_spoke.notifier import show_notification

logger = logging.getLogger("nexus-desktop")
RECONNECT_DELAY = 5

CLEAN_WS_URL = HUB_WS_URL.replace("HUB_WS_URL=", "").strip()

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

        # 1. FIXED: Actual blocking confirmation gate
        if require_confirm:
            logger.info(f"Command requires confirmation: {command}")
            
            def ask_user():
                # MessageBoxTimeoutW signature: (hWnd, lpText, lpCaption, uType, wLanguageId, dwMilliseconds)
                # Returns 32000 if it times out
                timeout_ms = timeout_s * 1000
                return ctypes.windll.user32.MessageBoxTimeoutW(
                    0, 
                    f"NEXUS is attempting to run a command:\n\n{command}\n\nAllow execution? (Auto-rejects in {timeout_s}s)", 
                    "NEXUS Security", 
                    4 | 32 | 262144, 
                    0, 
                    timeout_ms
                )
            
            user_response = await asyncio.to_thread(ask_user)
            
            if user_response == 32000:
                logger.warning(f"Confirmation timed out for: {command}")
                await websocket.send(json.dumps({
                    "type": "command_result",
                    "request_id": request_id,
                    "status": "timeout",
                    "reason": "User did not confirm in time",
                    "exit_code": -1,
                }))
                return
            elif user_response != 6:  # 6 is 'Yes'
                logger.warning(f"User denied execution of: {command}")
                await websocket.send(json.dumps({
                    "type": "command_result",
                    "request_id": request_id,
                    "status": "rejected",
                    "reason": "User denied execution",
                    "exit_code": -1,
                }))
                return

        # execute the command safely
        result = await asyncio.to_thread(
            execute_command,
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
            # 2. FIXED: Honor the HUB_WS_URL environment variable again
            async with websockets.connect(
                CLEAN_WS_URL,
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
                            # FIXED: Spawn a background task so long-running commands or prompts 
                            # don't block the Spoke from answering Hub heartbeats!
                            asyncio.create_task(handle_message(websocket, message))
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