// DineAssist animated floor plan (Streamlit components v2).
// Streamlit calls the default export again with new data on every refresh; the
// scene is built once and then updated in place so animations keep running.

const NS = "http://www.w3.org/2000/svg";
const SPEED = 240;              // walking speed, scene units per second
const DOOR = [-26, 122];        // just outside the entrance
const DOOR_IN = [44, 122];
const KITCHEN = [969, -20];
const KITCHEN_IN = [969, 66];
const REDUCED = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

// Table shapes by seat count. Seat offsets are chair centers relative to the table.
const GEOM = {
  2: { round: true, w: 62, h: 62, seats: [[-50, 0], [50, 0]], order: [0, 1] },
  4: { round: false, w: 78, h: 78, seats: [[0, -58], [0, 58], [-58, 0], [58, 0]], order: [0, 1, 2, 3] },
  6: { round: false, w: 132, h: 74, seats: [[-34, -58], [34, -58], [-34, 58], [34, 58], [-84, 0], [84, 0]], order: [0, 3, 1, 2, 4, 5] },
};
const SKIN = ["#F3CFAE", "#E6B48D", "#D19D74", "#B07A52", "#8A5A3B", "#6B4128", "#4E2E1C"];
const HAIR = ["#1E1612", "#2E1F17", "#4A3021", "#6B4A2E", "#A27A4E", "#C9A46C", "#8B8580", "#3A2418", "#151515"];
const SHIRT = ["#4C6E91", "#8E4B5A", "#5E7D5B", "#C9A15B", "#6B5B95", "#3F4A55", "#B5654A", "#D8D2C4",
  "#2F6F73", "#7C6A58", "#A3485A", "#3D5A80", "#9A8C7A", "#2B2B2B"];
const FOOD = ["#C0663F", "#7FA35A", "#D9A441", "#A8462E", "#E2C58C", "#5F8A4E", "#B9583A"];

