/* SKINRUSH — thin front-end client.
   All game logic (case contents & chances, draws, prices, wear, upgrade odds,
   daily rewards, balance) lives in the Django REST backend. This file only
   fetches from /api/... and renders/animates the results. */

// ---------- API helpers ----------
const API = "/api";
const jget = (u) => fetch(u).then((r) => r.json());
const jpost = (u, body) =>
  fetch(u, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  }).then((r) => r.json());

// ---------- small presentation helpers ----------
const IMG = (h) =>
  !h ? "" : h.startsWith("http") ? h : "https://community.akamai.steamstatic.com/economy/image/" + h;
const imgOf = (s) => IMG(s.img || s.image || "");
const fmt = (n) => Number(n).toLocaleString("ru-RU").replace(/,/g, " ");
const rand = (arr) => arr[Math.floor(Math.random() * arr.length)];
const COIN = '<img class="coin-img" src="images/coin.png" alt="coin" />';

// clean line-style SVG icons (no emojis)
const ICON = {
  clipboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg>',
  globe: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.5 2.5 3.8 5.6 3.8 9S14.5 18.5 12 21C9.5 18.5 8.2 15.4 8.2 12 8.2 8.6 9.5 5.5 12 3z"/></svg>',
  user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
  send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4 20-7z"/></svg>',
  users: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3.3"/><path d="M2.8 21a6.2 6.2 0 0 1 12.4 0"/><path d="M16.5 5.2a3.3 3.3 0 0 1 0 6.6"/><path d="M17.8 14.4A6.2 6.2 0 0 1 21.2 21"/></svg>',
  key: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="7.5" cy="15.5" r="4.5"/><path d="M10.7 12.3 20 3"/><path d="M15.5 7.5l3 3"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5 9-11"/></svg>',
};

// ---------- i18n (all strings come from the backend catalog) ----------
let T = {};
let LANG = "uz";
const tr = (key, vars) => {
  let s = T[key] != null ? T[key] : key;
  if (vars) for (const k in vars) s = s.split("{" + k + "}").join(vars[k]);
  return s;
};
function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = tr(el.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => {
    el.placeholder = tr(el.getAttribute("data-i18n-ph"));
  });
}

// ================= CASES =================
const casesGrid = document.getElementById("casesGrid");
let CASES = [];

function renderCases(list) {
  casesGrid.innerHTML = "";
  list.forEach((c) => {
    const el = document.createElement("div");
    el.className = "case";
    el.style.setProperty("--rc", c.color);
    el.innerHTML = `
      <div class="case__art">
        <img class="case__img" src="${c.image}?v=2" alt="${c.name}" loading="lazy"
             onerror="this.style.display='none';this.nextElementSibling.style.display='flex';" />
        <div class="case__crate" style="display:none"><span class="case__label">${c.name}</span></div>
      </div>
      <div class="case__meta">
        <div class="case__name">${c.name}</div>
        <div class="case__stats">
          <span class="pill pill--price">${fmt(c.price)} ${COIN}</span>
        </div>
      </div>`;
    el.addEventListener("click", () => openCase(c));
    casesGrid.appendChild(el);
  });
}

async function loadCases(query = "") {
  CASES = await jget(`${API}/cases/${query}`);
  renderCases(CASES);
}

// ---------- Search (filtered by the backend) ----------
const caseSearch = document.getElementById("caseSearch");
const caseMin = document.getElementById("caseMin");
const caseMax = document.getElementById("caseMax");
let searchTimer;
function filterCases() {
  const p = new URLSearchParams();
  const q = caseSearch.value.trim();
  if (q) p.set("q", q);
  if (caseMin.value) p.set("min", caseMin.value);
  if (caseMax.value) p.set("max", caseMax.value);
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadCases(`?${p.toString()}`), 180);
}
[caseSearch, caseMin, caseMax].forEach((el) => el.addEventListener("input", filterCases));

// ================= TOP DROPS strip =================
const topTrack = document.getElementById("topTrack");
async function buildTopDrops() {
  const drops = await jget(`${API}/top-drops/`);
  const skins = drops.map((d) => d.skin);
  const items = skins.sort(() => Math.random() - 0.5).slice(0, 24);
  const all = [...items, ...items]; // duplicate for a seamless marquee
  topTrack.innerHTML = all
    .map(
      (s) => `
    <div class="drop" style="--rc:${s.color}">
      <img class="drop__img" src="${imgOf(s)}" alt="" loading="lazy" />
      <div class="drop__name">${s.name}</div>
    </div>`
    )
    .join("");
}

