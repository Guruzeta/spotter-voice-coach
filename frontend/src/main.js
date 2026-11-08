import { Conversation } from "@elevenlabs/client";
import * as board from "./board.js";

const $ = (id) => document.getElementById(id);
const startBtn = $("start");
const recordBtn = $("record");

let conversation = null;
const sessionPlots = [];
if (import.meta.env.DEV) window.board = board; // lets you try the whiteboard from the console

// ---------- mode switch ----------
let mode = "todo";
try {
  mode = localStorage.getItem("mode") || "todo";
} catch {}
function setMode(m) {
  mode = m;
  try {
    localStorage.setItem("mode", m);
  } catch {}
  document.querySelectorAll(".mode").forEach((b) => b.classList.toggle("selected", b.dataset.mode === m));
}
document.querySelectorAll(".mode").forEach((b) => (b.onclick = () => !conversation && setMode(b.dataset.mode)));
setMode(mode);

// ---------- UI helpers ----------
function setStatus(text, live = false) {
  $("status").textContent = text;
  $("status").classList.toggle("live", live);
}

function logActivity(text, cls = "") {
  const li = document.createElement("li");
  li.className = cls;
  li.innerHTML = text;
  $("activity").appendChild(li);
  li.scrollIntoView({ block: "nearest" });
  return li;
}

function addTranscript(who, text) {
  const p = document.createElement("p");
  p.className = who === "ai" ? "ai" : "user";
  p.innerHTML = `<span class="who">${who === "ai" ? "Sam" : "You"}</span>`;
  p.append(document.createTextNode(text));
  $("transcript").appendChild(p);
  p.scrollIntoView({ block: "nearest" });
}

function showPlots(urls) {
  const box = $("plots");
  if (!sessionPlots.length) box.innerHTML = "";
  for (const url of urls) {
    sessionPlots.push(url);
    const img = document.createElement("img");
    img.src = url;
    img.alt = "Figure from sandbox analysis";
    img.onclick = () => img.classList.toggle("big");
    box.prepend(img);
  }
}

const TODO_ICON = { open: "☐", in_progress: "◐", done: "☑", skipped: "⊘" };
let prevTodos = {};

function renderTodos(todos = []) {
  const ul = $("todos");
  ul.innerHTML = todos.length ? "" : `<li class="empty">No to-dos.</li>`;
  for (const t of todos) {
    const li = document.createElement("li");
    li.className = t.status;
    if (prevTodos[t.id] && prevTodos[t.id] !== t.status) li.classList.add("flash");
    li.innerHTML = `<span class="box">${TODO_ICON[t.status]}</span><span class="text"></span>`;
    li.querySelector(".text").textContent = t.text;
    if (t.finding) {
      const f = document.createElement("span");
      f.className = "finding";
      f.textContent = t.finding;
      li.appendChild(f);
    }
    ul.appendChild(li);
  }
  prevTodos = Object.fromEntries(todos.map((t) => [t.id, t.status]));
  const open = todos.filter((t) => t.status === "open" || t.status === "in_progress").length;
  $("todo-count").textContent = todos.length ? `${todos.length - open}/${todos.length} cleared` : "";
}

async function postJSON(url, body) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return r.json();
}

// ---------- project (which repo Sam is pointed at) ----------
function showProject(d) {
  const p = d.active;
  const status = $("project-status");
  status.className = "project-status";
  status.innerHTML = `<strong></strong> · indexed in Daytona · ${p.memory_items} memories · ${p.todos.length} to-dos`;
  status.querySelector("strong").textContent = p.title;
  $("project-input").placeholder = p.source === "demo" ? "GitHub URL or owner/repo — or 'demo'" : p.source.replace(/\.git$/, "");
  $("recent-projects").innerHTML = "";
  for (const r of d.recent || []) {
    const o = document.createElement("option");
    o.value = r.source === "demo" ? "demo" : r.source.replace(/\.git$/, "");
    $("recent-projects").appendChild(o);
  }
  renderTodos(p.todos);
}

