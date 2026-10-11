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

# PayPal Smart Buttons (client-side checkout) needs only the public client ID.
# Server-side REST (paypal.py) remains the production path when the secret is set.
def _load_env():
    try:
        with open(os.path.join(os.path.dirname(__file__), "..", ".env")) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ.setdefault(k, v)
    except FileNotFoundError:
        pass

_load_env()
PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_SANDBOX_CLIENT_ID", "")

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

    # Closer: agent signals readiness with [DEPOSIT] -> create booking + PayPal button
    if "[DEPOSIT]" in reply:
        reply = reply.replace("[DEPOSIT]", "").strip()
        booking_id = store.new_booking(conv_id, b["deposit_usd"])
        store.update_booking(booking_id, deposit_status="awaiting_payment")
        reply += (f"\n\nTo lock your slot, place the {b['fee'].split(',')[0]} deposit "
                  f"with the PayPal button below.")
        return {"reply": reply, "conv_id": conv_id,
                "deposit_button": {"booking_id": booking_id,
                                   "amount_usd": b["deposit_usd"],
                                   "description": f"{b['business_name']} estimate deposit",
                                   "paypal_client_id": PAYPAL_CLIENT_ID}}
    store.add_message(conv_id, "assistant", reply)
    return {"reply": reply, "conv_id": conv_id}


class DepositConfirmedIn(BaseModel):
    booking_id: int
    paypal_order_id: str = ""


@app.post("/api/deposit-confirmed")
async def deposit_confirmed(inp: DepositConfirmedIn):
    """Called by the browser after the PayPal Smart Button captures payment."""
    booking = store.get_booking(inp.booking_id)
    if not booking:
        return {"ok": False}
    store.update_booking(inp.booking_id, deposit_status="paid",
                         paypal_order_id=inp.paypal_order_id or booking["paypal_order_id"])
    return {"ok": True}


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
    paypal_state = "LIVE (sandbox Smart Buttons)" if PAYPAL_CLIENT_ID else "DEMO MODE — add PayPal sandbox client ID"
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
    html = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Booked — Apex Heating & Air</title>
<style>
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;max-width:560px;margin:0 auto;padding:0;background:#f4f6f8;min-height:100vh}
header{background:#0b2545;color:#fff;padding:18px 20px}
header h2{margin:0;font-size:18px}header p{margin:4px 0 0;font-size:13px;opacity:.75}
#log{padding:20px 16px;min-height:380px}
.msg{max-width:80%;margin:10px 0;padding:12px 16px;border-radius:18px;line-height:1.55;font-size:15px;white-space:pre-wrap}
.a{background:#fff;color:#111;border-bottom-left-radius:6px;box-shadow:0 1px 2px rgba(0,0,0,.08)}
.u{background:#0b5fff;color:#fff;margin-left:auto;border-bottom-right-radius:6px}
.typing{color:#888;font-style:italic;font-size:14px;padding:4px 16px}
form{display:flex;gap:8px;padding:12px 16px;background:#fff;border-top:1px solid #e2e6ea;position:sticky;bottom:0}
input{flex:1;padding:12px;border-radius:24px;border:1px solid #d0d7de;font-size:15px}
button{padding:12px 22px;border-radius:24px;border:0;background:#0b5fff;color:#fff;font-weight:700;font-size:15px;cursor:pointer}
.foot{text-align:center;padding:14px;font-size:13px;color:#888}.foot a{color:#0b5fff}
</style>
</head><body>
<header><h2>Apex Heating &amp; Air</h2><p>Typically replies instantly · Powered by Booked</p></header>
<div id="log"><div class="msg a">Hi! This is Apex Heating &amp; Air's assistant. What can I help with tonight?</div></div>
<form id="f"><input id="t" autocomplete="off" placeholder="Type your message..."><button>Send</button></form>
<script src="https://www.paypal.com/sdk/js?client-id=__PAYPAL_CLIENT_ID__&currency=USD&intent=capture"></script>
<script>
const log=document.getElementById('log'),hist=[];let convId=null;
function renderPayPalButton(cfg){
 const wrap=document.createElement('div');wrap.className='msg a';wrap.id='pp-'+cfg.booking_id;
 log.appendChild(wrap);
 paypal.Buttons({
  createOrder:(data,actions)=>actions.order.create({purchase_units:[{
   amount:{value:cfg.amount_usd},description:cfg.description}]}),
  onApprove:(data,actions)=>actions.order.capture().then(details=>
   fetch('/api/deposit-confirmed',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({booking_id:cfg.booking_id,paypal_order_id:data.orderID})})
   .then(()=>{wrap.innerHTML='Deposit received - your estimate is locked in. We will see you soon!';})),
  onCancel:()=>{wrap.innerHTML='Deposit cancelled — no charge made.';}
 }).render(wrap);
 log.scrollTop=log.scrollHeight;
}
document.getElementById('f').onsubmit=async e=>{
 e.preventDefault();const t=document.getElementById('t');const m=t.value.trim();if(!m)return;t.value='';
 log.innerHTML+=`<div class="msg u">${m}</div>`;hist.push({role:'user',content:m});
 const ty=document.createElement('div');ty.className='typing';ty.id='ty';ty.textContent='Typing...';
 log.appendChild(ty);log.scrollTop=log.scrollHeight;
 const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({message:m,history:hist.slice(0,-1),conv_id:convId})});
 const d=await r.json();convId=d.conv_id;hist.push({role:'assistant',content:d.reply});
 document.getElementById('ty').remove();
 log.innerHTML+=`<div class="msg a">${d.reply}</div>`;
 if(d.deposit_button) renderPayPalButton(d.deposit_button);
 log.scrollTop=log.scrollHeight;
};
</script>
<div class="foot"><a href="/dashboard">Owner dashboard</a></div>
</body></html>"""
    return HTMLResponse(html.replace("__PAYPAL_CLIENT_ID__", PAYPAL_CLIENT_ID))