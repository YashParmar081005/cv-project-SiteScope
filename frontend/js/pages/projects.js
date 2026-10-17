// Home: the user's projects, each with its latest progress and estimated finish.
import { get } from "../api.js";
import { fmtDate, html, pct, setHTML } from "../ui.js";
import { CONSTRUCTION_TYPES } from "../validation.js";

export async function render(el, { alive }) {
  const projects = await get("/projects");
  if (!alive()) return;
  setHTML(el, html`
    <div class="head">
      <div><h1>My projects</h1><p class="muted">Add a project, then upload site photos to estimate when it will be finished.</p></div>
      <a class="btn primary" href="#/new">+ Add project</a>
    </div>
    ${projects.length ? html`<div class="cards">${projects.map(card)}</div>` : html`
      <div class="card empty"><h2>No projects yet</h2><p>Add your first construction project to start estimating.</p>
        <a class="btn primary" href="#/new">+ Add project</a></div>`}`);
}

function card(p) {
  const s = p.summary;
  const fc = s.forecast;
  const finish = fc.status === "estimated" ? html`<b>${fmtDate(fc.estimated_completion_date)}</b>`
    : fc.status === "completed" ? html`<b>Completed ${fmtDate(fc.estimated_completion_date)}</b>`
      : html`<span class="muted">${s.photos ? "Confirm a photo's stage to estimate" : "Add a photo to estimate"}</span>`;
  return html`
    <a class="card project-card" href="#/p/${p.id}">
      <div><h2 style="margin:0">${p.name}</h2>
        <p class="muted small">${CONSTRUCTION_TYPES[p.construction_type]}${p.location ? ` · ${p.location}` : ""}</p></div>
      <div class="row" style="justify-content:space-between"><span class="small">Progress</span><b>${pct(s.progress)}</b></div>
      <div class="bar"><span style="width:${((s.progress || 0) * 100).toFixed(1)}%"></span></div>
      <div class="small">Estimated finish: ${finish}</div>
      <div class="small muted">Planned finish ${fmtDate(p.target_completion_date)} · ${s.photos} photo(s)</div>
    </a>`;
}