$("project-bar").onsubmit = async (e) => {
  e.preventDefault();
  const source = $("project-input").value.trim();
  if (!source || conversation) return;
  const status = $("project-status");
  status.className = "project-status busy";
  status.textContent = "Cloning into a Daytona sandbox and indexing…";
  $("project-open").disabled = true;
  try {
    const r = await fetch("/api/project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.statusText);
    $("project-input").value = "";
    showProject(d);
    logActivity(`Pointed Sam at ${escapeHtml(d.active.title)}`, "done");
  } catch (err) {
    status.className = "project-status bad";
    status.textContent = String(err.message || err);
  } finally {
    $("project-open").disabled = false;
  }
};

fetch("/api/project").then((r) => r.json()).then(showProject);
$("todo-reset").onclick = async () => renderTodos((await postJSON("/api/todos/reset", {})).todos);

const escapeHtml = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

// ---------- Client tools (called by the ElevenLabs agent mid-conversation) ----------
const clientTools = {
  async get_experiment_overview() {
    const li = logActivity("Reading experiment folder…", "running");
    const r = await fetch(`/api/experiment?mode=${mode}`).then((x) => x.json());
    li.className = "done";
    li.textContent = "Read experiment folder and to-do list";
    renderTodos(r.todos);
    return r.overview;
  },

  async read_file({ path = "", start_line = 1, max_lines = 150 }) {
    const li = logActivity(`Reading <code>${escapeHtml(path)}</code>…`, "running");
    const r = await postJSON("/api/read", { path, start_line: Number(start_line) || 1, max_lines: Number(max_lines) || 150 });
    li.className = "done";
    li.innerHTML = `Read <code>${escapeHtml(path)}</code>`;
    return r.content;
  },

  async search_repo({ pattern = "" }) {
    const li = logActivity(`Searching repo for “${escapeHtml(pattern)}”…`, "running");
    const r = await postJSON("/api/search", { pattern });
    li.className = "done";
    li.textContent = `Searched repo for “${pattern}”`;
    return r.content;
  },

  async remember({ note = "" }) {
    await postJSON("/api/remember", { note });
    logActivity(`Remembered: ${escapeHtml(note)}`, "done");
    return "Saved to project memory.";
  },

  async update_todo({ id, status, finding = "" }) {
    const r = await postJSON("/api/todos/update", { id: Number(id), status, finding });
    renderTodos(r.todos);
    if (r.error) return `Error: ${r.error}`;
    logActivity(`To-do ${id} → ${status.replace("_", " ")}`, "done");
    return `To-do ${id} is now ${status}. Current list:\n` + r.todos.map((t) => `${t.id}. [${t.status}] ${t.text}`).join("\n");
  },

  async add_todo({ text = "" }) {
    const r = await postJSON("/api/todos/add", { text });
    renderTodos(r.todos);
    logActivity(`Added to-do: ${escapeHtml(text)}`, "done");
    return `Added as to-do ${r.todos.length}.`;
  },

  async run_analysis({ purpose = "", code = "" }) {
    const li = logActivity(`Daytona sandbox: ${escapeHtml(purpose || "running analysis")}…`, "running");
    try {
      const r = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ purpose, code }),
      }).then((x) => x.json());
      const ok = r.exit_code === 0;
      li.className = ok ? "done" : "error";
      li.textContent = `Daytona sandbox: ${purpose || "analysis"} — ${ok ? "done" : "error"}${r.seconds ? ` (${r.seconds}s)` : ""}`;
      if (r.plots?.length) showPlots(r.plots);
      return JSON.stringify({
        exit_code: r.exit_code,
        output: r.output,
        figures_shown_on_screen: r.plots?.length || 0,
      });
    } catch (e) {
      li.className = "error";
      li.textContent = `Sandbox request failed: ${e}`;
      return JSON.stringify({ exit_code: -1, output: String(e) });
    }
  },

  async sketch({ mermaid: code = "", caption = "" }) {
    try {
      const n = await board.sketch(code, caption);
      $("step").textContent = `sketch ${n}`;
      return "Drawing it on the whiteboard now (new parts animate in). Talk about the new part.";
    } catch (e) {
      document.querySelectorAll(`[id^="dsketch"]`).forEach((el) => el.remove()); // mermaid error leftovers
      logActivity("Sketch had a syntax error; agent is retrying", "error");
      return `Mermaid syntax error: ${String(e?.message || e).slice(0, 300)}. Simplify and retry.`;
    }
  },

  async write_on_board({ text = "" }) {
    board.write(String(text).slice(0, 80));
    return "Writing it on the board.";
  },

  async show_agenda({ items = "", current = 1 }) {
    const list = (Array.isArray(items) ? items : String(items).split("|")).map((s) => s.trim()).filter(Boolean);
    board.agenda(list, Number(current) || 1);
    return `Agenda on the board; now on section ${current} of ${list.length}.`;
  },

  async save_report({ title = "Experiment report", markdown = "" }) {
    const li = logActivity("Saving report…", "running");
    const r = await fetch("/api/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, markdown, plots: sessionPlots }),
    }).then((x) => x.json());
    li.className = "done";
    li.innerHTML = `Report saved: <a href="${r.url}" target="_blank">${escapeHtml(r.path)}</a>`;
    return `Saved to ${r.path}`;
  },
};