// ================= Online counter =================
const onlineEl = document.getElementById("onlineCount");
async function pollOnline() {
  try {
    const s = await jget(`${API}/stats/`);
    onlineEl.textContent = fmt(s.online);
  } catch (_) {}
}

// ================= Count-up user stats =================
function countUp(el, target) {
  const dur = 1600,
    start = performance.now();
  (function step(now) {
    const p = Math.min(1, (now - start) / dur);
    el.textContent = fmt(Math.floor(target * (1 - Math.pow(1 - p, 3))));
    if (p < 1) requestAnimationFrame(step);
  })(start);
}

// user state (coins etc.) — sourced from the backend session
let state = { balance: 0, streak: 0, invited: 0, total_won: 0 };
const coinStatEl = document.querySelector(".stats--user .stat__num.grad-gold");
const streakStatEl = document.querySelector(".stats--user .stat__num.grad-violet");
const invitedStatEl = document.querySelector(".stats--user .stat__num.grad-blue");
const wonStatEl = document.querySelector(".stats--user .stat__num.grad-green");

function paintBalance() {
  if (coinStatEl) coinStatEl.textContent = fmt(state.balance);
  if (wonStatEl) wonStatEl.textContent = fmt(state.total_won);
}
async function loadMe(animate) {
  state = await jget(`${API}/me/`);
  if (animate) {
    countUp(coinStatEl, state.balance);
    countUp(streakStatEl, state.streak);
    countUp(invitedStatEl, state.invited);
    countUp(wonStatEl, state.total_won);
  } else {
    paintBalance();
    if (streakStatEl) streakStatEl.textContent = fmt(state.streak);
    if (invitedStatEl) invitedStatEl.textContent = fmt(state.invited);
  }
}

// ================= CASE OPENING =================
// ================= SOUND (synthesized, no external files) =================
const Sound = (function () {
  let ctx = null;
  let muted = localStorage.getItem("sr_muted") === "1";
  function ac() {
    if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  }
  function tick() {
    if (muted) return;
    const c = ac(), t = c.currentTime;
    const o = c.createOscillator(), g = c.createGain();
    o.type = "square";
    o.frequency.value = 1050 + Math.random() * 250;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.12, t + 0.004);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.06);
    o.connect(g).connect(c.destination);
    o.start(t); o.stop(t + 0.07);
  }
  function win() {
    if (muted) return;
    const c = ac(), t0 = c.currentTime;
    [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => {
      const o = c.createOscillator(), g = c.createGain(), t = t0 + i * 0.09;
      o.type = "triangle";
      o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.22, t + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.4);
      o.connect(g).connect(c.destination);
      o.start(t); o.stop(t + 0.42);
    });
  }
  return {
    ac, tick, win,
    isMuted: () => muted,
    toggle() { muted = !muted; localStorage.setItem("sr_muted", muted ? "1" : "0"); return muted; },
  };
})();

const soundToggle = document.getElementById("soundToggle");
function paintSoundToggle() {
  const on = !Sound.isMuted();
  soundToggle.classList.toggle("is-on", on);
  soundToggle.setAttribute("aria-checked", String(on));
}
function flipSound() {
  Sound.ac(); // unlock/prime audio on the gesture
  Sound.toggle();
  paintSoundToggle();
}
soundToggle.addEventListener("click", flipSound);
soundToggle.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); flipSound(); }
});
paintSoundToggle();

const caseView = document.getElementById("caseView");
const rouletteBox = document.getElementById("roulette");
const rouletteTrack = document.getElementById("rouletteTrack");
const modalCrate = document.getElementById("modalCrate");
const modalCaseName = document.getElementById("modalCaseName");
const modalCasePrice = document.getElementById("modalCasePrice");
const caseHero = document.getElementById("caseHero");
const caseActions = document.getElementById("caseActions");

// wear name -> short badge (Field-Tested -> FT)
const WEAR_ABBR = {
  "Factory New": "FN", "Minimal Wear": "MW", "Field-Tested": "FT",
  "Well-Worn": "WW", "Battle-Scarred": "BS",
};
const wearAbbr = (w) =>
  WEAR_ABBR[w] || (w ? w.split(/\s+/).map((x) => x[0]).join("").toUpperCase().slice(0, 2) : "");
