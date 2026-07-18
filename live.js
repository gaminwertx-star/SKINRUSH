/* SKINRUSH — live battles (progressive enhancement, no framework).
 *
 * The site is server-rendered; this file only ADDS real-time updates to the
 * two battle screens by polling the same page every few seconds:
 *   • lobby  /janglar/       → silently swaps the battle-card list so new
 *                              lobbies (from any player) appear without a manual
 *                              refresh, and filled/cancelled ones drop off.
 *   • detail /janglar/<id>/  → while a battle is WAITING, watches the status +
 *                              seat count; the moment a player joins or the
 *                              battle resolves it reloads once so the seats /
 *                              reveal animation show up live.
 * Polling pauses while the tab is hidden. Works with JS disabled = static page.
 */
(function () {
  "use strict";

  // ---- LIVE / TOP drops strip: on every page ----
  // LIVE is a real event feed — it does not auto-scroll, it sits on the newest
  // real drops and only moves when a fresh opening arrives (the new skin slides
  // in at the front, see .drop--new). TOP is the most valuable wins, dearest
  // first. The label toggles which strip shows. Polling pauses when tab hidden.
  (function liveStrip() {
    var strip = document.getElementById("liveStrip");
    var live = document.getElementById("topTrack");
    var top = document.getElementById("topTrackTop");
    if (!strip || !live) return;
    var viewport = live.parentElement;
    var STRIP_POLL = 5000;

    function esc(s) {
      return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
      });
    }

    function cardHTML(d, fresh) {
      return '<a class="drop drop-link' + (fresh ? " drop--new" : "") +
        '" href="' + esc(d.href) + '" style="--rc:' + esc(d.color) + '">' +
        '<img class="drop__img" src="' + esc(d.img) + '" alt="" loading="lazy" />' +
        '<div class="drop__name">' + esc(d.name) + "</div></a>";
    }

    // ---- LIVE <-> TOP toggle ----
    strip.querySelectorAll(".live-tab").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var mode = btn.getAttribute("data-mode");
        strip.setAttribute("data-mode", mode);
        strip.querySelectorAll(".live-tab").forEach(function (b) {
          b.classList.toggle("is-active", b.getAttribute("data-mode") === mode);
        });
        var showTop = mode === "top";
        if (top) top.hidden = !showTop;
        live.hidden = showTop;
        viewport.scrollLeft = 0;
      });
    });

    setInterval(function () {
      if (document.hidden) return;
      fetch("/top-drops-feed/", { credentials: "same-origin", cache: "no-store" })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          // LIVE: prepend fresh drops at the front
          var drops = data && data.drops;
          if (drops && drops.length) {
            var newest = String(drops[0].id);
            var prevTop = parseInt(live.getAttribute("data-top"), 10) || 0;
            if (String(newest) !== String(prevTop)) {
              live.innerHTML = drops.map(function (d) {
                return cardHTML(d, d.id > prevTop);
              }).join("");
              live.setAttribute("data-top", newest);
              if (strip.getAttribute("data-mode") === "live") viewport.scrollLeft = 0;
            }
          }
          // TOP: refresh the valuable-wins list (order by price, changes rarely)
          if (top && data && data.top) {
            var sig = data.top.map(function (d) { return d.id; }).join(",");
            if (top.getAttribute("data-sig") !== sig) {
              top.innerHTML = data.top.map(function (d) { return cardHTML(d, false); }).join("");
              top.setAttribute("data-sig", sig);
            }
          }
        })
        .catch(function () {});
    }, STRIP_POLL);
  })();

  var path = location.pathname.replace(/\/+$/, "");
  var isLobby = /^\/janglar$/.test(path);
  var isDetail = /^\/janglar\/\d+$/.test(path);
  if (!isLobby && !isDetail) return;

  var POLL = 3000;

  function fetchDoc() {
    return fetch(location.href, {
      credentials: "same-origin",
      cache: "no-store",
      headers: { "X-Live": "1" }
    })
      .then(function (r) { return r.text(); })
      .then(function (h) { return new DOMParser().parseFromString(h, "text/html"); });
  }

  // ---- lobby: swap the card list in place ----
  if (isLobby) {
    setInterval(function () {
      if (document.hidden) return;
      fetchDoc().then(function (doc) {
        var fresh = doc.querySelector(".bt-list");
        var cur = document.querySelector(".bt-list");
        if (fresh && cur && fresh.innerHTML.trim() !== cur.innerHTML.trim()) {
          cur.innerHTML = fresh.innerHTML;
        }
      }).catch(function () {});
    }, POLL);
    return;
  }

  // ---- detail: reload once when the battle state changes ----
  var arena = document.querySelector(".bt-arena");
  if (!arena || arena.getAttribute("data-status") !== "waiting") return; // already resolved

  function sig(root) {
    var a = root.querySelector(".bt-arena");
    var status = a ? a.getAttribute("data-status") : "";
    var seats = root.querySelectorAll(".bt-lobby__seat.is-filled").length;
    return status + ":" + seats;
  }

  var current = sig(document);
  var timer = setInterval(function () {
    if (document.hidden) return;
    fetchDoc().then(function (doc) {
      if (sig(doc) === current) return;
      clearInterval(timer);
      var a = doc.querySelector(".bt-arena");
      var next = a ? a.getAttribute("data-status") : "";
      if (next === "completed") {
        // arrive with the reveal flag so the animation plays exactly once
        location.href = location.pathname + "?reveal=1";
      } else {
        location.reload(); // a seat filled — show the updated lobby
      }
    }).catch(function () {});
  }, POLL);
})();
