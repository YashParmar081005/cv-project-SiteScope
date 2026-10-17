// Project page: details, estimated completion, progress chart, add a photo, photo list.
import { api, get } from "../api.js";
import { progressChart } from "../charts.js";
import { $, duration, fmtDate, html, pct, raw, setHTML, titleCase, toast, todayISO } from "../ui.js";
import { CONSTRUCTION_TYPES, validateUpload } from "../validation.js";

export async function render(el, ctx) {
  const id = ctx.params[0];
  const [p, prog, fc, photos] = await Promise.all([get(`/projects/${id}`), get(`/projects/${id}/progress`),
    get(`/projects/${id}/forecast`), get(`/projects/${id}/observations`)]);
  if (!ctx.alive()) return;

  setHTML(el, html`
    <div class="head">
      <div>
        <a href="#/">← My projects</a>
        <h1 style="margin-top:6px">${p.name}</h1>
        <p class="muted">${CONSTRUCTION_TYPES[p.construction_type]}${p.location ? ` · ${p.location}` : ""} ·
          planned ${fmtDate(p.planned_start_date)} → ${fmtDate(p.target_completion_date)}</p>
        ${p.description ? html`<p style="margin-top:6px">${p.description}</p>` : ""}
      </div>
      <a class="btn" href="/api/projects/${id}/report.pdf" download>Download project report (PDF)</a>
    </div>
    <div class="grid">
      <section class="card">${estimateCard(p, fc)}</section>
      <section class="card">
        <h2>Progress</h2>
        <div class="row" style="justify-content:space-between"><span class="big">${pct(p.summary.progress)}</span>
          <span class="muted small">${p.summary.progress === null ? "no confirmed photo yet" : `as of ${fmtDate(p.summary.progress_date)}`}</span></div>
        ${raw(progressChart({ planned: prog.planned_curve.points, snapshots: prog.snapshots, forecast: fc, today: todayISO() }))}
        <div class="legend"><span>- - planned</span><span style="color:var(--accent)">● confirmed progress</span><span style="color:var(--violet)">··· estimate</span></div>
      </section>
    </div>
    <section class="card">
      <h2>Add a site photo</h2>
      <p class="muted small" style="margin:-6px 0 12px">The photo is analysed with classical computer vision (colour, edges, lines,
        texture, frequency…) and compared with trained reference photos to estimate the construction stage.</p>
      <form id="upload" novalidate>
        <div class="dropzone" id="drop" tabindex="0" role="button" aria-label="Choose a site photo">
          <div><b>Drop a site photo here</b> or click to choose</div><div id="preview"></div>
          <input type="file" name="file" accept="image/jpeg,image/png,image/webp,image/bmp" hidden>
        </div>
        <span class="err" data-err="file"></span>
        <div class="row" style="margin-top:12px;align-items:flex-end">
          <label class="field" style="flex:1;min-width:200px">Date the photo was taken
            <input type="date" name="capture_date" value="${todayISO()}" max="${todayISO()}"><span class="err" data-err="capture_date"></span></label>
          <button class="btn primary" type="submit">Analyse photo</button>
        </div>
        <div id="upload-error" style="margin-top:10px"></div>
      </form>
    </section>
    <section class="card">
      <h2>Photos (${photos.length})</h2>
      ${photos.length ? photos.map((o) => photoRow(o, p)) : html`<p class="muted">No photos yet.</p>`}
    </section>
    <div class="actions"><button class="btn danger" id="delete-project">Delete project</button></div>`);

  const form = $("#upload", el);
  const drop = $("#drop", el);
  let file = null;
  const choose = (f) => {
    file = f;
    setHTML($("#preview", el), f ? html`<small>${f.name}</small><img id="preview-img" alt="Selected photo">` : "");
    if (f) $("#preview-img", el).src = URL.createObjectURL(f);
  };
  drop.addEventListener("click", () => form.file.click());
  drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); form.file.click(); } });
  form.file.addEventListener("change", () => choose(form.file.files[0] || null));
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); choose(e.dataTransfer.files[0] || null); });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const errors = validateUpload({ file, captureDate: form.capture_date.value }, { today: todayISO() });
    form.querySelectorAll("[data-err]").forEach((s) => { s.textContent = errors[s.dataset.err] || ""; });
    if (Object.keys(errors).length) return;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    button.textContent = "Analysing (computer-vision pipeline)…";
    setHTML($("#upload-error", el), "");
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("capture_date", form.capture_date.value);
      const obs = await api(`/projects/${id}/observations`, { method: "POST", form: fd });
      location.hash = `#/photo/${obs.id}`;
    } catch (err) {
      setHTML($("#upload-error", el), html`<div class="banner error">${err.message}</div>`);
      button.disabled = false;
      button.textContent = "Analyse photo";
    }
  });

  el.querySelectorAll("[data-delete]").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm("Delete this photo? The estimate will be recalculated.")) return;
    await api(`/observations/${b.dataset.delete}`, { method: "DELETE" });
    toast("Photo deleted.", "ok");
    render(el, ctx);
  }));
  $("#delete-project", el).addEventListener("click", async () => {
    if (!confirm(`Delete project "${p.name}" and all its photos? This cannot be undone.`)) return;
    await api(`/projects/${id}`, { method: "DELETE" });
    toast("Project deleted.", "ok");
    location.hash = "#/";
  });
}

