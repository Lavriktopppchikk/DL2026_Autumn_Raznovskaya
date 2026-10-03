# QR Studio — генератор QR-кодов с кастомизацией

Тестовое задание DevCraft Lab (Fullstack Developer), вариант 3.
Введите ссылку или текст → настройте цвета, размер, логотип → видите живое превью → скачайте PNG/SVG или сохраните в историю и скопируйте ссылку на картинку.

**Стек:** FastAPI + segno + Pillow + SQLite (backend), React + Vite (frontend).

Документация: [проектирование](docs/design.md) · [рефлексия по AI](docs/AI_REFLECTION.md)

## Требования
- Python 3.10+
- Node.js 18+

## Запуск (два терминала)

### Backend
```bash
cd backend
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
API: http://127.0.0.1:8000 · Swagger: http://127.0.0.1:8000/docs

### Frontend
```bash
cd frontend
npm install
npm run dev
```
Откройте http://localhost:5173 (запросы `/api` проксируются на бэкенд, порт 8000).

## Как проверить
1. Выберите «Ссылка», введите `https://example.com` — появится превью.
2. Введите `example.com` — увидите ошибку валидации.
3. Загрузите логотип, поменяйте цвета и размер — превью обновляется.
4. «Скачать PNG/SVG» — файл скачивается; «Сохранить…» — запись в истории, ссылка в буфере обмена.
5. Клик по записи истории восстанавливает настройки.

Файл БД `backend/qr.db` создаётся автоматически при первом запуске.
