// Entry point: session check, hash router and the top bar.
import { api } from "./api.js";
import { $, errorBox, html, loading, setHTML } from "./ui.js";
import * as login from "./pages/login.js";
import * as projects from "./pages/projects.js";
import * as newProject from "./pages/new-project.js";
import * as project from "./pages/project.js";
import * as photo from "./pages/photo.js";

const state = { user: null };
const ROUTES = [
  { re: /^\/login$/, page: login, public: true },
  { re: /^\/$/, page: projects },
  { re: /^\/new$/, page: newProject },
  { re: /^\/p\/([a-f0-9]{32})$/, page: project },
  { re: /^\/photo\/([a-f0-9]{32})$/, page: photo },
];
let renderToken = 0;

const topbar = () => html`
  <header class="topbar"><div class="inner">
    <a class="brand" href="#/"><span class="brand-mark">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linejoin="round" aria-hidden="true"><path d="M3 21h18M6 21V10l6-5 6 5v11"/></svg>
    </span>SiteScope</a>
    <span class="user">${state.user.name}</span>
    <button type="button" class="btn small" id="logout">Sign out</button>
  </div></header>
  <main class="page" id="page"></main>`;

async function route() {
  const token = ++renderToken;
  const path = (location.hash.slice(1) || "/").split("?")[0] || "/";
  const match = ROUTES.map((r) => ({ r, m: path.match(r.re) })).find((x) => x.m);
  const app = $("#app");
  if (!match) return (location.hash = "#/");
  const { r, m } = match;
  if (!r.public && !state.user) return (location.hash = "#/login");
  if (r.public && state.user) return (location.hash = "#/");
  const ctx = { params: m.slice(1), state, alive: () => token === renderToken };
  if (r.public) {
    app.dataset.user = "";
    return r.page.render(app, ctx);
  }
  if (app.dataset.user !== state.user.id) {
    setHTML(app, topbar());
    app.dataset.user = state.user.id;
    $("#logout").addEventListener("click", async () => {
      await api("/auth/logout", { method: "POST" }).catch(() => {});
      state.user = null;
      location.hash = "#/login";
    });
  }
  const page = $("#page");
  setHTML(page, loading());
  window.scrollTo(0, 0);
  try {
    await r.page.render(page, ctx);
  } catch (err) {
    if (ctx.alive()) setHTML(page, errorBox(err));
    console.error(err);
  }
}

window.addEventListener("auth:required", () => {
  state.user = null;
  location.hash = "#/login";
});

(async function boot() {
  try {
    state.user = (await api("/auth/session")).user;
  } catch {
    state.user = null;
  }
  window.addEventListener("hashchange", route);
  route();
})();
