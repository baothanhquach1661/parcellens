## Bước 0.1 — Python, venv, Git repo

- **Làm gì, vì sao:** Cài Python 3.14 qua Homebrew, tạo venv riêng cho project, tạo repo và push lên GitHub. Mục đích: ai clone repo về cũng dựng lại được môi trường giống hệt, không phụ thuộc máy mình.
- **Lỗi gặp → cách sửa:**
  - Ghi đè nhầm `.venv/.gitignore` → xóa `.venv`, tạo lại, đặt `.gitignore` ở thư mục gốc.
  - zsh không hiểu `#` là comment nên tạo ra file/folder rác → bật `setopt interactive_comments`, xóa rác.
  - Clone báo "Repository not found" vì chưa push → commit + push trước. Bài học: đọc lỗi đầu tiên.
- **Commit:** `a658d82` chore: initialize project structure