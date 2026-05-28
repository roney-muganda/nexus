import subprocess
import os
import logging
import hmac
import hashlib
import json
import time
from desktop_spoke.allowlist import is_command_allowed, get_blocked_reason
from desktop_spoke.config import HMAC_SECRET

logger = logging.getLogger(__name__)


def verify_hmac(payload: dict, received_signature: str) -> bool:
    payload_without_sig = {k: v for k, v in payload.items() if k != "signature"}
    message = json.dumps(payload_without_sig, sort_keys=True).encode()
    expected = hmac.new(
        HMAC_SECRET.encode(),
        message,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received_signature)


def execute_command(
    command: str,
    working_dir: str = None,
    timeout_s: int = 30,
) -> dict:
    if not is_command_allowed(command):
        reason = get_blocked_reason(command)
        logger.warning(f"Blocked command: {command}")
        return {
            "status": "blocked",
            "command": command,
            "reason": reason,
            "stdout": "",
            "stderr": reason,
            "exit_code": -1,
        }

    # resolve working directory
    cwd = None
    if working_dir:
        cwd = os.path.expandvars(os.path.expanduser(working_dir))
        if not os.path.exists(cwd):
            return {
                "status": "error",
                "command": command,
                "reason": f"Working directory not found: {cwd}",
                "stdout": "",
                "stderr": f"Directory not found: {cwd}",
                "exit_code": -1,
            }

    logger.info(f"Executing: {command} (cwd={cwd})")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=cwd,
        )
        return {
            "status": "success",
            "command": command,
            "stdout": result.stdout[-3000:] if result.stdout else "",
            "stderr": result.stderr[-1000:] if result.stderr else "",
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "command": command,
            "stdout": "",
            "stderr": f"Command timed out after {timeout_s}s",
            "exit_code": -1,
        }
    except Exception as e:
        logger.exception(f"Command execution failed: {e}")
        return {
            "status": "error",
            "command": command,
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
        }