// ---------- small helpers ----------
function el(tag, attrs, parent) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}
function hashString(s) { let h = 2166136261; for (const c of s) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
function rng(seed) { let a = seed >>> 0; return () => { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const pick = (list, r) => list[Math.floor(r() * list.length)];
function shade(hex, f) {
  const n = parseInt(hex.slice(1), 16), c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(v => Math.max(0, Math.min(255, Math.round(v * f))));
  return "#" + c.map(v => v.toString(16).padStart(2, "0")).join("");
}
const facing = (sx, sy) => Math.atan2(-sy, -sx) * 180 / Math.PI + 90;   // local "up" points at the table
function currentXY(p) {
  const m = new DOMMatrixReadOnly(getComputedStyle(p.node).transform === "none" ? undefined : getComputedStyle(p.node).transform);
  return [m.e, m.f];
}
const setXY = (p, x, y) => { p.node.style.transform = `translate(${x}px, ${y}px)`; p.xy = [x, y]; };
const setAngle = (p, deg) => { p.orient.style.transform = `rotate(${deg}deg)`; };

// ---------- the room ----------
function drawDefs(svg) {
  const defs = el("defs", {}, svg);
  defs.innerHTML = `
    <pattern id="planks" patternUnits="userSpaceOnUse" width="300" height="44">
      <rect width="300" height="44" fill="#2E2119"/>
      <rect x="0" y="0" width="150" height="22" fill="#3A2A1F"/><rect x="150" y="0" width="150" height="22" fill="#33251B"/>
      <rect x="-75" y="22" width="150" height="22" fill="#37281D"/><rect x="75" y="22" width="150" height="22" fill="#3F2D21"/>
      <rect x="225" y="22" width="150" height="22" fill="#37281D"/>
      <path d="M0 22H300M0 44H300M150 0V22M75 22V44M225 22V44" stroke="#120C08" stroke-opacity=".55" stroke-width="1"/>
      <path d="M8 7 C60 5 100 9 140 7 M160 14 C210 12 250 16 292 13 M10 31 C40 29 60 33 70 31 M84 37 C130 35 170 39 218 36 M232 30 C260 29 280 32 296 30"
            stroke="#5A4230" stroke-opacity=".35" stroke-width=".8" fill="none"/>
    </pattern>
    <radialGradient id="vignette" cx=".5" cy=".55" r=".78">
      <stop offset="0" stop-color="#FFD7A3" stop-opacity=".08"/><stop offset=".55" stop-color="#000" stop-opacity="0"/>
      <stop offset="1" stop-color="#000" stop-opacity=".62"/>
    </radialGradient>
    <radialGradient id="pool"><stop offset="0" stop-color="#FFCF8F" stop-opacity=".26"/>
      <stop offset=".5" stop-color="#FFCF8F" stop-opacity=".08"/><stop offset="1" stop-color="#FFCF8F" stop-opacity="0"/></radialGradient>
    <linearGradient id="wood" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#9A6840"/><stop offset=".5" stop-color="#7A4D2E"/><stop offset="1" stop-color="#8B5A35"/></linearGradient>
    <pattern id="grain" patternUnits="userSpaceOnUse" width="80" height="14">
      <path d="M0 4 C20 2 40 6 80 3 M0 10 C25 8 55 12 80 9" stroke="#3E2414" stroke-opacity=".35" stroke-width=".9" fill="none"/></pattern>
    <linearGradient id="stone" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3B3531"/><stop offset="1" stop-color="#26211E"/></linearGradient>
    <radialGradient id="candle"><stop offset="0" stop-color="#FFE3A8" stop-opacity=".95"/><stop offset=".35" stop-color="#FFB45A" stop-opacity=".45"/>
      <stop offset="1" stop-color="#FF9A3C" stop-opacity="0"/></radialGradient>
    <filter id="soft" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="5"/></filter>
    <filter id="softer" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.4"/></filter>`;
}

function plant(g, x, y, s, seed) {
  const r = rng(seed), p = el("g", { transform: `translate(${x} ${y}) scale(${s})` }, g);
  el("circle", { cx: 3, cy: 5, r: 19, fill: "#000", opacity: .45, filter: "url(#softer)" }, p);
  el("circle", { r: 17, fill: "#4A403A", stroke: "#2A2420", "stroke-width": 2 }, p);
  for (let i = 0; i < 9; i++) {
    const a = i * 40 + r() * 20;
    el("ellipse", { cx: 13, cy: 0, rx: 15, ry: 5.5, fill: pick(["#3F6B45", "#4E7F52", "#5E9461", "#355C3B"], r),
      transform: `rotate(${a})` }, p);
  }
  el("circle", { r: 6, fill: "#2F5234" }, p);
}

function drawRoom(svg, W, H) {
  const g = el("g", { class: "room" }, svg);
  el("rect", { width: W, height: H, fill: "url(#planks)" }, g);
  // Rug under the central tables
  el("rect", { x: 300, y: 300, width: 470, height: 230, rx: 26, fill: "#3B1F1C", opacity: .55 }, g);
  el("rect", { x: 312, y: 312, width: 446, height: 206, rx: 20, fill: "none", stroke: "#8C5A3C", "stroke-opacity": .35, "stroke-width": 2 }, g);
  // Bar along the top wall
  const bar = el("g", {}, g);
  el("rect", { x: 562, y: 18, width: 372, height: 40, rx: 9, fill: "#000", opacity: .5, filter: "url(#softer)" }, bar);
  el("rect", { x: 560, y: 12, width: 372, height: 40, rx: 9, fill: "url(#stone)", stroke: "#4D453F" }, bar);
  el("rect", { x: 560, y: 46, width: 372, height: 6, rx: 3, fill: "#6E4A2E" }, bar);
  const bottleColors = ["#2F5D3A", "#7A3B2A", "#C9A15B", "#3D5A80", "#5E3A5A", "#D8D2C4"];
  for (let x = 576; x < 920; x += 15) el("circle", { cx: x, cy: 22, r: 4.2, fill: bottleColors[(x / 15) % 6 | 0], opacity: .9 }, bar);
  for (let x = 588; x < 920; x += 52) {
    el("circle", { cx: x + 2, cy: 76, r: 11, fill: "#000", opacity: .45, filter: "url(#softer)" }, bar);
    el("circle", { cx: x, cy: 73, r: 10.5, fill: "#2B211B", stroke: "#5A4537", "stroke-width": 2 }, bar);
  }
  el("text", { x: 746, y: 100, "text-anchor": "middle", class: "room-label" }, g).textContent = "Bar";
  // Host stand by the entrance
  el("rect", { x: 22, y: 186, width: 34, height: 24, rx: 5, fill: "#5A3F2C", stroke: "#2A1D14" }, g);
  el("rect", { x: 29, y: 191, width: 20, height: 13, rx: 2, fill: "#9FC2E6", opacity: .7 }, g);
  // Walls with the entrance (left) and kitchen door (top right)
  const wall = { fill: "none", stroke: "#0B0807", "stroke-width": 14, "stroke-linecap": "square" };
  el("path", { d: `M0 92 V0 H946 M992 0 H${W} V${H} H0 V152`, ...wall }, g);
  el("path", { d: `M0 92 V0 H946 M992 0 H${W} V${H} H0 V152`, fill: "none", stroke: "#F1E8DA", "stroke-opacity": .06, "stroke-width": 1,
    transform: "translate(7 7)" }, g);
  el("rect", { x: 8, y: 98, width: 30, height: 48, rx: 4, fill: "#2A2420", stroke: "#3E3530" }, g);
  el("path", { d: "M7 92 L52 104 M7 92 A46 46 0 0 1 52 104", fill: "none", stroke: "#A99B8A", "stroke-opacity": .45, "stroke-width": 1.5 }, g);
  el("path", { d: "M946 7 L958 46 M946 7 A40 40 0 0 0 958 46", fill: "none", stroke: "#A99B8A", "stroke-opacity": .45, "stroke-width": 1.5 }, g);
  el("text", { x: 64, y: 128, class: "room-label" }, g).textContent = "Entrance";
  el("text", { x: 968, y: 96, "text-anchor": "middle", class: "room-label" }, g).textContent = "Kitchen";
  plant(g, 30, 30, 1, 7); plant(g, 970, 628, 1.1, 11); plant(g, 30, 628, 1, 3); plant(g, 520, 640, .8, 5);
  return g;
}

// ---------- tables ----------
function buildTable(app, d, index) {
  const geom = GEOM[d.seats], hw = geom.w / 2, hh = geom.h / 2;
  const r = rng(hashString(d.id));
  // Light pool on the floor
  const pool = el("circle", { cx: d.x, cy: d.y, r: Math.max(geom.w, geom.h) * 1.15 + 40, fill: "url(#pool)", class: "pool" }, app.pools);

  const g = el("g", { class: "table", transform: `translate(${d.x} ${d.y})`, tabindex: 0, role: "button" }, app.tablesLayer);
  const wrap = el("g", { class: "enter-wrap" }, g);
  const lift = el("g", { class: "lift" }, wrap);
  const pad = 14;
  const roundRect = (grow, attrs, parent) => geom.round
    ? el("circle", { r: hw + grow, ...attrs }, parent)
    : el("rect", { x: -hw - grow, y: -hh - grow, width: geom.w + 2 * grow, height: geom.h + 2 * grow, rx: 12 + grow * .6, ...attrs }, parent);

  roundRect(pad + 14, { class: "sonar" }, lift);
  roundRect(pad + 14, { class: "sonar two" }, lift);
  roundRect(pad + 10, { class: "halo" }, lift);
  roundRect(pad + 18, { class: "select-ring" }, lift);

  // Chairs
  for (const [sx, sy] of geom.seats) {
    const c = el("g", { transform: `translate(${sx} ${sy}) rotate(${facing(sx, sy)})` }, lift);
    el("rect", { x: -14, y: -10, width: 30, height: 26, rx: 8, fill: "#000", opacity: .45, filter: "url(#softer)" }, c);
    el("rect", { x: -15, y: -12, width: 30, height: 24, rx: 7, fill: "#3A2A21", stroke: "#1E1611" }, c);
    el("rect", { x: -11, y: -9, width: 22, height: 15, rx: 5, fill: "#5A4031", opacity: .9 }, c);
    el("rect", { x: -15, y: 9, width: 30, height: 7, rx: 3.5, fill: "#22180F" }, c);
  }
  // Table top
  if (geom.round) el("circle", { cx: 4, cy: 8, r: hw + 2, fill: "#000", opacity: .55, filter: "url(#soft)" }, lift);
  else el("rect", { x: -hw + 4, y: -hh + 8, width: geom.w, height: geom.h, rx: 12, fill: "#000", opacity: .55, filter: "url(#soft)" }, lift);
  roundRect(0, { fill: "url(#wood)", stroke: "#3A2314", "stroke-width": 1.5 }, lift);
  roundRect(0, { fill: "url(#grain)" }, lift);
  roundRect(-3, { fill: "none", stroke: "#FFE8C8", "stroke-opacity": .12 }, lift);

  // Place settings
  const settings = [];
  geom.seats.forEach(([sx, sy], i) => {
    const len = Math.hypot(sx, sy), ux = sx / len, uy = sy / len;
    const px = Math.abs(ux) < .01 ? sx * .55 : Math.sign(sx) * Math.min(Math.abs(sx) * .6, hw - 14);
    const py = Math.abs(uy) < .01 ? sy * .55 : Math.sign(sy) * Math.min(Math.abs(sy) * .6, hh - 14);
    const s = el("g", { class: "setting" }, lift);
    const plateG = el("g", { class: "plate", style: `--mx:${(r() - .5) * 8}px;--my:${(r() - .5) * 8}px` }, s);
    el("circle", { cx: px, cy: py, r: 10, fill: "#EFE9DF", stroke: "#BDB4A6", "stroke-width": 1 }, plateG);
    el("circle", { cx: px, cy: py, r: 6.5, fill: "none", stroke: "#D6CEC1", "stroke-width": .8 }, plateG);
    el("ellipse", { cx: px + (r() - .5) * 2, cy: py + (r() - .5) * 2, rx: 5.5, ry: 4.2, fill: pick(FOOD, r), class: "food",
      transform: `rotate(${r() * 180} ${px} ${py})` }, plateG);
    // Napkin and glass to the diner's right
    const gx = px + (-uy) * 13 + ux * -2, gy = py + ux * 13 + uy * -2;
    el("rect", { x: px + uy * 13 - 3, y: py - ux * 13 - 5, width: 6, height: 10, rx: 1.5, fill: "#C9C1B3", class: "napkin",
      transform: `rotate(${facing(sx, sy)} ${px + uy * 13} ${py - ux * 13})` }, s);
    el("circle", { cx: gx, cy: gy, r: 3.6, fill: "#CFE3EC", "fill-opacity": .55, stroke: "#E9F3F7", "stroke-opacity": .7 }, s);
    // Crumbs and a used napkin when the table is dirty
    const mess = el("g", { class: "mess" }, s);
    for (let k = 0; k < 5; k++) el("circle", { cx: px + (r() - .5) * 22, cy: py + (r() - .5) * 22, r: .9 + r() * 1.2, fill: "#D6B98C" }, mess);
    el("path", { d: `M${px + 9} ${py - 4} q4 -6 9 -2 q-2 6 -9 2z`, fill: "#E7E1D6", opacity: .9 }, mess);
    settings.push(s);
  });
  // Candle
  el("circle", { r: 16, fill: "url(#candle)", class: "candle-glow" }, lift);
  el("circle", { r: 3.2, fill: "#F6EBD8", stroke: "#CDBFA8", "stroke-width": .6 }, lift);

  // Cleaning sparkles + "cleaned" burst
  const sp = el("g", { class: "sparkles", transform: `translate(${hw - 2} ${-hh + 2})` }, lift);
  const star = "M0 -7 L1.8 -1.8 L7 0 L1.8 1.8 L0 7 L-1.8 1.8 L-7 0 L-1.8 -1.8Z";
  el("path", { d: star, fill: "#FFE6A3", class: "sparkle" }, sp);
  el("path", { d: star, fill: "#FFE6A3", class: "sparkle", transform: "translate(-14 9) scale(.6)" }, sp);
  el("path", { d: star, fill: "#FFE6A3", class: "sparkle", transform: "translate(6 14) scale(.45)" }, sp);
  const burst = el("g", { class: "burst" }, lift);
  for (let k = 0; k < 10; k++) {
    const a = k / 10 * Math.PI * 2;
    el("circle", { r: 3, style: `--bx:${Math.cos(a) * 46}px;--by:${Math.sin(a) * 46}px`, opacity: 0 }, burst);
  }

  // Chip above the table (moved below later if another table is in the way)
  const ext = (sign) => Math.max(hh, ...geom.seats.filter(([, sy]) => Math.sign(sy) === sign).map(([, sy]) => Math.abs(sy) + 14));
  const extX = Math.max(hw, ...geom.seats.map(([sx]) => Math.abs(sx) + 14));
  const chip = el("g", { class: "chip" }, app.chips);
  const inner = el("g", { class: "inner" }, chip);
  const bg = el("rect", { class: "bg", y: -13, height: 26, rx: 13 }, inner);
  const dot = el("circle", { class: "dot", r: 4 }, inner);
  const label = el("text", { class: "label", y: 4.5 }, inner);
  const timer = el("text", { class: "timer", y: 4.5 }, inner);

  const crowd = el("g", { class: "crowd" }, app.people);
  const t = { id: d.id, d, geom, g, wrap, pool, settings, burst, chip, bg, dot, label, timer, crowd,
    box: { l: d.x - extX, r: d.x + extX, t: d.y - ext(-1), b: d.y + ext(1) },
    guests: [], staff: [], low: 0, prevState: null, chatNode: null, seed: hashString(d.id) };

  g.addEventListener("click", () => app.select(d.id));
  g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); app.select(d.id); } });
  g.addEventListener("mouseenter", () => app.showTip(t));
  g.addEventListener("mouseleave", () => app.hideTip());
  g.addEventListener("focus", () => app.showTip(t));
  g.addEventListener("blur", () => app.hideTip());
  if (app.firstBuild && !REDUCED) { wrap.classList.add("enter"); wrap.style.setProperty("--d", `${index * 55}ms`); }
  return t;
}

