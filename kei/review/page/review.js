/* Kei review page. Plain JavaScript, no outside assets. The page never approves on its own: the only request that
   names /api/accept is in the Accept button's handler, after a confirm. */
"use strict";

/* ---- the player clock: pure functions, tested under node ---------------------------------------------------- */

/* The number of pictures a play of the round shows: a loop's last picture repeats its first and is not played. */
function playedFrames(frames, loop) {
  return Math.max(1, loop && frames > 1 ? frames - 1 : frames);
}

/* The tick a time falls on, at the shot's fps. A small nudge keeps an exact frame time on its own frame. */
function tickAt(ms, fps) {
  return Math.floor((ms * fps) / 1000 + 1e-6);
}

/* The frame on screen after ms of play: from the elapsed time and the fps, never from the browser's timer rate. */
function frameAt(ms, fps, frames, loop) {
  const n = playedFrames(frames, loop);
  return ((tickAt(ms, fps) % n) + n) % n;
}

/* How many whole plays of the round fit in ms. */
function loopsAt(ms, fps, frames, loop) {
  return Math.floor(tickAt(ms, fps) / playedFrames(frames, loop));
}

/* Ten plays in a row: the frame, the plays finished, and whether the ten are done (then it rests on the last frame). */
function x10Frame(ms, fps, frames, loop) {
  const n = playedFrames(frames, loop);
  const loops = loopsAt(ms, fps, frames, loop);
  if (loops >= 10) return { frame: n - 1, loops: 10, done: true };
  return { frame: frameAt(ms, fps, frames, loop), loops: loops, done: false };
}

/* "before: blocking" or "after: p3, r2". Before and after are always labelled, never blind. */
function roundLabel(side, round) {
  if (!round) return side + ": none";
  if (round.round === round.pass) return side + ": " + round.pass;
  return side + ": " + round.pass + ", " + round.round;
}

/* One frame on or back from frame f. A cycle wraps at its seam; a shot that is not a loop stops at its ends. */
function stepFrame(f, delta, frames, loop) {
  const n = playedFrames(frames, loop);
  const g = f + delta;
  if (loop) return ((g % n) + n) % n;
  return Math.max(0, Math.min(n - 1, g));
}