const modalResult = document.getElementById("modalResult");
const revealBox = document.getElementById("revealBox");
const contentsGrid = document.getElementById("contentsGrid");
const contentsCount = document.getElementById("contentsCount");
const spinBtn = document.getElementById("spinBtn");
const sellBtn = document.getElementById("sellBtn");
const viewSkinBtn = document.getElementById("viewSkinBtn");
let currentCase = null,
  currentContents = [],
  spinning = false,
  currentWinner = null;
const ITEM_W = 124; // 114 width + 10 gap

function skinItem(s) {
  return `<div class="roul-item" style="--rc:${s.color}">
      <img class="roul-item__img" src="${imgOf(s)}" alt="" loading="lazy" />
      <div class="roul-item__name">${s.name}</div>
    </div>`;
}

function showReveal(skin) {
  const parts = skin.name.split(" | ");
  const weapon = skin.weapon || parts[0];
  const finish = parts[1] || "";
  const wear = skin.wear || { name: "—", float: "—" };
  revealBox.style.setProperty("--rc", skin.color);
  revealBox.innerHTML = `
    <div class="reveal__glow"></div>
    <div class="reveal__imgwrap">
      <div class="reveal__shine"></div>
      <img class="reveal__img" src="${imgOf(skin)}" alt="${skin.name}" />
    </div>
    <div class="reveal__tier">${skin.tier_label}</div>
    <div class="reveal__name">${skin.name}</div>
    <div class="reveal__price">${COIN} ${fmt(skin.price)}</div>
    <div class="reveal__details">
      <div class="reveal__row"><span>${tr("row_weapon")}</span><b>${weapon}</b></div>
      <div class="reveal__row"><span>${tr("row_finish")}</span><b>${finish || "—"}</b></div>
      <div class="reveal__row"><span>${tr("row_wear")}</span><b>${wear.name}</b></div>
      <div class="reveal__row"><span>${tr("row_float")}</span><b>${wear.float}</b></div>
      <div class="reveal__row"><span>${tr("row_rarity")}</span><b style="color:${skin.color}">${skin.tier_label}</b></div>
      <div class="reveal__row"><span>${tr("row_value")}</span><b class="coin">${COIN} ${fmt(skin.price)}</b></div>
    </div>`;
  revealBox.hidden = false;
  revealBox.classList.remove("is-in");
  void revealBox.offsetWidth; // restart animation
  revealBox.classList.add("is-in");
}
function hideReveal() {
  revealBox.hidden = true;
  revealBox.classList.remove("is-in");
  revealBox.innerHTML = "";
}

function renderContents() {
  contentsCount.textContent = `(${currentContents.length})`;
  contentsGrid.innerHTML = currentContents
    .map((it) => {
      const s = it.skin;
      const ch = it.chance >= 0.1 ? it.chance.toFixed(2) : it.chance.toFixed(3);
      const parts = s.name.split(" | ");
      const weapon = s.weapon || parts[0];
      const finish = s.finish || parts[1] || s.name;
      return `<div class="citem" data-idx="${it.idx}" style="--rc:${s.color}" title="${s.name}">
      <div class="citem__wear">${wearAbbr(s.wear)}</div>
      <div class="citem__chance">${ch}%</div>
      <div class="citem__art"><img class="citem__img" src="${imgOf(s)}" alt="" loading="lazy" /></div>
      <div class="citem__weapon">${weapon}</div>
      <div class="citem__name">${finish}</div>
      <div class="citem__price">${COIN} ${fmt(s.price)}</div>
    </div>`;
    })
    .join("");
}

// idle reel (decorative) built from the case contents
function buildReel(reelSkins) {
  const pool = currentContents.map((it) => it.skin);
  const reel = reelSkins || Array.from({ length: 60 }, () => rand(pool));
  rouletteTrack.style.transition = "none";
  rouletteTrack.style.transform = "translateX(0)";
  rouletteTrack.innerHTML = reel.map(skinItem).join("");
}

// open a skin detail popup from a case-contents item
contentsGrid.addEventListener("click", (e) => {
  const item = e.target.closest(".citem");
  if (!item) return;
  const it = currentContents[+item.dataset.idx];
  if (it) openSkinDetail(it.skin, it.chance);
});

