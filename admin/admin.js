/* SKINRUSH custom admin panel — thin client for /api/admin/*. */
const API = "/api/admin";
const jget = (u) => fetch(u).then((r) => r.json());
const jpost = (u, body) =>
  fetch(u, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  }).then(async (r) => ({ ok: r.ok, data: await r.json().catch(() => ({})) }));
const jpostForm = (u, formData) =>
  fetch(u, { method: "POST", body: formData }).then(async (r) => ({
    ok: r.ok,
    data: await r.json().catch(() => ({})),
  }));
const jdel = (u) =>
  fetch(u, { method: "DELETE" }).then(async (r) => ({
    ok: r.ok,
    data: await r.json().catch(() => ({})),
  }));

const IMG = (h) =>
  !h ? "" : h.startsWith("http") ? h : "https://community.akamai.steamstatic.com/economy/image/" + h;
const fmt = (n) => Number(n || 0).toLocaleString("ru-RU").replace(/,/g, " ");
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// short "new message" ding (WebAudio, no asset needed)
function adminDing() {
  try {
    const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
    const c = new AC(), o = c.createOscillator(), g = c.createGain();
    o.connect(g); g.connect(c.destination); o.type = "sine";
    o.frequency.setValueAtTime(880, c.currentTime);
    o.frequency.setValueAtTime(1174, c.currentTime + 0.09);
    g.gain.setValueAtTime(0.0001, c.currentTime);
    g.gain.exponentialRampToValueAtTime(0.14, c.currentTime + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + 0.4);
    o.start(); o.stop(c.currentTime + 0.42);
  } catch (e) {}
}

// fullscreen image viewer for chat receipts
let _lb = null;
function adminLightbox(src) {
  if (!_lb) {
    _lb = document.createElement("div"); _lb.className = "tu-lightbox";
    _lb.innerHTML = "<img alt=''/>";
    _lb.addEventListener("click", () => _lb.classList.remove("is-open"));
    document.body.appendChild(_lb);
  }
  _lb.querySelector("img").src = src;
  _lb.classList.add("is-open");
}

const loginView = document.getElementById("loginView");
const appView = document.getElementById("appView");
const main = document.getElementById("main");

// ---------- auth ----------
async function boot() {
  // Optimistically show the panel if we were logged in (no flash on refresh).
  const cached = localStorage.getItem("sr_admin");
  if (cached) showApp(cached);
  const me = await jget(`${API}/me/`).catch(() => ({ authenticated: false }));
  if (me.authenticated) { if (!cached) showApp(me.username); }
  else { showLogin(); try { localStorage.removeItem("sr_admin"); } catch (_) {} }
}

function showLogin() {
  appView.hidden = true;
  loginView.hidden = false;
}
function showApp(username) {
  loginView.hidden = true;
  appView.hidden = false;
  document.getElementById("whoami").textContent = username || "admin";
  try { localStorage.setItem("sr_admin", username || "admin"); } catch (_) {}
  switchView("dashboard");
}

const loginForm = document.getElementById("loginForm");
const loginError = document.getElementById("loginError");
const loginBtn = document.getElementById("loginBtn");
loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.textContent = "";
  loginBtn.disabled = true;
  const res = await jpost(`${API}/login/`, {
    username: document.getElementById("loginUser").value,
    password: document.getElementById("loginPass").value,
  });
  loginBtn.disabled = false;
  if (res.ok && res.data.authenticated) {
    document.getElementById("loginPass").value = "";
    showApp(res.data.username);
  } else {
    loginError.textContent = res.data.error || "Kirishда xatolik";
  }
});

document.getElementById("logoutBtn").addEventListener("click", async () => {
  await jpost(`${API}/logout/`);
  try { localStorage.removeItem("sr_admin"); } catch (_) {}
  showLogin();
});

// ---------- navigation ----------
document.getElementById("nav").addEventListener("click", (e) => {
  const btn = e.target.closest(".nav-item");
  if (!btn) return;
  switchView(btn.dataset.view);
});

// ---------- mobile drawer ----------
const VIEW_TITLES = {
  dashboard: "Dashboard", users: "Foydalanuvchilar", broadcast: "Broadcast",
  withdraws: "Withdraw so'rovlari",
  topups: "To'lov chat", payadmins: "To'lov adminlar", promos: "Promokodlar",
  channeltasks: "Kanal topshiriqlari", cases: "Keyslar",
};
function setDrawer(open) { document.getElementById("appView").classList.toggle("drawer-open", open); }
document.getElementById("drawerToggle").addEventListener("click", () => setDrawer(true));
document.getElementById("drawerBackdrop").addEventListener("click", () => setDrawer(false));

function switchView(view) {
  if (view !== "topups" && typeof stopTuPoll === "function") stopTuPoll();
  setDrawer(false);                        // close the drawer after picking a page
  const t = document.getElementById("topbarTitle");
  if (t) t.textContent = VIEW_TITLES[view] || "";
  document.querySelectorAll(".nav-item").forEach((b) =>
    b.classList.toggle("is-active", b.dataset.view === view)
  );
  if (view === "dashboard") renderDashboard();
  else if (view === "users") renderUsers();
  else if (view === "broadcast") renderBroadcast();
  else if (view === "withdraws") renderWithdraws();
  else if (view === "topups") renderTopups();
  else if (view === "payadmins") renderPayAdmins();
  else if (view === "promos") renderPromos();
  else if (view === "channeltasks") renderChannelTasks();
  else if (view === "cases") renderCases();
  else if (view === "audit") renderAudit();
}

const dt = (s) => (s ? new Date(s).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
const dOnly = (s) => (s ? new Date(s).toLocaleDateString("ru-RU") : "—");

// ---------- dashboard ----------
async function renderDashboard() {
  main.innerHTML = `<div class="page-head"><div>
      <div class="page-title">Dashboard</div>
      <div class="page-sub">Umumiy ko'rsatkichlar</div>
    </div></div>
    <div class="loading">Yuklanmoqda…</div>`;
  const s = await jget(`${API}/stats/`);
  setWithdrawBadge(s.withdraws_pending);
  setTopupBadge(s.topups_waiting);
  const cards = [
    { n: s.players, label: "Foydalanuvchilar", c: "var(--green)" },
    { n: s.cases, label: "Keyslar", c: "var(--violet)" },
    { n: s.skins, label: "Noyob skinlar", c: "var(--teal)" },
    { n: s.opens, label: "Ochilgan keyslar", c: "var(--pink)" },
    { n: s.items, label: "Jami elementlar", c: "var(--blue)" },
    { n: s.drops, label: "Droplar", c: "var(--gold)" },
  ];
  main.innerHTML = `
    <div class="page-head"><div>
      <div class="page-title">Dashboard</div>
      <div class="page-sub">Umumiy ko'rsatkichlar</div>
    </div></div>
    ${s.topups_waiting ? `
      <div class="alert-card" id="tuAlert">
        <div>
          <div class="alert-card__title">${fmt(s.topups_waiting)} ta to'lov so'rovi kutmoqda</div>
          <div class="alert-card__sub">Oxirgi 24 soatda: <b>${fmt(s.topups_waiting_24h)}</b> ta yangi so'rov</div>
        </div>
        <button class="admin-btn">Ko'rish</button>
      </div>` : ""}
    ${!s.payment_admins ? `
      <div class="alert-card alert-card--bad" id="paAlert">
        <div>
          <div class="alert-card__title">To'lov admini yo'q</div>
          <div class="alert-card__sub">Admin qo'shilmaguncha userlar balansni to'ldira olmaydi.</div>
        </div>
        <button class="admin-btn">Qo'shish</button>
      </div>` : ""}
    ${s.withdraws_pending ? `
      <div class="alert-card" id="wdAlert">
        <div>
          <div class="alert-card__title">${fmt(s.withdraws_pending)} ta withdraw so'rovi kutmoqda</div>
          <div class="alert-card__sub">Oxirgi 24 soatda: <b>${fmt(s.withdraws_pending_24h)}</b> ta yangi so'rov</div>
        </div>
        <button class="admin-btn">Ko'rish</button>
      </div>` : ""}
    <div class="stat-grid">
      ${cards.map((c) => `
        <div class="stat-card" style="--sc:${c.c}">
          <div class="stat-card__num">${fmt(c.n)}</div>
          <div class="stat-card__label">${c.label}</div>
        </div>`).join("")}
    </div>`;
  const go = (id, view) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("click", () => switchView(view));
  };
  go("wdAlert", "withdraws");
  go("tuAlert", "topups");
  go("paAlert", "payadmins");
}

// ---------- withdraws ----------
const WD_STATUS = {
  pending:   { label: "Kutilmoqda",  c: "var(--gold)" },
  approved:  { label: "Tasdiqlandi", c: "var(--blue)" },
  sent:      { label: "Yuborildi",   c: "var(--violet)" },
  completed: { label: "Yakunlandi",  c: "var(--green)" },
  rejected:  { label: "Rad etildi",  c: "var(--pink)" },
};
// Which buttons a row offers, by status: [label, endpoint suffix].
const WD_ACTIONS = {
  pending:  [["✅ Tasdiqlash", "approve"], ["❌ Rad etish", "reject"]],
  approved: [["📤 Yuborildi", "mark-sent"]],
  sent:     [["📥 Tushdi (yakunlash)", "complete"]],
};

function setWithdrawBadge(n) {
  const b = document.getElementById("wdBadge");
  if (!b) return;
  b.textContent = fmt(n);
  b.hidden = !n;
}

let wdFilter = "pending";

async function renderWithdraws() {
  main.innerHTML = `
    <div class="page-head"><div>
      <div class="page-title">Withdraw so'rovlari</div>
      <div class="page-sub">Skinni Steam inventariga chiqarish — qo'lda tasdiqlanadi</div>
    </div></div>
    <div class="filter-row" id="wdFilters"></div>
    <div id="wdBody"><div class="loading">Yuklanmoqda…</div></div>`;
  document.getElementById("wdFilters").addEventListener("click", (e) => {
    const chip = e.target.closest(".filter-chip");
    if (!chip) return;
    wdFilter = chip.dataset.status;
    loadWithdraws();
  });
  loadWithdraws();
}

