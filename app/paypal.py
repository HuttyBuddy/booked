"""PayPal sandbox deposit flow for Booked.

Reads PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET from the environment.
If either is missing, the module runs in DEMO mode: create_deposit_order()
returns a clearly-marked fake approval URL so the rest of the app (chat,
dashboard, booking records) can be exercised without credentials.
"""
import base64
import os

import httpx

SANDBOX = "https://api-m.sandbox.paypal.com"


def configured() -> bool:
    return bool(os.environ.get("PAYPAL_CLIENT_ID") and os.environ.get("PAYPAL_CLIENT_SECRET"))


async def _access_token(client: httpx.AsyncClient) -> str:
    cid = os.environ["PAYPAL_CLIENT_ID"]
    secret = os.environ["PAYPAL_CLIENT_SECRET"]
    basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    r = await client.post(
        f"{SANDBOX}/v1/oauth2/token",
        headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
        content="grant_type=client_credentials",
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


async def create_deposit_order(amount_usd: str, description: str, return_url: str, cancel_url: str) -> dict:
    """Create a PayPal order for the deposit. Returns {order_id, approval_url, demo}."""
    if not configured():
        return {
            "order_id": "DEMO-ORDER-1",
            "approval_url": f"{return_url}?token=DEMO-ORDER-1&demo=1",
            "demo": True,
        }
    async with httpx.AsyncClient() as client:
        token = await _access_token(client)
        r = await client.post(
            f"{SANDBOX}/v2/checkout/orders",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "intent": "CAPTURE",
                "purchase_units": [{
                    "amount": {"currency_code": "USD", "value": amount_usd},
                    "description": description,
                }],
                "application_context": {
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                    "user_action": "PAY_NOW",
                },
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    approval = next(l["href"] for l in data["links"] if l["rel"] == "approve")
    return {"order_id": data["id"], "approval_url": approval, "demo": False}


async def capture_order(order_id: str) -> dict:
    """Capture an approved order. Returns {captured, order_id, demo}."""
    if order_id == "DEMO-ORDER-1" or not configured():
        return {"captured": True, "order_id": order_id, "demo": True}
    async with httpx.AsyncClient() as client:
        token = await _access_token(client)
        r = await client.post(
            f"{SANDBOX}/v2/checkout/orders/{order_id}/capture",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    return {"captured": data.get("status") == "COMPLETED", "order_id": order_id, "demo": False}