async function openCase(c) {
  currentCase = c;
  spinning = false;
  modalCrate.src = c.image + "?v=2";
  modalCrate.alt = c.name;
  modalCaseName.textContent = c.name;
  modalCasePrice.textContent = fmt(c.price);
  caseHero.hidden = false;      // show the hero (openable state)
  rouletteBox.hidden = true;    // animation hidden until opened
  caseActions.hidden = true;    // sell/view hidden until a win
  modalResult.textContent = "";
  spinBtn.disabled = false;
  spinBtn.textContent = tr("open_btn");
  currentWinner = null;
  hideReveal();

  const data = await jget(`${API}/cases/${c.id}/contents/`);
  currentContents = data.items;
  renderContents();
  buildReel();

  promoEls.forEach((s) => (s.hidden = true));
  casesEl.hidden = true;
  upgradeView.hidden = true;
  caseView.hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

spinBtn.addEventListener("click", async () => {
  if (spinning || !currentCase) return;
  spinning = true;
  spinBtn.disabled = true;
  modalResult.textContent = "";
  hideReveal();
  Sound.ac(); // unlock audio within the user gesture
  caseHero.hidden = true;      // the hero closes...
  caseActions.hidden = true;
  rouletteBox.hidden = false;  // ...and the opening animation takes over

  // The backend decides the winner and returns the reel to land on.
  const res = await jpost(`${API}/cases/${currentCase.id}/open/`);
  const winner = res.winner;
  buildReel(res.reel);

  const viewport = rouletteBox.clientWidth;
  const jitter = Math.random() * 60 - 30;
  const offset = res.winner_index * ITEM_W - viewport / 2 + ITEM_W / 2 + jitter;

  requestAnimationFrame(() => {
    rouletteTrack.style.transition = "transform 5.2s cubic-bezier(.12,.62,.16,1)";
    rouletteTrack.style.transform = `translateX(${-offset}px)`;
  });

  // tick sound synced to the (decelerating) movement of the reel
  const startT = performance.now();
  let lastIdx = 0;
  (function tickLoop(now) {
    if (now - startT > 5300) return;
    const tf = getComputedStyle(rouletteTrack).transform;
    if (tf && tf !== "none") {
      const idx = Math.floor(Math.abs(new DOMMatrixReadOnly(tf).m41) / ITEM_W);
      if (idx > lastIdx) { lastIdx = idx; Sound.tick(); }
    }
    requestAnimationFrame(tickLoop);
  })(startT);

  setTimeout(() => {
    spinning = false;
    currentWinner = winner;
    const wEl = rouletteTrack.children[res.winner_index];
    if (wEl) wEl.classList.add("is-winner");
    sellBtn.textContent = `${tr("sell_btn")} · ${fmt(winner.price)}`;
    caseActions.hidden = false;
    showReveal(winner);
    Sound.win();
    showToast(tr("toast_win", { name: winner.name, price: fmt(winner.price) }));
  }, 5300);
});

function resetOpenState() {
  hideReveal();
  modalResult.textContent = "";
  currentWinner = null;
  spinning = false;
  spinBtn.disabled = false;
  spinBtn.textContent = tr("open_btn");
  caseActions.hidden = true;   // hide sell/view
  rouletteBox.hidden = true;   // hide the animation
  caseHero.hidden = false;     // bring the hero back (openable again)
  buildReel();
}

// sell the dropped skin for coins (backend credits the balance)
async function sellCurrent() {
  if (currentWinner) {
    const res = await jpost(`${API}/sell/`, { skin_id: currentWinner.id });
    if (res.balance != null) {
      state.balance = res.balance;
      state.total_won = res.total_won;
      paintBalance();
    }
    showToast(tr("toast_sold", { name: currentWinner.name, price: fmt(res.sold) }));
  }
  resetOpenState();
}

sellBtn.addEventListener("click", () => {
  if (!spinning) sellCurrent();
});

viewSkinBtn.addEventListener("click", () => {
  if (!currentWinner) return;
  const it = currentContents.find((x) => x.skin.name === currentWinner.name);
  openSkinDetail(currentWinner, it ? it.chance : null);
});

// ================= Skin detail popup =================
const skinModal = document.getElementById("skinModal");
const skinModalCard = document.getElementById("skinModalCard");

function openSkinDetail(skin, chance) {
  const parts = skin.name.split(" | ");
  const weapon = skin.weapon || parts[0];
  const finish = parts[1] || "";
  const isKnifeGlove = skin.name.startsWith("★");
  const type = isKnifeGlove ? tr("type_knife") : tr("type_weapon");
  skinModalCard.style.setProperty("--rc", skin.color);
  skinModalCard.innerHTML = `
    <button class="skin-modal__close" data-skinclose>&times;</button>
    <div class="skin-modal__glow"></div>
    <div class="skin-modal__imgwrap"><img src="${imgOf(skin)}" alt="${skin.name}" /></div>
    <div class="skin-modal__tier">${skin.tier_label}</div>
    <div class="skin-modal__name">${skin.name}</div>
    <div class="skin-modal__price">${COIN} ${fmt(skin.price)}</div>
    <div class="skin-modal__rows">
      <div><span>${tr("row_weapon")}</span><b>${weapon}</b></div>
      <div><span>${tr("row_finish")}</span><b>${finish || "—"}</b></div>
      <div><span>${tr("row_type")}</span><b>${type}</b></div>
      <div><span>${tr("row_rarity")}</span><b style="color:${skin.color}">${skin.tier_label}</b></div>
      ${chance != null ? `<div><span>${tr("row_drop_chance")}</span><b>${chance >= 0.1 ? chance.toFixed(2) : chance.toFixed(3)}%</b></div>` : ""}
      <div><span>${tr("row_wears_all")}</span><b>FN · MW · FT · WW · BS</b></div>
      <div><span>${tr("row_value")}</span><b>${COIN} ${fmt(skin.price)}</b></div>
    </div>`;
  skinModal.hidden = false;
}
skinModal.addEventListener("click", (e) => {
  if (e.target.closest("[data-skinclose]")) skinModal.hidden = true;
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !skinModal.hidden) skinModal.hidden = true;
});