function estimateCard(p, fc) {
  const how = html`<details><summary>How is this estimated?</summary><ul>
    <li>Each photo is analysed with computer vision and its construction stage is confirmed; stages have fixed weights (e.g. structure = 35 % of the work).</li>
    <li>Progress = the stages finished + how far the current stage is.</li>
    <li>That progress is compared with the planned schedule (Earned Schedule) and with the trend between photos, then projected to 100 %.</li>
    ${fc.warnings.map((w) => html`<li>${w}</li>`)}</ul></details>`;
  const title = html`<h2>Estimated completion</h2>`;
  if (fc.status === "estimated") {
    const late = fc.predicted_delay_days;
    return html`${title}
      <div class="big">${fmtDate(fc.estimated_completion_date)}</div>
      <div class="row" style="margin-top:6px">
        ${late > 0 ? html`<span class="badge bad">${late} days late</span>` : late < 0 ? html`<span class="badge ok">${-late} days early</span>` : html`<span class="badge ok">on time</span>`}
        <span class="badge ${fc.confidence === "medium" ? "ok" : "warn"}">${fc.confidence} confidence</span></div>
      <dl class="facts">
        <dt>Planned finish</dt><dd>${fmtDate(p.target_completion_date)}</dd>
        <dt>Work left</dt><dd>≈ ${duration(fc.remaining_days)} after the last confirmed photo</dd>
        ${fc.range ? html`<dt>Likely range</dt><dd>${fmtDate(fc.range.earliest)} – ${fmtDate(fc.range.latest)}</dd>` : ""}
        ${fc.spi_t ? html`<dt>Working speed</dt><dd>${Math.round(fc.spi_t * 100)} % of the planned pace</dd>` : ""}
      </dl>${how}`;
  }
  if (fc.status === "completed") return html`${title}<div class="big">Completed</div><p class="muted">Reached 100 % on ${fmtDate(fc.estimated_completion_date)}.</p>`;
  if (fc.status === "stalled") {
    return html`${title}<div class="big" style="font-size:1.5rem">Work has stalled</div>
      <p class="muted">Progress has not increased recently, so no finish date can be projected.
      ${fc.conditional_date_if_resumed ? `If work resumes at the planned pace: about ${fmtDate(fc.conditional_date_if_resumed)}.` : ""}</p>${how}`;
  }
  if (fc.status === "insufficient_data") {
    return html`${title}<div class="big" style="font-size:1.5rem">Not enough progress yet</div>
      <p class="muted">${fc.warnings.at(-1) || ""}</p>${how}`;
  }
  return html`${title}<div class="big" style="font-size:1.5rem">No estimate yet</div>
    <p class="muted">Add a site photo below: it is analysed and you confirm its construction stage. Until then only the
      planned finish (${fmtDate(p.target_completion_date)}) is known.</p>`;
}

function photoRow(o, project) {
  const r = o.stage_review;
  const stageName = r && (project.milestones.find((m) => m.key === r.stage_key)?.name || titleCase(r.stage_key));
  const stage = r ? html`<b>${stageName}</b>${r.stage_progress === null || r.stage_progress === undefined ? " · % not set" : ` · ${r.stage_progress}% done`}`
    : html`<span class="badge warn">stage not confirmed</span>`;
  const cv = o.summary;
  const cvText = cv?.phase ? `${cv.phase} (${cv.confidence} confidence)${cv.changed_area_share !== null && cv.changed_area_share !== undefined ? ` · ${(cv.changed_area_share * 100).toFixed(1)}% changed since previous photo` : ""}`
    : o.analysis_error || "analysed";
  return html`<div class="photo">
    <a href="#/photo/${o.id}"><img src="${o.thumbnail_url}" alt="Site photo ${fmtDate(o.capture_date)}" loading="lazy"></a>
    <div><div><b>${fmtDate(o.capture_date)}</b> · ${stage}</div><div class="muted small">Computer vision: ${cvText}</div></div>
    <div class="row"><a class="btn small" href="#/photo/${o.id}">Open analysis</a>
      <button class="btn small danger" data-delete="${o.id}">Delete</button></div>
  </div>`;
}
