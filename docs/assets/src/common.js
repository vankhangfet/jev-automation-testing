// Shared helpers for deterministic animation (t in seconds)
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const ease = x => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
// 0 -> 1 between a and b (eased)
const ramp = (t, a, b) => ease(clamp((t - a) / (b - a)));
// visible window: fades in at [a, a+d], out at [b-d, b]
const win = (t, a, b, d = 0.4) => Math.min(ramp(t, a, a + d), 1 - ramp(t, b - d, b));
const lerp = (a, b, k) => a + (b - a) * k;
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
function setO(el, o, dy = 0, dx = 0, sc = 1) {
  if (typeof el === "string") el = $(el);
  if (!el) return;
  el.style.opacity = o.toFixed(3);
  el.style.transform = `translate(${dx}px, ${dy}px) scale(${sc})`;
}
// typewriter: reveals el.dataset.full progressively between a and b
function type(el, t, a, b, caret = true) {
  if (typeof el === "string") el = $(el);
  const full = el.dataset.full ?? (el.dataset.full = el.textContent);
  const n = Math.round(full.length * clamp((t - a) / (b - a)));
  const showCaret = caret && t >= a - 0.6 && (t < b + 0.6) && Math.floor(t * 2.5) % 2 === 0;
  el.textContent = full.slice(0, n) + (showCaret ? "▌" : "");
}
// Live preview when opened in a browser (renderer sets window.__manual)
window.addEventListener("load", () => {
  const start = performance.now();
  const dur = window.DURATION || 10;
  const loop = () => {
    if (window.__manual) return;
    window.onFrame(((performance.now() - start) / 1000) % dur);
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
});