document.querySelectorAll("[data-back]").forEach((el) => el.addEventListener("click", backToCases));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !caseView.hidden) backToCases();
});
function backToCases() {
  caseView.hidden = true;
  const active = document.querySelector(".nav__item.is-active")?.dataset.tab || "keyslar";
  showView(active);
}

// ================= Nav / views =================
const promoEls = [document.getElementById("bonuslar"), document.querySelector(".stats--user")];
const casesEl = document.querySelector(".cases-section");
const upgradeView = document.getElementById("upgradeView");

function showView(tab) {
  const isBonus = tab === "bonuslar";
  const isUpgrade = tab === "yaxshilash";
  caseView.hidden = true;
  promoEls.forEach((s) => (s.hidden = !isBonus));
  casesEl.hidden = isUpgrade;
  upgradeView.hidden = !isUpgrade;
  if (isUpgrade) loadUpgrade();
  window.scrollTo({ top: 0, behavior: "smooth" });
}
document.getElementById("nav").addEventListener("click", (e) => {
  const btn = e.target.closest(".nav__item");
  if (!btn) return;
  document.querySelectorAll(".nav__item").forEach((b) => b.classList.remove("is-active"));
  btn.classList.add("is-active");
  const tab = btn.dataset.tab;
  showView(tab);
  if (tab !== "bonuslar" && tab !== "keyslar" && tab !== "yaxshilash") {
    showToast(tr("toast_section"));
  }
});
document.getElementById("loginBtn").addEventListener("click", () => showToast(tr("toast_login")));

// ---------- Language switcher ----------
// Little rounded SVG flags (self-contained, render the same on every OS).
const FLAGS = {
  uz: '<svg viewBox="0 0 24 16"><defs><clipPath id="fuz"><rect width="24" height="16" rx="3"/></clipPath></defs><g clip-path="url(#fuz)"><rect width="24" height="16" fill="#fff"/><rect width="24" height="5.1" fill="#1eb53a"/><rect y="10.9" width="24" height="5.1" fill="#0099b5"/><rect y="4.7" width="24" height="0.5" fill="#ce1126"/><rect y="10.5" width="24" height="0.5" fill="#ce1126"/><circle cx="5" cy="2.6" r="1.7" fill="#fff"/><circle cx="5.8" cy="2.6" r="1.4" fill="#0099b5"/></g></svg>',
  ru: '<svg viewBox="0 0 24 16"><defs><clipPath id="fru"><rect width="24" height="16" rx="3"/></clipPath></defs><g clip-path="url(#fru)"><rect width="24" height="16" fill="#fff"/><rect y="5.33" width="24" height="5.34" fill="#0039a6"/><rect y="10.67" width="24" height="5.33" fill="#d52b1e"/></g></svg>',
  en: '<svg viewBox="0 0 24 16"><defs><clipPath id="fen"><rect width="24" height="16" rx="3"/></clipPath></defs><g clip-path="url(#fen)"><rect width="24" height="16" fill="#fff"/><rect x="9.5" width="5" height="16" fill="#ce1124"/><rect y="5.5" width="24" height="5" fill="#ce1124"/></g></svg>',
};
const LANG_NAMES = { uz: "O‘zbekcha", ru: "Русский", en: "English" };
const LANG_ORDER = ["uz", "ru", "en"];

