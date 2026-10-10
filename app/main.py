"""Booked — AI sales agent for local service businesses. Week 1: talking machine."""
import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import httpx

app = FastAPI(title="Booked")

NEBIUS_BASE = "https://api.tokenfactory.nebius.com/v1"
MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"

SYSTEM_PROMPT = """You are Booked, the AI sales agent for {business_name}, a {trade} company in {area}.
Your job: turn inbound messages into booked estimates.

Playbook:
1. Greet warmly and acknowledge their problem.
2. Qualify with at most 3 short questions: what they need, urgency/timeline, and how to reach them (name + phone).
3. Once qualified, offer the next two available estimate slots (say "tomorrow between 9-11am or Thursday 2-4pm" as placeholders).
4. Keep every reply under 60 words. Friendly, plain-spoken, no hype, no emojis.

Services: {services}
Diagnostic/estimate fee: {fee}
"""


class ChatIn(BaseModel):
    message: str
    history: list[dict] = []
    business: str = "apex-hvac"


BUSINESSES = {
    "apex-hvac": {
        "business_name": "Apex Heating & Air",
        "trade": "HVAC",
        "area": "Sacramento, CA",
        "services": "AC repair and replacement, furnace tune-ups, ductwork, smart thermostats",
        "fee": "$89 diagnostic, credited toward the repair",
    },
    "bluewater-pools": {
        "business_name": "Bluewater Pools",
        "trade": "pool builder",
        "area": "Sacramento, CA",
        "services": "custom pool builds, remodels, equipment upgrades, weekly service plans",
        "fee": "free on-site estimate",
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
async def chat(inp: ChatIn):
    b = BUSINESSES.get(inp.business, BUSINESSES["apex-hvac"])
    system = SYSTEM_PROMPT.format(**b)
    reply = await agent_reply(system, inp.history, inp.message)
    return {"reply": reply}


@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Booked — demo</title>
<style>body{font-family:system-ui,sans-serif;max-width:560px;margin:40px auto;padding:0 16px}
#log{border:1px solid #ddd;border-radius:12px;padding:16px;min-height:300px;margin-bottom:12px}
.msg{margin:8px 0;line-height:1.5}.u{text-align:right;color:#0b5fff}.a{color:#111}
form{display:flex;gap:8px}input{flex:1;padding:10px;border-radius:8px;border:1px solid #ccc}
button{padding:10px 18px;border-radius:8px;border:0;background:#0b5fff;color:#fff;font-weight:700}</style>
</head><body>
<h2>Booked — homeowner chat demo</h2>
<div id="log"><div class="msg a">Hi! This is Apex Heating & Air's assistant. What can I help with?</div></div>
<form id="f"><input id="t" autocomplete="off" placeholder="e.g. My AC died, house is 90 degrees"><button>Send</button></form>
<script>
const log=document.getElementById('log'),hist=[];
document.getElementById('f').onsubmit=async e=>{
 e.preventDefault();const t=document.getElementById('t');const m=t.value.trim();if(!m)return;t.value='';
 log.innerHTML+=`<div class="msg u">${m}</div>`;hist.push({role:'user',content:m});
 const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({message:m,history:hist.slice(0,-1)})});
 const d=await r.json();hist.push({role:'assistant',content:d.reply});
 log.innerHTML+=`<div class="msg a">${d.reply}</div>`;log.scrollTop=log.scrollHeight;
};
</script></body></html>"""
