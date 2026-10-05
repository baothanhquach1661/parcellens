# ParcelLens

Shipment tracking system: monitors carrier status, detects late/stuck/returned parcels, and sends alerts.

## Requirements
- Python 3.14

## Setup
```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

## Database
1. Copy `.env.example` to `.env` and set your own password.
2. Start PostgreSQL 18: `docker compose up -d`
3. Connect at `localhost:5434` (user and database: `parcellens`).