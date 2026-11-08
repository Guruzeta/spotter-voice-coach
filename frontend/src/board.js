// Whiteboard that looks like someone drawing: only new parts of a diagram are animated in,
// stroke by stroke, with handwritten text revealed left to right and a pen that follows along.
import "@fontsource/caveat/400.css";
import "@fontsource/caveat/700.css";
import mermaid from "mermaid";

const INK = "#1f3a93";
mermaid.initialize({
  startOnLoad: false,
  look: "handDrawn",
  handDrawnSeed: 7,
  theme: "base",
  securityLevel: "strict",
  themeVariables: {
    fontFamily: "Caveat, 'Comic Sans MS', cursive",
    fontSize: "24px",
    primaryColor: "#fffdf6",
    primaryBorderColor: INK,
    primaryTextColor: "#1b1b1b",
    lineColor: INK,
    secondaryColor: "#fff3ee",
    tertiaryColor: "#f2f6ff",
    edgeLabelBackground: "#ffffff00",
  },
  flowchart: { curve: "basis", padding: 14, nodeSpacing: 50, rankSpacing: 60 },
});

const $ = (id) => document.getElementById(id);
const fontsReady = document.fonts.load("24px Caveat").catch(() => {});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let renderCount = 0;
let prevLabels = new Set();
let prevEdgeCount = 0;
let queue = Promise.resolve(); // drawing happens in order, but tools return immediately

// ---------- pen ----------
let penTimer = null;
function movePen(el, atEnd = false) {
  const pen = $("pen");
  const surface = $("surface").getBoundingClientRect();
  const r = el.getBoundingClientRect();
  const x = (atEnd ? r.right : r.left + r.width * 0.15) - surface.left;
  const y = r.top + r.height * 0.55 - surface.top;
  pen.style.transform = `translate(${x}px, ${y - 26}px)`;
  pen.classList.add("active");
  clearTimeout(penTimer);
  penTimer = setTimeout(() => pen.classList.remove("active"), 900);
}

// ---------- stroke animation ----------
function strokesOf(el) {
  if (el.matches("path, line, polyline, polygon, rect, circle, ellipse")) return [el];
  return [...el.querySelectorAll("path, line, polyline, polygon, rect, circle, ellipse")];
}

function textsOf(el) {
  return [...el.querySelectorAll("foreignObject > *, text")];
}

function hide(el) {
  el.style.visibility = "hidden";
  const marker = el.getAttribute?.("marker-end");
  if (marker) {
    el.dataset.marker = marker;
    el.removeAttribute("marker-end");
  }
}

async function drawElement(el, duration) {
  const strokes = strokesOf(el);
  const texts = textsOf(el);
  for (const s of strokes) {
    let len = 400;
    try {
      len = Math.max(20, s.getTotalLength());
    } catch {}
    s.style.transition = "none";
    s.style.strokeDasharray = `${len}`;
    s.style.strokeDashoffset = `${len}`;
    s.style.fillOpacity = "0";
  }
  for (const t of texts) {
    t.style.transition = "none";
    t.style.clipPath = "inset(-10% 100% -10% 0)";
  }
  el.style.visibility = "visible";
  movePen(el);
  await sleep(20);
  for (const s of strokes) {
    s.style.transition = `stroke-dashoffset ${duration}ms ease-in-out, fill-opacity 300ms ${duration * 0.7}ms`;
    s.style.strokeDashoffset = "0";
    s.style.fillOpacity = "";
  }
  await sleep(duration * 0.6);
  for (const t of texts) {
    t.style.transition = `clip-path ${Math.max(350, duration * 0.8)}ms linear`;
    t.style.clipPath = "inset(-10% 0 -10% 0)";
    movePen(t, true);
  }
  await sleep(duration * 0.6);
  if (el.dataset.marker) el.setAttribute("marker-end", el.dataset.marker);
  for (const s of strokes) s.style.strokeDasharray = "";
}

// ---------- public API ----------
export async function erase() {
  const surface = $("surface");
  surface.classList.add("erasing");
  await sleep(350);
  $("diagram").innerHTML = "";
  $("notes").innerHTML = "";
  surface.classList.remove("erasing");
  prevLabels = new Set();
  prevEdgeCount = 0;
}

/** Render a Mermaid diagram; animate only nodes/edges that weren't on the board before. Throws on syntax errors. */
export async function sketch(code, caption = "") {
  await fontsReady;
  const { svg } = await mermaid.render(`sketch${++renderCount}`, code); // throws before touching the board
  queue = queue.then(() => drawDiagram(svg, caption)).catch((e) => console.error(e));
  return renderCount;
}

async function drawDiagram(svgText, caption) {
  const holder = document.createElement("div");
  holder.innerHTML = svgText;
  const svg = holder.querySelector("svg");
  const nodes = [...svg.querySelectorAll("g.node")];
  const labels = nodes.map((n) => n.textContent.trim());
  const continuing = labels.some((l) => prevLabels.has(l));
  if (!continuing && $("diagram").childElementCount) await erase();

  const edges = [...svg.querySelectorAll(".edgePaths path, .edgePath path")];
  const edgeLabels = [...svg.querySelectorAll(".edgeLabels .edgeLabel")];
  const newNodes = nodes.filter((n, i) => !prevLabels.has(labels[i]));
  const newEdges = edges.slice(continuing ? prevEdgeCount : 0);
  const newEdgeLabels = edgeLabels.slice(continuing ? prevEdgeCount : 0);
  prevLabels = new Set(labels);
  prevEdgeCount = edges.length;

  [...newNodes, ...newEdges, ...newEdgeLabels].forEach(hide);
  $("diagram").replaceChildren(svg);
  if (caption) $("caption").textContent = caption;

  // Draw each new node, then any new edge leading into it, like a person would.
  const pace = newNodes.length + newEdges.length > 6 ? 450 : 650;
  for (const node of newNodes) await drawElement(node, pace);
  for (let i = 0; i < newEdges.length; i++) {
    await drawElement(newEdges[i], pace * 0.7);
    if (newEdgeLabels[i]) await drawElement(newEdgeLabels[i], 300);
  }
}

/** Handwrite a line of text (an equation, a number, a takeaway) under the diagram. */
export function write(text) {
  queue = queue.then(async () => {
    const notes = $("notes");
    const line = document.createElement("div");
    line.className = "note";
    notes.appendChild(line);
    while (notes.childElementCount > 4) notes.firstElementChild.remove();
    for (const ch of [...text]) {
      line.textContent += ch;
      movePen(line, true);
      await sleep(ch === " " ? 20 : 45);
    }
  });
}

/** Agenda written in the board's corner. items: string[]; current: 1-based index. */
export function agenda(items, current) {
  const box = $("agenda");
  const isNew = box.dataset.items !== JSON.stringify(items);
  box.dataset.items = JSON.stringify(items);
  box.hidden = !items.length;
  box.innerHTML = "";
  items.forEach((item, i) => {
    const li = document.createElement("li");
    const n = i + 1;
    li.className = n < current ? "past" : n === current ? "now" : "";
    li.textContent = `${n < current ? "✓" : n === current ? "➜" : "·"} ${item}`;
    if (isNew) {
      li.style.clipPath = "inset(0 100% 0 0)";
      setTimeout(() => {
        li.style.transition = "clip-path 500ms linear";
        li.style.clipPath = "inset(0 0 0 0)";
      }, 120 + i * 350);
    }
    box.appendChild(li);
  });
}
