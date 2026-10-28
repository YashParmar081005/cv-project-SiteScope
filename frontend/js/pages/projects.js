// Home: the user's projects, each with its latest progress, estimated finish and a delete button.
import { api, get } from "../api.js";
import { $, fmtDate, html, pct, setHTML, toast } from "../ui.js";
import { CONSTRUCTION_TYPES } from "../validation.js";

export async function render(el, ctx) {
  const projects = await get("/projects");
  if (!ctx.alive()) return;
  setHTML(el, html`
    <div class="head">
      <div><h1>My projects</h1><p class="muted">Add a project, then upload site photos to estimate when it will be finished.</p></div>
      <a class="btn primary" href="#/new">+ Add project</a>
    </div>
    ${projects.length ? html`<div class="cards">${projects.map(card)}</div>` : html`
      <div class="card empty"><h2>No projects yet</h2><p>Add your first construction project to start estimating.</p>
        <a class="btn primary" href="#/new">+ Add project</a></div>`}`);

  $(".cards", el)?.addEventListener("click", async (e) => {
    const btn = e.target.closest(".card-del");
    if (!btn) return;
    e.preventDefault();              // the whole card is a link; the button must not follow it
    if (!confirm(`Delete project "${btn.dataset.name}" and all its photos? This cannot be undone.`)) return;
    btn.disabled = true;
    try {
      await api(`/projects/${btn.dataset.id}`, { method: "DELETE" });
      toast("Project deleted.", "ok");
      render(el, ctx);
    } catch (err) {
      toast(err.message, "error");
      btn.disabled = false;
    }
  });
}

function card(p) {
  const s = p.summary;
  const fc = s.forecast;
  const finish = fc.status === "estimated" ? html`<b>${fmtDate(fc.estimated_completion_date)}</b>`
    : fc.status === "completed" ? html`<b>Completed ${fmtDate(fc.estimated_completion_date)}</b>`
      : html`<span class="muted">${s.photos ? "Confirm a photo's stage to estimate" : "Add a photo to estimate"}</span>`;
  return html`
    <div class="project-card-wrap">
      <a class="card project-card" href="#/p/${p.id}">
        <div class="pc-title"><h2 style="margin:0">${p.name}</h2>
          <p class="muted small">${CONSTRUCTION_TYPES[p.construction_type]}${p.location ? ` · ${p.location}` : ""}</p></div>
        <div class="row" style="justify-content:space-between"><span class="small">Progress</span><b>${pct(s.progress)}</b></div>
        <div class="bar"><span style="width:${((s.progress || 0) * 100).toFixed(1)}%"></span></div>
        <div class="small">Estimated finish: ${finish}</div>
        <div class="small muted">Planned finish ${fmtDate(p.target_completion_date)} · ${s.photos} photo(s)</div>
      </a>
      <button type="button" class="card-del" data-id="${p.id}" data-name="${p.name}"
              title="Delete project" aria-label="Delete project ${p.name}">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6"/>
        </svg>
      </button>
    </div>`;
}
