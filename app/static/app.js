// Números como los escribís: "1.500" son mil quinientos, "0,5" es medio.
function parseNum(text, { thousands = true } = {}) {
  let s = String(text ?? "").replace(/[^\d.,-]/g, "");
  if (!s) return 0;
  if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
  else if (thousands && ((s.match(/\./g) || []).length > 1 || /^-?[1-9]\d{0,2}\.\d{3}$/.test(s))) s = s.replace(/\./g, "");
  const n = Number(s);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

// Formato de edición: no convierte a Number ni redondea lo que todavía se escribe.
function formatMoneyInput(value) {
  const clean = String(value ?? "").replace(/[^\d,]/g, "");
  const [whole, ...decimal] = clean.split(",");
  const integer = whole.replace(/^0+(?=\d)/, "");
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return grouped + (decimal.length ? "," + decimal.join("").slice(0, 2) : "");
}

// Borrar junto a un separador borra una cifra, no un punto que reaparecería.
document.addEventListener("beforeinput", (event) => {
  const input = event.target;
  if (!input.matches?.("input[data-money]") || input.selectionStart !== input.selectionEnd) return;
  const pos = input.selectionStart;
  if (event.inputType === "deleteContentBackward" && input.value[pos - 1] === ".") {
    input.setSelectionRange(Math.max(0, pos - 2), pos);
  } else if (event.inputType === "deleteContentForward" && input.value[pos] === ".") {
    input.setSelectionRange(pos, pos + 2);
  }
}, true);

// Captura: Alpine recibe el valor ya formateado. La posición sigue a las cifras, no a los puntos.
document.addEventListener("input", (event) => {
  const input = event.target;
  if (!input.matches?.("input[data-money]") || event.isComposing) return;
  const raw = input.value;
  const start = input.selectionStart ?? raw.length;
  const end = input.selectionEnd ?? start;
  const formatted = formatMoneyInput(raw);
  const removedZeros = (raw.replace(/[^\d,]/g, "").match(/^0+(?=\d)/) || [""])[0].length;
  const position = (offset) => {
    const count = Math.max(0, raw.slice(0, offset).replace(/[^\d,]/g, "").length - removedZeros);
    if (!count) return 0;
    let seen = 0;
    for (let i = 0; i < formatted.length; i++) {
      if (/[\d,]/.test(formatted[i]) && ++seen === count) return i + 1;
    }
    return formatted.length;
  };
  input.value = formatted;
  input.setSelectionRange(position(start), position(end));
}, true);

const moneyFormat = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 });
const money = (n) => "$ " + moneyFormat.format(Math.round(n * 100) / 100);
const normalize = (name) => name.trim().replace(/\s+/g, " ").toLowerCase();

function shareList(link) {
  if (navigator.share) {
    navigator.share({ text: link.dataset.shareText }).catch(() => {});
    return false;
  }
  return true; // sin Web Share: abre wa.me
}

let itemKey = 0;
// Lo que viene del servidor llega como "3250.5"; acá se escribe "3250,5".
const toLocal = (value) => String(value ?? "").replace(".", ",");
const withKey = (item) => ({ ...item, key: ++itemKey });