/* The Left and Right arrow keys step one frame; never while the user types in a field. */
function keyDelta(key, tag, editable) {
  if (editable || tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return 0;
  if (key === "ArrowRight") return 1;
  if (key === "ArrowLeft") return -1;
  return 0;
}

/* The frame on screen while a question loops over its own frames (range [first, last]; none: the whole round). */
function rangeFrame(ms, fps, range, frames, loop) {
  if (!range) return frameAt(ms, fps, frames, loop);
  const last = playedFrames(frames, loop) - 1;
  const a = Math.max(0, Math.min(last, range[0]));
  const b = Math.max(a, Math.min(last, range[1]));
  return a + (tickAt(ms, fps) % (b - a + 1));
}

/* Y and N answer the question on screen, E switches a no between this shot and every shot; never while the user
   types in a field. */
function keyCard(key, tag, editable) {
  if (editable || tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return null;
  const k = String(key).toLowerCase();
  return k === "y" ? "yes" : k === "n" ? "no" : k === "e" ? "every" : null;
}

/* The scope of the note the cards send: every shot (a rule) when any no was marked every shot, else this shot. */
function noteScope(answers) {
  return answers.some((a) => a && a.answer === "no" && a.scope === "every") ? "every" : "shot";
}

/* One question at a time. A yes only passes that check; a no needs words or a pen stroke. Only the deliberate
   Approve event, after the last card with every answer yes, gives the "accept" effect: a run of yes never does. */
function cardStart(total) {
  return { i: 0, total: total, answers: [] };
}

function cardReducer(state, event) {
  const done = state.i >= state.total;
  const allYes = state.answers.length === state.total && state.answers.every((a) => a.answer === "yes");
  const next = (answer) => {
    const answers = state.answers.slice();
    answers[state.i] = answer;
    return { state: { ...state, answers: answers, i: state.i + 1 }, effects: ["next"] };
  };
  switch (event.type) {
    case "yes":
      return done ? { state, effects: [] } : next({ answer: "yes" });
    case "no":
      if (done) return { state, effects: [] };
      if (!(event.note || "").trim() && !event.drew) return { state, effects: ["need-reason"] };
      return next({ answer: "no", note: event.note || "", drew: !!event.drew,
        scope: event.scope === "every" ? "every" : "shot" });
    case "back":
      return { state: { ...state, i: Math.max(0, state.i - 1) }, effects: ["next"] };
    case "approve":
      return { state, effects: done && allYes ? ["accept"] : ["refused"] };
    case "send":
      return { state, effects: done && !allYes ? ["needs-work"] : ["refused"] };
    default:
      return { state, effects: [] };
  }
}

/* The author's note from the cards answered no: their words as typed; a no with only a drawing names its check. */
function noteFromCards(cards, answers) {
  const out = [];
  answers.forEach((a, i) => {
    if (!a || a.answer !== "no") return;
    out.push((a.note || "").trim() ? a.note : cards[i].text + " (see my drawing)");
  });
  return out.join("\n\n");
}

function summaryLine(answers) {
  const yes = answers.filter((a) => a && a.answer === "yes").length;
  const no = answers.filter((a) => a && a.answer === "no").length;
  return answers.length + " checked: " + yes + " yes, " + no + " no";
}

/* One line of the share log, as the page shows it after Accept or Reject. */
function shareLine(e) {
  const head = "Lesson " + e.lesson + ": ";
  if (e.result === "sent") return head + "sent to " + e.repo + ": " + e.pr;
  if (e.result === "refused") return head + "not sent to " + e.repo + ": " + e.reason;
  if (e.result === "form opened") return head + "GitHub's pull request form was opened for " + e.repo;
  if (e.result === "kept") return head + "kept here, not shared: " + e.reason;
  return head + (e.reason || e.result || "");
}

if (typeof module !== "undefined") {
  module.exports = { playedFrames, frameAt, loopsAt, x10Frame, roundLabel, stepFrame, keyDelta, rangeFrame,
    keyCard, noteScope, cardStart, cardReducer, noteFromCards, summaryLine, shareLine };
}

/* ---- the page --------------------------------------------------------------------------------------------------- */

if (typeof document !== "undefined") {
  const TOKEN = document.querySelector('meta[name="kei-token"]').content;
  const VIEWS = ["side", "three quarter", "front", "back"];
  const pad4 = (n) => String(n).padStart(4, "0");

  function el(tag, attrs, ...children) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) {
      if (c === null || c === undefined || c === false) continue;
      e.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return e;
  }

  async function getJson(path) {
    const r = await fetch(path, { credentials: "same-origin" });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || "the request failed (" + r.status + ")");
    return data;
  }

  async function postJson(path, body) {
    const r = await fetch(path, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-Kei-Token": TOKEN },
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || "the request failed (" + r.status + ")");
    return data;
  }

  const app = document.getElementById("app");
  const ui = { tabs: {}, panes: {} };

  function say(text, kind) {
    for (const m of document.querySelectorAll("#message, .say")) {
      m.textContent = text || "";
      m.className = (m.classList.contains("say") ? "say " : "") + "message" + (kind ? " " + kind : "");
    }
  }

  /* ---- a round player: preloaded pictures drawn on a canvas, so the frame on screen is exact ---------------- */

  function makePlayer(side, round) {
    const box = el("figure", { class: "player " + side });
    const label = el("figcaption", { class: "round-label", text: roundLabel(side, round) });
    const stage = el("div", { class: "stage" });
    const canvas = el("canvas", { class: "frame" });
    stage.append(canvas);
    for (const v of VIEWS) stage.append(el("span", { class: "view-label v" + VIEWS.indexOf(v), text: v }));
    box.append(label, stage);
    const p = { side, round, box, stage, canvas, images: [], ready: false, frame: 0, overlay: null };
    if (!round) {
      stage.classList.add("empty");
      stage.append(el("p", { class: "empty-note", text: "No round to compare with yet." }));
      p.ready = true;
      return p;
    }
    let loaded = 0;
    const done = new Promise((resolve) => {
      for (let f = 0; f < round.frames; f++) {
        const img = new Image();
        img.onload = img.onerror = () => {
          loaded += 1;
          if (loaded === round.frames) resolve();
        };
        img.src = "/file/" + round.round + "/f" + pad4(f);
        p.images.push(img);
      }
    });
    p.loaded = done.then(() => {
      const first = p.images[0];
      canvas.width = first.naturalWidth || 2 * (round.size || 360);
      canvas.height = first.naturalHeight || 2 * (round.size || 360);
      p.ready = true;
      show(p, 0);
    });
    return p;
  }

  function show(p, f) {
    if (!p.round || !p.ready) return;
    p.frame = f;
    const img = p.images[f];
    const ctx = p.canvas.getContext("2d");
    ctx.clearRect(0, 0, p.canvas.width, p.canvas.height);
    if (img && img.complete && img.naturalWidth) ctx.drawImage(img, 0, 0);
    if (p.overlay) p.overlay.redraw(f);
  }

  /* ---- the sign-off view ---------------------------------------------------------------------------------- */

  const clock = { ms: 0, playing: false, start: 0, x10: false, seenSent: false, raf: 0 };

  function renderShot(data) {
    const pane = ui.panes.review;
    pane.replaceChildren();
    const after = data.after;
    const before = data.before;
    const head = el("header", { class: "shot-head" },
      el("h1", { text: "Sign-off: " + data.shot }),
      el("p", { class: "status", text: "status: " + data.status.replace("_", " ") + ", stage: " + data.stage }));
    pane.append(head);
    if (!after) {
      pane.append(el("p", { text: "This shot has no review round." }));
      return;
    }
    if (data.latest_round && data.latest_round !== after.round) {
      pane.append(el("p", { class: "message warn",
        text: "A newer round (" + data.latest_round + ") exists. Close this page and run kei review again." }));
    }
    const pb = makePlayer("before", before);
    const pa = makePlayer("after", after);
    ui.after = pa;
    ui.before = pb;
    ui.data = data;
    if (window.KeiPen) pa.overlay = window.KeiPen.attach(pa, after);
    pane.append(el("div", { class: "players" }, pb.box, pa.box));
    if (data.characters_differ) {
      pane.append(el("p", { class: "message warn", text: "Before is drawn on " + before.character + ", after on " +
        after.character + ": each pass plays on the character its shot.json names." }));
    }

    const counter = el("span", { class: "counter", id: "counter" });
    const frameNo = el("strong", { class: "frame-no", id: "frame-no", "aria-live": "polite" });
    const loops = el("span", { class: "loops", id: "loops" });
    const scrub = el("input", { type: "range", min: "0", max: String(playedLastIndex(after)), value: "0",
      class: "scrub", "aria-label": "frame", oninput: () => seekFrame(Number(scrub.value)) });
    ui.scrub = scrub;
    const playBtn = el("button", { type: "button", id: "play", text: "Play", onclick: togglePlay });
    const controls = el("div", { class: "controls" },
      el("button", { type: "button", text: "Step back", title: "one frame back", onclick: () => step(-1) }),
      playBtn,
      el("button", { type: "button", text: "Step", title: "one frame on", onclick: () => step(1) }),
      el("button", { type: "button", id: "x10", text: "Play x10", title: "ten loops at the shot's frame rate",
        onclick: playTen }),
      scrub, frameNo, counter, loops);
    pane.append(controls);
    if (window.KeiPen) pane.append(window.KeiPen.toolbar(pa));
    pane.append(el("p", { class: "fps-note",
      text: "Plays at " + after.fps + " fps from frame times" + (after.loop ? ", as a loop." : ".") +
        " The Left and Right arrow keys step one frame." }));
    window.KeiPage.onStep = step;

    Promise.all([pa.loaded, pb.loaded].filter(Boolean)).then(() => {
      if (ui.mode === "cards") loopCard();   // the question's frames loop at once
      else seekFrame(0);
      say("");
    });
    say("Loading " + after.frames + " frames.");

    const full = [pb.box, renderChecklist(data), renderActions(data)];
    pane.append(full[1], full[2]);
    if (data.share && data.share.lessons && data.share.lessons.length && window.KeiShare) {
      pane.append(window.KeiShare.panel(data.share));
    }
    if (data.share && data.share.mode === "auto" && data.share.log && data.share.log.length && window.KeiShare) {
      pane.append(window.KeiShare.sent(data.share));
    }
    if (data.actions.length) {
      const cards = renderCards(data);
      pane.insertBefore(cards, controls);
      const toggle = el("button", { type: "button", class: "see-all", id: "see-all" });
      const setMode = (mode) => {
        ui.mode = mode;
        for (const e of full) e.hidden = mode === "cards";
        cards.hidden = mode !== "cards";
        pane.querySelector(".players").classList.toggle("single", mode === "cards");
        toggle.textContent = mode === "cards" ? "See everything" : "One question at a time";
        if (mode !== "cards") ui.cardRange = null;
        else showCard();
      };
      toggle.addEventListener("click", () => setMode(ui.mode === "cards" ? "all" : "cards"));
      head.append(toggle);
      setMode("cards");
    } else {
      ui.mode = "all";
    }
    updateCounter();
  }

  /* ---- one question at a time ---------------------------------------------------------------------------- */

  const cardUi = { state: null, items: [], penBase: 0 };

  function renderCards(data) {
    cardUi.items = data.checklist;
    cardUi.state = cardStart(data.checklist.length);
    const box = el("section", { class: "cards", id: "cards", "aria-live": "polite" });
    cardUi.box = box;
    cardUi.message = el("p", { class: "say message", role: "status" });
    return box;
  }

  function strokes() {
    return ui.after && ui.after.pen ? ui.after.pen.strokes.length : 0;
  }

  function showCard() {
    const box = cardUi.box;
    const st = cardUi.state;
    const items = cardUi.items;
    box.replaceChildren(cardUi.message);
    if (st.i < st.total) {
      const item = items[st.i];
      ui.cardRange = item.range;
      cardUi.penBase = strokes();
      const why = el("textarea", { id: "card-note", rows: "2",
        placeholder: "If no: say what is wrong, or draw on the frame with the Pen. Kei keeps your words as you write them." });
      const every = el("input", { type: "checkbox", id: "card-every" });
      cardUi.every = every;
      box.append(
        el("p", { class: "card-count", text: "Question " + (st.i + 1) + " of " + st.total }),
        el("p", { class: "card-text", text: item.text }),
        el("div", { class: "card-buttons" },
          el("button", { type: "button", class: "primary", text: "Yes (Y)", onclick: () => answer("yes") }),
          el("button", { type: "button", class: "danger", text: "No (N)", onclick: () => answer("no") }),
          st.i > 0 ? el("button", { type: "button", text: "Back", onclick: () => apply({ type: "back" }) }) : null),
        why,
        el("p", {}, every, el("label", { for: "card-every",
          text: " If no: a rule for every shot, not only this one (E). Kei can share a rule once you see it fixed." })),
        el("p", { class: "hint", text: "The shot loops over " + (item.range ? "frames " + item.range[0] + "-" +
          item.range[1] : "the whole round") + ". Left and Right step a frame; Y and N answer; E marks a rule." }));
      if (ui.after && ui.after.ready) loopCard();
      return;
    }
    ui.cardRange = null;
    const allYes = st.answers.every((a) => a.answer === "yes");
    box.append(el("p", { class: "card-text", text: st.total ? summaryLine(st.answers) + "." :
      "The critics left no question for you to answer by eye." }));
    if (allYes) {
      box.append(el("p", { class: "hint", text: "Your yes answers do not sign the shot off. Approve does, and only when you press it." }),
        el("div", { class: "card-buttons" },
          el("button", { type: "button", class: "primary", text: "Approve the shot", onclick: () => apply({ type: "approve" }) }),
          st.total ? el("button", { type: "button", text: "Back", onclick: () => apply({ type: "back" }) }) : null));
    } else {
      const stage = el("select", { id: "card-stage", "aria-label": "the stage the shot goes back to" },
        ui.data.stages.map((x) => el("option", { value: x, text: x, selected: x === ui.data.default_stage })));
      box.append(el("pre", { class: "card-note", text: noteFromCards(cardUi.items, st.answers) }),
        el("p", { class: "hint", text: noteScope(st.answers) === "every" ? "This note is a rule for every shot." :
          "This note is for this shot only." }),
        el("div", { class: "card-buttons" }, el("label", { for: "card-stage", text: "Send it back to " }), stage,
          el("button", { type: "button", class: "primary", text: "Send it back with my notes", onclick: () => apply({ type: "send" }) }),
          el("button", { type: "button", text: "Back", onclick: () => apply({ type: "back" }) })));
    }
  }

  function loopCard() {
    if (ui.mode !== "cards") return;
    if (clock.playing) stopPlay();
    clock.x10 = false;
    clock.ms = 0;
    startPlay();
  }

  function answer(kind) {
    if (kind === "every") {
      if (cardUi.every) cardUi.every.checked = !cardUi.every.checked;
      return;
    }
    if (kind === "yes") return apply({ type: "yes" });
    const note = document.getElementById("card-note");
    return apply({ type: "no", note: note ? note.value : "", drew: strokes() > cardUi.penBase,
      scope: cardUi.every && cardUi.every.checked ? "every" : "shot" });
  }

  async function apply(event) {
    const r = cardReducer(cardUi.state, event);
    cardUi.state = r.state;
    if (r.effects.includes("need-reason")) {
      say("A no needs a reason: write what is wrong, or draw on the frame with the Pen.", "error");
      return;
    }
    if (r.effects.includes("refused")) return;
    if (r.effects.includes("accept")) return approveFromCards();
    if (r.effects.includes("needs-work")) return sendFromCards();
    say("");
    showCard();
  }

  async function approveFromCards() {
    const r = ui.after.round;
    if (!confirm("Approve " + roundLabel("after", r) + "? The shot is done.")) return;
    try {
      await postJson("/api/accept", { round: r.round, ticked: cardUi.items.flatMap((i) => i.checks) });
      await refresh();
      say("Approved. The shot is done.", "ok");
    } catch (e) {
      say(e.message, "error");
    }
  }

  async function sendFromCards() {
    const r = ui.after.round;
    const st = cardUi.state;
    const stage = document.getElementById("card-stage").value;
    if (!confirm("Send the shot back to " + stage + " with your notes?")) return;
    const cards = st.answers.map((a, i) => ({ check: cardUi.items[i].checks[0], checks: cardUi.items[i].checks,
      answer: a.answer, note: a.note || "", scope: a.scope || "shot" }));
    try {
      const out = await postJson("/api/needs-work", { round: r.round, text: noteFromCards(cardUi.items, st.answers),
        stage: stage, cards: cards, scope: noteScope(st.answers),
        drawings: window.KeiPen ? window.KeiPen.export(ui.after) : [] });
      await refresh();
      say("Sent back to " + out.stage + ". Lesson " + out.lesson + " added. Continue with kei run.", "ok");
    } catch (e) {
      say(e.message, "error");
    }
  }

  function playedLastIndex(round) {
    return playedFrames(round.frames, round.loop) - 1;
  }

  function currentMs() {
    return clock.playing ? clock.ms + (performance.now() - clock.start) : clock.ms;
  }

  function paint() {
    const a = ui.after.round;
    let ms = currentMs();
    let fa;
    let loopsDone;
    if (clock.x10) {
      const r = x10Frame(ms, a.fps, a.frames, a.loop);
      fa = r.frame;
      loopsDone = r.loops;
      if (r.done) {
        stopPlay(ms);
        clock.x10 = false;
        clock.ms = (fa + 0.5) * 1000 / a.fps;
        ms = clock.ms;   // both players rest on the last frame of the after round's time
        document.getElementById("loops").textContent = "10 of 10 loops";
        markSeen(10);
      } else {
        document.getElementById("loops").textContent = "loop " + (loopsDone + 1) + " of 10";
      }
    } else if (ui.mode === "cards" && ui.cardRange && clock.playing) {
      fa = rangeFrame(ms, a.fps, ui.cardRange, a.frames, a.loop);
      document.getElementById("loops").textContent = "looping frames " + ui.cardRange[0] + "-" + ui.cardRange[1];
    } else {
      fa = frameAt(ms, a.fps, a.frames, a.loop);
      loopsDone = loopsAt(ms, a.fps, a.frames, a.loop);
      if (clock.playing) document.getElementById("loops").textContent = loopsDone + " loops played";
    }
    show(ui.after, fa);
    const b = ui.before.round;
    if (b) {
      // playing: the same clock at the before round's own fps; paused or stepping: the same frame as after
      show(ui.before, clock.playing ? frameAt(ms, b.fps, b.frames, b.loop)
        : Math.min(fa, playedFrames(b.frames, b.loop) - 1));
    }
    ui.scrub.value = String(fa);
    updateCounter();
    if (clock.playing) clock.raf = requestAnimationFrame(paint);
  }

  function updateCounter() {
    const c = document.getElementById("counter");
    if (!c || !ui.after) return;
    const a = ui.after.round;
    const no = document.getElementById("frame-no");
    if (no) no.textContent = "frame " + ui.after.frame;
    let text = "after f" + ui.after.frame + " of " + playedLastIndex(a);
    if (ui.before && ui.before.round) text += ", before f" + ui.before.frame + " of " + playedLastIndex(ui.before.round);
    c.textContent = text;
  }

  function startPlay() {
    if (!ui.after.ready) return;
    clock.start = performance.now();
    clock.playing = true;
    document.getElementById("play").textContent = "Pause";
    clock.raf = requestAnimationFrame(paint);
  }

  function stopPlay(ms) {
    clock.ms = ms === undefined ? currentMs() : ms;
    clock.playing = false;
    cancelAnimationFrame(clock.raf);
    document.getElementById("play").textContent = "Play";
  }

  function togglePlay() {
    if (clock.playing) {
      const a = ui.after.round;
      const played = loopsAt(currentMs(), a.fps, a.frames, a.loop);
      stopPlay();
      clock.x10 = false;
      if (played >= 1) markSeen(played);
      paint();
    } else {
      startPlay();
    }
  }

  function playTen() {
    if (clock.playing) stopPlay();
    clock.ms = 0;
    clock.x10 = true;
    document.getElementById("loops").textContent = "loop 1 of 10";
    startPlay();
  }

  function seekFrame(f) {
    if (clock.playing) stopPlay();
    clock.x10 = false;
    const a = ui.after.round;
    clock.ms = (f + 0.5) * 1000 / a.fps;
    paint();
  }

  function step(d) {
    const a = ui.after.round;
    seekFrame(stepFrame(ui.after.frame, d, a.frames, a.loop));   // seekFrame pauses the play first
  }

  function markSeen(loops) {
    if (clock.seenSent) return;
    clock.seenSent = true;
    postJson("/api/seen", { round: ui.after.round.round, loops: loops }).catch(() => { clock.seenSent = false; });
  }

  function renderChecklist(data) {
    const items = data.checklist;
    const box = el("details", { class: "checklist", id: "checklist" });
    const n = items.length;
    box.append(el("summary", {}, el("strong", { text: n ? n + (n === 1 ? " thing" : " things") + " to check by eye" :
      "Nothing left to check by eye" }), el("span", { class: "hint", text: n ? " before you accept (click to open)" : "" })));
    if (!n) {
      box.append(el("p", { text: "The critics left no check about this pass. Watch the loop and judge it by eye." }));
      return box;
    }
    box.append(el("p", { class: "hint", text: "The critics could not check these. Tick each one yourself." }));
    const list = el("ul");
    items.forEach((item, i) => {
      const id = "check" + i;
      const input = el("input", { type: "checkbox", id: id, class: "tick" });
      input.dataset.checks = JSON.stringify(item.checks);
      const buttons = item.parts.slice(1).map((part) => part.frame !== undefined
        ? el("button", { type: "button", class: "chip", text: part.label, title: "show frame " + part.frame,
          onclick: () => { seekFrame(Math.min(part.frame, playedLastIndex(ui.after.round))); } })
        : el("button", { type: "button", class: "chip", text: "play " + part.play,
          title: "play this pass on the page (" + part.play + ")", onclick: playTen }));
      const meta = [item.rules.join(", "), item.from.join(", ")].filter(Boolean).join("; ");
      list.append(el("li", {}, input, el("label", { for: id, text: " " + item.text }), " ", ...buttons,
        el("span", { class: "from", text: " " + meta, title: item.checks.join("\n\n") })));
    });
    box.append(list);
    if (data.checklist_hidden) {
      box.append(el("p", { class: "hint", text: data.checklist_hidden + " older check(s) about other passes are kept in the shot's state file and not shown." }));
    }
    return box;
  }

  function ticked() {
    return Array.from(document.querySelectorAll("input.tick:checked")).flatMap((i) => JSON.parse(i.dataset.checks));
  }

  function renderActions(data) {
    const box = el("section", { class: "actions" });
    box.append(el("p", { id: "message", class: "message", role: "status" }));
    if (!data.actions.length) {
      box.append(el("p", { text: "This shot is not waiting for a sign-off, so there is nothing to sign here." }));
      return box;
    }
    const stage = el("select", { id: "stage", "aria-label": "the stage the shot goes back to" },
      data.stages.map((s) => el("option", { value: s, text: s, selected: s === data.default_stage })));
    const note = el("textarea", { id: "note", rows: "4", placeholder: "What is wrong, in your own words. Kei keeps them as you write them." });
    const reason = el("textarea", { id: "reason", rows: "2", placeholder: "Why the shot is rejected." });
    const keep = el("input", { type: "checkbox", id: "keep" });
    box.append(
      el("div", { class: "action accept" },
        el("h2", { text: "Accept" }),
        el("p", { text: "The shot is done. Only you can do this." }),
        el("button", { type: "button", class: "primary", text: "Accept", onclick: onAccept })),
      el("div", { class: "action needs-work" },
        el("h2", { text: "Needs work" }),
        note,
        el("label", { for: "stage", text: "Send it back to " }), stage,
        el("p", {}, el("input", { type: "checkbox", id: "every" }),
          el("label", { for: "every", text: " A rule for every shot, not only this one" })),
        el("p", { class: "hint", id: "drawn-note" }),
        el("button", { type: "button", text: "Needs work", onclick: onNeedsWork })),
      el("div", { class: "action reject" },
        el("h2", { text: "Reject" }),
        reason,
        el("p", {}, keep, el("label", { for: "keep", text: " Keep the reason as a lesson" })),
        el("button", { type: "button", class: "danger", text: "Reject", onclick: onReject })));
    return box;
  }

  async function onAccept() {
    const r = ui.after.round;
    if (!confirm("Accept " + roundLabel("after", r) + "? The shot is done.")) return;
    try {
      const out = await postJson("/api/accept", { round: r.round, ticked: ticked() });
      await refresh();
      say("Accepted. The shot is done.", "ok");
      if (out.share && window.KeiShare) window.KeiShare.after(out.share);
    } catch (e) {
      say(e.message, "error");
    }
  }

  async function onNeedsWork() {
    const r = ui.after.round;
    const text = document.getElementById("note").value;
    const stage = document.getElementById("stage").value;
    if (!text.trim()) return say("Say what is wrong first: the note needs words.", "error");
    const drawn = window.KeiPen ? window.KeiPen.count(ui.after) : 0;
    if (!confirm("Send the shot back to " + stage + " with your note" + (drawn ? " and " + drawn + " drawing(s)" : "") + "?")) return;
    try {
      const drawings = window.KeiPen ? window.KeiPen.export(ui.after) : [];
      const out = await postJson("/api/needs-work", { round: r.round, text: text, stage: stage, drawings: drawings,
        scope: document.getElementById("every").checked ? "every" : "shot" });
      say("Sent back to " + out.stage + ". Lesson " + out.lesson + " added. Continue with kei run.", "ok");
      await refresh();
    } catch (e) {
      say(e.message, "error");
    }
  }

  async function onReject() {
    const r = ui.after.round;
    const reason = document.getElementById("reason").value;
    if (!reason.trim()) return say("Say why first: a reject needs a reason.", "error");
    if (!confirm("Reject this shot? kei note can reopen it later.")) return;
    try {
      const out = await postJson("/api/reject", { round: r.round, reason: reason, keep_as_lesson: document.getElementById("keep").checked });
      say("Rejected. The reason is kept with the shot.", "ok");
      await refresh();
      if (out.share && window.KeiShare) window.KeiShare.after(out.share);
    } catch (e) {
      say(e.message, "error");
    }
  }

  async function refresh() {
    const data = await getJson("/api/shot");
    const keepMsg = document.getElementById("message");
    const text = keepMsg ? keepMsg.textContent : "";
    const kind = keepMsg ? keepMsg.className.replace("message", "").trim() : "";
    if (clock.playing) stopPlay();
    renderShot(data);
    say(text, kind);
  }

  /* ---- tabs and start --------------------------------------------------------------------------------------- */

  window.KeiPage = { el, getJson, postJson, say, makePlayer, show, ui, VIEWS, pad4 };

  function addTab(name, title) {
    const btn = el("button", { type: "button", role: "tab", class: "tab", text: title,
      onclick: () => selectTab(name) });
    const pane = el("section", { class: "pane", role: "tabpanel", id: "pane-" + name, hidden: true });
    ui.tabs[name] = btn;
    ui.panes[name] = pane;
    document.getElementById("tabs").append(btn);
    app.append(pane);
    return pane;
  }

  function selectTab(name) {
    for (const [k, b] of Object.entries(ui.tabs)) {
      b.setAttribute("aria-selected", k === name ? "true" : "false");
      ui.panes[k].hidden = k !== name;
    }
    if (name === "settings" && window.KeiSettings) window.KeiSettings.load(ui.panes.settings);
  }

  async function start() {
    app.replaceChildren();
    const bar = el("nav", { class: "bar" }, el("span", { class: "brand", text: "Kei review" }),
      el("div", { id: "tabs", role: "tablist" }),
      el("button", { type: "button", class: "close", text: "Close", title: "stop the local server",
        onclick: onClose }));
    document.body.prepend(bar);
    addTab("review", "Review");
    if (window.KeiSettings) addTab("settings", "Settings");
    selectTab("review");
    try {
      const mode = await getJson("/api/mode");
      if (mode.mode === "shot") renderShot(await getJson("/api/shot"));
      else if (mode.mode === "lesson" && window.KeiLesson) window.KeiLesson.render(ui.panes.review);
      else if (mode.mode === "list" && window.KeiList) window.KeiList.render(ui.panes.review, mode);
      else if (mode.mode === "settings") selectTab("settings");
    } catch (e) {
      ui.panes.review.replaceChildren(el("p", { class: "message error", text: e.message }));
    }
  }

  async function onClose() {
    if (!confirm("Stop the review server? This page stops working.")) return;
    try { await postJson("/api/close", {}); } catch (e) { /* the server may already be gone */ }
    document.body.replaceChildren(el("p", { class: "closed", text: "The review server stopped. You can close this tab." }));
  }

  document.addEventListener("keydown", (ev) => {
    if (ev.altKey || ev.ctrlKey || ev.metaKey) return;
    const t = ev.target || {};
    const typing = t.tagName === "INPUT" && !["range", "checkbox", "radio", "button", "color"].includes(t.type);
    const tag = t.tagName === "INPUT" && !typing ? "BODY" : t.tagName;
    const card = keyCard(ev.key, tag, !!t.isContentEditable);
    if (card && window.KeiPage.lessonKey && !(ui.panes.review && ui.panes.review.hidden)) {
      ev.preventDefault();
      window.KeiPage.lessonKey(card);
      return;
    }
    if (card && ui.mode === "cards" && cardUi.box && !cardUi.box.hidden && cardUi.state.i < cardUi.state.total
        && !(ui.panes.review && ui.panes.review.hidden)) {
      ev.preventDefault();
      answer(card);
      return;
    }
    const d = keyDelta(ev.key, tag, !!t.isContentEditable);
    const pane = ui.panes.review;
    if (!d || !window.KeiPage.onStep || (pane && pane.hidden)) return;
    ev.preventDefault();
    window.KeiPage.onStep(d);
  });

  document.addEventListener("DOMContentLoaded", start);
}