async function loadWithdraws() {
  const body = document.getElementById("wdBody");
  const d = await jget(`${API}/withdraws/?status=${encodeURIComponent(wdFilter)}`);

  const tabs = [["all", "Hammasi", d.total], ...Object.keys(WD_STATUS).map((k) =>
    [k, WD_STATUS[k].label, d.counts[k] || 0])];
  document.getElementById("wdFilters").innerHTML = tabs.map(([k, label, n]) => `
    <button class="filter-chip ${k === wdFilter ? "is-active" : ""}" data-status="${k}">
      ${label} <span class="filter-chip__n">${fmt(n)}</span>
    </button>`).join("");
  setWithdrawBadge(d.counts.pending || 0);

  if (!d.rows.length) {
    body.innerHTML = `<div class="loading">Bu holatda so'rov yo'q.</div>`;
    return;
  }
  body.innerHTML = `<div class="wd-list">${d.rows.map(wdCard).join("")}</div>`;

  body.querySelectorAll("[data-act]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const { id, act } = btn.dataset;
      if (act === "reject") openRejectModal(+id, btn.dataset.skin);
      else runWithdrawAction(+id, act, {}, btn);
    })
  );
  body.querySelectorAll("[data-copy]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(btn.dataset.copy);
        const old = btn.textContent;
        btn.textContent = "✓ Nusxalandi";
        setTimeout(() => { btn.textContent = old; }, 1200);
      } catch (_) {
        btn.textContent = "Nusxalab bo'lmadi";
      }
    })
  );
}

function wdCard(w) {
  const st = WD_STATUS[w.status] || { label: w.status, c: "#555" };
  const acts = WD_ACTIONS[w.status] || [];
  return `
    <div class="wd-card">
      <div class="wd-card__skin">
        <img class="wd-card__img" src="${IMG(w.skin.image)}" alt=""
             onerror="this.style.visibility='hidden'" />
        <div>
          <div class="cell-name">${esc(w.skin.name)}</div>
          <div class="cell-muted" style="font-size:12px">
            ${esc(w.skin.wear || "—")} · <span class="coin">${fmt(w.skin.price)}</span>
          </div>
          <div class="cell-muted" style="font-size:12px">Key: ${esc(w.case_name || "—")}</div>
        </div>
      </div>

      <div class="wd-card__user">
        <div class="cell-name">${esc(w.player.name)}</div>
        ${w.player.username ? `<div class="cell-muted" style="font-size:12px">@${esc(w.player.username)}</div>` : ""}
        <div class="cell-muted" style="font-size:12px">TG ID: ${w.player.telegram_id || "—"}</div>
        <div class="cell-muted" style="font-size:12px">${dt(w.created_at)}</div>
      </div>

      <div class="wd-card__url">
        <div class="wd-card__url-val" title="${esc(w.trade_url)}">${esc(w.trade_url)}</div>
        <div class="wd-card__url-acts">
          <button class="copy-btn" data-copy="${esc(w.trade_url)}">Nusxalash</button>
          <a class="copy-btn" href="${esc(w.trade_url)}" target="_blank" rel="noopener">Ochish ↗</a>
        </div>
      </div>

      <div class="wd-card__side">
        <span class="status-badge" style="--bc:${st.c}">${st.label}</span>
        ${w.status === "rejected" && w.reject_reason
          ? `<div class="wd-card__reason">Sabab: ${esc(w.reject_reason)}</div>` : ""}
        <div class="wd-card__acts">
          ${acts.map(([label, act]) => `
            <button class="admin-btn ${act === "reject" ? "admin-btn--danger" : ""}"
                    data-id="${w.id}" data-act="${act}" data-skin="${esc(w.skin.name)}">
              ${label}
            </button>`).join("")}
        </div>
      </div>
    </div>`;
}

async function runWithdrawAction(id, act, body, btn) {
  if (btn) btn.disabled = true;
  const res = await jpost(`${API}/withdraws/${id}/${act}/`, body);
  if (res.ok && res.data.ok) {
    loadWithdraws();
    return true;
  }
  if (btn) btn.disabled = false;
  // A 409 means someone else already moved it — reload so the row tells the truth.
  if (res.data.error) {
    const body_ = document.getElementById("wdBody");
    if (body_) {
      const note = document.createElement("div");
      note.className = "wd-error";
      note.textContent = res.data.error;
      body_.prepend(note);
      setTimeout(() => note.remove(), 4000);
    }
    loadWithdraws();
  }
  return false;
}

// ---------- top-up requests ----------
const TU_STATUS = {
  waiting:   { label: "Kutilmoqda", c: "var(--gold)" },
  connected: { label: "Aloqada",    c: "var(--blue)" },
  paid:      { label: "To'landi",   c: "var(--green)" },
  closed:    { label: "Yopilgan",   c: "var(--pink)" },
};
let tuFilter = "all";

function setTopupBadge(n) {
  const b = document.getElementById("tuBadge");
  if (!b) return;
  b.textContent = fmt(n);
  b.hidden = !n;
}

// ---------- top-up chat inbox (many conversations at once) ----------
let tuOpenId = null;      // currently open conversation
let tuSeen = {};          // message id -> rendered element in the open chat
let tuPoll = null;        // polling timer
let tuPrevUnread = -1;    // last seen total unread (for the new-message ding)

function stopTuPoll() { if (tuPoll) { clearInterval(tuPoll); tuPoll = null; } }

async function renderTopups() {
  stopTuPoll();
  tuOpenId = null; tuSeen = {}; tuPrevUnread = -1;
  main.innerHTML = `
    <div class="page-head"><div>
      <div class="page-title">To'lov chat</div>
      <div class="page-sub">Bir vaqtda bir nechta foydalanuvchi bilan yozishing mumkin</div>
    </div></div>
    <div class="tuc">
      <div class="tuc__list" id="tucList"><div class="loading">Yuklanmoqda…</div></div>
      <div class="tuc__chat" id="tucChat">
        <div class="tuc__empty">Suhbatni tanlang</div>
      </div>
    </div>`;
  await loadTuInbox();
  tuPoll = setInterval(() => {
    if (document.hidden) return;
    loadTuInbox();
    if (tuOpenId) refreshTuChat(tuOpenId);
  }, 3500);
}

async function loadTuInbox() {
  const list = document.getElementById("tucList");
  if (!list) { stopTuPoll(); return; }
  const d = await jget(`${API}/topup-chats/`);
  setTopupBadge(d.active || 0);
  const badge = document.getElementById("tuBadge");
  if (badge) { badge.textContent = fmt(d.active || 0); badge.hidden = !d.active; }
  const unread = d.unread || 0;
  if (tuPrevUnread >= 0 && unread > tuPrevUnread) adminDing();  // a user just wrote
  tuPrevUnread = unread;
  if (!d.rows.length) {
    list.innerHTML = `<div class="loading">Faol suhbat yo'q.</div>`;
    return;
  }
  list.innerHTML = d.rows.map((t) => {
    const st = TU_STATUS[t.status] || { label: t.status, c: "#555" };
    return `<button class="tuc-item ${t.id === tuOpenId ? "is-active" : ""}" data-id="${t.id}">
      <div class="tuc-item__top">
        <span class="tuc-item__name">${esc(t.player.name)}</span>
        ${t.unread ? `<span class="tuc-item__unread">${t.unread}</span>` : ""}
      </div>
      <div class="tuc-item__sub">
        <b class="coin">${fmt(t.amount_sum)}</b> so'm → ${fmt(t.coins)} coin
      </div>
      <span class="status-badge status-badge--sm" style="--bc:${st.c}">${st.label}</span>
    </button>`;
  }).join("");
  list.querySelectorAll("[data-id]").forEach((b) =>
    b.addEventListener("click", () => openTuChat(+b.dataset.id)));
}

function closeTuChat() {
  tuOpenId = null;
  const tuc = document.querySelector(".tuc");
  if (tuc) tuc.classList.remove("chat-open");
  document.querySelectorAll(".tuc-item").forEach((b) => b.classList.remove("is-active"));
  const chat = document.getElementById("tucChat");
  if (chat) chat.innerHTML = `<div class="tuc__empty">Suhbatni tanlang</div>`;
}

async function openTuChat(id) {
  tuOpenId = id; tuSeen = {};
  const tuc = document.querySelector(".tuc"); if (tuc) tuc.classList.add("chat-open");
  document.querySelectorAll(".tuc-item").forEach((b) =>
    b.classList.toggle("is-active", +b.dataset.id === id));
  const chat = document.getElementById("tucChat");
  chat.innerHTML = `<div class="loading">Yuklanmoqda…</div>`;
  const d = await jget(`${API}/topup-chats/${id}/`);
  if (d.error) { chat.innerHTML = `<div class="loading">${esc(d.error)}</div>`; return; }
  const open = d.status === "waiting" || d.status === "connected";
  chat.innerHTML = `
    <div class="tuc-head">
      <button class="tuc-back" id="tucBack" aria-label="Orqaga">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>
      </button>
      <div>
        <div class="tuc-head__name">${esc(d.player.name)}
          ${d.player.username ? `<span class="cell-muted">@${esc(d.player.username)}</span>` : ""}</div>
        <div class="cell-muted" style="font-size:12px">
          TG ${d.player.telegram_id || "—"} · Balans <b class="coin">${fmt(d.player.balance)}</b>
        </div>
      </div>
      <div class="tuc-head__sum">
        <b>${fmt(d.amount_sum)}</b> so'm → <b class="coin">${fmt(d.coins)}</b>
        ${d.bonus_percent ? `<span class="pct">+${d.bonus_percent}%</span>` : ""}
        ${d.card ? `<div class="cell-muted" style="font-size:11px">Karta: ${esc(d.card.number)} · ${esc(d.card.holder)}</div>` : `<div class="tu-red" style="font-size:11px">Karta biriktirilmagan</div>`}
      </div>
    </div>
    <div class="tuc-body" id="tucBody"></div>
    ${open ? `
      <div class="tuc-canned">
        <button class="tuc-chip" data-kind="card">💳 Karta + summa</button>
        <button class="tuc-chip" data-kind="soon">⏳ 2 daqiqada</button>
        <button class="tuc-chip" data-kind="bad">❌ Check noto'g'ri</button>
      </div>
      <div class="tuc-bar">
        <input class="tuc-input" id="tucInput" placeholder="Xabar yozing…" autocomplete="off" />
        <button class="admin-btn" id="tucSend">Yuborish</button>
      </div>
      <div class="tuc-acts">
        <button class="admin-btn admin-btn--danger" id="tucClose">Suhbatni yopish</button>
        <button class="admin-btn" id="tucPay">✅ Balansni to'ldirish (${fmt(d.coins)})</button>
      </div>` : `<div class="tuc-closed">Suhbat ${d.status === "paid" ? "to'landi ✓" : "yopilgan"}.</div>`}`;
  const backBtn = document.getElementById("tucBack");
  if (backBtn) backBtn.addEventListener("click", closeTuChat);
  const bodyEl = document.getElementById("tucBody");
  bodyEl.addEventListener("click", (e) => {
    const im = e.target.closest(".tuc-msg__img");
    if (im) adminLightbox(im.getAttribute("data-full") || im.src);
  });
  (d.messages || []).forEach((m) => addTuMsg(bodyEl, m));

  if (open) {
    chat.querySelectorAll(".tuc-chip").forEach((b) =>
      b.addEventListener("click", () => sendTu(id, { kind: b.dataset.kind })));
    const input = document.getElementById("tucInput");
    const send = () => { const t = input.value.trim(); if (t) { input.value = ""; sendTu(id, { text: t }); } };
    document.getElementById("tucSend").addEventListener("click", send);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
    document.getElementById("tucPay").addEventListener("click", () => openConfirm(
      "Balansni to'ldirish",
      `${fmt(d.coins)} coin foydalanuvchi hisobiga qo'shiladi. Check to'g'riligini tekshirdingizmi?`,
      async () => { await jpost(`${API}/topup-chats/${id}/pay/`); openTuChat(id); loadTuInbox(); }));
    document.getElementById("tucClose").addEventListener("click", () => openConfirm(
      "Suhbatni yopish",
      "Bu suhbat yopiladi (to'lovsiz). Promokod bo'lsa qaytariladi.",
      async () => { await jpost(`${API}/topup-chats/${id}/close/`); openTuChat(id); loadTuInbox(); }));
  }
}

