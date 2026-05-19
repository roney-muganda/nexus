import hmac
import hashlib
import json
import time
from fastapi import HTTPException, status
from hub.config import settings


def _compute_signature(payload: dict) -> str:
    message = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(
        settings.hmac_secret.encode(),
        message,
        hashlib.sha256
    ).hexdigest()


def sign_payload(payload: dict) -> dict:
    payload["timestamp"] = int(time.time())
    payload["signature"] = _compute_signature(payload)
    return payload


def verify_signature(payload: dict, max_age_seconds: int = 30) -> bool:
    timestamp = payload.get("timestamp", 0)
    age = int(time.time()) - timestamp
    if age > max_age_seconds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Payload signature expired"
        )
    received_signature = payload.get("signature", "")
    payload_without_sig = {k: v for k, v in payload.items() if k != "signature"}
    expected = _compute_signature(payload_without_sig)
    if not hmac.compare_digest(expected, received_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid payload signature"
        )
    return True