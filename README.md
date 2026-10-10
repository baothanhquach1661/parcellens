# ShipRadar

> Catch order problems before your customers do.

ShipRadar is an order exception tracker for e-commerce operations. It imports orders, inventory and carrier tracking data, applies configurable fulfillment rules, and gives an operations coordinator a prioritized daily work queue.

**Status:** Week 1 of 4. Foundation is in place: Django and PostgreSQL in Docker Compose, a custom user model with roles, and a themed admin back office. The rules engine and the work queue come next.

## Planned rules

| Rule | Flags an order when | Severity |
|---|---|---|
| Overdue unfulfilled | Paid but not fulfilled after 2 business days | High |
| Stockout | On-hand stock cannot cover open orders for a SKU | High |
| Delivery exception | Carrier reports an exception, failed attempt or return to sender | High |
| Missing tracking | Fulfilled more than 24 hours ago with no tracking number | Medium |
| Stale tracking | In transit with no carrier update for more than 3 days | Medium |
| Late delivery | Past the expected delivery date and not delivered | Medium |
| Suspicious address | Missing fields or invalid ZIP code | Low |

Design goals: thresholds live in the database, SLAs count business days only, and re-running the rules never creates duplicate exceptions.

## Tech stack

- Python 3.14, Django 6.1
- PostgreSQL 18
- Docker Compose
- django-unfold (admin theme)

## Requirements

- Docker Desktop
- Python 3.14, only if you want to run Django outside Docker or get editor autocompletion

## Getting started

```bash
git clone https://github.com/baothanhquach1661/shipradar.git
cd shipradar
cp .env.example .env
```

Edit `.env` and set `POSTGRES_PASSWORD` and `DJANGO_SECRET_KEY`. Generate a key with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

Then start everything:

```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Open http://127.0.0.1:8000/admin/ and log in.

## Everyday commands

| Task | Command |
|---|---|
| Start database and web | `docker compose up -d` |
| Stop (keeps data) | `docker compose down` |
| Follow Django logs | `docker compose logs -f web` |
| Run a management command | `docker compose exec web python manage.py <command>` |
| Create migrations | `docker compose exec web python manage.py makemigrations` |
| Apply migrations | `docker compose exec web python manage.py migrate` |
| Open a PostgreSQL shell | `docker compose exec db psql -U shipradar -d shipradar` |
| Rebuild after changing `requirements.txt` | `docker compose up -d --build` |

### Running Django outside Docker

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
docker compose up -d db
python manage.py runserver
```

Stop the `web` container first (`docker compose stop web`), because both use port 8000.

## Configuration

All settings come from environment variables. Locally they are read from `.env`; variables already set in the environment take precedence.

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | Yes | | The app refuses to start without it |
| `DJANGO_DEBUG` | No | `False` | `True` for local development |
| `DJANGO_ALLOWED_HOSTS` | No | empty | Comma-separated, e.g. `localhost,127.0.0.1` |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Yes | | Also used by Compose to create the database |
| `POSTGRES_HOST` | No | `127.0.0.1` | Compose overrides it to `db` inside the `web` container |
| `POSTGRES_PORT` | No | `5432` | `.env` uses `5434`, the port published on the host |

## Users and roles

| Field | Meaning |
|---|---|
| `role = admin` | Can change rule settings and manage users |
| `role = staff` | Works the exception queue (default for new users) |
| `is_staff` | Django flag: may log in to `/admin` |
| `is_superuser` | Django flag: has every Django permission |

`createsuperuser` creates a user with the admin role.

## Project structure

```text
accounts/   Custom user model with admin and staff roles
config/     Django settings and URL configuration
docs/       Learning log and notes
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError` after pulling changes | `requirements.txt` changed | `python -m pip install -r requirements.txt` or `docker compose up -d --build` |
| `port is already allocated` | Another server or container uses 8000 or 5434 | Stop it, or `docker compose stop web` before running Django locally |
| `Connection refused` to `127.0.0.1` from inside a container | Inside a container, `127.0.0.1` is the container itself | Use host `db` and port `5432` (Compose sets this for `web`) |
| `role "shipradar" does not exist` | The database volume was created with other credentials | `docker compose down -v` (deletes all data), then `docker compose up -d` |
| `Docker Desktop is manually paused` | Docker Desktop is paused | Unpause it from the whale menu |

## Data

ShipRadar uses generated sample data only. It never stores real customer data.
