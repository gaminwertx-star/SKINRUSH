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

  // ---- top drops strip: live feed on every page ----
  // The strip is a marquee whose list is duplicated for a seamless loop. When a
  // newer drop appears we rebuild both halves, newest first, so fresh openings
  // slide in without a reload. Polling pauses while the tab is hidden.
  (function liveStrip() {
    var track = document.getElementById("topTrack");
    if (!track) return;
    var STRIP_POLL = 5000;

    function esc(s) {
      return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
      });
    }

    function cardHTML(d, dim) {
      return '<a class="drop drop-link" href="' + esc(d.href) +
        '" style="--rc:' + esc(d.color) + '"' + (dim ? ' aria-hidden="true" tabindex="-1"' : "") + ">" +
        '<img class="drop__img" src="' + esc(d.img) + '" alt="" loading="lazy" />' +
        '<div class="drop__name">' + esc(d.name) + "</div></a>";
    }

    setInterval(function () {
      if (document.hidden) return;
      fetch("/top-drops-feed/", { credentials: "same-origin", cache: "no-store" })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var drops = data && data.drops;
          if (!drops || !drops.length) return;
          var newest = String(drops[0].id);
          if (track.getAttribute("data-top") === newest) return;  // nothing new
          var half = drops.map(function (d) { return cardHTML(d, false); }).join("");
          var dim = drops.map(function (d) { return cardHTML(d, true); }).join("");
          track.innerHTML = half + dim;         // both marquee halves
          track.setAttribute("data-top", newest);
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
