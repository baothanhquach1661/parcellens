# Laravel → Django: ghi chú đối chiếu

Ghi chú cá nhân khi chuyển từ Laravel sang Django trong project ShipRadar.

## Lệnh

| Laravel | Django | Ghi chú |
|---|---|---|
| `php artisan serve` | `python manage.py runserver` | Trong Docker: `docker compose up -d` |
| `composer install` | `python -m pip install -r requirements.txt` | Dùng `python -m pip` để cài đúng vào Python đang chạy |
| `php artisan make:migration` | `python manage.py makemigrations` | Django tự sinh migration từ `models.py` |
| `php artisan migrate` | `python manage.py migrate` | |
| `php artisan tinker` | `python manage.py shell` | |
| `php artisan make:model` / `make:controller` | `python manage.py startapp <tên>` | Một app gồm models, views, admin, migrations của một mảng nghiệp vụ |
| `php artisan make:command` | Tạo file `<app>/management/commands/<tên>.py` | |
| `php artisan db` | `docker compose exec db psql -U shipradar -d shipradar` | `dbshell` cần psql cài trên máy |
| `php artisan route:list` | Không có sẵn | `django-extensions` có `show_urls` |

Khi chạy bằng Docker, thêm `docker compose exec web` trước mọi lệnh `python manage.py ...`.

## Khái niệm

| Laravel | Django | Khác biệt cần nhớ |
|---|---|---|
| `artisan` | `manage.py` | |
| `config/*.php` + `.env` | `config/settings.py` + `.env` | Settings là code Python, đọc biến môi trường bằng `os.environ` |
| `routes/web.php` | `config/urls.py` (+ `urls.py` của từng app) | |
| Controller | View (`views.py`) | "View" của Django ≈ controller; template mới là phần hiển thị |
| Blade | Django templates | `{% block %}`, `{% extends %}` gần giống `@section`, `@extends` |
| Eloquent model | Model (`models.py`) | Migration được sinh ra từ model, không viết tay |
| `App\Models\User` có sẵn trong code | `AUTH_USER_MODEL` (custom user phải tạo trước lần migrate đầu) | |
| Filament / Nova | Django admin (+ Unfold) | Cấu hình bằng settings và class `ModelAdmin`, không sửa template trong package |
| `vendor/` | `.venv/lib/python3.14/site-packages/` | Chỉ đọc để tìm hiểu, không sửa |

## ORM

| Eloquent | Django ORM |
|---|---|
| `Order::all()` | `Order.objects.all()` |
| `Order::where('status', 'paid')->get()` | `Order.objects.filter(status='paid')` |
| `Order::find(1)` | `Order.objects.get(pk=1)` (không có thì báo `Order.DoesNotExist`) |
| `Order::firstOrCreate([...])` | `Order.objects.get_or_create(...)` |
| `$order->items` | `order.items.all()` (tên lấy từ `related_name`) |
| `Order::with('items')` | `Order.objects.prefetch_related('items')` (quan hệ nhiều), `select_related('customer')` (khóa ngoại) |
