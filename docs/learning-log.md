## Bước 0.1 — Python, venv, Git repo

- **Làm gì, vì sao:** Cài Python 3.14 qua Homebrew, tạo venv riêng cho project, tạo repo và push lên GitHub. Mục đích: ai clone repo về cũng dựng lại được môi trường giống hệt, không phụ thuộc máy mình.
- **Lỗi gặp → cách sửa:**
  - Ghi đè nhầm `.venv/.gitignore` → xóa `.venv`, tạo lại, đặt `.gitignore` ở thư mục gốc.
  - zsh không hiểu `#` là comment nên tạo ra file/folder rác → bật `setopt interactive_comments`, xóa rác.
  - Clone báo "Repository not found" vì chưa push → commit + push trước. Bài học: đọc lỗi đầu tiên.
- **Commit:** `a658d82` chore: initialize project structure

## Bước 1.1 — Đổi tên ParcelLens → ShipRadar

- **Làm gì:** Ghim `name: shipradar` trong Compose, đổi tên container, user/DB trong `.env`, xóa container + volume cũ, đổi tên repo GitHub và thư mục, tạo lại venv.
- **Lỗi gặp → cách sửa:** `Docker Desktop is manually paused` → unpause Docker Desktop rồi chạy lại.
- **Bài học (tự viết):**
- **Commit:** `7d05359` chore: rename project to ShipRadar

## Bước 1.2 + 1.3a — Django + nối PostgreSQL

- **Làm gì:** Cài Django 6.1.2 + psycopg 3, `django-admin startproject config .`, settings đọc `.env` (python-dotenv), `DATABASES` dùng chung biến `POSTGRES_*` với Compose.
- **Lỗi gặp → cách sửa:**
- **Bài học (tự viết):**
- **Commit:** `6d66c23` feat: add Django project with PostgreSQL settings from .env

## Bước 1.3b — Custom User + role

- **Làm gì:** App `accounts`, `User(AbstractUser)` với `role` (admin/staff) + CheckConstraint, `AUTH_USER_MODEL`, migrate lần đầu, `createsuperuser`.
- **Lỗi gặp → cách sửa:**
- **Bài học (tự viết):**
- **Commit:** `026ff1d` feat: add custom User model with admin/staff roles

## Theme admin bằng Unfold

- **Làm gì:** django-unfold, tone navy, ẩn Groups, gom role/is_staff/is_superuser vào mục Access.
- **Lỗi gặp → cách sửa:** `ModuleNotFoundError: No module named 'unfold'` → quên `python -m pip install -r requirements.txt` sau khi requirements thay đổi.
- **Bài học (tự viết):**
- **Commit:** `a20a5a3` feat: style Django admin with Unfold and navy theme

## Bước 1.4 — Dockerfile + service web

- **Làm gì:** Dockerfile (python:3.14-slim-trixie, user không phải root, cache layer requirements), `.dockerignore`, service `web` trong Compose (host `db`, port 5432, bind mount code).
- **Lỗi gặp → cách sửa:** (thí nghiệm cố ý) `Connection refused` tới `127.0.0.1` từ trong container → trong container, `127.0.0.1` là chính container; dùng tên service `db`.
- **Bài học (tự viết):**
- **Commit:** `9c7e459` build: add Dockerfile for the Django app, `acd54df` build: run Django in Docker Compose alongside PostgreSQL
