// Photo analysis page: result (+ confirm/adjust), every computer-vision step, how the answer was obtained, PDF.
import { get, post, put } from "../api.js";
import { $, duration, fmtDate, html, pct, setHTML, titleCase, toast } from "../ui.js";

const PHASE_NAMES = { earthwork: "Earthwork / site preparation", foundation: "Foundation", structure: "Structure (frame & walls)", finishing: "Finishing & facade" };

function fmt(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : String(+v.toFixed(3));
  if (Array.isArray(v)) return v.map(fmt).join(", ");
  if (typeof v === "object") return Object.entries(v).map(([k, x]) => `${k}: ${fmt(x)}`).join(" · ");
  return String(v);
}

export async function render(el, ctx) {
  const o = await get(`/observations/${ctx.params[0]}`);
  if (!ctx.alive()) return;
  const p = o.project;
  const a = o.analysis;
  const used = o.result?.used;
  const pred = a?.prediction;
  const report = `/api/observations/${o.id}/report.pdf`;

  setHTML(el, html`
    <div class="head">
      <div><a href="#/p/${p.id}">← ${p.name}</a>
        <h1 style="margin-top:6px">Photo analysis · ${fmtDate(o.capture_date)}</h1>
        <p class="muted">${o.image.filename || ""} · ${o.image.width}×${o.image.height} px</p></div>
      <a class="btn primary" href="${report}" download>Download analysis report (PDF)</a>
    </div>
    ${o.analysis_error ? html`<div class="banner error">${o.analysis_error}</div>` : ""}
    <div class="grid">
      <section class="card"><img src="${o.image.url}" alt="Site photo" style="border-radius:10px;width:100%">
        ${pred ? html`<p class="small" style="margin-top:10px">Computer vision: <b>${pred.phase_label}</b>
          <span class="badge ${pred.confidence === "medium" ? "ok" : "warn"}">${pred.confidence} confidence</span></p>` : ""}
        ${a?.change ? html`<p class="small muted" style="margin-top:4px">${a.change.same_viewpoint
          ? `Change since the photo of ${fmtDate(a.change.previous_photo_date)}: ${(a.change.changed_area_share * 100).toFixed(1)}% of the area`
          : `Not compared with the previous photo: ${a.change.reason}`}</p>` : ""}
      </section>
      <section class="card" id="result"></section>
    </div>
    ${simpleSummary(o, used)}
    ${a ? html`
    <section class="card">
      <details class="pipeline">
        <summary>Show how the computer looked at this photo (${a.steps.length} steps)</summary>
        <p class="muted small" style="margin:10px 0 14px">Classical computer vision only (OpenCV + NumPy), no neural network.
          Each step shows the algorithm, why it is used, its parameters, what it measured and its output image.</p>
        <div class="steps">${a.steps.map(stepCard)}</div>
      </details>
    </section>` : ""}
    ${o.explanation.length ? html`
    <section class="card">
      <h2>How we got the answer</h2>
      <div class="explain">${o.explanation.map((s) => html`
        <div class="explain-step"><h3>${s.title}</h3><p>${s.text}</p>
          ${s.rows ? html`<table class="kv ${s.key === "pipeline" ? "path" : ""}">${s.rows.map((r) => html`<tr>${r.map((c) => html`<td>${c}</td>`)}</tr>`)}</table>` : ""}
        </div>`)}</div>
    </section>` : ""}
    <div class="actions"><a class="btn" href="#/p/${p.id}">Back to project</a><a class="btn primary" href="${report}" download>Download analysis report (PDF)</a></div>`);

  drawResult($("#result", el), o, used, ctx);
}

function stepCard(s) {
  const kv = (obj) => Object.entries(obj || {}).map(([k, v]) => html`<tr><td>${titleCase(k)}</td><td>${fmt(v)}</td></tr>`);
  return html`<article class="step">
    <div class="step-head"><span class="num">${s.number}</span><h3>${s.title}</h3></div>
    <p class="algo"><code>${s.algorithm}</code></p>
    <p class="small">${s.purpose}</p>
    ${s.image_url ? html`<img src="${s.image_url}" alt="${s.title} output" loading="lazy">` : ""}
    <div class="kv-grid">
      ${Object.keys(s.params || {}).length ? html`<div><h4>Parameters</h4><table class="kv">${kv(s.params)}</table></div>` : ""}
      ${Object.keys(s.metrics || {}).length ? html`<div><h4>Measured</h4><table class="kv">${kv(s.metrics)}</table></div>` : ""}
    </div>
  </article>`;
}