// ---------- people ----------
function makePerson(t, kind, n) {
  const r = rng(t.seed * 31 + n * 7919 + (kind === "staff" ? 99991 : 0));
  const skin = pick(SKIN, r), hair = pick(HAIR, r);
  const shirt = kind === "staff" ? "#ECE7DD" : pick(SHIRT, r);
  const node = el("g", { class: "walker" }, t.crowd);
  const orient = el("g", { class: "orient" }, node);
  el("ellipse", { cx: 2, cy: 6, rx: 19, ry: 13, fill: "#000", opacity: .4, filter: "url(#softer)" }, orient);
  const body = el("g", { class: "body", style: `--br:${3.4 + r() * 2}s;--bd:${-r() * 4}s` }, orient);
  const sleeve = shade(shirt, .82);
  el("rect", { class: "arm-l", x: -20, y: -12, width: 7.5, height: 18, rx: 3.7, fill: sleeve }, body);
  el("rect", { class: "arm-r", x: 12.5, y: -12, width: 7.5, height: 18, rx: 3.7, fill: sleeve }, body);
  el("circle", { cx: -16, cy: -13, r: 3.4, fill: skin }, body);
  el("circle", { cx: 16, cy: -13, r: 3.4, fill: skin }, body);
  if (kind === "guest" && r() < .45) el("ellipse", { cx: 0, cy: 6, rx: 10, ry: 9, fill: hair }, body); // long hair behind
  el("ellipse", { cx: 0, cy: 2, rx: 17, ry: 10.5, fill: shirt }, body);
  el("path", { d: "M-12 -3 Q0 4 12 -3", fill: "none", stroke: shade(shirt, .7), "stroke-width": 1.2, opacity: .7 }, body);
  if (kind === "staff") {
    el("path", { d: "M-9 -4 L-6 11 M9 -4 L6 11", stroke: "#1B1714", "stroke-width": 3, "stroke-linecap": "round" }, body);
    el("circle", { cx: 21, cy: -10, r: 9.5, fill: "#C9CDD2", stroke: "#8E949B", "stroke-width": 1.2 }, body);
    el("circle", { cx: 19, cy: -12, r: 3, fill: "#CFE3EC", opacity: .8 }, body);
  }
  const head = el("g", { class: "head", style: `--lk:${7 + r() * 6}s;--ld:${-r() * 9}s` }, body);
  el("circle", { cx: 0, cy: -1, r: 9, fill: hair }, head);
  el("ellipse", { cx: 0, cy: -6.4, rx: 5.6, ry: 3.8, fill: skin }, head);
  if (r() < .25) el("circle", { cx: 0, cy: 6, r: 3.6, fill: shade(hair, .85) }, head); // bun
  return { node, orient, kind, mode: null, xy: [0, 0], anim: null, timers: [] };
}

