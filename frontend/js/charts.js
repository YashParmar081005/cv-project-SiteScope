// Dependency-free SVG charts.
import { esc, fmtDate } from "./ui.js";

const DAY = 86400000;
const t = (iso) => Date.parse(String(iso).slice(0, 10));

/**
 * Progress chart: planned curve (user-entered schedule), reviewed snapshots (measurements),
 * and the forecast projection with its range (model estimate).
 */
export function progressChart({ planned = [], snapshots = [], forecast = null, today = null }) {
  const W = 760, H = 300, L = 46, R = 18, T = 16, B = 34;
  const pts = [...planned.map((p) => t(p.date)), ...snapshots.map((s) => t(s.as_of_date))];
  if (forecast?.estimated_completion_date) pts.push(t(forecast.estimated_completion_date));
  if (forecast?.range?.latest) pts.push(t(forecast.range.latest));
  if (forecast?.range?.earliest) pts.push(t(forecast.range.earliest));
  if (today) pts.push(t(today));
  if (pts.length < 2) {
    return `<div class="empty"><h3>Nothing to chart yet</h3><p>Add a planned schedule and review observations to see progress over time.</p></div>`;
  }
  let x0 = Math.min(...pts), x1 = Math.max(...pts);
  const pad = Math.max(7 * DAY, (x1 - x0) * 0.03);
  x0 -= pad; x1 += pad;
  const X = (ms) => L + ((ms - x0) / (x1 - x0)) * (W - L - R);
  const Y = (v) => T + (1 - v) * (H - T - B);
  const parts = [];

  for (const v of [0, 0.25, 0.5, 0.75, 1]) {
    parts.push(`<line class="gridline" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/>`);
    parts.push(`<text class="tick" x="${L - 8}" y="${Y(v) + 4}" text-anchor="end">${v * 100}%</text>`);
  }
  const spanDays = (x1 - x0) / DAY;
  const stepMonths = spanDays > 1500 ? 12 : spanDays > 700 ? 6 : spanDays > 300 ? 3 : 1;
  const d = new Date(x0);
  d.setUTCDate(1);
  d.setUTCMonth(d.getUTCMonth() + 1);
  while (d.getTime() < x1) {
    if (d.getUTCMonth() % stepMonths === 0) {
      const x = X(d.getTime());
      parts.push(`<line class="axis" x1="${x}" x2="${x}" y1="${H - B}" y2="${H - B + 4}"/>`);
      parts.push(`<text class="tick" x="${x}" y="${H - B + 18}" text-anchor="middle">${d.toLocaleString("en", { month: "short", timeZone: "UTC" })} ${String(d.getUTCFullYear()).slice(2)}</text>`);
    }
    d.setUTCMonth(d.getUTCMonth() + 1);
  }
  parts.push(`<line class="axis" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/>`);

  if (forecast?.range?.earliest && forecast?.range?.latest) {
    const a = X(t(forecast.range.earliest)), b = X(t(forecast.range.latest));
    parts.push(`<rect class="range" x="${a}" y="${T}" width="${Math.max(2, b - a)}" height="${H - T - B}"><title>Estimate range ${esc(fmtDate(forecast.range.earliest))} – ${esc(fmtDate(forecast.range.latest))} (model estimate)</title></rect>`);
  }
  if (today) {
    const x = X(t(today));
    parts.push(`<line class="today" x1="${x}" x2="${x}" y1="${T}" y2="${H - B}"/><text class="tick" x="${x + 4}" y="${T + 10}">today</text>`);
  }
  if (planned.length) {
    parts.push(`<polyline class="planned" points="${planned.map((p) => `${X(t(p.date))},${Y(p.progress)}`).join(" ")}"><title>Planned (user-entered schedule)</title></polyline>`);
  }
  if (snapshots.length && forecast?.estimated_completion_date && forecast.status === "estimated") {
    const last = snapshots[snapshots.length - 1];
    parts.push(`<line class="projection" x1="${X(t(last.as_of_date))}" y1="${Y(last.progress)}" x2="${X(t(forecast.estimated_completion_date))}" y2="${Y(1)}"><title>Forecast projection (model estimate)</title></line>`);
  }
  if (snapshots.length) {
    parts.push(`<polyline class="actual" points="${snapshots.map((s) => `${X(t(s.as_of_date))},${Y(s.progress)}`).join(" ")}"/>`);
    for (const s of snapshots) {
      parts.push(`<circle class="dot ${s.lower_bound ? "lower" : ""}" cx="${X(t(s.as_of_date))}" cy="${Y(s.progress)}" r="5"><title>${esc(fmtDate(s.as_of_date))}: ${(s.progress * 100).toFixed(1)}% reviewed${s.lower_bound ? " (lower bound)" : ""}</title></circle>`);
    }
  }
  return `<div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Progress over time">${parts.join("")}</svg></div>`;
}