// Plain-language answer before any algorithm detail: how much is built, how much is left, what is going on now.
function simpleSummary(o, used) {
  const r = o.result;
  if (!r || !used) {
    return html`<section class="card">
      <h2>In simple words</h2>
      <p class="muted">Choose the construction stage in the box above. This will then show how much of the project
        is done, how much is left and when it should finish.</p>
    </section>`;
  }
  const done = Math.round(r.progress * 100);
  const fc = r.forecast;
  const left = fc && fc.remaining_days !== null && fc.remaining_days !== undefined ? duration(fc.remaining_days) : null;
  const finish = fc && (fc.status === "estimated" || fc.status === "completed") ? fmtDate(fc.estimated_completion_date) : null;
  const idx = used.stage_index;
  const stagePct = used.stage_progress;

  return html`<section class="card">
    <h2>In simple words</h2>
    <p class="muted small" style="margin:-6px 0 16px">${used.source === "confirmed"
      ? "Based on the stage you confirmed for this photo."
      : "Based on the stage the computer vision suggests. Confirm it above to save it."}</p>
    <div class="plain-top">
      <div><div class="plain-num">${done}%</div><div class="small muted">of the work is done</div></div>
      <div><div class="plain-num left">${100 - done}%</div><div class="small muted">is still left</div></div>
      ${left ? html`<div><div class="plain-num">${left}</div><div class="small muted">of work still to go</div></div>` : ""}
      ${finish ? html`<div><div class="plain-num">${finish}</div><div class="small muted">expected finish</div></div>` : ""}
    </div>
    <div class="bar plain-bar"><span style="width:${done}%"></span></div>
    <ul class="plain-stages">
      ${o.project.milestones.map((m, i) => html`<li>
        <span class="mark ${i < idx ? "done" : i === idx ? "now" : "todo"}">${i < idx ? "✓" : i === idx ? "•" : ""}</span>
        <b>${m.name}</b>
        <span class="share">${Math.round(m.weight * 100)}% of the job</span>
        <span class="what">${i < idx ? "Finished"
          : i === idx ? (stagePct === null || stagePct === undefined ? "Going on now" : `Going on now · ${stagePct}% of this part done`)
          : "Not started"}</span>
      </li>`)}
    </ul>
    <p class="small muted" style="margin-top:12px">Every part is a different share of the whole job, so finishing a
      big part moves the number more than finishing a small one. ${left ? `At the speed seen so far, the rest takes about ${left}.` : ""}</p>
  </section>`;
}

function estimateBlock(fc, progress, label) {
  if (!fc) return html`<p class="muted">Choose a stage to get an estimate.</p>`;
  const late = fc.predicted_delay_days;
  const date = fc.status === "estimated" || fc.status === "completed" ? fmtDate(fc.estimated_completion_date) : null;
  return html`
    <div class="small muted">${label}</div>
    <div class="big">${date || titleCase(fc.status)}</div>
    ${date ? html`<div class="row" style="margin-top:6px">
      ${late > 0 ? html`<span class="badge bad">${late} days late</span>` : html`<span class="badge ok">${late < 0 ? `${-late} days early` : "on time"}</span>`}
      <span class="badge ${fc.confidence === "medium" ? "ok" : "warn"}">${fc.confidence} confidence</span></div>` : html`<p class="small muted">${fc.warnings.at(-1) || ""}</p>`}
    <dl class="facts">
      <dt>Overall progress</dt><dd>${pct(progress)}</dd>
      ${fc.range ? html`<dt>Likely range</dt><dd>${fmtDate(fc.range.earliest)} – ${fmtDate(fc.range.latest)}</dd>` : ""}
      ${fc.remaining_days !== null && fc.remaining_days !== undefined ? html`<dt>Work left</dt><dd>≈ ${duration(fc.remaining_days)}</dd>` : ""}
      <dt>Planned finish</dt><dd>${fmtDate(fc.target_completion_date)}</dd>
    </dl>`;
}