function tuTick(read) { return read ? "✓✓" : "✓"; }
function addTuMsg(bodyEl, m) {
  if (!bodyEl) return;
  if (tuSeen[m.id]) {              // already shown → refresh the read tick
    if (m.sender === "admin") {
      const tk = tuSeen[m.id].querySelector(".tuc-tick");
      if (tk) { tk.textContent = tuTick(m.read); tk.classList.toggle("is-read", !!m.read); }
    }
    return;
  }
  const el = document.createElement("div");
  el.className = "tuc-msg tuc-msg--" + m.sender;
  let inner = "";
  if (m.image) inner += `<img class="tuc-msg__img" src="${esc(m.image)}" alt="" data-full="${esc(m.image)}"/>`;
  if (m.text) inner += `<div class="tuc-msg__text">${esc(m.text).replace(/\n/g, "<br>")}</div>`;
  inner += `<div class="tuc-msg__at">${esc(m.at)}`;
  if (m.sender === "admin") inner += ` <span class="tuc-tick${m.read ? " is-read" : ""}">${tuTick(m.read)}</span>`;
  inner += `</div>`;
  el.innerHTML = inner;
  bodyEl.appendChild(el);
  tuSeen[m.id] = el;
  bodyEl.scrollTop = bodyEl.scrollHeight;
}

async function sendTu(id, payload) {
  const res = await jpost(`${API}/topup-chats/${id}/send/`, payload);
  if (res.ok && res.data.message) addTuMsg(document.getElementById("tucBody"), res.data.message);
}

async function refreshTuChat(id) {
  if (id !== tuOpenId) return;
  const d = await jget(`${API}/topup-chats/${id}/`);
  if (d.messages) d.messages.forEach((m) => addTuMsg(document.getElementById("tucBody"), m));
}

// ---------- payment admins ----------
async function renderPayAdmins() {
  main.innerHTML = `
    <div class="page-head"><div>
      <div class="page-title">To'lov adminlar</div>
      <div class="page-sub">Telegramda to'lovlarni qabul qiladigan odamlar</div>
    </div></div>

    <div class="give-box">
      <div class="give-box__title">Admin qo'shish</div>
      <div class="give-box__sub">
        Telegram chat ID kerak — admin botga /start yozgach, uning chat ID sini
        @userinfobot orqali bilib olishingiz mumkin.
      </div>
      <div class="give-row">
        <input class="admin-input" id="paChat" placeholder="Telegram chat ID (masalan 123456789)" />
        <input class="admin-input" id="paName" placeholder="Ism (masalan Jasur)" />
      </div>
      <div class="give-row" style="margin-top:10px">
        <input class="admin-input" id="paCard" placeholder="Karta raqami (8600 ...)" />
        <input class="admin-input" id="paHolder" placeholder="Karta egasi (JASUR RAHIMOV)" />
        <button class="admin-btn" id="paAdd">Qo'shish</button>
      </div>
      <div class="give-msg" id="paMsg"></div>
    </div>

    <div id="paBody"><div class="loading">Yuklanmoqda…</div></div>`;

  document.getElementById("paAdd").addEventListener("click", async () => {
    const msg = document.getElementById("paMsg");
    const res = await jpost(`${API}/payment-admins/`, {
      tg_chat_id: document.getElementById("paChat").value.trim(),
      name: document.getElementById("paName").value.trim(),
      card_number: document.getElementById("paCard").value.trim(),
      card_holder: document.getElementById("paHolder").value.trim(),
    });
    if (res.ok && res.data.ok) {
      msg.className = "give-msg is-ok";
      msg.textContent = "Qo'shildi!";
      ["paChat", "paName", "paCard", "paHolder"].forEach((i) => (document.getElementById(i).value = ""));
      loadPayAdmins();
    } else {
      msg.className = "give-msg is-err";
      msg.textContent = res.data.error || "Xatolik";
    }
  });
  loadPayAdmins();
}

async function loadPayAdmins() {
  const body = document.getElementById("paBody");
  const rows = await jget(`${API}/payment-admins/`);
  if (!rows.length) {
    body.innerHTML = `<div class="loading">Hali to'lov admini qo'shilmagan.
      Admin bo'lmasa userlar balansni to'ldira olmaydi.</div>`;
    return;
  }
  body.innerHTML = `
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr>
        <th>Admin</th><th>Telegram chat ID</th><th>Karta</th>
        <th>So'rovlar</th><th>Holati</th><th></th>
      </tr></thead>
      <tbody>
        ${rows.map((a) => `
          <tr>
            <td class="cell-name">${esc(a.name)}</td>
            <td class="cell-muted">${a.tg_chat_id}</td>
            <td>
              <div>${esc(a.card_number)}</div>
              <div class="cell-muted" style="font-size:12px">${esc(a.card_holder)}</div>
            </td>
            <td>${fmt(a.topups)}</td>
            <td><span class="status-badge" style="--bc:${a.is_active ? "var(--green)" : "var(--pink)"}">
              ${a.is_active ? "Faol" : "O'chirilgan"}</span></td>
            <td style="white-space:nowrap">
              <button class="admin-btn admin-btn--ghost" data-toggle="${a.id}">
                ${a.is_active ? "To'xtatish" : "Yoqish"}</button>
              <button class="admin-btn admin-btn--danger" data-del="${a.id}">Olib tashlash</button>
            </td>
          </tr>`).join("")}
      </tbody>
    </table></div></div>`;

  body.querySelectorAll("[data-toggle]").forEach((b) =>
    b.addEventListener("click", async () => {
      await jpost(`${API}/payment-admins/${b.dataset.toggle}/`);
      loadPayAdmins();
    })
  );
  body.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", () => openConfirm(
      "Adminni olib tashlash",
      "Bu adminni ro'yxatdan o'chirasizmi? Uning ochiq suhbatlari yopiladi.",
      async () => { await jdel(`${API}/payment-admins/${b.dataset.del}/`); loadPayAdmins(); }
    ))
  );
}

// ---------- promo codes ----------
let prKind = "bonus";

