/* delight.js — tiny helpers for the shared animation layer.
 * No dependencies. Import once; call where a moment of delight helps.
 * Keep it sparing: a count-up on a headline number, a bar reveal, a step
 * transition, a one-line welcome typer. That is enough — more would distract.
 */
const Delight = {
  // Count a number up to `to` in ~0.9s. el: element, to: number, suffix optional.
  countUp(el, to, suffix = "") {
    if (!el) return;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { el.textContent = to + suffix; return; }
    let n = 0; const step = Math.max(1, Math.round(to / 40));
    const t = setInterval(() => {
      n += step; if (n >= to) { n = to; clearInterval(t); }
      el.textContent = n + suffix;
    }, 22);
  },

  // Grow histogram/bar heights. container holds .d-bar elements; counts is an array.
  revealBars(container, counts, { max = null, delay = 60 } = {}) {
    if (!container) return;
    const m = max || Math.max(...counts, 1);
    [...container.querySelectorAll(".d-bar")].forEach((b, i) => {
      const pct = 6 + 92 * (counts[i] || 0) / m;
      setTimeout(() => { b.style.height = pct + "%"; }, 120 + i * delay);
    });
  },

  // Apply a one-shot class then clean up (e.g. a success pop).
  play(el, cls = "d-pop") {
    if (!el) return;
    el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls);
  },

  // Reveal a screen's children with a gentle stagger.
  enter(root, { stagger = 90 } = {}) {
    if (!root) return;
    [...root.children].forEach((c, i) => {
      c.style.setProperty("--d", (i * stagger) / 1000 + "s");
      c.classList.add("d-rise");
    });
  },
};
if (typeof window !== "undefined") window.Delight = Delight;