function drawResult(box, o, used, ctx) {
  const p = o.project;
  const sug = o.stage_suggestion;
  const current = used?.stage_key || "";
  const knownPct = used?.stage_progress;
  setHTML(box, html`
    <h2>Result</h2>
    ${sug ? html`<p class="small"><span class="badge cv">Computer vision</span> suggests
      <b>${p.milestones[sug.stage_index].name} · ${sug.stage_progress}%</b> (${PHASE_NAMES[sug.phase]} phase)</p>` : html`<p class="small muted">No stage suggestion for this photo: choose the stage yourself.</p>`}
    ${used?.source === "confirmed" ? html`<p class="small" style="margin-top:4px"><span class="badge ok">Confirmed</span> ${used.stage_name}
      ${knownPct === null || knownPct === undefined ? "· % not set" : `· ${knownPct}%`}</p>` : ""}
    <div id="estimate" style="margin:12px 0">${estimateBlock(o.result?.forecast, o.result?.progress,
      used?.source === "confirmed" ? "Estimated completion (confirmed)" : "Estimated completion (from the computer-vision result)")}</div>
    <div style="border-top:1px solid var(--line);padding-top:12px;display:flex;flex-direction:column;gap:10px">
      <b>${used?.source === "confirmed" ? "Change the stage" : "Confirm or adjust the result"}</b>
      <label class="field">Construction stage in this photo<select id="stage"><option value="">Choose…</option>
        ${p.milestones.map((m) => html`<option value="${m.key}" ${m.key === current ? "selected" : ""}>${m.name}</option>`)}</select></label>
      <label class="row small" style="font-weight:600"><input type="checkbox" id="unsure" ${knownPct === null || knownPct === undefined ? "checked" : ""}> Not sure how much of this stage is done</label>
      <label class="field" id="pct-field">How much of this stage is done? <b id="pct-val">${knownPct ?? 50}%</b>
        <input type="range" id="pct" min="0" max="100" step="5" value="${knownPct ?? 50}"></label>
      <div class="actions"><button class="btn primary" id="save">${used?.source === "confirmed" ? "Save change" : "Confirm & save"}</button></div>
    </div>`);

  const stageSel = $("#stage", box), unsure = $("#unsure", box), pctInput = $("#pct", box), est = $("#estimate", box);
  let timer = null, seq = 0;
  $("#pct-field", box).hidden = unsure.checked;
  const update = () => {
    $("#pct-field", box).hidden = unsure.checked;
    $("#pct-val", box).textContent = `${pctInput.value}%`;
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (!stageSel.value) return setHTML(est, html`<p class="muted">Choose the stage to see the estimate.</p>`);
      const mine = ++seq;
      try {
        const res = await post(`/projects/${p.id}/forecast/preview`, { observation_id: o.id, stage_key: stageSel.value,
          stage_progress: unsure.checked ? null : Number(pctInput.value) });
        if (mine !== seq) return;
        const s = res.scenarios;
        if (s.length === 1) setHTML(est, estimateBlock(s[0].forecast, s[0].progress, "Estimated completion if you save"));
        else {
          const dates = s.filter((x) => x.forecast.estimated_completion_date).map((x) => x.forecast.estimated_completion_date).sort();
          setHTML(est, html`<div class="small muted">Estimated completion if you save (stage % unknown → range)</div>
            <div class="big" style="font-size:1.5rem">${dates.length ? `${fmtDate(dates[0])} – ${fmtDate(dates.at(-1))}` : "Not enough progress"}</div>
            <p class="small">Overall progress ${pct(s[0].progress)} – ${pct(s[1].progress)}. Earlier date if the stage is nearly finished, later if it has just started.</p>`);
        }
      } catch (err) {
        setHTML(est, html`<div class="banner error">${err.message}</div>`);
      }
    }, 200);
  };
  stageSel.addEventListener("change", update);
  unsure.addEventListener("change", update);
  pctInput.addEventListener("input", update);
  $("#save", box).addEventListener("click", async (e) => {
    if (!stageSel.value) return toast("Choose the construction stage first.", "error");
    e.target.disabled = true;
    try {
      await put(`/observations/${o.id}/review`, { stage_key: stageSel.value, stage_progress: unsure.checked ? null : Number(pctInput.value) });
      toast("Saved: the project estimate is updated and the model learns from this photo.", "ok");
      render(box.closest("#page") || document.querySelector("#page"), ctx);
    } catch (err) {
      toast(err.message, "error");
      e.target.disabled = false;
    }
  });
}