function spot(t, kind, i, mode) {
  const { geom, d } = t;
  if (kind === "staff") {
    const ext = Math.max(geom.w, geom.h) / 2 + 44;
    const a = (i === 0 ? -35 : 145) * Math.PI / 180;
    const x = d.x + Math.cos(a) * ext, y = d.y + Math.sin(a) * ext;
    return { x, y, angle: facing(x - d.x, y - d.y) };
  }
  const [sx, sy] = geom.seats[geom.order[i % geom.order.length]];
  const len = Math.hypot(sx, sy), push = mode === "standing" ? 26 : -5;
  const x = d.x + sx + sx / len * push, y = d.y + sy + sy / len * push;
  return { x, y, angle: facing(sx, sy), seat: geom.order[i % geom.order.length] };
}

function stopWalk(p) {
  p.timers.forEach(clearTimeout); p.timers = [];
  if (p.anim) { const [x, y] = currentXY(p); p.anim.cancel(); p.anim = null; setXY(p, x, y); }
}

function walk(p, points, { delay = 0, face = null, onDone = null } = {}) {
  stopWalk(p);
  const start = p.xy;
  const pts = [start, ...points];
  const segs = []; let total = 0;
  for (let i = 1; i < pts.length; i++) { const L = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); segs.push(L); total += L; }
  if (REDUCED || total < 1) {
    const [x, y] = pts[pts.length - 1]; setXY(p, x, y); if (face !== null) setAngle(p, face); onDone && onDone(); return;
  }
  const duration = Math.max(600, total / SPEED * 1000);
  let acc = 0;
  const frames = pts.map((pt, i) => {
    if (i > 0) acc += segs[i - 1];
    return { transform: `translate(${pt[0]}px, ${pt[1]}px)`, offset: total ? acc / total : 0 };
  });
  frames[0].easing = "ease-in"; if (frames.length > 2) frames[frames.length - 2].easing = "ease-out";
  p.anim = p.node.animate(frames, { duration, delay, fill: "forwards" });
  // Turn to face each leg of the walk.
  let tAcc = delay;
  segs.forEach((L, i) => {
    const [ax, ay] = pts[i], [bx, by] = pts[i + 1];
    const heading = Math.atan2(by - ay, bx - ax) * 180 / Math.PI + 90;
    p.timers.push(setTimeout(() => { p.node.classList.add("walking"); setAngle(p, heading); }, tAcc));
    tAcc += L / total * duration;
  });
  const [fx, fy] = pts[pts.length - 1];
  p.anim.onfinish = () => {
    p.anim.cancel(); p.anim = null; setXY(p, fx, fy);
    p.node.classList.remove("walking");
    if (face !== null) setAngle(p, face);
    onDone && onDone();
  };
}