// ---------- broadcast ----------
const BC_ICONS = {
  megaphone: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11v2a1 1 0 0 0 1 1h2l3.5 5.5a1 1 0 0 0 1.8-.6V6.1a1 1 0 0 0-1.8-.6L6 11H4a1 1 0 0 0-1 1z"/><path d="M17 9a3 3 0 0 1 0 6"/><path d="M17.5 4.5a8 8 0 0 1 0 15"/></svg>`,
  list: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>`,
  text: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M4 12h16M4 18h10"/></svg>`,
  image: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>`,
  layers: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>`,
  users: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`,
  userCheck: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><polyline points="17 11 19 13 23 9"/></svg>`,
  clock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
  checkCircle: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`,
  info: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
  send: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`,
  trash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>`,
  upload: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>`,
  x: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
  mail: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2.5" y="5.5" width="19" height="14" rx="2.5"/><path d="M3 7.5l9 6.2 9-6.2"/></svg>`,
  back: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>`,
};
let bcType = "text";
let bcAudience = "all";
let bcImageFile = null;

async function renderBroadcast() {
  bcType = "text"; bcAudience = "all"; bcImageFile = null;
  main.innerHTML = `
    <div class="page-head">
      <div>
        <div class="page-title page-title--ic"><span class="page-title__ic bc-ic--violet">${BC_ICONS.megaphone}</span>Broadcast xabar yuborish</div>
        <div class="page-sub">Barcha foydalanuvchilarga xabar yuboring</div>
      </div>
      <button class="admin-btn admin-btn--ghost bc-histbtn" id="bcHistBtn">${BC_ICONS.list}<span>Yuborilgan xabarlar</span></button>
    </div>
    <div class="bc-grid">
      <div class="bc-main">
        <div class="give-box">
          <div class="give-box__title">Xabar turi</div>
          <div class="seg bc-seg" id="bcTypeSeg">
            <button class="seg__btn is-active" data-type="text" type="button">${BC_ICONS.text}<span>Matn</span></button>
            <button class="seg__btn" data-type="image" type="button">${BC_ICONS.image}<span>Rasm</span></button>
            <button class="seg__btn" data-type="image_text" type="button">${BC_ICONS.layers}<span>Rasm + matn</span></button>
          </div>

          <div class="give-box__title bc-mt">Foydalanuvchilar</div>
          <div class="seg bc-seg" id="bcAudSeg">
            <button class="seg__btn is-active" data-aud="all" type="button">${BC_ICONS.users}<span>Barcha foydalanuvchilar</span></button>
            <button class="seg__btn" data-aud="active" type="button">${BC_ICONS.userCheck}<span>Faol (7 kun)</span></button>
          </div>

          <div id="bcTextWrap" class="bc-mt">
            <div class="give-box__title">Xabar matni</div>
            <textarea class="admin-input bc-textarea" id="bcText" maxlength="1000" placeholder="Xabar matnini kiriting..."></textarea>
            <div class="bc-counter"><span id="bcCount">0</span> / 1000</div>
          </div>

          <div id="bcImageWrap" class="bc-mt" hidden>
            <div class="give-box__title">Rasm</div>
            <label class="bc-drop" id="bcDrop">
              <input type="file" id="bcFile" accept="image/*" hidden />
              <span class="bc-drop__ic">${BC_ICONS.upload}</span>
              <span class="bc-drop__text">Rasmni tanlash uchun bosing</span>
              <span class="bc-drop__hint">JPG, PNG, WEBP — 8MB gacha</span>
            </label>
            <div class="bc-drop-preview" id="bcDropPreview" hidden>
              <img id="bcDropImg" alt="" />
              <button class="bc-drop-x" id="bcDropRemove" type="button">${BC_ICONS.x}</button>
            </div>
          </div>

          <div class="give-msg" id="bcMsg"></div>

          <div class="bc-acts">
            <button class="admin-btn bc-btn-ic" id="bcSend" type="button">${BC_ICONS.send}<span>Xabar yuborish</span></button>
            <button class="admin-btn admin-btn--ghost bc-btn-ic" id="bcClear" type="button">${BC_ICONS.trash}<span>Tozalash</span></button>
          </div>
        </div>
      </div>

      <div class="bc-side">
        <div class="bc-preview-card">
          <div class="bc-preview-card__title">Xabar oldindan ko'rish</div>
          <div class="bc-preview" id="bcPreview">
            <span class="bc-preview__ic">${BC_ICONS.mail}</span>
            <div class="bc-preview__hint">Xabar yuborilganda foydalanuvchilar quyidagi ko'rinishda oladi</div>
          </div>
        </div>
        <div class="bc-stats" id="bcStats"><div class="loading">Yuklanmoqda…</div></div>
        <div class="bc-info">
          <div class="bc-info__head">${BC_ICONS.info}<span>Ma'lumot</span></div>
          <p>Broadcast xabarlar tanlangan foydalanuvchilar guruhiga Telegram bot orqali yetkaziladi.</p>
          <p>Noto'g'ri xabar yuborish foydalanuvchilarni bezovta qilishi mumkin.</p>
        </div>
      </div>
    </div>`;

  const typeSeg = document.getElementById("bcTypeSeg");
  const audSeg = document.getElementById("bcAudSeg");
  const textWrap = document.getElementById("bcTextWrap");
  const imageWrap = document.getElementById("bcImageWrap");
  const textArea = document.getElementById("bcText");
  const countEl = document.getElementById("bcCount");
  const dropInput = document.getElementById("bcFile");
  const dropZone = document.getElementById("bcDrop");
  const dropPreview = document.getElementById("bcDropPreview");
  const dropImg = document.getElementById("bcDropImg");
  const dropRemove = document.getElementById("bcDropRemove");
  const preview = document.getElementById("bcPreview");
  const msg = document.getElementById("bcMsg");
  const sendBtn = document.getElementById("bcSend");
  const clearBtn = document.getElementById("bcClear");
  const histBtn = document.getElementById("bcHistBtn");

  function syncFields() {
    textWrap.hidden = bcType === "image";
    imageWrap.hidden = bcType === "text";
  }
  function updatePreview() {
    const text = textArea.value.trim();
    const hasImage = !!bcImageFile && !dropPreview.hidden;
    if (!text && !hasImage) {
      preview.classList.remove("has-content");
      preview.innerHTML = `<span class="bc-preview__ic">${BC_ICONS.mail}</span>
        <div class="bc-preview__hint">Xabar yuborilganda foydalanuvchilar quyidagi ko'rinishda oladi</div>`;
      return;
    }
    preview.classList.add("has-content");
    preview.innerHTML = `<div class="bc-bubble">
      ${hasImage ? `<img class="bc-bubble__img" src="${dropImg.src}" alt="" />` : ""}
      ${text ? `<div class="bc-bubble__text">${esc(text).replace(/\n/g, "<br>")}</div>` : ""}
    </div>`;
  }

  typeSeg.addEventListener("click", (e) => {
    const b = e.target.closest(".seg__btn"); if (!b) return;
    bcType = b.dataset.type;
    typeSeg.querySelectorAll(".seg__btn").forEach((x) => x.classList.toggle("is-active", x === b));
    syncFields(); updatePreview();
  });
  audSeg.addEventListener("click", (e) => {
    const b = e.target.closest(".seg__btn"); if (!b) return;
    bcAudience = b.dataset.aud;
    audSeg.querySelectorAll(".seg__btn").forEach((x) => x.classList.toggle("is-active", x === b));
  });
  textArea.addEventListener("input", () => {
    countEl.textContent = textArea.value.length;
    updatePreview();
  });
  dropZone.addEventListener("click", () => dropInput.click());
  dropInput.addEventListener("change", () => {
    const f = dropInput.files[0];
    if (!f) return;
    bcImageFile = f;
    const reader = new FileReader();
    reader.onload = () => {
      dropImg.src = reader.result;
      dropZone.hidden = true;
      dropPreview.hidden = false;
      updatePreview();
    };
    reader.readAsDataURL(f);
  });
  dropRemove.addEventListener("click", () => {
    bcImageFile = null;
    dropInput.value = "";
    dropZone.hidden = false;
    dropPreview.hidden = true;
    updatePreview();
  });

  clearBtn.addEventListener("click", () => {
    textArea.value = ""; countEl.textContent = "0";
    bcImageFile = null; dropInput.value = "";
    dropZone.hidden = false; dropPreview.hidden = true;
    msg.className = "give-msg"; msg.textContent = "";
    updatePreview();
  });

  sendBtn.addEventListener("click", async () => {
    const text = textArea.value.trim();
    if (bcType !== "image" && !text && !bcImageFile) {
      msg.className = "give-msg is-err"; msg.textContent = "Xabar matni yoki rasm kerak"; return;
    }
    if (bcType === "image" && !bcImageFile) {
      msg.className = "give-msg is-err"; msg.textContent = "Rasm tanlang"; return;
    }
    const audLabel = bcAudience === "active" ? "faol" : "barcha";
    if (!confirm(`Xabar ${audLabel} foydalanuvchilarga yuborilsinmi?`)) return;
    sendBtn.disabled = true;
    const fd = new FormData();
    fd.append("text", bcType === "image" ? "" : text);
    fd.append("audience", bcAudience);
    if (bcImageFile && bcType !== "text") fd.append("image", bcImageFile);
    const res = await jpostForm(`${API}/broadcasts/`, fd);
    sendBtn.disabled = false;
    if (res.ok && res.data.ok) {
      msg.className = "give-msg is-ok";
      msg.textContent = `Yuborildi: ${res.data.sent}/${res.data.total} foydalanuvchiga yetkazildi.`;
      clearBtn.click();
      loadBcStats();
    } else {
      msg.className = "give-msg is-err";
      msg.textContent = res.data.error || "Xatolik";
    }
  });

  histBtn.addEventListener("click", () => renderBroadcastHistory());

  syncFields();
  loadBcStats();
}

async function loadBcStats() {
  const el = document.getElementById("bcStats");
  if (!el) return;
  const res = await jget(`${API}/broadcasts/`);
  const s = res.stats || {};
  el.innerHTML = `
    <div class="bc-stats__title">Statistika</div>
    <div class="bc-stat"><span class="bc-stat__ic">${BC_ICONS.users}</span><span class="bc-stat__label">Jami foydalanuvchilar</span><span class="bc-stat__num">${fmt(s.players)}</span></div>
    <div class="bc-stat"><span class="bc-stat__ic">${BC_ICONS.userCheck}</span><span class="bc-stat__label">Faol foydalanuvchilar</span><span class="bc-stat__num">${fmt(s.active)}</span></div>
    <div class="bc-stat"><span class="bc-stat__ic">${BC_ICONS.clock}</span><span class="bc-stat__label">So'nggi 24 soat</span><span class="bc-stat__num">${fmt(s.new_24h)}</span></div>
    <div class="bc-stat"><span class="bc-stat__ic">${BC_ICONS.checkCircle}</span><span class="bc-stat__label">Xabar yetkazilishi</span><span class="bc-stat__num">${s.delivery_rate}%</span></div>`;
}

async function renderBroadcastHistory() {
  main.innerHTML = `
    <div class="page-head"><div>
      <div class="page-title page-title--ic">
        <button class="icon-back" id="bcBack" type="button">${BC_ICONS.back}</button>
        Yuborilgan xabarlar
      </div>
      <div class="page-sub">Oxirgi 50 ta broadcast</div>
    </div></div>
    <div id="bcHistBody"><div class="loading">Yuklanmoqda…</div></div>`;
  document.getElementById("bcBack").addEventListener("click", () => renderBroadcast());
  const res = await jget(`${API}/broadcasts/`);
  const rows = res.items || [];
  const body = document.getElementById("bcHistBody");
  if (!rows.length) { body.innerHTML = `<div class="loading">Hali xabar yuborilmagan.</div>`; return; }
  body.innerHTML = `
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Vaqt</th><th>Xabar</th><th>Auditoriya</th><th>Yetkazildi</th><th>Admin</th></tr></thead>
      <tbody>
        ${rows.map((b) => `<tr>
          <td class="cell-muted">${dt(b.created_at)}</td>
          <td class="bc-hist-cell">
            ${b.image ? `<img class="bc-hist-thumb" src="${b.image}" alt="" />` : ""}
            ${b.text ? `<span class="bc-hist-text">${esc(b.text.slice(0, 80))}${b.text.length > 80 ? "…" : ""}</span>` : (b.image ? "" : `<span class="cell-muted">—</span>`)}
          </td>
          <td>${b.audience === "active" ? "Faol" : "Barcha"}</td>
          <td>${fmt(b.delivered)} / ${fmt(b.recipients)}</td>
          <td class="cell-muted">${esc(b.sent_by || "—")}</td>
        </tr>`).join("")}
      </tbody>
    </table></div></div>`;
}

