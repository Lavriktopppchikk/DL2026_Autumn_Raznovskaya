import { useEffect, useState } from "react";

const DEFAULTS = { data: "", kind: "url", fg: "#000000", bg: "#ffffff", size: 512, logo: null };

// Обёртка над fetch: достаёт текст ошибки из ответа бэкенда
async function api(path, options) {
  const res = await fetch("/api" + path, options);
  if (!res.ok) {
    let msg = "Ошибка сервера";
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : "Проверьте введённые данные";
    } catch { /* тело не JSON */ }
    throw new Error(msg);
  }
  return res;
}
const post = (path, body) =>
  api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

// Контраст по WCAG: если < 3, QR может плохо сканироваться
function contrast(a, b) {
  const lum = (hex) => {
    const [r, g, bl] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

export default function App() {
  const [form, setForm] = useState(DEFAULTS);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);
  const [notice, setNotice] = useState("");
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  const loadHistory = () => api("/history").then((r) => r.json()).then(setHistory).catch(() => {});
  useEffect(() => { loadHistory(); }, []);

  // Живое превью: debounce 300 мс, устаревшие ответы игнорируем
  useEffect(() => {
    if (!form.data.trim()) { setPreview(null); setError(""); return; }
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const blob = await (await post("/qr", { ...form, format: "svg" })).blob();
        if (cancelled) return;
        setPreview((old) => { if (old) URL.revokeObjectURL(old); return URL.createObjectURL(blob); });
        setError("");
      } catch (e) { if (!cancelled) { setError(e.message); setPreview(null); } }
    }, 300);
    return () => { cancelled = true; clearTimeout(t); };
  }, [form]);

  const onLogo = (file) => {
    if (!file) return set({ logo: null });
    const reader = new FileReader();
    reader.onload = () => set({ logo: reader.result });
    reader.readAsDataURL(file);
  };

  const download = async (format) => {
    try {
      const blob = await (await post("/qr", { ...form, format })).blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `qr.${format}`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { setError(e.message); }
  };

  const save = async () => {
    try {
      const { id } = await (await post("/history", form)).json();
      const link = `${location.origin}/api/qr/${id}.png`;
      await navigator.clipboard.writeText(link);
      setNotice("Сохранено. Ссылка на PNG скопирована: " + link);
      loadHistory();
    } catch (e) { setError(e.message); }
  };

  const restore = async (id) => {
    const item = await (await api(`/history/${id}`)).json();
    setForm({ ...DEFAULTS, ...item });
  };
  const remove = async (id) => { await api(`/history/${id}`, { method: "DELETE" }); loadHistory(); };

  const lowContrast = contrast(form.fg, form.bg) < 3;
  const ready = form.data.trim() && preview && !error;

  return (
    <main className="app">
      <h1>QR Studio</h1>
      <div className="grid">
        <section className="panel">
          <div className="row">
            <label><input type="radio" checked={form.kind === "url"} onChange={() => set({ kind: "url" })} /> Ссылка</label>
            <label><input type="radio" checked={form.kind === "text"} onChange={() => set({ kind: "text" })} /> Текст</label>
          </div>
          <textarea rows={3} placeholder={form.kind === "url" ? "https://example.com" : "Любой текст"}
            value={form.data} onChange={(e) => set({ data: e.target.value })} />
          <div className="row">
            <label>Код <input type="color" value={form.fg} onChange={(e) => set({ fg: e.target.value })} /></label>
            <label>Фон <input type="color" value={form.bg} onChange={(e) => set({ bg: e.target.value })} /></label>
          </div>
          <label>Размер: {form.size}px
            <input type="range" min="128" max="1024" step="32" value={form.size}
              onChange={(e) => set({ size: +e.target.value })} />
          </label>
          <label>Логотип в центре (PNG/JPG, до 1 МБ)
            <input type="file" accept="image/png,image/jpeg" onChange={(e) => onLogo(e.target.files[0])} />
          </label>
          {form.logo && <button className="link" onClick={() => onLogo(null)}>Убрать логотип</button>}
          {lowContrast && <p className="warn">Низкий контраст — код может плохо сканироваться.</p>}
        </section>

        <section className="panel center">
          {error && <p className="error">{error}</p>}
          {preview ? <img className="qr" src={preview} alt="QR-код" /> :
            !error && <p className="hint">Введите ссылку или текст — превью появится здесь</p>}
          <div className="row">
            <button disabled={!ready} onClick={() => download("png")}>Скачать PNG</button>
            <button disabled={!ready} onClick={() => download("svg")}>Скачать SVG</button>
            <button disabled={!ready} onClick={save}>Сохранить и скопировать ссылку</button>
          </div>
          {notice && <p className="notice">{notice}</p>}
        </section>
      </div>

      <h2>История</h2>
      {history.length === 0 && <p className="hint">Пока пусто</p>}
      <ul className="history">
        {history.map((h) => (
          <li key={h.id}>
            <img src={`/api/qr/${h.id}.png`} width="56" height="56" alt="" onClick={() => restore(h.id)} />
            <span onClick={() => restore(h.id)}>{h.data.slice(0, 60)}</span>
            <button className="link" onClick={() => remove(h.id)}>Удалить</button>
          </li>
        ))}
      </ul>
    </main>
  );
}
