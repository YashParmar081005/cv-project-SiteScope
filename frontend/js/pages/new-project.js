// Add a project: name, type, location, details and the planned schedule.
import { post } from "../api.js";
import { $, html, setHTML, toast } from "../ui.js";
import { CONSTRUCTION_TYPES, validateProject } from "../validation.js";

export async function render(el) {
  setHTML(el, html`
    <div class="head"><div><a href="#/">← My projects</a><h1 style="margin-top:6px">Add project</h1></div></div>
    <form class="card" id="project-form" novalidate style="display:flex;flex-direction:column;gap:14px">
      <div id="form-error"></div>
      <div class="form-grid">
        <label class="field">Project name<input name="name" maxlength="120" placeholder="e.g. Green Park Tower"><span class="err" data-err="name"></span></label>
        <label class="field">Construction type<select name="construction_type">
          ${Object.entries(CONSTRUCTION_TYPES).map(([k, v]) => html`<option value="${k}">${v}</option>`)}</select>
          <span class="err" data-err="construction_type"></span></label>
        <label class="field">Location<input name="location" maxlength="200" placeholder="e.g. Ahmedabad, Gujarat"></label>
        <label class="field">Start date<input type="date" name="planned_start_date"><span class="err" data-err="planned_start_date"></span></label>
        <label class="field">Planned finish date<input type="date" name="target_completion_date"><span class="err" data-err="target_completion_date"></span></label>
      </div>
      <label class="field">Project details (optional)<textarea name="description" rows="3" maxlength="2000" placeholder="e.g. 14-storey residential tower, 120 flats"></textarea></label>
      <p class="muted small">The construction stages (e.g. foundation, structure, finishing) and their planned dates are filled in automatically from the type.</p>
      <div class="actions"><a class="btn" href="#/">Cancel</a><button class="btn primary" type="submit">Create project</button></div>
    </form>`);

  const form = $("#project-form", el);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(form));
    const body = { name: f.name.trim(), construction_type: f.construction_type, location: f.location.trim() || null,
      description: f.description.trim() || null, planned_start_date: f.planned_start_date, target_completion_date: f.target_completion_date };
    const errors = validateProject(body);
    el.querySelectorAll("[data-err]").forEach((s) => { s.textContent = errors[s.dataset.err] || ""; });
    if (Object.keys(errors).length) return;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const project = await post("/projects", body);
      toast("Project created.", "ok");
      location.hash = `#/p/${project.id}`;
    } catch (err) {
      setHTML($("#form-error", el), html`<div class="banner error">${err.message}</div>`);
      button.disabled = false;
    }
  });
  form.name.focus();
}
