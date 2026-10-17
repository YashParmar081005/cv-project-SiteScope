import { api } from "../api.js";
import { $, html, setHTML } from "../ui.js";
import { validateCredentials } from "../validation.js";

export async function render(el, { state }) {
  let mode = "login";
  const draw = () => {
    setHTML(el, html`
      <div class="center">
        <form class="card login" id="auth-form" novalidate style="display:flex;flex-direction:column;gap:14px">
          <div class="brand"><span class="brand-mark">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linejoin="round" aria-hidden="true"><path d="M3 21h18M6 21V10l6-5 6 5v11"/></svg>
          </span>SiteScope</div>
          <p class="muted" style="text-align:center">Estimate when a construction project will finish — from site photos.</p>
          <h2>${mode === "login" ? "Sign in" : "Create account"}</h2>
          <div id="form-error"></div>
          ${mode === "register" ? html`<label class="field">Name<input name="name" autocomplete="name"><span class="err" data-err="name"></span></label>` : ""}
          <label class="field">Email<input name="email" type="email" autocomplete="email"><span class="err" data-err="email"></span></label>
          <label class="field">Password<input name="password" type="password" autocomplete="${mode === "login" ? "current-password" : "new-password"}"><span class="err" data-err="password"></span></label>
          <button class="btn primary" type="submit">${mode === "login" ? "Sign in" : "Create account"}</button>
          <p class="muted small" style="text-align:center">${mode === "login" ? "No account?" : "Already registered?"}
            <a href="#" id="switch">${mode === "login" ? "Create one" : "Sign in"}</a></p>
        </form>
      </div>`);
    $("#switch", el).addEventListener("click", (e) => { e.preventDefault(); mode = mode === "login" ? "register" : "login"; draw(); });
    $("#auth-form", el).addEventListener("submit", async (e) => {
      e.preventDefault();
      const data = Object.fromEntries(new FormData(e.target));
      const errors = validateCredentials(data, mode);
      el.querySelectorAll("[data-err]").forEach((s) => { s.textContent = errors[s.dataset.err] || ""; });
      if (Object.keys(errors).length) return;
      const button = e.target.querySelector("button[type=submit]");
      button.disabled = true;
      try {
        state.user = (await api(mode === "login" ? "/auth/login" : "/auth/register", { method: "POST", json: data })).user;
        location.hash = "#/";
      } catch (err) {
        setHTML($("#form-error", el), html`<div class="banner error">${err.message}</div>`);
        button.disabled = false;
      }
    });
    $("input", el).focus();
  };
  draw();
}
