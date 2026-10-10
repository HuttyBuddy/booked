"""Booked — AI sales agent for local service businesses. Week 2: money moves."""
import os
import re

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
import httpx

from app import paypal, store

app = FastAPI(title="Booked")
store.init()

NEBIUS_BASE = "https://api.tokenfactory.nebius.com/v1"
MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"

SYSTEM_PROMPT = """You are Booked, the AI sales agent for {business_name}, a {trade} company in {area}.
Your job: turn inbound messages into booked estimates.

Playbook:
1. Greet warmly and acknowledge their problem.
2. Qualify with at most 3 short questions: what they need, urgency/timeline, and how to reach them (name + phone).
3. Once you have their name, phone number, and a time preference, do NOT ask more questions. Instead end your reply with the exact token [DEPOSIT] on its own line — the system will attach the deposit link automatically.
4. Keep every reply under 60 words. Friendly, plain-spoken, no hype, no emojis.

Services: {services}
Diagnostic/estimate fee: {fee} (this is the deposit amount: {deposit_usd})
"""


class ChatIn(BaseModel):
    message: str
    history: list[dict] = []
    business: str = "apex-hvac"
    conv_id: int | None = None


BUSINESSES = {
    "apex-hvac": {
        "business_name": "Apex Heating & Air",
        "trade": "HVAC",
        "area": "Sacramento, CA",
        "services": "AC repair and replacement, furnace tune-ups, ductwork, smart thermostats",
        "fee": "$89 diagnostic, credited toward the repair",
        "deposit_usd": "89.00",
    },
    "bluewater-pools": {
        "business_name": "Bluewater Pools",
        "trade": "pool builder",
        "area": "Sacramento, CA",
        "services": "custom pool builds, remodels, equipment upgrades, weekly service plans",
        "fee": "free on-site estimate",
        "deposit_usd": "150.00",
    },
}


async def agent_reply(system: str, history: list[dict], message: str) -> str:
    api_key = os.environ["NEBIUS_API_KEY"]
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{NEBIUS_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": MODEL,
                "messages": [{"role": "system", "content": system}]
                + history
                + [{"role": "user", "content": message}],
                "max_tokens": 1024,
            },
        )
        r.raise_for_status()
        data = r.json()
    return data["choices"][0]["message"]["content"] or "(no reply — try again)"


@app.post("/api/chat")
async def chat(inp: ChatIn, request: Request):
    b = BUSINESSES.get(inp.business, BUSINESSES["apex-hvac"])
    conv_id = inp.conv_id or store.new_conversation(inp.business)
    store.add_message(conv_id, "user", inp.message)
    system = SYSTEM_PROMPT.format(**b)
    reply = await agent_reply(system, inp.history, inp.message)

    # Closer: agent signals readiness with [DEPOSIT] -> create booking + PayPal order
    if "[DEPOSIT]" in reply:
        reply = reply.replace("[DEPOSIT]", "").strip()
        booking_id = store.new_booking(conv_id, b["deposit_usd"])
        base = str(request.base_url).rstrip("/")
        order = await paypal.create_deposit_order(
            b["deposit_usd"],
            f"{b['business_name']} estimate deposit",
            return_url=f"{base}/pay/return?booking_id={booking_id}",
            cancel_url=f"{base}/pay/cancel?booking_id={booking_id}",
        )
        store.update_booking(booking_id, paypal_order_id=order["order_id"],
                             deposit_status="awaiting_payment")
        tag = " (demo link — PayPal sandbox not connected)" if order["demo"] else ""
        reply += (f"\n\nTo lock your slot, please place the {b['fee'].split(',')[0]} deposit here: "
                  f"{order['approval_url']}{tag}")
    store.add_message(conv_id, "assistant", reply)
    return {"reply": reply, "conv_id": conv_id}


