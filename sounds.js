/* SKINRUSH — sound effects (progressive enhancement).
 *
 * The site is fully server-rendered and works with JS disabled; this file only
 * ADDS audio feedback. It plays three real audio files (no synthesis):
 *   click    — mouse-click.mp3   → every button / link press
 *   open     — case-unlock.mp3   → opening a case (played on the result page)
 *   contract — click-clack.mp3   → creating a contract (played on its result)
 *
 * Every action is a full-page POST→redirect, so the open/contract sounds are
 * played on the page you LAND on, keyed off what it rendered — this way the
 * sound is never cut off by navigation. A mute toggle persists in localStorage.
 */
(function () {
  "use strict";

  var KEY = "sr_muted";
  var muted = localStorage.getItem(KEY) === "1";
  var ctx = null;

  var FILES = {
    click: "/sounds/mouse-click.mp3",
    open: "/sounds/case-unlock.mp3",
    contract: "/sounds/click-clack.mp3"
  };
  var buffers = {};
  var loading = {};

  function ac() {
    if (!ctx) {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      try { ctx = new AC(); } catch (e) { return null; }
    }
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  }

  function load(name) {
    if (buffers[name]) return Promise.resolve(buffers[name]);
    if (loading[name]) return loading[name];
    var c = ac(); if (!c) return Promise.reject();
    loading[name] = fetch(FILES[name])
      .then(function (r) { return r.arrayBuffer(); })
      .then(function (ab) { return c.decodeAudioData(ab); })
      .then(function (buf) { buffers[name] = buf; return buf; });
    return loading[name];
  }

  function play(name, vol) {
    if (muted) return;
    var c = ac(); if (!c) return;
    load(name).then(function (buf) {
      if (muted) return;
      var src = c.createBufferSource(); src.buffer = buf;
      var g = c.createGain(); g.gain.value = vol == null ? 0.9 : vol;
      src.connect(g).connect(c.destination);
      src.start();
    }).catch(function () {});
  }

  // Play now if the context is already running; otherwise try to resume (Chrome
  // may allow it via media-engagement) AND arm a one-time gesture fallback, so a
  // page-load sound still fires the moment the user next touches the page.
  function playOrArm(name) {
    if (muted) return;
    var c = ac(); if (!c) return;
    var done = false;
    function go() {
      if (done) return; done = true;
      document.removeEventListener("pointerdown", go, true);
      play(name);
    }
    if (c.state === "running") { go(); return; }
    document.addEventListener("pointerdown", go, true);
    c.resume().then(function () { if (c.state === "running") go(); }).catch(function () {});
  }

  // ---- instant click on press (fires before navigation) -----------------
  document.addEventListener("pointerdown", function (e) {
    var el = e.target.closest("a, button, summary, label.ss-fastopt, .armory-card, .forge-chip--rm");
    if (!el || el.classList.contains("sfx-toggle")) return;
    // opening a case / forging a contract get their OWN sound on the next page;
    // don't also play the generic click on those presses.
    var form = el.closest("form");
    var action = form ? (form.getAttribute("action") || "") : "";
    if (action.indexOf("/keys/") > -1 && action.indexOf("/ochish/") > -1) return;
    if (action.indexOf("/kontraktlar/create/") > -1) return;
    play("click");
  }, true);

  // ---- page-load cues ---------------------------------------------------
  function onReady() {
    ac();
    load("click"); load("open"); load("contract"); // warm the cache

    // landed on a case-opening result → the unlock sound (reel stays silent)
    if (document.querySelector(".case-view") && document.querySelector(".opening__track--ssr")) {
      playOrArm("open");
    }
    // landed on a contract result → the click-clack of the forge
    if (document.querySelector(".forge-core.is-done")) {
      playOrArm("contract");
    }

    buildToggle();
  }

  // ---- mute toggle (floating) ------------------------------------------
  var ON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M19 5a9 9 0 0 1 0 14"/></svg>';
  var OFF = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4z"/><path d="m23 9-6 6"/><path d="m17 9 6 6"/></svg>';

  function buildToggle() {
    if (document.querySelector(".sfx-toggle")) return;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "sfx-toggle";
    btn.setAttribute("aria-label", "Ovoz / Sound");
    function paint() { btn.classList.toggle("is-muted", muted); btn.innerHTML = muted ? OFF : ON; }
    btn.addEventListener("click", function () {
      muted = !muted;
      localStorage.setItem(KEY, muted ? "1" : "0");
      paint();
      if (!muted) play("click");
    });
    paint();
    document.body.appendChild(btn);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", onReady);
  } else {
    onReady();
  }
})();