async function renderPromos() {
  const cases = await jget(`${API}/cases/`);
  main.innerHTML = `
    <div class="page-head"><div>
      <div class="page-title">Promokodlar</div>
      <div class="page-sub">To'ldirish bonusi yoki bepul keys beradi</div>
    </div></div>

    <div class="give-box">
      <div class="give-box__title">Promokod yaratish</div>
      <div class="give-box__sub">Kod, turi va nechta odam ishlata olishini o'zingiz belgilaysiz.</div>

      <div class="seg" id="prKindSeg">
        <button class="seg__btn is-active" data-kind="bonus">To'ldirish bonusi</button>
        <button class="seg__btn" data-kind="case">Bepul keys</button>
      </div>

      <div class="give-row" style="margin-top:12px">
        <input class="admin-input" id="prCode" placeholder="Kod (masalan DONK)" />
        <input class="admin-input" id="prBonus" type="number" placeholder="Bonus % (masalan 20)" />
        <select class="admin-input" id="prCase" hidden>
          <option value="">Keysni tanlang…</option>
          ${cases.map((c) => `<option value="${c.id}">${esc(c.name)} · ${fmt(c.price)} coin</option>`).join("")}
        </select>
        <input class="admin-input" id="prMax" type="number" min="0"
               placeholder="Aktivatsiya (0 = cheksiz)" />
        <button class="admin-btn" id="prAdd">Yaratish</button>
      </div>
      <div class="give-msg" id="prMsg"></div>
    </div>

    <div id="prBody"><div class="loading">Yuklanmoqda…</div></div>`;

  const bonusIn = document.getElementById("prBonus");
  const caseIn = document.getElementById("prCase");
  document.getElementById("prKindSeg").addEventListener("click", (e) => {
    const b = e.target.closest(".seg__btn");
    if (!b) return;
    prKind = b.dataset.kind;
    document.querySelectorAll("#prKindSeg .seg__btn").forEach((x) =>
      x.classList.toggle("is-active", x.dataset.kind === prKind));
    bonusIn.hidden = prKind !== "bonus";
    caseIn.hidden = prKind !== "case";
  });

  document.getElementById("prAdd").addEventListener("click", async () => {
    const msg = document.getElementById("prMsg");
    const res = await jpost(`${API}/promos/`, {
      code: document.getElementById("prCode").value.trim(),
      kind: prKind,
      bonus_percent: bonusIn.value.trim(),
      case_id: caseIn.value,
      max_uses: document.getElementById("prMax").value.trim() || 0,
    });
    if (res.ok && res.data.ok) {
      msg.className = "give-msg is-ok";
      msg.textContent = "Yaratildi!";
      document.getElementById("prCode").value = "";
      bonusIn.value = "";
      caseIn.value = "";
      document.getElementById("prMax").value = "";
      loadPromos();
    } else {
      msg.className = "give-msg is-err";
      msg.textContent = res.data.error || "Xatolik";
    }
  });
  loadPromos();
}

async function loadPromos() {
  const body = document.getElementById("prBody");
  const rows = await jget(`${API}/promos/`);
  if (!rows.length) {
    body.innerHTML = `<div class="loading">Hali promokod yaratilmagan.</div>`;
    return;
  }
  body.innerHTML = `
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr>
        <th>Kod</th><th>Turi</th><th>Beradi</th><th>Aktivatsiya</th>
        <th>Yaratilgan</th><th>Holati</th><th></th>
      </tr></thead>
      <tbody>
        ${rows.map((p) => {
          const isCase = p.kind === "case";
          // "spent" is not the same as "switched off" — say which.
          const st = !p.is_active
            ? { label: "O'chirilgan", c: "var(--pink)" }
            : p.is_spent
              ? { label: "Limit tugagan", c: "var(--gold)" }
              : { label: "Faol", c: "var(--green)" };
          return `<tr>
            <td class="cell-name">${esc(p.code)}</td>
            <td><span class="status-badge" style="--bc:${isCase ? "var(--violet)" : "var(--teal)"}">
              ${isCase ? "Bepul keys" : "Bonus"}</span></td>
            <td>${isCase
                  ? `<span class="cell-name">${esc(p.case ? p.case.name : "— o'chirilgan keys")}</span>`
                  : `<span class="pct">+${p.bonus_percent}%</span>`}</td>
            <td>${fmt(p.uses)}${p.max_uses ? " / " + fmt(p.max_uses) : ' <span class="cell-muted">/ ∞</span>'}</td>
            <td class="cell-muted">${dOnly(p.created_at)}</td>
            <td><span class="status-badge" style="--bc:${st.c}">${st.label}</span></td>
            <td style="white-space:nowrap">
              <button class="admin-btn admin-btn--ghost" data-toggle="${p.id}">
                ${p.is_active ? "To'xtatish" : "Yoqish"}</button>
              <button class="admin-btn admin-btn--danger" data-del="${p.id}">Olib tashlash</button>
            </td>
          </tr>`;
        }).join("")}
      </tbody>
    </table></div></div>`;

  body.querySelectorAll("[data-toggle]").forEach((b) =>
    b.addEventListener("click", async () => {
      await jpost(`${API}/promos/${b.dataset.toggle}/`);
      loadPromos();
    })
  );
  body.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", () => openConfirm(
      "Promokodni o'chirish",
      "Bu promokod butunlay o'chiriladi.",
      async () => { await jdel(`${API}/promos/${b.dataset.del}/`); loadPromos(); }
    ))
  );
}

// ---------- channel subscribe tasks ----------
const CT_ICONS = {
  channel: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>`,
  link: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>`,
};

async function renderChannelTasks() {
  main.innerHTML = `
    <div class="page-head"><div>
      <div class="page-title page-title--ic"><span class="page-title__ic bc-ic--violet">${CT_ICONS.channel}</span>Kanal topshiriqlari</div>
      <div class="page-sub">Home sahifada ko'rsatiladigan "kanalga obuna bo'ling" topshiriqlari — birinchisi bajarilgach navbatdagisi ochiladi</div>
    </div></div>

    <div class="give-box">
      <div class="give-box__title">Yangi topshiriq qo'shish</div>
      <div class="give-box__sub">Kanal nomi, havolasi (t.me/...) va sovg'a miqdorini kiriting. Bot kanalga admin qilib qo'shilgan bo'lishi kerak.</div>
      <div class="give-row" style="margin-top:12px">
        <input class="admin-input" id="ctName" placeholder="Kanal nomi (masalan SKINRUSH UZ)" />
        <input class="admin-input" id="ctLink" placeholder="https://t.me/kanal_nomi" />
        <input class="admin-input" id="ctReward" type="number" min="1" placeholder="Sovg'a (coin)" value="500" />
        <input class="admin-input" id="ctOrder" type="number" min="0" placeholder="Tartib (ixtiyoriy)" />
        <button class="admin-btn" id="ctAdd">Qo'shish</button>
      </div>
      <div class="give-msg" id="ctMsg"></div>
    </div>

    <div id="ctBody"><div class="loading">Yuklanmoqda…</div></div>`;

  document.getElementById("ctAdd").addEventListener("click", async () => {
    const msg = document.getElementById("ctMsg");
    const res = await jpost(`${API}/channel-tasks/`, {
      name: document.getElementById("ctName").value.trim(),
      link: document.getElementById("ctLink").value.trim(),
      reward: document.getElementById("ctReward").value.trim() || 500,
      sort_order: document.getElementById("ctOrder").value.trim() || undefined,
    });
    if (res.ok && res.data.ok) {
      msg.className = "give-msg is-ok";
      msg.textContent = "Qo'shildi!";
      document.getElementById("ctName").value = "";
      document.getElementById("ctLink").value = "";
      document.getElementById("ctReward").value = "500";
      document.getElementById("ctOrder").value = "";
      loadChannelTasks();
    } else {
      msg.className = "give-msg is-err";
      msg.textContent = res.data.error || "Xatolik";
    }
  });
  loadChannelTasks();
}

async function loadChannelTasks() {
  const body = document.getElementById("ctBody");
  const rows = await jget(`${API}/channel-tasks/`);
  if (!rows.length) {
    body.innerHTML = `<div class="loading">Hali topshiriq qo'shilmagan.</div>`;
    return;
  }
  body.innerHTML = `
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr>
        <th>Tartib</th><th>Nomi</th><th>Havola</th><th>Mukofot</th>
        <th>Bajarganlar</th><th>Holati</th><th></th>
      </tr></thead>
      <tbody>
        ${rows.map((t) => {
          const st = !t.is_active
            ? { label: "O'chirilgan", c: "var(--pink)" }
            : !t.checkable
              ? { label: "Havola noto'g'ri", c: "var(--gold)" }
              : { label: "Faol", c: "var(--green)" };
          return `<tr>
            <td class="cell-muted">${t.sort_order}</td>
            <td class="cell-name">${esc(t.name)}</td>
            <td><a href="${esc(t.link)}" target="_blank" rel="noopener" class="ct-link">${CT_ICONS.link}<span>${esc(t.link.replace(/^https?:\/\//, ""))}</span></a></td>
            <td><span class="pct">+${fmt(t.reward)} coin</span></td>
            <td class="cell-muted">${fmt(t.claims)}</td>
            <td><span class="status-badge" style="--bc:${st.c}">${st.label}</span></td>
            <td style="white-space:nowrap">
              <button class="admin-btn admin-btn--ghost" data-toggle="${t.id}" data-active="${t.is_active}">
                ${t.is_active ? "To'xtatish" : "Yoqish"}</button>
              <button class="admin-btn admin-btn--danger" data-del="${t.id}">Olib tashlash</button>
            </td>
          </tr>`;
        }).join("")}
      </tbody>
    </table></div></div>`;

  body.querySelectorAll("[data-toggle]").forEach((b) =>
    b.addEventListener("click", async () => {
      await jpost(`${API}/channel-tasks/${b.dataset.toggle}/`, {
        is_active: b.dataset.active !== "true",
      });
      loadChannelTasks();
    })
  );
  body.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", () => openConfirm(
      "Topshiriqni o'chirish",
      "Bu kanal topshirig'i butunlay o'chiriladi. Bajargan foydalanuvchilar tarixi ham o'chadi.",
      async () => { await jdel(`${API}/channel-tasks/${b.dataset.del}/`); loadChannelTasks(); }
    ))
  );
}

// ---------- generic confirm ----------
// An in-page dialog, not window.confirm(): a native dialog blocks the page and
// there is no way back from it if something goes wrong mid-automation.
const confirmModal = document.getElementById("confirmModal");
const confirmOk = document.getElementById("confirmOk");
let confirmAction = null;

function openConfirm(title, sub, onOk) {
  document.getElementById("confirmTitle").textContent = title;
  document.getElementById("confirmSub").textContent = sub;
  confirmAction = onOk;
  confirmModal.hidden = false;
}

function closeConfirm() {
  confirmModal.hidden = true;
  confirmAction = null;
}

document.getElementById("confirmCancel").addEventListener("click", closeConfirm);
confirmModal.addEventListener("click", (e) => {
  if (e.target === confirmModal) closeConfirm();
});
confirmOk.addEventListener("click", async () => {
  const fn = confirmAction;
  confirmOk.disabled = true;
  try { if (fn) await fn(); } finally { confirmOk.disabled = false; closeConfirm(); }
});