// ---------- Conversation ----------
async function startCall() {
  startBtn.disabled = true;
  setStatus("connecting…");
  try {
    await navigator.mediaDevices.getUserMedia({ audio: true });
    fetch("/api/warmup", { method: "POST" }); // spin up the Daytona sandbox while we connect
    const auth = await fetch("/api/session").then(async (r) => {
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    });
    const connection = auth.conversation_token
      ? { conversationToken: auth.conversation_token, connectionType: "webrtc" }
      : { signedUrl: auth.signed_url, connectionType: "websocket" };

    conversation = await Conversation.startSession({
      ...connection,
      clientTools,
      onConnect: () => {
        setStatus("live", true);
        startBtn.textContent = "End call";
        startBtn.disabled = false;
      },
      onDisconnect: () => {
        setStatus("offline");
        $("mode").textContent = "";
        startBtn.textContent = "Start call";
        startBtn.disabled = false;
        conversation = null;
      },
      onError: (err) => logActivity(`Error: ${escapeHtml(String(err?.message || err))}`, "error"),
      onModeChange: ({ mode }) => ($("mode").textContent = mode === "speaking" ? "Sam is speaking" : "listening"),
      onMessage: (m) => {
        const who = m.source || m.role;
        if (m.message) addTranscript(who === "ai" || who === "agent" ? "ai" : "user", m.message);
      },
    });
  } catch (e) {
    setStatus("offline");
    startBtn.disabled = false;
    logActivity(`Could not start: ${escapeHtml(String(e?.message || e))}`, "error");
  }
}

startBtn.onclick = async () => {
  if (conversation) {
    startBtn.disabled = true;
    await conversation.endSession();
  } else {
    startCall();
  }
};

// ---------- Explainer video: record this tab (board + agent voice + your mic) ----------
let recorder = null;

recordBtn.onclick = async () => {
  if (recorder) {
    recorder.stop();
    return;
  }
  try {
    const screen = await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: 30 },
      audio: true,
      preferCurrentTab: true,
      selfBrowserSurface: "include",
    });
    const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
    const ctx = new AudioContext();
    const mix = ctx.createMediaStreamDestination();
    for (const s of [screen, mic]) {
      if (s.getAudioTracks().length) ctx.createMediaStreamSource(s).connect(mix);
    }
    const stream = new MediaStream([...screen.getVideoTracks(), ...mix.stream.getAudioTracks()]);
    const chunks = [];
    recorder = new MediaRecorder(stream, { mimeType: "video/webm" });
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.onstop = () => {
      [...screen.getTracks(), ...mic.getTracks()].forEach((t) => t.stop());
      ctx.close();
      const url = URL.createObjectURL(new Blob(chunks, { type: "video/webm" }));
      const a = Object.assign(document.createElement("a"), { href: url, download: `explainer-${Date.now()}.webm` });
      a.click();
      logActivity(`Explainer video saved: <a href="${url}" download="explainer.webm">download again</a>`, "done");
      recorder = null;
      recordBtn.textContent = "● Record explainer";
      recordBtn.classList.remove("recording");
    };
    screen.getVideoTracks()[0].onended = () => recorder?.state === "recording" && recorder.stop();
    recorder.start(1000);
    recordBtn.textContent = "■ Stop & save video";
    recordBtn.classList.add("recording");
    if (!screen.getAudioTracks().length) logActivity("Tip: tick 'Share tab audio' to capture Sam's voice in the video", "error");
  } catch (e) {
    logActivity(`Recording not started: ${escapeHtml(String(e?.message || e))}`, "error");
    recorder = null;
  }
};
