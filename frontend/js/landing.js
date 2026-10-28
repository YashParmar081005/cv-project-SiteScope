// Landing page behaviour: live server status, mobile menu, scroll reveal, counters, back-to-top.
// Plain ES module, no dependencies (the app's CSP allows scripts from this origin only).

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ── 1. live server status ────────────────────────────────────────────────
   Hits the real /api/health endpoint so the page shows whether the backend
   is actually up before anyone clicks "Open the app". */
async function checkHealth() {
  const box = $("#status");
  const text = $("#status-text");
  if (!box || !text) return;
  try {
    const res = await fetch("/api/health", { credentials: "same-origin" });
    if (!res.ok) throw new Error(String(res.status));
    const data = await res.json();
    box.classList.add("up");
    text.textContent = `Server running · v${data.version || "1.0.0"}`;
  } catch {
    box.classList.add("down");
    text.textContent = "Server offline — start the backend";
  }
}

/* ── 2. mobile menu ─────────────────────────────────────────────────────── */
function initMenu() {
  const toggle = $("#nav-toggle");
  const links = $("#nav-links");
  if (!toggle || !links) return;

  const setOpen = (open) => {
    links.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  };

  toggle.addEventListener("click", () => setOpen(!links.classList.contains("open")));
  links.addEventListener("click", (e) => { if (e.target.closest("a")) setOpen(false); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });
  document.addEventListener("click", (e) => {
    if (links.classList.contains("open") && !e.target.closest(".nav-inner")) setOpen(false);
  });
}

/* ── 3. reveal sections as they scroll into view ────────────────────────── */
function initReveal() {
  const items = $$(".reveal");
  if (reduced || !("IntersectionObserver" in window)) {
    items.forEach((el) => el.classList.add("in"));
    return;
  }
  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry, i) => {
      if (!entry.isIntersecting) return;
      setTimeout(() => entry.target.classList.add("in"), i * 70);
      io.unobserve(entry.target);
    });
  }, { threshold: 0.12, rootMargin: "0px 0px -40px" });
  items.forEach((el) => io.observe(el));
}

/* ── 4. sticky-nav shadow and back-to-top button ────────────────────────── */
function initScrollChrome() {
  const nav = $("#nav");
  const top = $("#to-top");
  let ticking = false;
  const onScroll = () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      const y = window.scrollY;
      nav?.classList.toggle("scrolled", y > 8);
      top?.classList.toggle("show", y > 600);
      ticking = false;
    });
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
}

checkHealth();
initMenu();
initReveal();
initScrollChrome();
