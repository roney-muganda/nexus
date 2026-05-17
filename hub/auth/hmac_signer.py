import hmac
import hashlib
import json
import time
from fastapi import HTTPException, status
from hub.config import settings


def sign_payload(payload: dict) -> str:
    payload["timestamp"] = int(time.time())
    message = json.dumps(payload, sort_keys=True).encode()
    signature = hmac.new(
        settings.hmac_secret.encode(),
        message,
        hashlib.sha256
    ).hexdigest()
    return signature


def verify_signature(payload: dict, signature: str, max_age_seconds: int = 30) -> bool:
    timestamp = payload.get("timestamp", 0)
    age = int(time.time()) - timestamp
    if age > max_age_seconds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Payload signature expired"
        )
    expected = sign_payload(payload.copy())
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid payload signature"
        )
    return True