const langWrap = document.querySelector(".lang-wrap");
const langBtn = document.getElementById("langBtn");
const langLabel = document.getElementById("langLabel");
const langFlag = document.getElementById("langFlag");
const langMenu = document.getElementById("langMenu");

langMenu.innerHTML = LANG_ORDER.map(
  (code) => `<button class="lang-menu__item" data-lang="${code}">
      <span class="flag">${FLAGS[code]}</span>
      <span class="lang-menu__name">${LANG_NAMES[code]}</span>
      <span class="lang-menu__check" aria-hidden="true"><svg viewBox="0 0 16 16"><path d="M3 8.5 6.5 12 13 4.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
    </button>`
).join("");

function closeLangMenu() {
  langMenu.hidden = true;
  langWrap.classList.remove("is-open");
  langBtn.setAttribute("aria-expanded", "false");
}
function updateLangUI() {
  langLabel.textContent = LANG.toUpperCase();
  langFlag.innerHTML = FLAGS[LANG] || "";
  langMenu.querySelectorAll(".lang-menu__item").forEach((el) => {
    el.classList.toggle("is-active", el.dataset.lang === LANG);
  });
}

langBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  const open = langMenu.hidden;
  langMenu.hidden = !open;
  langWrap.classList.toggle("is-open", open);
  langBtn.setAttribute("aria-expanded", String(open));
});
langMenu.addEventListener("click", (e) => {
  const item = e.target.closest("[data-lang]");
  if (!item) return;
  closeLangMenu();
  setLanguage(item.dataset.lang);
});
document.addEventListener("click", closeLangMenu);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeLangMenu();
});

async function setLanguage(lang) {
  if (lang === LANG) return;
  const r = await jpost(`${API}/lang/`, { lang });
  T = r.strings;
  LANG = r.lang;
  updateLangUI();
  applyI18n();
  relocalizeDynamic();
  showToast(tr("toast_lang", { lang: LANG.toUpperCase() }));
}

// Re-render JS-generated content after a language change.
function relocalizeDynamic() {
  dailyCtl.reload();
  upg.relocalize();
  if (currentCase) {
    spinBtn.textContent = tr("open_btn");
    if (currentWinner) sellBtn.textContent = `${tr("sell_btn")} · ${fmt(currentWinner.price)}`;
    if (!revealBox.hidden && currentWinner) showReveal(currentWinner);
  }
}

