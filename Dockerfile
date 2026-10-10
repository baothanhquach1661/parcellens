# syntax=docker/dockerfile:1

# Same Python minor version as the local venv (3.14).
# "slim" = Debian without extras; "trixie" pins the Debian release
# so the base OS does not change underneath us.
FROM python:3.14-slim-trixie

# PYTHONDONTWRITEBYTECODE: no .pyc files in the image.
# PYTHONUNBUFFERED: logs show up immediately in `docker logs`.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Unprivileged user that runs the app.
RUN useradd --create-home --uid 1000 app

# Dependencies first: this layer is reused until requirements.txt changes,
# so editing Python code does not reinstall every package.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Project code. .dockerignore keeps .env, .venv and .git out of the image.
# Files stay owned by root, so the app user can read but not modify them.
# chmod: files that are owner-only on the Mac (mode 600) would otherwise be
# unreadable for the app user and fail with "Permission denied".
COPY . .
RUN chmod -R a+rX /app

USER app

EXPOSE 8000

# Development server for now. Production switches to gunicorn at deploy time.
# 0.0.0.0 = accept connections from outside the container (port mapping).
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
