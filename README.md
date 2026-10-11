# Booked

An open-source AI sales agent for local service businesses. It answers inbound leads instantly, qualifies them, books estimates, and collects a deposit — so no $5,000 job is ever lost to a missed call again.

**Triple-hackathon entry:**
- **Nebius x NVIDIA Global AI Hackathon** (due Oct 30, 2026) — agent runs on NVIDIA Nemotron via Nebius Token Factory
- **PayPal AI Hackathon** (due Nov 12, 2026) — deposit collection via PayPal Smart Buttons (sandbox-verified)
- **Code for a Billion** (due Nov 15, 2026) — fully open source, MIT licensed

## Demo

- [Nebius × NVIDIA cut (84s)](https://www.youtube.com/watch?v=OClpsdGXRVk) — the infra story: Nemotron on Token Factory
- [PayPal cut (75s)](https://www.youtube.com/watch?v=_8BLm5gxhrM) — the commerce story: real $89 deposit captured
- [Code for a Billion cut (79s)](https://www.youtube.com/watch?v=ZiGmUL4lAJY) — the open-source story: fork it for any trade

**The 60-second version:** a homeowner's AC dies at 9:47 PM. They message the business. Booked (powered by Nemotron on Nebius) greets them, asks three qualifying questions, and the moment it has a name, phone, and time preference, it drops a PayPal button into the chat. The homeowner pays the $89 deposit with a card — no account needed — and the owner sees the booking flip to `paid` on the dashboard. Missed call turned into booked revenue, while the owner sleeps.

## Quickstart

```bash
pip install -r requirements.txt
export NEBIUS_API_KEY=...              # Nebius Token Factory key
export PAYPAL_SANDBOX_CLIENT_ID=...    # PayPal Developer sandbox app client ID
uvicorn app.main:app --reload
```

- Chat demo: http://localhost:8000
- Owner dashboard: http://localhost:8000/dashboard

No PayPal secret needed: the live deposit path uses PayPal's official client-side Smart Buttons integration (works with the public client ID alone). A server-side REST module (`app/paypal.py`) is included as the production path.

## How it works

```
homeowner chat ──> FastAPI ──> Qualifier (Nemotron via Nebius Token Factory)
                        │            │
                        │            └─> [DEPOSIT] signal when qualified
                        │                      │
                        │                      v
                        │              PayPal Smart Button (sandbox)
                        │              card payment, no login required
                        │                      │
                        v                      v
              owner dashboard <── SQLite bookings (pending → paid)
```

1. **Qualify** — the agent follows a tight playbook: acknowledge the problem, ask at most 3 questions (need, urgency, name + phone).
2. **Close** — once qualified, the agent emits a `[DEPOSIT]` token; the backend creates a booking record and renders a PayPal button inline.
3. **Collect** — the homeowner pays by card in PayPal's sandbox checkout; the capture callback marks the booking `paid`.
4. **Show** — the owner dashboard lists every conversation, booking, and deposit status.

Business knowledge (services, pricing, deposit amount) lives in `BUSINESSES` in `app/main.py` — swap in any trade in minutes.

## Tech

- **Inference:** NVIDIA Nemotron 3 Nano via Nebius Token Factory (OpenAI-compatible API)
- **Payments:** PayPal JS SDK Smart Buttons (sandbox) — verified end-to-end with a captured $89 test payment
- **Stack:** FastAPI, SQLite, vanilla JS — no build step, runs anywhere Python runs

## Project plan

See [triple-hackathon-project-plan.md](../triple-hackathon-project-plan.md).

## License

MIT — see [LICENSE](LICENSE).
