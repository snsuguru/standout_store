# Standout Store (FastAPI + SQLModel + HTMX + Tailwind)

A modern, *experimentation-first* e‑commerce demo built to stand out in hackathons & internships.

## Features
- FastAPI backend with SQLModel (SQLite by default).
- Clean Jinja2 + Tailwind UI (no bulky frontend frameworks).
- HTMX for snappy UX (cart updates, admin uploads).
- JWT auth (signup/login), password hashing with passlib.
- Product catalog, search, filters, cart, orders (mock checkout), receipts.
- Live inventory updates via WebSocket (see "Admin → Toggle Stock").
- Built-in **A/B content experiments** for product titles/descriptions.
- Lightweight **content‑based recommendations** (TF‑IDF + cosine).
- **Analytics** event table with mini dashboard (top products, CTR, conversions).
- Admin bulk import via CSV and feature flags (e.g., enable experiments globally).

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Then open http://127.0.0.1:8000

## Default admin
- email: admin@demo.dev
- password: admin123

> Not for production. Secrets are in `.env.example` for convenience.