function approach(t, target) {
  // Come in through the door, then step around to the chair from outside the table.
  const { d } = t, dx = target.x - d.x, dy = target.y - d.y, L = Math.hypot(dx, dy) || 1;
  const outside = [d.x + dx / L * (L + 34), d.y + dy / L * (L + 34)];
  return [outside, [target.x, target.y]];
}

function placeGuests(app, t, d, instant) {
  let want = 0, mode = "seated";
  if (d.state === "occupied") want = Math.max(1, d.customers);
  else if (d.pending) { want = Math.max(1, d.customers); mode = "standing"; }
  const have = t.guests.length;
  // Detections flicker: drop a guest only after two refreshes in a row agree.
  if (d.state === "occupied" && t.prevState === "occupied" && want < have) {
    t.low += 1; if (t.low < 2) want = have; else t.low = 0;
  } else t.low = 0;

  t.guests.forEach((p, i) => {
    if (p.mode !== mode) {
      const s = spot(t, "guest", i, mode); p.mode = mode;
      p.node.classList.toggle("waiting", mode === "standing");
      if (instant) { setXY(p, s.x, s.y); setAngle(p, s.angle); } else walk(p, [[s.x, s.y]], { face: s.angle });
    }
  });
  for (let i = have; i < want; i++) {
    const p = makePerson(t, "guest", i), s = spot(t, "guest", i, mode);
    p.mode = mode; p.node.classList.toggle("waiting", mode === "standing");
    if (instant) { setXY(p, s.x, s.y); setAngle(p, s.angle); if (app.firstBuild) p.node.classList.add("pop"); }
    else { setXY(p, ...DOOR); setAngle(p, 90); walk(p, [DOOR_IN, ...approach(t, s)], { delay: (i - have) * 450, face: s.angle }); }
    t.guests.push(p);
  }
  while (t.guests.length > want) leave(t.guests.pop(), instant, DOOR_IN, DOOR);
}