@app.get("/pay/return")
async def pay_return(booking_id: int, token: str = "", demo: str = ""):
    booking = store.get_booking(booking_id)
    order_id = booking["paypal_order_id"] if booking else token
    result = await paypal.capture_order(order_id)
    if result["captured"]:
        store.update_booking(booking_id, deposit_status="paid")
        msg = "Deposit received — your estimate is locked in. We'll see you soon!"
    else:
        store.update_booking(booking_id, deposit_status="failed")
        msg = "The payment didn't complete. Reply and we'll try again."
    return HTMLResponse(f"<body style='font-family:system-ui;padding:40px'><h2>{msg}</h2>"
                        f"<p><a href='/dashboard'>Owner dashboard</a></p></body>")


@app.get("/pay/cancel")
async def pay_cancel(booking_id: int):
    store.update_booking(booking_id, deposit_status="cancelled")
    return HTMLResponse("<body style='font-family:system-ui;padding:40px'>"
                        "<h2>Deposit cancelled — no charge made.</h2></body>")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    bookings = store.recent_bookings()
    convs = store.recent_conversations()
    rows = "".join(
        f"<tr><td>{r['id']}</td><td>{r['business']}</td><td>${r['amount_usd']}</td>"
        f"<td>{r['deposit_status']}</td><td>{r['paypal_order_id'][:18]}</td></tr>"
        for r in bookings)
    crows = "".join(
        f"<tr><td>{r['id']}</td><td>{r['business']}</td></tr>" for r in convs)
    paypal_state = "LIVE (sandbox)" if paypal.configured() else "DEMO MODE — add PayPal sandbox credentials"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Booked — owner dashboard</title>
<style>body{{font-family:system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 16px}}
table{{border-collapse:collapse;width:100%;margin-bottom:32px}}
td,th{{border:1px solid #ddd;padding:8px;text-align:left;font-size:14px}}
.badge{{display:inline-block;background:#eee;border-radius:6px;padding:2px 10px;font-size:13px}}</style>
</head><body>
<h2>Booked — owner dashboard</h2>
<p>PayPal: <span class="badge">{paypal_state}</span></p>
<h3>Bookings & deposits</h3>
<table><tr><th>#</th><th>Business</th><th>Deposit</th><th>Status</th><th>Order</th></tr>{rows or "<tr><td colspan=5>No bookings yet</td></tr>"}</table>
<h3>Conversations</h3>
<table><tr><th>#</th><th>Business</th></tr>{crows or "<tr><td colspan=2>None yet</td></tr>"}</table>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Booked — demo</title>
<style>body{font-family:system-ui,sans-serif;max-width:560px;margin:40px auto;padding:0 16px}
#log{border:1px solid #ddd;border-radius:12px;padding:16px;min-height:300px;margin-bottom:12px}
.msg{margin:8px 0;line-height:1.5;white-space:pre-wrap}.u{text-align:right;color:#0b5fff}.a{color:#111}
form{display:flex;gap:8px}input{flex:1;padding:10px;border-radius:8px;border:1px solid #ccc}
button{padding:10px 18px;border-radius:8px;border:0;background:#0b5fff;color:#fff;font-weight:700}</style>
</head><body>
<h2>Booked — homeowner chat demo</h2>
<div id="log"><div class="msg a">Hi! This is Apex Heating & Air's assistant. What can I help with?</div></div>
<form id="f"><input id="t" autocomplete="off" placeholder="e.g. My AC died, house is 90 degrees"><button>Send</button></form>
<script>
const log=document.getElementById('log'),hist=[];let convId=null;
document.getElementById('f').onsubmit=async e=>{
 e.preventDefault();const t=document.getElementById('t');const m=t.value.trim();if(!m)return;t.value='';
 log.innerHTML+=`<div class="msg u">${m}</div>`;hist.push({role:'user',content:m});
 const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({message:m,history:hist.slice(0,-1),conv_id:convId})});
 const d=await r.json();convId=d.conv_id;hist.push({role:'assistant',content:d.reply});
 log.innerHTML+=`<div class="msg a">${d.reply}</div>`;log.scrollTop=log.scrollHeight;
};
</script>
<p><a href="/dashboard">Owner dashboard</a></p>
</body></html>"""
