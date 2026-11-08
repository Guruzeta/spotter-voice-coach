import { Conversation } from "@elevenlabs/client";
import mermaid from "mermaid";

mermaid.initialize({ startOnLoad: false, theme: "neutral", look: "handDrawn", securityLevel: "strict" });

const $ = (id) => document.getElementById(id);
const startBtn = $("start");
const recordBtn = $("record");

let conversation = null;
let sketchCount = 0;
const sessionPlots = [];

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

const escapeHtml = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

// ---------- Client tools (called by the ElevenLabs agent mid-conversation) ----------
const clientTools = {
  async get_experiment_overview() {
    const li = logActivity("Reading experiment folder…", "running");
    const r = await fetch("/api/experiment").then((x) => x.json());
    li.className = "done";
    li.textContent = "Read experiment folder";
    return r.overview;
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
      const { svg } = await mermaid.render(`sketch${++sketchCount}`, code);
      const board = $("diagram");
      board.innerHTML = svg;
      board.classList.remove("fresh");
      void board.offsetWidth;
      board.classList.add("fresh");
      $("caption").textContent = caption;
      $("step").textContent = `step ${sketchCount}`;
      return "Drawn on the whiteboard.";
    } catch (e) {
      document.querySelectorAll(`[id^="dsketch"]`).forEach((n) => n.remove()); // mermaid error leftovers
      logActivity("Sketch had a syntax error; agent is retrying", "error");
      return `Mermaid syntax error: ${String(e?.message || e).slice(0, 300)}. Simplify and retry.`;
    }
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
