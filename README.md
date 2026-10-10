# Booked

An open-source AI sales agent for local service businesses. It answers inbound leads instantly, qualifies them, books estimates, and collects a deposit — so no $5,000 job is ever lost to a missed call again.

Triple-hackathon entry:
- **Nebius x NVIDIA Global AI Hackathon** (due Oct 30, 2026) — agent runs on NVIDIA Nemotron via Nebius Token Factory
- **PayPal AI Hackathon** (due Nov 12, 2026) — deposit collection via PayPal Checkout
- **Code for a Billion** (due Nov 15, 2026) — fully open source, MIT licensed

## Quickstart

```bash
pip install -r requirements.txt
export NEBIUS_API_KEY=...            # Token Factory key
export PAYPAL_CLIENT_ID=...         # sandbox, optional — demo mode without
export PAYPAL_CLIENT_SECRET=...     # sandbox, optional
uvicorn app.main:app --reload
```

Open http://localhost:8000 — the chat widget demos the homeowner conversation.
Open http://localhost:8000/dashboard — the owner view: bookings, deposit status, conversations.

## Architecture

```
homeowner chat widget ──> FastAPI ──> Qualifier agent ──> Nemotron (Nebius Token Factory)
                                     Closer agent ──────> PayPal deposit link
                                     owner dashboard <── bookings + deposits
```

- **Qualifier agent**: conversation, needs analysis, slot finding.
- **Closer agent**: deposit checkout link, booking confirmation.
- **Business knowledge**: `app/businesses/` holds per-business service/FAQ context ingested into the system prompt.

## Project plan

See [triple-hackathon-project-plan.md](../triple-hackathon-project-plan.md).