// ---------- reject modal ----------
const rejectModal = document.getElementById("rejectModal");
const rejectReason = document.getElementById("rejectReason");
const rejectError = document.getElementById("rejectError");
const rejectSub = document.getElementById("rejectSub");
const rejectConfirm = document.getElementById("rejectConfirm");
let rejectId = null;

function openRejectModal(id, skinName) {
  rejectId = id;
  rejectReason.value = "";
  rejectError.textContent = "";
  rejectSub.textContent = skinName ? `${skinName} — skin foydalanuvchiga qaytariladi.`
                                   : "Skin foydalanuvchiga qaytariladi.";
  rejectModal.hidden = false;
  rejectReason.focus();
}

function closeRejectModal() {
  rejectModal.hidden = true;
  rejectId = null;
}

document.getElementById("rejectCancel").addEventListener("click", closeRejectModal);
rejectModal.addEventListener("click", (e) => {
  if (e.target === rejectModal) closeRejectModal();   // click the backdrop
});
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!rejectModal.hidden) closeRejectModal();
  if (!confirmModal.hidden) closeConfirm();
});

rejectConfirm.addEventListener("click", async () => {
  const reason = rejectReason.value.trim();
  if (!reason) {
    rejectError.textContent = "Sababni yozing — u foydalanuvchiga yuboriladi.";
    return;
  }
  rejectConfirm.disabled = true;
  const ok = await runWithdrawAction(rejectId, "reject", { reason });
  rejectConfirm.disabled = false;
  if (ok) closeRejectModal();
  else rejectError.textContent = "Rad etib bo'lmadi — qayta urinib ko'ring.";
});

// ---------- users ----------
let uQuery = "", uSort = "new", uFilter = "all";
async function renderUsers() {
  main.innerHTML = `
    <div class="page-head"><div>
      <div class="page-title">Foydalanuvchilar</div>
      <div class="page-sub">Qidiruv · filtr · saralash</div>
    </div></div>
    <div class="u-toolbar">
      <input class="admin-input" id="userSearch" placeholder="Ism / @username / TG id..." value="${esc(uQuery)}" />
      <select class="admin-input" id="userSort">
        <option value="new">Eng yangi</option>
        <option value="old">Eng eski</option>
        <option value="rich">Balans ↓</option>
        <option value="poor">Balans ↑</option>
        <option value="opens">Ko'p ochgan</option>
        <option value="active_seen">So'nggi faol</option>
      </select>
    </div>
    <div class="filter-row" id="userFilter">
      <button class="filter-chip ${uFilter === "all" ? "is-active" : ""}" data-f="all">Barchasi</button>
      <button class="filter-chip ${uFilter === "active" ? "is-active" : ""}" data-f="active">Aktiv</button>
      <button class="filter-chip ${uFilter === "banned" ? "is-active" : ""}" data-f="banned">Bloklangan</button>
    </div>
    <div id="usersBody"><div class="loading">Yuklanmoqda…</div></div>`;
  const search = document.getElementById("userSearch");
  const sort = document.getElementById("userSort");
  sort.value = uSort;
  let t;
  search.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(() => { uQuery = search.value.trim(); loadUsers(); }, 200);
  });
  sort.addEventListener("change", () => { uSort = sort.value; loadUsers(); });
  document.getElementById("userFilter").addEventListener("click", (e) => {
    const b = e.target.closest(".filter-chip"); if (!b) return;
    uFilter = b.dataset.f;
    document.querySelectorAll("#userFilter .filter-chip").forEach((c) =>
      c.classList.toggle("is-active", c.dataset.f === uFilter));
    loadUsers();
  });
  loadUsers();
}

async function loadUsers() {
  const body = document.getElementById("usersBody");
  if (!body) return;
  const qp = `?q=${encodeURIComponent(uQuery)}&sort=${uSort}&filter=${uFilter}`;
  const users = await jget(`${API}/users/${qp}`);
  if (!users.length) {
    body.innerHTML = `<div class="loading">Hech narsa topilmadi.</div>`;
    return;
  }
  body.innerHTML = `
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr>
        <th>Foydalanuvchi</th><th>Balans</th><th>Sotib olgan</th>
        <th>Ochgan</th><th>Ro'yxatdan o'tgan</th>
      </tr></thead>
      <tbody>
        ${users.map((u) => `
          <tr class="clickable" data-id="${u.id}">
            <td>
              <div class="cell-name">${esc(u.name)} ${u.is_banned ? '<span class="ban-tag">BLOK</span>' : ""}</div>
              ${u.username ? `<div class="cell-muted" style="font-size:12px">@${esc(u.username)}</div>` : ""}
            </td>
            <td class="coin">${fmt(u.balance)}</td>
            <td class="coin">${fmt(u.coins_purchased)}</td>
            <td>${u.opens_count}</td>
            <td class="cell-muted">${dOnly(u.created_at)}</td>
          </tr>`).join("")}
      </tbody>
    </table></div></div>`;
  body.querySelectorAll("tr[data-id]").forEach((tr) =>
    tr.addEventListener("click", () => renderUserDetail(+tr.dataset.id))
  );
}