function placeStaff(app, t, d, instant) {
  const want = d.state === "unknown" ? 0 : d.staff;
  for (let i = t.staff.length; i < want; i++) {
    const p = makePerson(t, "staff", i), s = spot(t, "staff", i);
    if (instant) { setXY(p, s.x, s.y); setAngle(p, s.angle); }
    else { setXY(p, ...KITCHEN); setAngle(p, 180); walk(p, [KITCHEN_IN, [s.x, s.y]], { delay: i * 400, face: s.angle }); }
    t.staff.push(p);
  }
  while (t.staff.length > want) leave(t.staff.pop(), instant, KITCHEN_IN, KITCHEN);
}

function leave(p, instant, via, exit) {
  if (instant) { p.node.remove(); return; }
  p.node.classList.remove("waiting");
  walk(p, [via, exit], { delay: Math.random() * 300, onDone: () => p.node.remove() });
  p.node.classList.add("leaving");
}

function updateChat(t, d) {
  const seated = d.state === "occupied" ? t.guests.filter(p => p.mode === "seated") : [];
  if (seated.length < 2) { t.chatNode?.remove(); t.chatNode = null; return; }
  if (t.chatNode && t.chatNode.__count === seated.length) return;
  t.chatNode?.remove();
  const r = rng(t.seed + seated.length);
  const { x, y } = spot(t, "guest", Math.floor(r() * seated.length), "seated");
  const c = el("g", { class: "chat", transform: `translate(${x + 10} ${y - 30})`, style: `--ct:${6 + r() * 5}s;--cd:${-r() * 6}s` }, t.crowd);
  el("rect", { x: 0, y: -12, width: 30, height: 18, rx: 9, fill: "#F1E8DA", opacity: .95 }, c);
  el("path", { d: "M5 5 L2 11 L11 5Z", fill: "#F1E8DA", opacity: .95 }, c);
  [8, 15, 22].forEach(cx => el("circle", { class: "dot", cx, cy: -3, r: 2, fill: "#3A2E26" }, c));
  c.__count = seated.length;
  t.chatNode = c;
}