/* ---- the pen: strokes per frame and view, in view pixels, flattened to one PNG per drawn frame and view -------- */

if (typeof document !== "undefined") {
  const K = window.KeiPage;
  const PEN = { color: "#ff3b6b", width: 3 };

  window.KeiPen = {
    attach(player, round) {
      const pen = K.el("canvas", { class: "pen off", "aria-label": "drawing layer" });
      player.stage.append(pen);
      const o = { pen, strokes: [], on: false, current: null, player };
      player.pen = o;
      const panel = () => pen.width / 2;
      const sync = () => {
        if (pen.width !== player.canvas.width) {
          pen.width = player.canvas.width;
          pen.height = player.canvas.height;
        }
      };
      const at = (ev) => {
        const r = pen.getBoundingClientRect();
        return [(ev.clientX - r.left) * pen.width / r.width, (ev.clientY - r.top) * pen.height / r.height];
      };
      o.redraw = (f) => {
        sync();
        const ctx = pen.getContext("2d");
        ctx.clearRect(0, 0, pen.width, pen.height);
        for (const s of o.strokes.filter((s) => s.frame === f)) drawStroke(ctx, s, panel());
        if (o.current) drawStroke(ctx, o.current, panel());
      };
      pen.addEventListener("pointerdown", (ev) => {
        if (!o.on) return;
        const play = document.getElementById("play");
        if (play && play.textContent === "Pause") play.click();   // drawing stops the play on the frame shown
        sync();
        const [x, y] = at(ev);
        const p = panel();
        const col = x < p ? 0 : 1;
        const row = y < p ? 0 : 1;
        const view = K.VIEWS[row * 2 + col];
        o.current = { frame: player.frame, view, points: [[x - col * p, y - row * p]], color: PEN.color,
          width: PEN.width, _ox: col * p, _oy: row * p };
        pen.setPointerCapture(ev.pointerId);
      });
      pen.addEventListener("pointermove", (ev) => {
        if (!o.current) return;
        const [x, y] = at(ev);
        o.current.points.push([round1(x - o.current._ox), round1(y - o.current._oy)]);
        o.redraw(player.frame);
      });
      const end = () => {
        if (!o.current) return;
        const s = o.current;
        o.current = null;
        delete s._ox;
        delete s._oy;
        if (s.points.length === 1) s.points.push([s.points[0][0] + 0.1, s.points[0][1] + 0.1]);   // a dot
        o.strokes.push(s);
        o.redraw(player.frame);
        listDrawn(o);
      };
      pen.addEventListener("pointerup", end);
      pen.addEventListener("pointercancel", end);
      return o;
    },

    toolbar(player) {
      const o = player.pen;
      const toggle = K.el("button", { type: "button", "aria-pressed": "false", text: "Pen", title: "draw on the frame shown",
        onclick: () => {
          o.on = !o.on;
          toggle.setAttribute("aria-pressed", o.on ? "true" : "false");
          o.pen.classList.toggle("off", !o.on);
        } });
      const color = K.el("input", { type: "color", value: PEN.color, "aria-label": "pen colour",
        oninput: () => { PEN.color = color.value; } });
      const width = K.el("input", { type: "number", min: "1", max: "20", value: String(PEN.width), class: "pen-width",
        "aria-label": "pen width", oninput: () => { PEN.width = Math.max(1, Math.min(20, Number(width.value) || 3)); } });
      const clear = K.el("button", { type: "button", text: "Clear this frame", onclick: () => {
        o.strokes = o.strokes.filter((s) => s.frame !== player.frame);
        o.redraw(player.frame);
        listDrawn(o);
      } });
      o.list = K.el("span", { class: "drawn-frames" });
      return K.el("div", { class: "pen-tools" }, toggle, color, width, clear, K.el("span", { text: "Drawn frames:" }), o.list);
    },

    count(player) {
      return player.pen ? drawnKeys(player.pen).length : 0;
    },

    export(player) {
      const o = player.pen;
      if (!o || !o.strokes.length) return [];
      const p = o.pen.width / 2;
      const pngs = {};
      for (const key of drawnKeys(o)) {
        const [f, view] = key;
        const v = K.VIEWS.indexOf(view);
        const c = document.createElement("canvas");
        c.width = c.height = p;
        const ctx = c.getContext("2d");
        ctx.drawImage(player.images[f], (v % 2) * p, Math.floor(v / 2) * p, p, p, 0, 0, p, p);
        for (const s of o.strokes.filter((s) => s.frame === f && s.view === view)) drawStroke(ctx, s, p, true);
        pngs["f" + K.pad4(f) + "_" + view.replace(" ", "_")] = c.toDataURL("image/png").split(",")[1];
      }
      return { strokes: o.strokes, pngs };
    },
  };

  function round1(v) {
    return Math.round(v * 10) / 10;
  }

  function drawnKeys(o) {
    const seen = new Map();
    for (const s of o.strokes) seen.set(s.frame + "|" + s.view, [s.frame, s.view]);
    return Array.from(seen.values()).sort((a, b) => a[0] - b[0] || a[1].localeCompare(b[1]));
  }

  function drawStroke(ctx, s, panel, local) {
    const v = K.VIEWS.indexOf(s.view);
    const ox = local ? 0 : (v % 2) * panel;
    const oy = local ? 0 : Math.floor(v / 2) * panel;
    ctx.save();
    ctx.strokeStyle = s.color;
    ctx.lineWidth = s.width;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    s.points.forEach(([x, y], i) => (i ? ctx.lineTo(ox + x, oy + y) : ctx.moveTo(ox + x, oy + y)));
    ctx.stroke();
    ctx.restore();
  }

  function listDrawn(o) {
    if (!o.list) return;
    const frames = Array.from(new Set(o.strokes.map((s) => s.frame))).sort((a, b) => a - b);
    o.list.replaceChildren(...(frames.length ? frames.map((f) => K.el("button", { type: "button", text: "f" + f,
      onclick: () => { const s = document.querySelector(".scrub"); s.value = String(f); s.dispatchEvent(new Event("input")); } }))
      : [K.el("span", { class: "hint", text: " none" })]));
    const note = document.getElementById("drawn-note");
    if (note) note.textContent = frames.length ? "Your drawings on " + frames.length + " frame(s) go with the note." : "";
  }
}

