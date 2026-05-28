import re
from desktop_spoke.config import ALLOWED_COMMANDS


def is_command_allowed(command: str) -> bool:
    command = command.strip()
    for pattern in ALLOWED_COMMANDS:
        if re.match(pattern, command, re.IGNORECASE):
            return True
    return False


def get_blocked_reason(command: str) -> str:
    return (
        f"Command not in allowlist: '{command}'. "
        f"Add a pattern to ALLOWED_COMMANDS in config.py to permit it."
    )