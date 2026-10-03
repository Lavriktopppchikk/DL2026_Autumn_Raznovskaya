"""QR Studio backend: FastAPI + segno (генерация QR) + SQLite (история)."""
import base64
import io
import re
import sqlite3
import time
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlparse

import segno
from fastapi import FastAPI, HTTPException, Response
from PIL import Image
from pydantic import BaseModel, Field

DB_PATH = Path(__file__).with_name("qr.db")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_LOGO_BYTES = 1_000_000
BORDER = 4  # "quiet zone" по спецификации QR — 4 модуля

app = FastAPI(title="QR Studio API")


# ---------- БД (стандартный sqlite3, без ORM — проект маленький) ----------
def run(sql: str, args: tuple = ()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        with conn:  # commit/rollback
            cur = conn.execute(sql, args)
            return cur.fetchall(), cur.lastrowid
    finally:
        conn.close()


run("""CREATE TABLE IF NOT EXISTS qr_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL, kind TEXT NOT NULL,
    fg TEXT NOT NULL, bg TEXT NOT NULL, size INTEGER NOT NULL,
    logo TEXT, created_at INTEGER NOT NULL)""")


# ---------- Схема и валидация ----------
class QRParams(BaseModel):
    data: str = Field(min_length=1, max_length=1000)
    kind: Literal["text", "url"] = "text"
    fg: str = "#000000"
    bg: str = "#ffffff"
    size: int = Field(512, ge=128, le=1024)
    format: Literal["png", "svg"] = "png"
    logo: Optional[str] = None  # data URL (base64)


def decode_logo(data_url: str) -> bytes:
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1], validate=True)
    except Exception:
        raise HTTPException(422, "Некорректный логотип")
    if len(raw) > MAX_LOGO_BYTES:
        raise HTTPException(422, "Логотип больше 1 МБ")
    try:
        Image.open(io.BytesIO(raw)).verify()  # реально ли это картинка
    except Exception:
        raise HTTPException(422, "Некорректный логотип")
    return raw


def validate(p: QRParams) -> Optional[bytes]:
    if not (HEX.match(p.fg) and HEX.match(p.bg)):
        raise HTTPException(422, "Цвет должен быть в формате #RRGGBB")
    if p.fg.lower() == p.bg.lower():
        raise HTTPException(422, "Цвета кода и фона совпадают")
    if p.kind == "url":
        u = urlparse(p.data.strip())
        if u.scheme not in ("http", "https") or not u.netloc:
            raise HTTPException(422, "Введите корректную ссылку (http:// или https://)")
    return decode_logo(p.logo) if p.logo else None


# ---------- Генерация ----------
def render(p: QRParams) -> tuple[bytes, str]:
    logo_raw = validate(p)
    # С логотипом закрываем центр -> нужен максимальный уровень коррекции ошибок (H)
    qr = segno.make(p.data.strip(), error="h" if logo_raw else "m")
    modules = qr.symbol_size(scale=1, border=BORDER)[0]
    scale = max(1, p.size // modules)  # целый масштаб -> чёткие границы модулей
    px = modules * scale
    box = int(px * 0.20)  # логотип занимает ~20% стороны (≈4% площади)
    pad = max(2, box // 8)
    buf = io.BytesIO()

    if p.format == "png":
        qr.save(buf, kind="png", scale=scale, border=BORDER, dark=p.fg, light=p.bg)
        if logo_raw:
            img = Image.open(io.BytesIO(buf.getvalue())).convert("RGBA")
            logo = Image.open(io.BytesIO(logo_raw)).convert("RGBA")
            logo.thumbnail((box, box))
            plate = Image.new("RGBA", (logo.width + 2 * pad, logo.height + 2 * pad), p.bg)
            plate.paste(logo, (pad, pad), logo)
            img.paste(plate, ((px - plate.width) // 2, (px - plate.height) // 2), plate)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
        return buf.getvalue(), "image/png"

    qr.save(buf, kind="svg", scale=scale, border=BORDER, dark=p.fg, light=p.bg,
            xmldecl=False, svgns=True)
    svg = buf.getvalue().decode()
    if logo_raw:
        lw, lh = Image.open(io.BytesIO(logo_raw)).size
        k = min(box / lw, box / lh)
        w, h = lw * k, lh * k
        x, y = (px - w) / 2, (px - h) / 2
        overlay = (f'<rect x="{x - pad}" y="{y - pad}" width="{w + 2 * pad}" '
                   f'height="{h + 2 * pad}" fill="{p.bg}"/>'
                   f'<image href="{p.logo}" x="{x}" y="{y}" width="{w}" height="{h}"/>')
        svg = svg.replace("</svg>", overlay + "</svg>")
    return svg.encode(), "image/svg+xml"


# ---------- Эндпоинты ----------
@app.post("/api/qr")
def make_qr(p: QRParams):
    """Сгенерировать изображение (для превью, скачивания). Ничего не сохраняет."""
    body, mime = render(p)
    return Response(body, media_type=mime)


@app.post("/api/history", status_code=201)
def save(p: QRParams):
    validate(p)
    _, new_id = run(
        "INSERT INTO qr_codes (data, kind, fg, bg, size, logo, created_at) VALUES (?,?,?,?,?,?,?)",
        (p.data, p.kind, p.fg, p.bg, p.size, p.logo, int(time.time())))
    return {"id": new_id}


@app.get("/api/history")
def history():
    rows, _ = run("SELECT id, data, kind, fg, bg, logo IS NOT NULL AS has_logo, created_at "
                  "FROM qr_codes ORDER BY id DESC LIMIT 50")
    return [dict(r) for r in rows]


def get_row(qr_id: int):
    rows, _ = run("SELECT * FROM qr_codes WHERE id = ?", (qr_id,))
    if not rows:
        raise HTTPException(404, "QR-код не найден")
    return dict(rows[0])


@app.get("/api/history/{qr_id}")
def history_item(qr_id: int):
    return get_row(qr_id)  # включая logo — чтобы восстановить форму


@app.delete("/api/history/{qr_id}", status_code=204)
def delete(qr_id: int):
    get_row(qr_id)
    run("DELETE FROM qr_codes WHERE id = ?", (qr_id,))


@app.get("/api/qr/{qr_id:int}.{fmt}")
def shared_image(qr_id: int, fmt: Literal["png", "svg"]):
    """Постоянная ссылка на сохранённый QR: картинка пересобирается из настроек."""
    row = get_row(qr_id)
    fields = {k: row[k] for k in ("data", "kind", "fg", "bg", "size", "logo")}
    body, mime = render(QRParams(**fields, format=fmt))
    return Response(body, media_type=mime)