// ---------- chips, tooltip ----------
function placeChips(app, sceneH) {
  // Put each label above its table unless that would cover a neighbouring table.
  const all = [...app.tables.values()];
  const hits = (x, y, self) => all.some(o => o !== self &&
    x + 62 > o.box.l && x - 62 < o.box.r && y + 13 > o.box.t && y - 13 < o.box.b);
  for (const t of all) {
    const above = t.box.t - 16, below = t.box.b + 16;
    let y = above;
    if ((hits(t.d.x, above, t) || above < 24) && !hits(t.d.x, below, t) && below < sceneH - 16) y = below;
    t.chip.setAttribute("transform", `translate(${t.d.x} ${y})`);
  }
}

function updateChip(t, d) {
  let text = d.label, time = d.timer || "", alert = false;
  if (d.state === "occupied" && d.greeting === "overdue") { text = `${d.label}  Greet`; alert = true; }
  else if (d.state === "needs_cleaning") { text = `${d.label}  Clean`; alert = true; }
  else if (d.pending) text = `${d.label}  Arriving`;
  else if (d.heldFor && d.state === "free") { text = `${d.label}  Held`; alert = true; }
  else if (d.state === "occupied" && d.greeting === "greeted") text = `${d.label}  Greeted`;
  t.chip.setAttribute("class", `chip s-${d.state}${alert ? " alert" : ""}${d.dim ? " dim" : ""}`);
  if (t.label.textContent !== text) t.label.textContent = text;
  if (t.timer.textContent !== time) {
    t.timer.textContent = time;
    t.timer.classList.remove("tick"); void t.timer.getBBox(); if (time) t.timer.classList.add("tick");
  }
  let lw = text.length * 6.6, tw = time.length * 6.2;
  try { lw = t.label.getComputedTextLength() || lw; tw = time ? (t.timer.getComputedTextLength() || tw) : 0; } catch (e) { /* not rendered yet */ }
  const width = 12 + 8 + 7 + lw + (time ? 8 + tw : 0) + 12;
  const left = -width / 2;
  t.bg.setAttribute("x", left); t.bg.setAttribute("width", width);
  t.dot.setAttribute("cx", left + 16); t.label.setAttribute("x", left + 26);
  t.timer.setAttribute("x", left + 26 + lw + 8);
}

const escapeHTML = (s) => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function tipHTML(d) {
  const rows = [];
  if (d.state === "occupied") {
    rows.push(`Seated for ${d.timer || "—"}`);
    rows.push(`${d.customers} guest${d.customers === 1 ? "" : "s"} detected`);
    rows.push(d.greeting === "greeted" ? "Greeting recorded" : d.greeting === "overdue" ? "Greeting overdue" : `Greeting due in ${d.dueIn || "—"}`);
  } else if (d.state === "needs_cleaning") rows.push(`Waiting for cleaning ${d.timer || ""}`);
  else if (d.pending) rows.push("Possible arrival, waiting for a steady detection");
  else if (d.state === "unknown") rows.push("No observation yet");
  if (d.staff) rows.push(`${d.staff} staff at the table`);
  if (d.heldFor && d.state === "free") rows.push(`Held for ${escapeHTML(d.heldFor)}, guest has been texted`);
  return `<b>${escapeHTML(d.name)}</b><span class="st"><i></i>${d.stateName}</span>${rows.map(r => `<div class="row">${r}</div>`).join("")}
    <div class="hint">Click to open table details</div>`;
}