/* ---- the list: shots waiting for a sign-off and shared lessons, each with the command that opens it ---------- */

if (typeof document !== "undefined") {
  const K = window.KeiPage;
  window.KeiList = {
    render(pane, mode) {
      pane.replaceChildren(K.el("h1", { text: "Waiting for you" }));
      const block = (title, items, empty) => {
        const box = K.el("section", { class: "lesson-block" }, K.el("h2", { text: title }));
        if (!items.length) box.append(K.el("p", { class: "hint", text: empty }));
        else box.append(K.el("ul", {}, items.map((i) => K.el("li", {}, K.el("strong", { text: i.path }), " ",
          K.el("code", { text: i.command })))));
        return box;
      };
      pane.append(block("Shots waiting for a sign-off", mode.shots, "No shot under this folder waits for a sign-off."),
        block("Shared lessons", mode.lessons, "No shared lesson under lessons/incoming/."),
        K.el("p", { class: "hint", text: "Close this page and run the command of the one to open." }));
    },
  };
}

/* ---- the share panel: shown after Accept; sends nothing until the user presses the button ------------------- */

if (typeof document !== "undefined") {
  const K = window.KeiPage;
  window.KeiShare = {
    panel(share) {
      const box = K.el("section", { class: "share", id: "share" },
        K.el("h2", { text: "Share what you taught Kei?" }),
        K.el("p", { text: "This shot made " + share.lessons.length + " new lesson(s). Kei can rebuild each one on its own " +
          "open character, kei, as a failing and a passing case, and show you every file before anything leaves this " +
          "machine. Your character, your shot and your drawings are never in it." }));
      if (share.mode === "always") box.append(K.el("p", { class: "hint", text: "share.mode is always: Kei prepared and opened each contribution at Accept." }));
      for (const id of share.lessons) {
        const slot = K.el("div", { class: "lesson-block" });
        slot.append(K.el("h2", { text: "Lesson " + id }),
          K.el("button", { type: "button", text: "Prepare the bundle", onclick: () => prepare(id, slot) }),
          K.el("p", { class: "hint", text: "An agent writes the two cases and Kei measures them. This takes a few minutes." }));
        box.append(slot);
      }
      return box;
    },
    sent(share) {
      const box = K.el("section", { class: "share", id: "share" },
        K.el("h2", { text: "Lessons shared automatically" }),
        K.el("p", { class: "hint", text: "share.mode is auto: Kei sends each lesson that is ready to " + share.repo +
          " at the sign-off, with no dialog. The share log beside your lessons file keeps every line." }));
      for (const e of share.log) {
        box.append(K.el("p", { class: "message " + (e.result === "sent" ? "ok" : "warn"), text: shareLine(e) }));
      }
      return box;
    },
    after(share) {
      /* auto: the reloaded page already lists the log; ask and always: the results and the rules kept here */
      if (share.mode === "auto") return;
      if (share.results) this.results(share.results);
      if (share.kept && share.kept.length) {
        this.results(share.kept.map((k) => ({ lesson: k.lesson, message: shareLine({ ...k, result: "kept" }).replace(/^Lesson \S+: /, "") })));
      }
    },
    results(list) {
      const box = document.getElementById("share") || K.ui.panes.review;
      for (const r of list) box.append(K.el("p", { class: "message " + (r.error ? "error" : "ok"),
        text: "Lesson " + r.lesson + ": " + (r.error || r.message) }));
    },
  };

  async function prepare(id, slot) {
    slot.replaceChildren(K.el("h2", { text: "Lesson " + id }), K.el("p", { class: "hint", text: "Preparing the bundle." }));
    let b;
    try {
      b = await K.postJson("/api/share/prepare", { lesson: id });
    } catch (e) {
      slot.append(K.el("p", { class: "message error", text: e.message }));
      return;
    }
    slot.replaceChildren(K.el("h2", { text: "Lesson " + id + ": exactly what would be sent" }));
    if (b.rounds && b.rounds.fails) {
      const pf = K.makePlayer("fails", b.rounds.fails);
      const pp = K.makePlayer("passes", b.rounds.passes);
      pf.box.querySelector(".round-label").textContent = "fails (on kei)";
      pp.box.querySelector(".round-label").textContent = "passes (on kei)";
      slot.append(K.el("div", { class: "players" }, pf.box, pp.box));
      playCases([pf, pp]);
    }
    for (const [name, text] of Object.entries(b.files)) {
      slot.append(K.el("h2", { text: name }), K.el("pre", { text: text }));
    }
    slot.append(K.el("p", { text: "The folder: " + b.folder }));
    if (b.gh) {
      slot.append(K.el("h2", { text: "The commands Kei runs with your own gh and git" }),
        K.el("pre", { text: b.commands.map((c) => c.join(" ")).join(String.fromCharCode(10)) }),
        K.el("p", { class: "message warn", text: b.public_note }),
        K.el("button", { type: "button", class: "primary", text: "Send: fork and push to my fork", onclick: () => send(id, slot) }));
    } else {
      slot.append(K.el("h2", { text: "gh is not installed: send it by hand" }),
        K.el("ol", {}, b.manual.map((step) => K.el("li", { text: step }))));
    }
  }

  function playCases(players) {
    const show = K.show;
    Promise.all(players.map((p) => p.loaded)).then(() => {
      const t0 = performance.now();
      const tick = () => {
        if (!document.body.contains(players[0].box)) return;
        const ms = performance.now() - t0;
        for (const p of players) show(p, frameAt(ms, p.round.fps, p.round.frames, p.round.loop));
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
  }

  async function send(id, slot) {
    if (!confirm("Send? Kei forks the project and pushes this lesson folder to a public branch of your fork, then opens GitHub's pull request form. The pull request opens only at GitHub's button.")) return;
    try {
      const out = await K.postJson("/api/share/send", { lesson: id });
      slot.append(K.el("p", { class: "message ok", text: out.message }));
    } catch (e) {
      slot.append(K.el("p", { class: "message error", text: e.message }));
    }
  }
}

/* ---- the lesson review (maintainers): the two cases on kei, the numbers side by side, the verdict ------------- */

if (typeof document !== "undefined") {
  const K = window.KeiPage;

  window.KeiLesson = {
    async render(pane) {
      const d = await K.getJson("/api/lesson");
      pane.replaceChildren(
        K.el("header", { class: "shot-head" }, K.el("h1", { text: "Lesson review: " + d.lesson }),
          K.el("p", { class: "status", text: "stage: " + d.stage + (d.author ? ", shared by @" + d.author : "") })),
        K.el("section", { class: "lesson-block" }, K.el("h2", { text: d.title }), K.el("pre", { text: d.text })));

      const fails = K.makePlayer("fails", d.rounds.fails);
      const passes = K.makePlayer("passes", d.rounds.passes);
      fails.box.querySelector(".round-label").textContent = "fails (on kei)";
      passes.box.querySelector(".round-label").textContent = "passes (on kei)";
      if (window.KeiPen) fails.overlay = window.KeiPen.attach(fails, d.rounds.fails);
      pane.append(K.el("div", { class: "players" }, fails.box, passes.box));
      pane.append(controls([fails, passes]));
      if (window.KeiPen) pane.append(window.KeiPen.toolbar(fails));
      pane.append(K.el("p", { class: "hint", text: "The pen draws on the failing case." }));

      const table = K.el("table", { class: "numbers" },
        K.el("tr", {}, ["case", "check", "in the bundle", "Kei here", ""].map((h) => K.el("th", { text: h }))),
        d.numbers.map((r) => K.el("tr", { class: r.differs ? "differs" : "" },
          K.el("td", { text: r.case }), K.el("td", { text: r.check }), K.el("td", { text: String(r.bundle) }),
          K.el("td", { text: String(r.kei) }), K.el("td", { text: r.differs ? "differs" : "" }))));
      pane.append(K.el("section", { class: "lesson-block" },
        K.el("h2", { text: "The numbers (kei check" + (d.check ? ", the lesson's check: " + d.check : ", a lesson of taste: not measured") + ")" }),
        d.any_differs ? K.el("p", { class: "message error", text: "Kei's own numbers differ from the bundle's. Look at the rows in red." }) : null,
        table));

      const overlap = K.el("details", { class: "lesson-block" },
        K.el("summary", { text: "Rules of the same stage that share words with it (" + d.overlap.length + ")" }),
        d.overlap.length ? K.el("ul", {}, d.overlap.map((o) => K.el("li", { text: o.id + ". " + o.title + " (" + o.topic + "): " + o.words.join(", ") })))
          : K.el("p", { class: "hint", text: "None." }));
      pane.append(overlap);

      const box = K.el("section", { class: "actions" }, K.el("p", { id: "message", class: "message", role: "status" }));
      if (d.verdict) {
        box.append(K.el("p", { text: "Verdict given: " + d.verdict.verdict + (d.verdict.rule ? ", rule " + d.verdict.rule : "") + " (" + d.verdict.at + ")." }));
      }
      const words = K.el("textarea", { id: "verdict-text", rows: "3", placeholder: "Your words for the contributor." });
      box.append(K.el("div", { class: "action" }, K.el("h2", { text: "Your verdict" }), words),
        K.el("div", { class: "action" },
          K.el("button", { type: "button", class: "primary", text: "Accept", onclick: () => onVerdict("accept", fails) }),
          K.el("p", { class: "hint", text: "Writes the rule with its next ID into the book in your clone. Kei never pushes or merges." })),
        K.el("div", { class: "action" },
          K.el("button", { type: "button", text: "Needs work", onclick: () => onVerdict("needs_work", fails) }),
          K.el("button", { type: "button", class: "danger", text: "Reject", onclick: () => onVerdict("reject", fails) })));
      pane.append(box);

      const fullParts = Array.from(pane.children).filter((e) => !e.classList.contains("shot-head") &&
        !e.classList.contains("players") && !e.classList.contains("controls"));
      const card = K.el("section", { class: "cards" });
      const toggle = K.el("button", { type: "button", class: "see-all" });
      const head = pane.querySelector(".shot-head");
      head.append(toggle);
      pane.insertBefore(card, pane.querySelector(".controls"));
      let mode = "cards";
      let choice = null;
      const draw = () => {
        card.replaceChildren(K.el("p", { class: "card-count", text: "The lesson in one line" }),
          K.el("p", { class: "card-text", text: d.title.replace(" (provisional)", "") }));
        if (d.verdict) {
          card.append(K.el("p", { text: "Verdict given: " + d.verdict.verdict + "." }));
          return;
        }
        if (!choice) {
          const why = K.el("textarea", { id: "lesson-card-note", rows: "2", placeholder: "If no or needs work: your words for the contributor." });
          card.append(K.el("div", { class: "card-buttons" },
            K.el("button", { type: "button", class: "primary", text: "Yes, accept (Y)", onclick: () => pick("accept") }),
            K.el("button", { type: "button", class: "danger", text: "No, reject (N)", onclick: () => pick("reject") }),
            K.el("button", { type: "button", text: "Needs work", onclick: () => pick("needs_work") })), why);
          return;
        }
        card.append(K.el("p", { text: "Your answer: " + choice.verdict.replace("_", " ") + (choice.text ? ". " + choice.text : ".") }),
          K.el("div", { class: "card-buttons" },
            K.el("button", { type: "button", class: "primary", text: "Write the verdict", onclick: write }),
            K.el("button", { type: "button", text: "Back", onclick: () => { choice = null; draw(); } })));
      };
      const pick = (verdict) => {
        const text = (document.getElementById("lesson-card-note") || {}).value || "";
        if (verdict !== "accept" && !text.trim() && !(window.KeiPen && window.KeiPen.count(fails))) {
          K.say("A no or a needs work needs a reason: your words, or a drawing on the failing case.", "error");
          return;
        }
        choice = { verdict, text };
        draw();
      };
      const write = async () => {
        if (!confirm("Write the verdict " + choice.verdict.replace("_", " ") + "? Kei never pushes or merges.")) return;
        try {
          const out = await K.postJson("/api/lesson/verdict", { verdict: choice.verdict, text: choice.text,
            drawings: window.KeiPen ? window.KeiPen.export(fails) : [] });
          d.verdict = out;
          draw();
          K.say("Verdict written to verdict.json" + (out.rule ? "; rule " + out.rule + " added to " + out.book : "") + ".", "ok");
        } catch (e) {
          K.say(e.message, "error");
        }
      };
      K.lessonKey = (k) => { if (k !== "every" && mode === "cards" && !choice && !d.verdict) pick(k === "yes" ? "accept" : "reject"); };
      const setMode = (m) => {
        mode = m;
        for (const e of fullParts) e.hidden = m === "cards";
        card.hidden = m !== "cards";
        toggle.textContent = m === "cards" ? "See everything" : "One question at a time";
      };
      toggle.addEventListener("click", () => setMode(mode === "cards" ? "all" : "cards"));
      draw();
      setMode("cards");
      card.after(K.el("p", { class: "say message", role: "status" }));
    },
  };

  function controls(players) {
    const clock = { ms: 0, playing: false, start: 0, x10: false, raf: 0 };
    const master = players[0];
    const label = K.el("span", { class: "loops" });
    const frameNo = K.el("strong", { class: "frame-no", "aria-live": "polite" });
    const now = () => (clock.playing ? clock.ms + performance.now() - clock.start : clock.ms);
    const paint = () => {
      let ms = now();
      const r = master.round;
      if (clock.x10) {
        const x = x10Frame(ms, r.fps, r.frames, r.loop);
        label.textContent = x.done ? "10 of 10 loops" : "loop " + (x.loops + 1) + " of 10";
        if (x.done) {
          clock.playing = false;
          clock.x10 = false;
          clock.ms = ms = (x.frame + 0.5) * 1000 / r.fps;
          play.textContent = "Play";
        }
      }
      const f0 = frameAt(ms, master.round.fps, master.round.frames, master.round.loop);
      for (const p of players) {
        K.show(p, clock.playing ? frameAt(ms, p.round.fps, p.round.frames, p.round.loop)
          : Math.min(f0, playedFrames(p.round.frames, p.round.loop) - 1));
      }
      frameNo.textContent = "frame " + master.frame;
      if (clock.playing) clock.raf = requestAnimationFrame(paint);
    };
    const play = K.el("button", { type: "button", text: "Play", onclick: () => {
      if (clock.playing) { clock.ms = now(); clock.playing = false; play.textContent = "Play"; paint(); return; }
      clock.start = performance.now(); clock.playing = true; play.textContent = "Pause"; paint();
    } });
    const step = (dir) => {
      clock.ms = now(); clock.playing = false; clock.x10 = false; play.textContent = "Play";
      const r = master.round;
      clock.ms = (stepFrame(master.frame, dir, r.frames, r.loop) + 0.5) * 1000 / r.fps;
      paint();
    };
    K.onStep = step;
    const ten = K.el("button", { type: "button", text: "Play x10", onclick: () => {
      clock.ms = 0; clock.x10 = true; clock.start = performance.now(); clock.playing = true; play.textContent = "Pause"; paint();
    } });
    Promise.all(players.map((p) => p.loaded)).then(paint);
    return K.el("div", { class: "controls" },
      K.el("button", { type: "button", text: "Step back", onclick: () => step(-1) }), play,
      K.el("button", { type: "button", text: "Step", onclick: () => step(1) }), ten, frameNo, label);
  }

  async function onVerdict(verdict, fails) {
    const text = document.getElementById("verdict-text").value;
    const words = { accept: "Accept this lesson and write it into the book in your clone?",
      needs_work: "Send it back to the contributor as needs work?", reject: "Reject this lesson?" };
    if (!confirm(words[verdict])) return;
    try {
      const drawings = window.KeiPen ? window.KeiPen.export(fails) : [];
      const out = await K.postJson("/api/lesson/verdict", { verdict, text, drawings });
      K.say("Verdict written to verdict.json" + (out.rule ? "; rule " + out.rule + " added to " + out.book : "") +
        ". Nothing was pushed: send it with your own gh when you are ready.", "ok");
    } catch (e) {
      K.say(e.message, "error");
    }
  }
}

/* ---- the Settings tab: the same rows and checks as kei settings; a refusal shows next to its field ----------- */

if (typeof document !== "undefined") {
  const K = window.KeiPage;
  const state = { rows: [], sha: null, fields: {} };

  function group(key) {
    const m = /^critics\[([^\]]+)\]/.exec(key);
    return m ? "critic " + m[1] : key.split(".")[0];
  }

  function shown(v) {
    return v === null || v === undefined ? "" : typeof v === "string" ? v : JSON.stringify(v);
  }

  function field(row) {
    const id = "set-" + row.key.replace(/[^a-z0-9]+/gi, "-");
    let input;
    if (row.kind === "choice") {
      input = K.el("select", { id }, row.choices.map((c) => K.el("option", { value: c, text: c, selected: c === row.value })));
    } else if (row.kind === "int") {
      input = K.el("input", { id, type: "number", min: "1", step: "1", value: row.value === null ? "" : String(row.value) });
    } else if (row.kind === "command") {
      input = K.el("textarea", { id, rows: String(Math.min(8, Math.max(2, (row.value || []).length))),
        "aria-describedby": id + "-m" });
      input.value = (row.value || []).join("\n");
    } else {
      input = K.el("input", { id, type: "text", value: shown(row.value) });
    }
    const read = () => {
      if (row.kind === "int") return input.value === "" ? null : Number(input.value);
      if (row.kind === "command") return input.value.split("\n").map((s) => s.trim()).filter(Boolean);
      return input.value;
    };
    return { id, input, read };
  }

  window.KeiSettings = {
    async load(pane) {
      pane.replaceChildren(K.el("p", { text: "Loading the settings." }));
      let d;
      try {
        d = await K.getJson("/api/settings");
      } catch (e) {
        pane.replaceChildren(K.el("p", { class: "message error", text: e.message }));
        return;
      }
      state.rows = d.rows;
      state.sha = d.sha256;
      state.fields = {};
      const head = K.el("header", { class: "shot-head" }, K.el("h1", { text: "Settings" }),
        K.el("p", { class: "status", text: (d.exists ? "" : "no file yet: Save writes ") + d.path }));
      const top = K.el("p", { class: "message", id: "settings-message", role: "status" });
      pane.replaceChildren(head, K.el("p", { class: "hint", text: "A change is checked the way a shot reads kei.toml before it is saved; the old file is kept as kei.toml.bak. Changes apply from the next kei run." }), top);
      const groups = {};
      for (const row of d.rows) (groups[group(row.key)] = groups[group(row.key)] || []).push(row);
      for (const [name, rows] of Object.entries(groups)) {
        const box = K.el("section", { class: "settings-group" }, K.el("h2", { text: name }));
        for (const row of rows) {
          const f = field(row);
          state.fields[row.key] = { ...f, row, original: JSON.stringify(f.read()) };
          const refusal = K.el("p", { class: "refusal", id: f.id + "-r", role: "alert" });
          const extra = [];
          if (row.kind === "command") extra.push(K.el("button", { type: "button", text: "Test this seat",
            onclick: () => testSeat(row.key, refusal) }));
          if (row.source === "kei.toml" && row.default !== null) extra.push(K.el("button", { type: "button", text: "Use the default",
            onclick: () => { state.fields[row.key].unset = true; save(); } }));
          box.append(K.el("div", { class: "setting" },
            K.el("label", { for: f.id, class: "key", text: row.key }),
            K.el("div", {}, f.input, " ", ...extra, K.el("span", { class: "source", text: " " + row.source +
              (row.source === "default" ? "" : ", default " + (shown(row.default) || "none")) })),
            K.el("p", { class: "meaning", id: f.id + "-m", text: row.meaning + (row.help ? ". " + row.help : "") }),
            refusal));
        }
        pane.append(box);
      }
      pane.append(K.el("p", {}, K.el("button", { type: "button", class: "primary", text: "Save", onclick: () => save() })));
    },
  };

  function changes() {
    const out = {};
    for (const [key, f] of Object.entries(state.fields)) {
      if (f.unset) { out[key] = null; f.unset = false; continue; }
      const now = JSON.stringify(f.read());
      if (now !== f.original) out[key] = f.read();
    }
    return out;
  }

  function sayTop(text, kind) {
    const m = document.getElementById("settings-message");
    m.textContent = text;
    m.className = "message" + (kind ? " " + kind : "");
  }

  async function save(code, pending) {
    document.querySelectorAll(".setting .refusal").forEach((r) => { r.textContent = ""; });
    const ch = pending || changes();
    if (!Object.keys(ch).length) return sayTop("Nothing changed.", "");
    try {
      const body = { changes: ch, sha256: state.sha };
      if (typeof code === "string") body.confirm_code = code;
      const out = await K.postJson("/api/settings", body);
      if (!out.saved && out.confirm) {
        const text = out.confirm.map((c) => c.key + "\n  now: " + (c.old || []).join(" ") + "\n  new: " + c.new.join(" ")).join("\n\n");
        const typed = prompt((out.wrong_code ? "That code did not match; Kei printed a new one. " : "") +
          "Kei will run this program as a seat:\n\n" + text +
          "\n\nTo save it, type the six-digit code Kei just printed in the terminal where kei review runs.");
        if (typed) return save(typed, ch);
        return sayTop("Not saved: the command change needs the code from the terminal.", "warn");
      }
      await window.KeiSettings.load(K.ui.panes.settings);
      sayTop("Saved: " + out.changes.map((c) => c[0] + " " + JSON.stringify(c[1]) + " -> " + JSON.stringify(c[2])).join(", ") +
        ". " + (out.notes || []).join(" ") + " Applies from the next kei run.", "ok");
    } catch (e) {
      sayTop("Not saved. " + e.message, "error");
      for (const k of Object.keys(ch)) {
        if (e.message.includes(k) || e.message.includes(k.split(".").pop())) {
          const f = state.fields[k];
          if (f) document.getElementById(f.id + "-r").textContent = e.message;
        }
      }
    }
  }

  async function testSeat(key, out) {
    out.className = "refusal";
    out.textContent = "Running " + key + " --version (10 seconds at most).";
    try {
      const r = await K.postJson("/api/settings/test-seat", { key });
      out.className = r.ok ? "meaning" : "refusal";
      out.textContent = (r.ok ? "It answers: " : "It did not answer (exit " + r.code + "): ") + r.output;
    } catch (e) {
      out.textContent = e.message;
    }
  }
}
