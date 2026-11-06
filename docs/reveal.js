// Landing: los bloques aparecen al bajar, los números cuentan y un aviso invita a deslizar.
// Sin JS (o con movimiento reducido) todo queda visible desde el principio.
(() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce || !("IntersectionObserver" in window)) return;

  // Qué aparece, y con qué escalonado entre hermanos (ms).
  const groups = [
    [".facts > div", 90],
    [".section-title", 0],
    [".module-copy", 0],
    [".module-shots .phone", 140],
    [".hermes, .agent-copy", 120],
    [".chat .msg, .chat-note", 220],
    [".cards li", 90],
    [".stack-list li", 40],
    [".stack-section p, .footer", 0],
  ];

  const fold = innerHeight * 0.92;
  const io = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.add("is-in");
      io.unobserve(entry.target);
    }
  }, { rootMargin: "0px 0px -8% 0px" });

  for (const [selector, step] of groups) {
    const counts = new Map();
    for (const el of document.querySelectorAll(selector)) {
      if (el.getBoundingClientRect().top < fold) continue; // lo que ya se ve, no parpadea
      const i = counts.get(el.parentElement) ?? 0;
      counts.set(el.parentElement, i + 1);
      el.style.setProperty("--reveal-delay", `${i * step}ms`);
      el.setAttribute("data-reveal", "");
      io.observe(el);
    }
  }

  // Números de "en números": cuentan de 0 al valor cuando aparecen.
  const counter = new IntersectionObserver((entries) => {
    for (const { isIntersecting, target } of entries) {
      if (!isIntersecting) continue;
      counter.unobserve(target);
      const end = Number(target.dataset.count);
      const start = performance.now();
      const tick = (now) => {
        const t = Math.min(1, (now - start) / 900);
        target.textContent = Math.round(end * (1 - (1 - t) ** 3));
        if (t < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }
  }, { threshold: 0.6 });
  for (const el of document.querySelectorAll(".facts strong")) {
    el.dataset.count = el.textContent.trim();
    el.textContent = "0";
    counter.observe(el);
  }

  // Aviso "Deslizá hacia abajo": se va apenas empezás a bajar.
  const hint = document.querySelector(".scroll-hint");
  if (hint) {
    const update = () => hint.classList.toggle("is-gone", scrollY > 60);
    hint.hidden = false;
    requestAnimationFrame(() => hint.classList.add("is-ready"));
    addEventListener("scroll", update, { passive: true });
    update();
  }
})();
