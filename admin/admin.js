/* SKINRUSH custom admin panel — thin client for /api/admin/*. */
const API = "/api/admin";
const jget = (u) => fetch(u).then((r) => r.json());
const jpost = (u, body) =>
  fetch(u, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  }).then(async (r) => ({ ok: r.ok, data: await r.json().catch(() => ({})) }));

const IMG = (h) =>
  !h ? "" : h.startsWith("http") ? h : "https://community.akamai.steamstatic.com/economy/image/" + h;
const fmt = (n) => Number(n || 0).toLocaleString("ru-RU").replace(/,/g, " ");
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

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

function switchView(view) {
  document.querySelectorAll(".nav-item").forEach((b) =>
    b.classList.toggle("is-active", b.dataset.view === view)
  );
  if (view === "dashboard") renderDashboard();
  else if (view === "users") renderUsers();
  else if (view === "withdraws") renderWithdraws();
  else if (view === "cases") renderCases();
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
  const alert = document.getElementById("wdAlert");
  if (alert) alert.addEventListener("click", () => switchView("withdraws"));
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
  if (e.key === "Escape" && !rejectModal.hidden) closeRejectModal();
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
async function renderUsers() {
  main.innerHTML = `
    <div class="page-head">
      <div>
        <div class="page-title">Foydalanuvchilar</div>
        <div class="page-sub">Ro'yxatdan o'tgan barcha o'yinchilar</div>
      </div>
      <input class="admin-input" id="userSearch" placeholder="Ism yoki username..." />
    </div>
    <div id="usersBody"><div class="loading">Yuklanmoqda…</div></div>`;
  const search = document.getElementById("userSearch");
  let t;
  search.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(() => loadUsers(search.value.trim()), 200);
  });
  loadUsers("");
}

async function loadUsers(q) {
  const body = document.getElementById("usersBody");
  const users = await jget(`${API}/users/${q ? "?q=" + encodeURIComponent(q) : ""}`);
  if (!users.length) {
    body.innerHTML = `<div class="loading">Hozircha foydalanuvchi yo'q.</div>`;
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
              <div class="cell-name">${esc(u.name)}</div>
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
}

// ---------- cases ----------
let casesCache = [];
async function renderCases() {
  main.innerHTML = `
    <div class="page-head">
      <div>
        <div class="page-title">Keyslar</div>
        <div class="page-sub">Barcha keyslar va ularning ichidagi skinlar</div>
      </div>
      <input class="admin-input" id="caseSearch" placeholder="Key qidirish..." />
    </div>
    <div id="casesBody"><div class="loading">Yuklanmoqda…</div></div>`;
  const search = document.getElementById("caseSearch");
  let t;
  search.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(() => loadCases(search.value.trim()), 200);
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

async function renderCaseDetail(id) {
  main.innerHTML = `<div class="loading">Yuklanmoqda…</div>`;
  const d = await jget(`${API}/cases/${id}/`);
  const c = d.case;
  main.innerHTML = `
    <button class="back-btn" id="backBtn">‹ Keyslarga qaytish</button>
    <div class="page-head">
      <div style="display:flex;align-items:center;gap:14px">
        <img class="crate-thumb" style="width:70px;height:52px" src="${esc(c.image)}" alt="" onerror="this.style.visibility='hidden'"/>
        <div>
          <div class="page-title">${esc(c.name)}</div>
          <div class="page-sub"><span class="coin">${fmt(c.price)}</span> · ${c.items_count} skin · ${fmt(c.openings)} ochilgan</div>
        </div>
      </div>
    </div>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr>
        <th>Skin</th><th>Holati</th><th>Ehtimol</th><th>Narx</th><th>Noyoblik</th>
      </tr></thead>
      <tbody>
        ${d.items.map((it) => {
          const ch = it.chance >= 0.1 ? it.chance.toFixed(2) : it.chance.toFixed(3);
          return `<tr>
            <td><img class="thumb" src="${IMG(it.image)}" alt="" onerror="this.style.visibility='hidden'"/>
                <span class="cell-name" style="margin-left:10px">${esc(it.name)}</span></td>
            <td class="cell-muted">${esc(it.wear || "—")}</td>
            <td class="pct">${ch}%</td>
            <td class="coin">${fmt(it.price)}</td>
            <td><span class="rarity-badge" style="background:${esc(it.color) || "#555"}">${esc(it.rarity || "—")}</span></td>
          </tr>`;
        }).join("")}
      </tbody>
    </table></div></div>`;
  document.getElementById("backBtn").addEventListener("click", () => switchView("cases"));
}

boot();