async function renderUserDetail(id) {
  main.innerHTML = `<div class="loading">Yuklanmoqda…</div>`;
  const d = await jget(`${API}/users/${id}/`);
  const u = d.player;
  const info = [
    ["Ism", esc(u.name)],
    ["Username", u.username ? "@" + esc(u.username) : "—"],
    ["Telegram ID", u.telegram_id || "—"],
    ["Hozirgi balans", `<span class="coin">${fmt(u.balance)}</span>`],
    ["Jami sotib olingan coin", `<span class="coin">${fmt(u.coins_purchased)}</span>`],
    ["Ro'yxatdan o'tgan", dt(u.created_at)],
    ["Oxirgi faollik", dt(u.last_seen)],
    ["Jami ochgan keys", d.totals.opens],
    ["Yutgan skinlar qiymati", `<span class="coin">${fmt(d.totals.won_value)}</span>`],
  ];
  main.innerHTML = `
    <button class="back-btn" id="backBtn">‹ Foydalanuvchilarga qaytish</button>
    <div class="page-head"><div>
      <div class="page-title">${esc(u.name)}</div>
      <div class="page-sub">${u.username ? "@" + esc(u.username) : "Telegram foydalanuvchi"}</div>
    </div></div>

    <div class="info-grid">
      ${info.map(([k, v]) => `<div class="info-card"><div class="info-k">${k}</div><div class="info-v">${v}</div></div>`).join("")}
    </div>

    <div class="give-box">
      <div class="give-box__title">Coin berish (donat)</div>
      <div class="give-box__sub">Foydalanuvchi balansiga coin qo'shing. Manfiy son yozsangiz — yechib olinadi.</div>
      <div class="give-row">
        <input class="admin-input" id="giveAmount" type="number" placeholder="Miqdor (masalan 1000)" />
        <input class="admin-input" id="giveNote" placeholder="Izoh (ixtiyoriy)" />
        <button class="admin-btn" id="giveBtn">Berish</button>
      </div>
      <div class="give-msg" id="giveMsg"></div>
      <div class="give-quick">
        ${[500, 1000, 5000, 10000].map((a) => `<button class="give-chip" data-amt="${a}">+${fmt(a)}</button>`).join("")}
      </div>
    </div>

    <div class="a-tools">
      <div class="a-tool">
        <div class="a-tool__h">Moderatsiya</div>
        <div class="a-tool__row">
          <input class="admin-input" id="banReason" placeholder="Blok sababi (ixtiyoriy)" ${u.is_banned ? "disabled" : ""}/>
          <button class="admin-btn ${u.is_banned ? "" : "admin-btn--danger"}" id="banBtn">${u.is_banned ? "Blokdan chiqarish" : "Bloklash"}</button>
        </div>
        ${u.is_banned ? `<div class="a-banned">⛔ Bloklangan${u.ban_reason ? " — " + esc(u.ban_reason) : ""}</div>` : ""}
      </div>

      <div class="a-tool">
        <div class="a-tool__h">Skin berish</div>
        <input class="admin-input" id="skinSearch" placeholder="Skin qidirish (nom)..." />
        <div class="a-skinres" id="skinRes"></div>
      </div>

      <div class="a-tool">
        <div class="a-tool__h">Bepul keys berish</div>
        <div class="a-tool__row">
          <select class="admin-input" id="freeCaseSel"><option value="">Keys tanlang…</option></select>
          <input class="admin-input a-num" id="freeCaseN" type="number" value="1" min="1" max="20"/>
          <button class="admin-btn" id="freeCaseBtn">Berish</button>
        </div>
      </div>

      <div class="a-tool">
        <div class="a-tool__h">Telegram xabar</div>
        <textarea class="admin-input a-area" id="dmText" rows="2" placeholder="Xabar matni..."></textarea>
        <button class="admin-btn" id="dmBtn" style="margin-top:8px">Yuborish</button>
      </div>

      <div class="a-tool a-tool--wide">
        <div class="a-tool__h">Inventar — skin olib qo'yish (${d.inventory.length})</div>
        <div class="a-inv" id="takeInv">
          ${d.inventory.length ? d.inventory.map((it) => `
            <div class="a-invitem" style="--rc:${esc(it.color) || "#555"}">
              <img src="${IMG(it.image)}" onerror="this.style.visibility='hidden'"/>
              <div class="a-invitem__b"><div class="a-invitem__n">${esc(it.name)}</div><div class="coin">${fmt(it.price)}</div></div>
              <button class="a-invitem__x" data-rec="${it.id}" data-name="${esc(it.name)}" title="Olib qo'yish">✕</button>
            </div>`).join("") : `<div class="cell-muted">Inventar bo'sh</div>`}
        </div>
      </div>
    </div>
    <div class="give-msg" id="toolMsg"></div>

    <div class="section-title">Keys ochish tarixi — qaysi keysdan nima tushgani</div>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Sana</th><th>Key</th><th>Tushgan skin</th><th>Holati</th><th>Qiymati</th><th>Noyoblik</th><th>Sotilgan</th></tr></thead>
      <tbody>
        ${d.opens.length ? d.opens.map((o) => `
          <tr>
            <td class="cell-muted">${dt(o.created_at)}</td>
            <td>${esc(o.case)}</td>
            <td><img class="thumb" src="${IMG(o.image)}" onerror="this.style.visibility='hidden'"/>
                <span style="margin-left:8px">${esc(o.skin)}</span></td>
            <td class="cell-muted">${esc(o.wear || "—")}</td>
            <td class="coin">${fmt(o.price)}</td>
            <td><span class="rarity-badge" style="background:${esc(o.color) || "#555"}">${esc(o.rarity || "—")}</span></td>
            <td>${o.sold ? '<span class="pct">Sotildi</span>' : '<span class="cell-muted">Inventarda</span>'}</td>
          </tr>`).join("") : `<tr><td colspan="7" class="cell-muted" style="text-align:center;padding:24px">Hali keys ochmagan</td></tr>`}
      </tbody>
    </table></div></div>

    ${d.purchases.length ? `
      <div class="section-title">Coin sotib olish tarixi</div>
      <div class="table-wrap"><div class="table-scroll"><table>
        <thead><tr><th>Sana</th><th>Miqdor</th><th>Izoh</th></tr></thead>
        <tbody>${d.purchases.map((p) => `<tr><td class="cell-muted">${dt(p.created_at)}</td><td class="coin">+${fmt(p.amount)}</td><td class="cell-muted">${esc(p.note || "—")}</td></tr>`).join("")}</tbody>
      </table></div></div>` : ""}`;
  document.getElementById("backBtn").addEventListener("click", () => switchView("users"));

  // --- give coins (donation top-up) ---
  const giveAmount = document.getElementById("giveAmount");
  const giveNote = document.getElementById("giveNote");
  const giveBtn = document.getElementById("giveBtn");
  const giveMsg = document.getElementById("giveMsg");

  async function giveCoins(amount) {
    if (!amount) { giveMsg.className = "give-msg is-err"; giveMsg.textContent = "Miqdorni kiriting"; return; }
    giveBtn.disabled = true;
    const res = await jpost(`${API}/users/${id}/coins/`, { amount, note: giveNote.value.trim() });
    giveBtn.disabled = false;
    if (res.ok && res.data.ok) {
      giveMsg.className = "give-msg is-ok";
      giveMsg.textContent = `Bajarildi! Yangi balans: ${fmt(res.data.balance)} coin`;
      setTimeout(() => renderUserDetail(id), 700);  // reload with fresh data
    } else {
      giveMsg.className = "give-msg is-err";
      giveMsg.textContent = res.data.error || "Xatolik";
    }
  }

  giveBtn.addEventListener("click", () => giveCoins(parseInt(giveAmount.value, 10)));
  document.querySelectorAll(".give-chip").forEach((b) =>
    b.addEventListener("click", () => { giveAmount.value = b.dataset.amt; giveCoins(+b.dataset.amt); })
  );

  // --- admin tools (ban / give-skin / take-skin / free-case / message) ---
  const toolMsg = document.getElementById("toolMsg");
  function tmsg(ok, txt) { toolMsg.className = "give-msg " + (ok ? "is-ok" : "is-err"); toolMsg.textContent = txt; }

  document.getElementById("banBtn").addEventListener("click", async () => {
    const res = await jpost(`${API}/users/${id}/ban/`,
      { reason: (document.getElementById("banReason").value || "").trim() });
    if (res.ok && res.data.ok) renderUserDetail(id); else tmsg(false, (res.data || {}).error || "Xatolik");
  });

  const skinSearch = document.getElementById("skinSearch");
  const skinRes = document.getElementById("skinRes");
  let st;
  skinSearch.addEventListener("input", () => {
    clearTimeout(st);
    st = setTimeout(async () => {
      const q = skinSearch.value.trim();
      if (q.length < 2) { skinRes.innerHTML = ""; return; }
      const items = await jget(`${API}/skins/?q=${encodeURIComponent(q)}`);
      skinRes.innerHTML = items.map((it) => `
        <button class="a-skin" data-item="${it.id}" style="--rc:${esc(it.color) || "#555"}">
          <img src="${IMG(it.image)}" onerror="this.style.visibility='hidden'"/>
          <span class="a-skin__n">${esc(it.name)}</span><span class="coin">${fmt(it.price)}</span>
        </button>`).join("");
      skinRes.querySelectorAll(".a-skin").forEach((b) => b.addEventListener("click", async () => {
        const r = await jpost(`${API}/users/${id}/give-skin/`, { item_id: +b.dataset.item });
        if (r.ok && r.data.ok) { tmsg(true, "Skin berildi ✓"); setTimeout(() => renderUserDetail(id), 600); }
        else tmsg(false, (r.data || {}).error || "Xatolik");
      }));
    }, 250);
  });

  document.getElementById("takeInv").addEventListener("click", (e) => {
    const b = e.target.closest(".a-invitem__x"); if (!b) return;
    openConfirm("Skinni olib qo'yish", `«${b.dataset.name}» inventardan o'chiriladi.`, async () => {
      const r = await jpost(`${API}/users/${id}/take-skin/`, { record_id: +b.dataset.rec });
      if (r.ok && r.data.ok) { tmsg(true, "Olindi ✓"); setTimeout(() => renderUserDetail(id), 500); }
      else tmsg(false, (r.data || {}).error || "Xatolik");
    });
  });

  (async () => {
    const cs = await jget(`${API}/cases/`);
    const sel = document.getElementById("freeCaseSel");
    if (sel) sel.innerHTML = `<option value="">Keys tanlang…</option>` +
      cs.map((c) => `<option value="${c.id}">${esc(c.name)} (${fmt(c.price)})</option>`).join("");
  })();
  document.getElementById("freeCaseBtn").addEventListener("click", async () => {
    const cid = +document.getElementById("freeCaseSel").value;
    if (!cid) { tmsg(false, "Keys tanlang"); return; }
    const n = +document.getElementById("freeCaseN").value || 1;
    const r = await jpost(`${API}/users/${id}/free-case/`, { case_id: cid, count: n });
    if (r.ok && r.data.ok) tmsg(true, "Bepul keys berildi ✓"); else tmsg(false, (r.data || {}).error || "Xatolik");
  });

  document.getElementById("dmBtn").addEventListener("click", async () => {
    const text = document.getElementById("dmText").value.trim();
    if (!text) { tmsg(false, "Xabar bo'sh"); return; }
    const r = await jpost(`${API}/users/${id}/message/`, { text });
    if (r.ok && r.data.ok) { tmsg(true, "Yuborildi ✓"); document.getElementById("dmText").value = ""; }
    else tmsg(false, (r.data || {}).error || "Xatolik");
  });
}

// ---------- audit log ----------
const AUDIT_LABEL = {
  coins: "💰 Coin", ban: "⛔ Blok", unban: "✅ Blokdan", give_skin: "🎁 Skin berdi",
  take_skin: "🗑 Skin oldi", free_case: "📦 Bepul keys", message: "✉️ Xabar",
  broadcast: "📣 Broadcast", case_add: "➕ Keys", case_del: "🗑 Keys o'chirdi",
  skin_add: "➕ Skin", skin_edit: "✏️ Skin", skin_del: "🗑 Skin",
};
async function renderAudit() {
  main.innerHTML = `
    <div class="page-head"><div>
      <div class="page-title">Audit log</div>
      <div class="page-sub">Admin harakatlari — eng yangisi tepada</div>
    </div></div>
    <div id="auditBody"><div class="loading">Yuklanmoqda…</div></div>`;
  const rows = await jget(`${API}/audit/`);
  const body = document.getElementById("auditBody");
  if (!rows.length) { body.innerHTML = `<div class="loading">Hozircha yozuv yo'q.</div>`; return; }
  body.innerHTML = `
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Vaqt</th><th>Admin</th><th>Amal</th><th>Tafsilot</th></tr></thead>
      <tbody>
        ${rows.map((a) => `<tr>
          <td class="cell-muted">${esc(a.at)}</td>
          <td>${esc(a.actor)}</td>
          <td>${AUDIT_LABEL[a.action] || esc(a.action)}</td>
          <td class="cell-muted">${esc(a.detail)}</td>
        </tr>`).join("")}
      </tbody>
    </table></div></div>`;
}

// ---------- cases ----------
let casesCache = [];
function caseFormHTML(c) {
  c = c || {};
  return `
    <div class="cf-grid">
      <label class="cf-f"><span>Nomi</span><input class="admin-input" data-cf="name" value="${esc(c.name || "")}" placeholder="Masalan: STRIKE"/></label>
      <label class="cf-f"><span>Narx (coin)</span><input class="admin-input" data-cf="price" type="number" value="${c.price || ""}" placeholder="5000"/></label>
      <label class="cf-f cf-f--wide"><span>Rasm URL / Steam hash</span><input class="admin-input" data-cf="image" value="${esc(c.image || "")}" placeholder="https://... yoki hash"/></label>
      <label class="cf-f"><span>Tartib</span><input class="admin-input" data-cf="sort_order" type="number" value="${c.sort_order || 0}"/></label>
    </div>`;
}
function readForm(scope, attr) {
  const o = {};
  scope.querySelectorAll(`[data-${attr}]`).forEach((el) => { o[el.getAttribute(`data-${attr}`)] = el.value.trim(); });
  return o;
}

async function renderCases() {
  main.innerHTML = `
    <div class="page-head">
      <div>
        <div class="page-title">Keyslar</div>
        <div class="page-sub">Keys qo'shish · tahrirlash · o'chirish</div>
      </div>
      <button class="admin-btn" id="newCaseBtn">+ Yangi keys</button>
    </div>
    <div class="cf-panel" id="newCasePanel" hidden>
      <div class="a-tool__h">Yangi keys qo'shish</div>
      ${caseFormHTML()}
      <div style="display:flex;gap:8px;margin-top:12px">
        <button class="admin-btn" id="newCaseSave">Qo'shish</button>
        <button class="admin-btn admin-btn--ghost" id="newCaseCancel">Bekor</button>
        <span class="give-msg" id="newCaseMsg" style="margin:0;align-self:center"></span>
      </div>
    </div>
    <div class="page-head" style="margin:0 0 14px"><input class="admin-input" id="caseSearch" placeholder="Key qidirish..." /></div>
    <div id="casesBody"><div class="loading">Yuklanmoqda…</div></div>`;
  const search = document.getElementById("caseSearch");
  let t;
  search.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(() => loadCases(search.value.trim()), 200);
  });
  const panel = document.getElementById("newCasePanel");
  document.getElementById("newCaseBtn").addEventListener("click", () => { panel.hidden = !panel.hidden; });
  document.getElementById("newCaseCancel").addEventListener("click", () => { panel.hidden = true; });
  document.getElementById("newCaseSave").addEventListener("click", async () => {
    const body = readForm(panel, "cf");
    const msg = document.getElementById("newCaseMsg");
    const r = await jpost(`${API}/cases/`, body);
    if (r.ok && r.data.ok) { panel.hidden = true; loadCases(search.value.trim()); }
    else { msg.className = "give-msg is-err"; msg.style.margin = "0"; msg.textContent = (r.data || {}).error || "Xatolik"; }
  });
  loadCases("");
}