document.addEventListener("alpine:init", () => {
  Alpine.data("market", (stateId) => {
    const state = JSON.parse(document.getElementById(stateId).textContent);
    const storageKey = `origo-trip-${state.tripId}`;
    let local = null;
    try { local = JSON.parse(localStorage.getItem(storageKey)); } catch {}
    const source = local?.dirty ? local : state; // si quedó algo sin sincronizar, gana lo del teléfono

    return {
      items: source.items.map((item) => withKey({ ...item,
        price: formatMoneyInput(source === state ? toLocal(item.price) : item.price),
        qty: source === state ? toLocal(item.qty) : item.qty,
      })),
      budget: formatMoneyInput(source === state ? toLocal(source.budget) : source.budget),
      lastPrices: state.lastPrices,
      draft: { name: "", price: "", qty: "", hint: "" },
      status: "Guardado.",
      timer: null,
      money,

      init() { if (local?.dirty) this.sync(); },

      priceOf(item) { return parseNum(item.price); },
      qtyOf(item) { return parseNum(item.qty, { thousands: false }) || 1; },
      fmtQty(item) { return String(this.qtyOf(item)).replace(".", ","); },
      subtotal(item) { return this.priceOf(item) * this.qtyOf(item); },
      get total() { return this.items.reduce((sum, item) => sum + this.subtotal(item), 0); },
      get unpriced() { return this.items.filter((item) => !this.priceOf(item)).length; },
      get budgetValue() { return parseNum(this.budget); },

      hintFor(item) {
        const last = this.lastPrices[normalize(item.name || "")];
        return last ? "antes " + money(Number(last)) : "";
      },
      trend(item) {
        const last = Number(this.lastPrices[normalize(item.name || "")]);
        const now = this.priceOf(item);
        if (!last || !now || last === now) return null;
        const pct = Math.round(((now - last) / last) * 100);
        if (!pct) return null;
        return { up: pct > 0, text: `${pct > 0 ? "▲ subió" : "▼ bajó"} ${Math.abs(pct)}%, antes ${money(last)}` };
      },
      suggest() { this.draft.hint = this.hintFor(this.draft); },

      // Precio solo, o producto solo (para completar después), o las dos cosas.
      add() {
        const name = this.draft.name.trim();
        if (!name && !parseNum(this.draft.price)) return;
        this.items.forEach((item) => (item.fresh = false));
        this.items.unshift(withKey({ name, price: this.draft.price, qty: this.draft.qty || "1", fresh: true }));
        this.draft = { name: "", price: "", qty: "", hint: "" };
        this.$refs.price.focus();
        this.changed();
      },
      remove(index) { this.items.splice(index, 1); this.changed(); },
      confirmRemove(index) {
        const item = this.items[index];
        requestConfirmation(`¿Quitar ${item.name || "este producto"} de la compra?`, () => this.remove(index));
      },

      changed() {
        this.persist(true);
        this.status = "Guardando…";
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.sync(), 600);
      },
      persist(dirty) {
        try {
          const items = this.items.map(({ name, price, qty }) => ({ name, price, qty }));
          localStorage.setItem(storageKey, JSON.stringify({ items, budget: this.budget, dirty }));
        } catch {}
      },
      payload() {
        return {
          budget: String(this.budgetValue || ""),
          items: this.items.map((item) => ({
            name: item.name,
            price: String(this.priceOf(item)),
            qty: String(this.qtyOf(item)),
          })),
        };
      },
      async sync() {
        try {
          const response = await fetch(`/super/compra/${state.tripId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(this.payload()),
          });
          if (!response.ok) throw new Error(response.status);
          this.persist(false);
          this.status = "Guardado.";
          return true;
        } catch {
          this.status = "Sin señal: queda guardado en el teléfono.";
          return false;
        }
      },
      async finish() {
        clearTimeout(this.timer);
        if (!(await this.sync())) return;
        const question = state.isOwner
          ? `¿Guardar ${money(this.total)} como gasto en Súper?`
          : `¿Terminar la compra de ${money(this.total)}?`;
        requestConfirmation(question, () => {
          try { localStorage.removeItem(storageKey); } catch {}
          this.$refs.close.submit();
        });
      },
    };
  });
});

// Gráfico de peso. Se lee de data-* para que funcione igual con navegación htmx.
function drawCharts(root) {
  root.querySelectorAll("canvas[data-chart='weight']").forEach((canvas) => {
    if (canvas.dataset.drawn) return;
    canvas.dataset.drawn = "1";
    const { labels, values } = JSON.parse(canvas.dataset.values);
    const goal = Number(canvas.dataset.goal);
    const css = getComputedStyle(document.documentElement);
    const color = css.getPropertyValue("--pen").trim();
    const grid = css.getPropertyValue("--rule").trim();
    const soft = css.getPropertyValue("--ink-soft").trim();
    const datasets = [{ data: values, borderColor: color, backgroundColor: color, tension: 0.3, pointRadius: 2 }];
    if (goal) datasets.push({ data: labels.map(() => goal), borderColor: css.getPropertyValue("--pos").trim(), borderDash: [6, 4], pointRadius: 0, borderWidth: 1.5 });
    new Chart(canvas, {
      type: "line",
      data: { labels: labels.map((d) => d.slice(8, 10) + "/" + d.slice(5, 7)), datasets },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { maxTicksLimit: 6, color: soft }, grid: { display: false } },
          y: { ticks: { color: soft, maxTicksLimit: 5 }, grid: { color: grid } },
        },
      },
    });
  });
}
document.addEventListener("DOMContentLoaded", () => drawCharts(document));
document.addEventListener("htmx:load", (event) => {
  drawCharts(event.target);
  setupPageChrome();
});

let confirmationCallback = null;
function requestConfirmation(message, callback) {
  const dialog = document.getElementById("confirmation-dialog");
  if (!dialog) return callback?.();
  document.getElementById("confirmation-message").textContent = message;
  confirmationCallback = callback;
  dialog.showModal();
}

function setupPageChrome() {
  const title = document.querySelector("#main-content .page-head h1");
  const compactBar = document.getElementById("compact-bar");
  const compactTitle = document.getElementById("compact-title");
  if (title && compactBar && compactTitle && "IntersectionObserver" in window) {
    compactTitle.textContent = title.textContent.trim().replace(/\s+/g, " ");
    if (window.origoTitleObserver) window.origoTitleObserver.disconnect();
    window.origoTitleObserver = new IntersectionObserver(([entry]) => {
      const shown = !entry.isIntersecting && entry.boundingClientRect.top < 0;
      compactBar.classList.toggle("is-visible", shown);
      compactBar.setAttribute("aria-hidden", String(!shown));
    }, { threshold: 0, rootMargin: "-8px 0px 0px 0px" });
    window.origoTitleObserver.observe(title);
  }

  const hint = document.getElementById("install-hint");
  const ios = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  let dismissed = false;
  try { dismissed = localStorage.getItem("origo-install-dismissed") === "1"; } catch {}
  if (hint && ios && !standalone && !dismissed) hint.hidden = false;
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {}));
}

document.addEventListener("click", (event) => {
  const opener = event.target.closest("[data-dialog-open]");
  if (opener) {
    const dialog = document.getElementById(opener.dataset.dialogOpen);
    if (dialog) {
      dialog.showModal();
      dialog.querySelector("input:not([type=hidden]), select, textarea")?.focus({ preventScroll: true });
    }
  }
  if (event.target.closest("[data-dialog-close]")) event.target.closest("dialog")?.close();
  if (event.target.closest("[data-confirm-cancel]")) {
    document.getElementById("confirmation-dialog")?.close();
    confirmationCallback = null;
  }
  if (event.target.closest("[data-confirm-accept]")) {
    const callback = confirmationCallback;
    confirmationCallback = null;
    document.getElementById("confirmation-dialog")?.close();
    callback?.();
  }
  if (event.target.closest("[data-install-dismiss]")) {
    try { localStorage.setItem("origo-install-dismissed", "1"); } catch {}
    const hint = document.getElementById("install-hint");
    if (hint) hint.hidden = true;
  }
  if (event.target.matches("dialog")) event.target.close();
});

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!form.matches("form[data-confirm]") || form.dataset.confirmed === "true") return;
  event.preventDefault();
  event.stopImmediatePropagation();
  const submitter = event.submitter;
  requestConfirmation(form.dataset.confirm, () => {
    form.dataset.confirmed = "true";
    form.requestSubmit(submitter || undefined);
  });
}, true);

let touchStartY = null;
document.addEventListener("touchstart", (event) => {
  if (event.target.closest("dialog[open]")) touchStartY = event.touches[0]?.clientY ?? null;
}, { passive: true });
document.addEventListener("touchend", (event) => {
  const dialog = event.target.closest("dialog[open]");
  const endY = event.changedTouches[0]?.clientY;
  if (dialog && touchStartY !== null && endY - touchStartY > 100) dialog.close();
  touchStartY = null;
}, { passive: true });

document.addEventListener("DOMContentLoaded", setupPageChrome);