// ================= Toast =================
const toast = document.getElementById("toast");
let toastTimer;
function showToast(msg) {
  toast.textContent = msg;
  toast.classList.add("is-show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("is-show"), 2600);
}

// ================= UPGRADE =================
const upg = (function initUpgrade() {
  const RING_R = 96;
  const CIRC = 2 * Math.PI * RING_R;

  const el = {
    fromSlot: document.getElementById("upgFromSlot"),
    toSlot: document.getElementById("upgToSlot"),
    arc: document.getElementById("upgArc"),
    pointer: document.getElementById("upgPointer"),
    chance: document.getElementById("upgChance"),
    mult: document.getElementById("upgMult"),
    btn: document.getElementById("upgBtn"),
    result: document.getElementById("upgResult"),
    inv: document.getElementById("upgInv"),
    targets: document.getElementById("upgTargets"),
    search: document.getElementById("upgSearch"),
  };

  let inventory = [],
    targets = [],
    fromItem = null,
    toItem = null,
    spinning = false,
    pointerDeg = 0,
    curChance = 0,
    loaded = false;

  const cardHTML = (skin, value) => `
    <div class="upg-card" style="--rc:${skin.color}">
      <div class="upg-card__art"><img src="${imgOf(skin)}" alt="" loading="lazy" /></div>
      <div class="upg-card__name">${skin.name}</div>
      <div class="upg-card__val">${COIN} ${fmt(value)}</div>
    </div>`;

  function renderInventory() {
    el.inv.innerHTML = inventory.length
      ? inventory
          .map(
            (it) => `<div class="upg-pick__item${fromItem && fromItem.uid === it.uid ? " is-sel" : ""}"
          data-uid="${it.uid}">${cardHTML(it.skin, it.value)}</div>`
          )
          .join("")
      : `<div class="upg-empty">${tr("upg_empty")}</div>`;
  }
  function renderTargets() {
    el.targets.innerHTML = targets
      .map(
        (t) => `<div class="upg-pick__item${toItem && toItem.skin.id === t.skin.id ? " is-sel" : ""}"
      data-id="${t.skin.id}">${cardHTML(t.skin, t.value)}</div>`
      )
      .join("");
  }

  function setArc(chance) {
    const win = CIRC * chance;
    el.arc.style.strokeDasharray = `${win} ${CIRC - win}`;
  }

  async function refresh() {
    el.fromSlot.innerHTML = fromItem
      ? cardHTML(fromItem.skin, fromItem.value)
      : `<div class="upg-slot__empty">${tr("upg_pick_inv")}</div>`;
    el.toSlot.innerHTML = toItem
      ? cardHTML(toItem.skin, toItem.value)
      : `<div class="upg-slot__empty">${tr("upg_pick_target")}</div>`;

    if (fromItem && toItem && toItem.value > fromItem.value) {
      // odds are computed on the backend
      const r = await jpost(`${API}/upgrade/compute/`, {
        from_uid: fromItem.uid,
        to_skin_id: toItem.skin.id,
      });
      if (r.valid) {
        curChance = r.chance;
        el.chance.textContent = (r.chance * 100).toFixed(1) + "%";
        el.mult.textContent = "x" + r.mult.toFixed(2);
        setArc(r.chance);
        el.btn.disabled = spinning;
        return;
      }
    }
    curChance = 0;
    el.chance.textContent = "—";
    el.mult.textContent = toItem && fromItem ? tr("upg_need_higher") : tr("upg_pick_target_hint");
    setArc(0);
    el.btn.disabled = true;
  }

  el.inv.addEventListener("click", (e) => {
    const item = e.target.closest("[data-uid]");
    if (!item || spinning) return;
    fromItem = inventory.find((it) => it.uid === +item.dataset.uid);
    renderInventory();
    refresh();
  });
  el.targets.addEventListener("click", (e) => {
    const item = e.target.closest("[data-id]");
    if (!item || spinning) return;
    toItem = targets.find((t) => t.skin.id === +item.dataset.id);
    renderTargets();
    refresh();
  });
  let tSearchTimer;
  el.search.addEventListener("input", () => {
    clearTimeout(tSearchTimer);
    tSearchTimer = setTimeout(loadTargets, 200);
  });

  el.btn.addEventListener("click", async () => {
    if (spinning || el.btn.disabled || !fromItem || !toItem) return;
    spinning = true;
    el.btn.disabled = true;
    el.result.textContent = "";
    el.result.className = "upg-result";

    const res = await jpost(`${API}/upgrade/play/`, {
      from_uid: fromItem.uid,
      to_skin_id: toItem.skin.id,
    });
    if (res.error) {
      spinning = false;
      showToast(res.error);
      refresh();
      return;
    }

    const total = pointerDeg - (pointerDeg % 360) + 360 * 6 + res.landing_deg;
    el.pointer.style.transition = "transform 4.4s cubic-bezier(.15,.6,.15,1)";
    el.pointer.style.transform = `rotate(${total}deg)`;
    pointerDeg = total;

    setTimeout(() => {
      spinning = false;
      inventory = res.inventory;
      if (res.won) {
        el.result.innerHTML = `${tr("upg_result_win", { name: res.target.skin.name })}${COIN} ${fmt(res.target.value)}`;
        el.result.classList.add("is-win");
        showToast(tr("toast_upg_win", { name: res.target.skin.name }));
      } else {
        el.result.textContent = tr("upg_result_lose", { name: fromItem.skin.name });
        el.result.classList.add("is-lose");
        showToast(tr("toast_upg_lose"));
      }
      fromItem = null;
      toItem = null;
      renderInventory();
      refresh();
    }, 4600);
  });

  async function loadTargets() {
    const q = el.search.value.trim();
    const r = await jget(`${API}/upgrade/targets/${q ? "?q=" + encodeURIComponent(q) : ""}`);
    targets = r.targets;
    renderTargets();
  }

  async function load() {
    if (loaded) return;
    loaded = true;
    const r = await jget(`${API}/upgrade/inventory/`);
    inventory = r.inventory;
    renderInventory();
    await loadTargets();
    refresh();
  }

  function relocalize() {
    renderInventory();
    renderTargets();
    refresh();
  }

  return { load, relocalize };
})();
function loadUpgrade() {
  upg.load();
}

// ================= DAILY REWARD + TASKS =================
const dailyCtl = (function initDaily() {
  const daysRow = document.getElementById("daysRow");
  const taskList = document.getElementById("taskList");
  const timerEl = document.getElementById("dailyTimer");
  const claimBtn = document.getElementById("dailyClaim");
  const tasksAll = document.getElementById("tasksAll");
  let timerHandle = null;

  function renderDays(days) {
    if (!daysRow) return;
    daysRow.innerHTML = days
      .map((day) => {
        const badge =
          day.state === "special"
            ? `<img class="day__chest" src="images/icons/chests.png" alt="" />`
            : day.state === "locked"
            ? `<img class="day__lock" src="images/icons/lock.png" alt="" />`
            : day.state === "claimed"
            ? `<div class="day__check">${ICON.check}</div>`
            : "";
        const reward = day.state === "special" ? `<span class="day__key">${tr("day_key")}</span>` : `${day.r} ${COIN}`;
        return `<div class="day day--${day.state}">
          <div class="day__label">${tr("day_label", { n: day.d })}</div>
          <div class="day__mid">${badge}</div>
          <div class="day__reward">${reward}</div>
        </div>`;
      })
      .join("");
  }

  function renderTasks(tasks) {
    if (!taskList) return;
    taskList.innerHTML = tasks
      .map(
        (t) => `
      <div class="task">
        <div class="task__ic">${ICON[t.icon] || ""}</div>
        <div class="task__label">${t.label}</div>
        <div class="task__reward">+${t.reward} ${COIN}</div>
      </div>`
      )
      .join("");
  }

  function startTimer(seconds) {
    if (!timerEl) return;
    if (timerHandle) clearInterval(timerHandle);
    let secs = seconds;
    const tick = () => {
      secs = (secs - 1 + 86400) % 86400;
      const h = String(Math.floor(secs / 3600)).padStart(2, "0");
      const m = String(Math.floor((secs % 3600) / 60)).padStart(2, "0");
      const s = String(secs % 60).padStart(2, "0");
      timerEl.textContent = `${h}:${m}:${s}`;
    };
    timerHandle = setInterval(tick, 1000);
  }

  async function load() {
    const d = await jget(`${API}/daily/`);
    renderDays(d.days);
    renderTasks(d.tasks);
    startTimer(d.timer_seconds);
    if (claimBtn) claimBtn.disabled = d.claimed;
  }

  if (claimBtn) {
    claimBtn.addEventListener("click", async () => {
      if (claimBtn.disabled) return;
      claimBtn.disabled = true;
      const res = await jpost(`${API}/daily/claim/`);
      renderDays(res.days);
      if (res.balance != null) {
        state.balance = res.balance;
        paintBalance();
      }
      showToast(tr("toast_daily", { n: res.reward }));
    });
  }
  if (tasksAll)
    tasksAll.addEventListener("click", () => showToast(tr("toast_tasks_all")));

  return { reload: load };
})();

// ================= BOOT =================
async function boot() {
  // Load translations first so everything renders in the chosen language.
  try {
    const r = await jget(`${API}/i18n/`);
    T = r.strings;
    LANG = r.lang;
    updateLangUI();
    applyI18n();
  } catch (_) {}

  loadCases();
  buildTopDrops();
  setInterval(buildTopDrops, 45000);
  pollOnline();
  setInterval(pollOnline, 3000);
  dailyCtl.reload();
  loadMe(false);

  const statObs = new IntersectionObserver(
    (es) =>
      es.forEach((e) => {
        if (e.isIntersecting) {
          loadMe(true);
          statObs.disconnect();
        }
      }),
    { threshold: 0.4 }
  );
  const statsSection = document.querySelector(".stats--user");
  if (statsSection) statObs.observe(statsSection);
}
boot();