async function loadCases(q) {
  const body = document.getElementById("casesBody");
  casesCache = await jget(`${API}/cases/${q ? "?q=" + encodeURIComponent(q) : ""}`);
  body.innerHTML = `
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr>
        <th>Key</th><th>Narx</th><th>Skinlar</th><th>Ochilgan</th>
      </tr></thead>
      <tbody>
        ${casesCache.map((c) => `
          <tr class="clickable" data-id="${c.id}">
            <td><img class="crate-thumb" src="${esc(c.image)}" alt="" onerror="this.style.visibility='hidden'"/>
                <span class="cell-name" style="margin-left:10px">${esc(c.name)}</span></td>
            <td class="coin">${fmt(c.price)}</td>
            <td>${c.items_count}</td>
            <td class="cell-muted">${fmt(c.openings)}</td>
          </tr>`).join("")}
      </tbody>
    </table></div></div>`;
  body.querySelectorAll("tr[data-id]").forEach((tr) =>
    tr.addEventListener("click", () => renderCaseDetail(+tr.dataset.id))
  );
}

function skinFormHTML(it) {
  it = it || {};
  return `
    <div class="cf-grid">
      <label class="cf-f cf-f--wide"><span>Skin nomi</span><input class="admin-input" data-sf="name" value="${esc(it.name || "")}" placeholder="AK-47 | Redline"/></label>
      <label class="cf-f"><span>Ehtimol (%)</span><input class="admin-input" data-sf="chance" type="number" step="0.001" value="${it.chance != null ? it.chance : ""}" placeholder="8.5"/></label>
      <label class="cf-f"><span>Narx (coin)</span><input class="admin-input" data-sf="price" type="number" value="${it.price != null ? it.price : ""}" placeholder="12000"/></label>
      <label class="cf-f"><span>Holati (wear)</span><input class="admin-input" data-sf="wear" value="${esc(it.wear || "")}" placeholder="Field-Tested"/></label>
      <label class="cf-f"><span>Noyoblik</span><input class="admin-input" data-sf="rarity" value="${esc(it.rarity || "")}" placeholder="Covert"/></label>
      <label class="cf-f"><span>Rang (#hex)</span><input class="admin-input" data-sf="color" value="${esc(it.color || "")}" placeholder="#eb4b4b"/></label>
      <label class="cf-f cf-f--wide"><span>Rasm (Steam hash / URL)</span><input class="admin-input" data-sf="image" value="${esc(it.image || "")}" placeholder="hash yoki https://..."/></label>
    </div>`;
}

async function renderCaseDetail(id) {
  main.innerHTML = `<div class="loading">Yuklanmoqda…</div>`;
  const d = await jget(`${API}/cases/${id}/`);
  const c = d.case;
  const totalChance = d.items.reduce((s, it) => s + (it.chance || 0), 0);
  main.innerHTML = `
    <button class="back-btn" id="backBtn">‹ Keyslarga qaytish</button>
    <div class="page-head">
      <div style="display:flex;align-items:center;gap:14px">
        <img class="crate-thumb" style="width:70px;height:52px" src="${esc(c.image)}" alt="" onerror="this.style.visibility='hidden'"/>
        <div>
          <div class="page-title">${esc(c.name)}</div>
          <div class="page-sub"><span class="coin">${fmt(c.price)}</span> · ${c.items_count} skin · ${fmt(c.openings)} ochilgan · jami ehtimol <b class="${Math.abs(totalChance - 100) < 0.5 ? "pct" : "tu-red"}">${totalChance.toFixed(2)}%</b></div>
        </div>
      </div>
      <div style="display:flex;gap:8px">
        <button class="admin-btn admin-btn--ghost" id="editCaseBtn">✏️ Tahrirlash</button>
        <button class="admin-btn admin-btn--danger" id="delCaseBtn">🗑 O'chirish</button>
      </div>
    </div>

    <div class="cf-panel" id="editCasePanel" hidden>
      <div class="a-tool__h">Keysni tahrirlash</div>
      ${caseFormHTML(c)}
      <div style="display:flex;gap:8px;margin-top:12px">
        <button class="admin-btn" id="editCaseSave">Saqlash</button>
        <button class="admin-btn admin-btn--ghost" id="editCaseCancel">Bekor</button>
        <span class="give-msg" id="editCaseMsg" style="margin:0;align-self:center"></span>
      </div>
    </div>

    <div class="section-title" style="display:flex;justify-content:space-between;align-items:center">
      <span>Skinlar (${c.items_count})</span>
      <button class="admin-btn" id="addSkinBtn">+ Skin qo'shish</button>
    </div>
    <div class="cf-panel" id="addSkinPanel" hidden>
      ${skinFormHTML()}
      <div style="display:flex;gap:8px;margin-top:12px">
        <button class="admin-btn" id="addSkinSave">Qo'shish</button>
        <button class="admin-btn admin-btn--ghost" id="addSkinCancel">Bekor</button>
        <span class="give-msg" id="addSkinMsg" style="margin:0;align-self:center"></span>
      </div>
    </div>

    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr>
        <th>Skin</th><th>Holati</th><th>Ehtimol</th><th>Narx</th><th>Noyoblik</th><th></th>
      </tr></thead>
      <tbody id="skinRows">
        ${d.items.map((it) => skinRowHTML(it)).join("")}
      </tbody>
    </table></div></div>`;

  document.getElementById("backBtn").addEventListener("click", () => switchView("cases"));

  // edit case
  const ecp = document.getElementById("editCasePanel");
  document.getElementById("editCaseBtn").addEventListener("click", () => { ecp.hidden = !ecp.hidden; });
  document.getElementById("editCaseCancel").addEventListener("click", () => { ecp.hidden = true; });
  document.getElementById("editCaseSave").addEventListener("click", async () => {
    const r = await jpost(`${API}/cases/${id}/`, readForm(ecp, "cf"));
    const m = document.getElementById("editCaseMsg");
    if (r.ok && r.data.ok) renderCaseDetail(id);
    else { m.className = "give-msg is-err"; m.style.margin = "0"; m.textContent = (r.data || {}).error || "Xatolik"; }
  });
  // delete case
  document.getElementById("delCaseBtn").addEventListener("click", () => {
    openConfirm("Keysni o'chirish", `«${c.name}» va uning barcha skinlari o'chiriladi. Bu qaytmas.`, async () => {
      const r = await jdel(`${API}/cases/${id}/`);
      if (r.ok) switchView("cases");
    });
  });
  // add skin
  const asp = document.getElementById("addSkinPanel");
  document.getElementById("addSkinBtn").addEventListener("click", () => { asp.hidden = !asp.hidden; });
  document.getElementById("addSkinCancel").addEventListener("click", () => { asp.hidden = true; });
  document.getElementById("addSkinSave").addEventListener("click", async () => {
    const r = await jpost(`${API}/cases/${id}/items/`, readForm(asp, "sf"));
    const m = document.getElementById("addSkinMsg");
    if (r.ok && r.data.ok) renderCaseDetail(id);
    else { m.className = "give-msg is-err"; m.style.margin = "0"; m.textContent = (r.data || {}).error || "Xatolik"; }
  });
  // per-skin edit / delete (delegated)
  document.getElementById("skinRows").addEventListener("click", (e) => onSkinRowClick(e, id));
}

function skinRowHTML(it) {
  const ch = it.chance >= 0.1 ? it.chance.toFixed(2) : it.chance.toFixed(3);
  return `<tr data-skin="${it.id}">
    <td><img class="thumb" src="${IMG(it.image)}" alt="" onerror="this.style.visibility='hidden'"/>
        <span class="cell-name" style="margin-left:10px">${esc(it.name)}</span></td>
    <td class="cell-muted">${esc(it.wear || "—")}</td>
    <td class="pct">${ch}%</td>
    <td class="coin">${fmt(it.price)}</td>
    <td><span class="rarity-badge" style="background:${esc(it.color) || "#555"}">${esc(it.rarity || "—")}</span></td>
    <td style="white-space:nowrap">
      <button class="s-mini s-edit" data-id="${it.id}" title="Tahrir">✏️</button>
      <button class="s-mini s-del" data-id="${it.id}" data-name="${esc(it.name)}" title="O'chir">🗑</button>
    </td>
  </tr>`;
}

function onSkinRowClick(e, caseId) {
  const edit = e.target.closest(".s-edit");
  const del = e.target.closest(".s-del");
  if (del) {
    openConfirm("Skinni o'chirish", `«${del.dataset.name}» keysdan o'chiriladi.`, async () => {
      const r = await jdel(`${API}/case-items/${del.dataset.id}/`);
      if (r.ok) renderCaseDetail(caseId);
    });
    return;
  }
  if (edit) {
    const id = edit.dataset.id;
    const row = document.querySelector(`tr[data-skin="${id}"]`);
    if (row.nextElementSibling && row.nextElementSibling.classList.contains("s-editrow")) {
      row.nextElementSibling.remove(); return;
    }
    // pull current values from the row cells
    jget(`${API}/cases/${caseId}/`).then((d) => {
      const it = d.items.find((x) => x.id === +id);
      const tr = document.createElement("tr");
      tr.className = "s-editrow";
      tr.innerHTML = `<td colspan="6"><div class="cf-panel" style="margin:0">
        ${skinFormHTML(it)}
        <div style="display:flex;gap:8px;margin-top:10px">
          <button class="admin-btn" data-save>Saqlash</button>
          <button class="admin-btn admin-btn--ghost" data-cancel>Bekor</button>
          <span class="give-msg" data-msg style="margin:0;align-self:center"></span>
        </div></div></td>`;
      row.after(tr);
      tr.querySelector("[data-cancel]").addEventListener("click", () => tr.remove());
      tr.querySelector("[data-save]").addEventListener("click", async () => {
        const r = await jpost(`${API}/case-items/${id}/`, readForm(tr, "sf"));
        const m = tr.querySelector("[data-msg]");
        if (r.ok && r.data.ok) renderCaseDetail(caseId);
        else { m.className = "give-msg is-err"; m.style.margin = "0"; m.textContent = (r.data || {}).error || "Xatolik"; }
      });
    });
  }
}

boot();
