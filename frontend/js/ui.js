// DOM helpers, safe HTML templating and formatting.

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ESC[c]);

class Raw {
  constructor(s) { this.s = s; }
  toString() { return this.s; }
}
export const raw = (s) => new Raw(String(s));

function render(v) {
  if (v instanceof Raw) return v.s;
  if (Array.isArray(v)) return v.map(render).join("");
  if (v === null || v === undefined || v === false) return "";
  return esc(v);
}

/** Tagged template: interpolated values are HTML-escaped unless wrapped in raw() or produced by html``. */
export function html(strings, ...values) {
  let out = strings[0];
  values.forEach((v, i) => { out += render(v) + strings[i + 1]; });
  return new Raw(out);
}

export const $ = (sel, root = document) => root.querySelector(sel);
export function setHTML(el, content) { el.innerHTML = String(content); return el; }

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function fmtDate(iso) {
  if (!iso) return "—";
  const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}
export const pct = (v) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(1)}%`);
export const titleCase = (s) => String(s ?? "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
export const todayISO = () => new Date().toISOString().slice(0, 10);

export function duration(days) {
  if (days === null || days === undefined) return "—";
  if (Math.abs(days) < 60) return `${days} days`;
  const months = days / 30.44;
  return months < 24 ? `${months.toFixed(1)} months` : `${(months / 12).toFixed(1)} years`;
}

export const loading = () => html`<div class="center" style="min-height:200px"><div class="spinner" role="status" aria-label="Loading"></div></div>`;
export const errorBox = (err) => html`<div class="banner error" role="alert">${err?.message || String(err)}</div>`;

export function toast(message, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), 4000);
}