// ---------- app ----------
function createApp(root) {
  const app = { tables: new Map(), firstBuild: true, setTrigger: null, layoutKey: null };
  root.innerHTML = "";
  const svg = el("svg", { class: "scene", "aria-label": "Dining room floor plan" });
  root.appendChild(svg);
  app.svg = svg;
  const hud = document.createElement("div"); hud.className = "hud";
  hud.innerHTML = `<div class="pill"><span class="led"></span><span class="txt"></span><span class="clock"></span></div>`;
  root.appendChild(hud);
  const legend = document.createElement("div"); legend.className = "legend";
  legend.innerHTML = `<span><i style="background:#86C08F"></i>Available</span><span><i style="background:#E0656F"></i>Occupied</span>
    <span><i style="background:#E8B341"></i>Needs cleaning</span><span><i style="background:#7A6F64"></i>Not observed yet</span>
    <span class="who">Each guest is a live detection</span>`;
  root.appendChild(legend);
  const tip = document.createElement("div"); tip.className = "tip"; root.appendChild(tip);
  Object.assign(app, { root, hud, tip, pill: hud.querySelector(".pill") });

  app.select = (id) => { app.setTrigger && app.setTrigger("select", id); };
  app.showTip = (t) => {
    tip.innerHTML = tipHTML(t.d);
    tip.style.setProperty("--c", getComputedStyle(t.g).getPropertyValue("--c") || "#F1E8DA");
    const box = t.g.getBoundingClientRect(), host = root.getBoundingClientRect();
    let left = box.right - host.left + 10, top = box.top - host.top;
    if (left + 220 > host.width) left = box.left - host.left - 230;
    tip.style.left = `${Math.max(8, left)}px`; tip.style.top = `${Math.max(8, Math.min(top, host.height - 150))}px`;
    tip.classList.add("show"); app.tipFor = t;
  };
  app.hideTip = () => { tip.classList.remove("show"); app.tipFor = null; };

  app.build = (data) => {
    svg.innerHTML = "";
    svg.setAttribute("viewBox", `0 0 ${data.w} ${data.h}`);
    drawDefs(svg);
    app.floor = el("g", { class: "floor-layer" }, svg);
    drawRoom(app.floor, data.w, data.h);
    app.pools = el("g", {}, app.floor);
    el("rect", { width: data.w, height: data.h, fill: "url(#vignette)", "pointer-events": "none" }, svg);
    app.tablesLayer = el("g", {}, app.floor);
    app.people = el("g", {}, app.floor);
    app.chips = el("g", {}, svg);
    app.tables = new Map();
    data.tables.forEach((d, i) => app.tables.set(d.id, buildTable(app, d, i)));
    placeChips(app, data.h);
  };

  app.update = (data) => {
    const key = data.tables.map(d => `${d.id}:${d.x}:${d.y}:${d.seats}`).join("|");
    if (key !== app.layoutKey) { app.build(data); app.layoutKey = key; app.firstBuild = true; }
    const instant = app.firstBuild;
    const paused = data.status !== "live";
    root.classList.toggle("paused", paused);
    const labels = { live: "Live", finished: "Replay finished", stale: "Waiting for camera data", offline: "Offline, showing cached data", waiting: "Waiting for video" };
    app.pill.className = `pill ${data.status}`;
    app.pill.querySelector(".txt").textContent = labels[data.status] || data.status;
    app.pill.querySelector(".clock").textContent = data.clock ? data.clock : "";

    for (const d of data.tables) {
      const t = app.tables.get(d.id); if (!t) continue;
      const prev = t.prevState;
      t.d = d;
      const held = d.heldFor && d.state === "free";
      t.g.setAttribute("class", `table s-${d.state}${d.attention || held ? " attention" : ""}${d.selected ? " selected" : ""}${d.dim ? " dim" : ""}`);
      t.g.setAttribute("aria-label", `${d.name}, ${d.stateName}`);
      t.crowd.setAttribute("class", `crowd${d.dim ? " dim" : ""}`);
      t.pool.setAttribute("class", `pool${d.state === "occupied" ? " lit" : ""}`);
      if (prev === "needs_cleaning" && d.state === "free" && !instant) {
        t.burst.classList.remove("go"); void t.burst.getBBox(); t.burst.classList.add("go");
      }
      placeGuests(app, t, d, instant);
      placeStaff(app, t, d, instant);
      // Plates get food for each seated guest.
      const served = new Set(d.state === "occupied" ? t.guests.map((p, i) => spot(t, "guest", i, "seated").seat) : []);
      t.settings.forEach((s, i) => s.classList.toggle("served", served.has(i)));
      updateChat(t, d);
      updateChip(t, d);
      t.prevState = d.state;
      if (app.tipFor === t) app.showTip(t);
    }
    app.firstBuild = false;
  };

  app.destroy = () => {
    for (const t of app.tables.values()) [...t.guests, ...t.staff].forEach(stopWalk);
    root.innerHTML = "";
  };
  return app;
}

export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  const root = parentElement.querySelector(".tf-root");
  if (!root || !data) return;
  let app = root.__dineassist;
  if (!app) { app = createApp(root); root.__dineassist = app; }
  app.setTrigger = setTriggerValue;
  app.update(data);
  return () => { app.destroy(); delete root.__dineassist; };
}
