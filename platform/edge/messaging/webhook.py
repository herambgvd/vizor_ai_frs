"""Outbound webhooks — POST a JSON payload to a customer-supplied URL.

Some integrations want events pushed to their own endpoint instead of email/push.
``send_webhook`` does a plain JSON POST, and — if a shared ``secret`` is given —
signs the exact bytes it sends with HMAC-SHA256 in an ``X-Signature`` header so the
receiver can verify the request really came from us (and wasn't tampered with).

As with the other channels, all network work is wrapped so a dead endpoint never
propagates into the caller.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx

from ..core.logging import get_logger

log = get_logger("edge.messaging.webhook")


async def send_webhook(url: str, payload: dict, secret: str | None = None) -> bool:
    """POST ``payload`` as JSON to ``url``; optionally HMAC-sign the body.

    When ``secret`` is set we sign the RAW serialized body (the same bytes we send)
    and attach ``X-Signature: sha256=<hex>`` so the receiver can recompute + compare.
    Returns True on a 2xx response, False otherwise.
    """
    if not url:
        log.warning("send_webhook called with no url; skipping")
        return False

    # Serialize once so the signature covers exactly the bytes we transmit.
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    headers = {"Content-Type": "application/json"}
    if secret:
        signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        headers["X-Signature"] = f"sha256={signature}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, content=raw, headers=headers)
        resp.raise_for_status()
        log.info("webhook delivered to %s (%d)", url, resp.status_code)
        return True
    except Exception:  # never let a webhook failure break the caller
        log.exception("failed to deliver webhook to %s", url)
        return False
