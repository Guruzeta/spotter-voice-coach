import { Conversation } from "@elevenlabs/client";

const $ = (id) => document.getElementById(id);
let conversation = null;
let prevSetCount = 0;

// ---------- UI ----------
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

function log(text, cls = "") {
  const li = document.createElement("li");
  li.className = cls;
  li.innerHTML = text;
  $("activity").appendChild(li);
  li.scrollIntoView({ block: "nearest" });
  return li;
}

function say(who, text) {
  const p = document.createElement("p");
  p.className = who;
  p.innerHTML = `<span class="who">${who === "ai" ? "Spotter" : "You"}</span>`;
  p.append(document.createTextNode(text));
  $("transcript").appendChild(p);
  p.scrollIntoView({ block: "nearest" });
}

function renderSets(sets, editedN = null) {
  const tb = $("sets");
  if (!sets.length) {
    tb.innerHTML = `<tr><td colspan="5" class="empty">No sets yet.</td></tr>`;
  } else {
    tb.innerHTML = "";
    for (const s of sets) {
      const tr = document.createElement("tr");
      if (s.n > prevSetCount) tr.className = "new";
      if (s.n === editedN) tr.className = "edited";
      tr.innerHTML = `<td>${s.n}</td><td>${esc(s.exercise)}</td><td>${s.weight_lb}</td><td>${s.reps}</td><td>${s.rpe}</td>`;
      tb.appendChild(tr);
    }
  }
  prevSetCount = sets.length;
}

function showPlot(urls) {
  if (!urls?.length) return;
  $("plot").innerHTML = `<img src="${urls[0]}" alt="Training analysis chart" />`;
  $("sandbox-badge").hidden = false;
}

async function post(url, body = {}) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return r.json();
}

// ---------- rest timer ----------
let restTimer = null;
function startRest(seconds) {
  clearInterval(restTimer);
  const card = $("rest-card");
  card.hidden = false;
  card.classList.remove("done");
  let left = Math.max(5, Math.round(seconds));
  const draw = () => ($("rest-time").textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`);
  draw();
  restTimer = setInterval(() => {
    left -= 1;
    draw();
    if (left <= 0) {
      clearInterval(restTimer);
      card.classList.add("done");
      $("rest-time").textContent = "GO";
      conversation?.sendContextualUpdate?.("The rest timer just finished; the lifter can start the next set.");
    }
  }, 1000);
}

// ---------- client tools the ElevenLabs agent calls ----------
const clientTools = {
  async log_set({ exercise, weight_lb, reps, rpe = 8 }) {
    const r = await post("/api/log_set", { exercise, weight_lb: Number(weight_lb), reps: Number(reps), rpe: Number(rpe) });
    renderSets(r.sets);
    log(`Logged set ${r.set_number}: ${esc(r.logged.exercise)} ${r.logged.weight_lb}×${r.logged.reps} @${r.logged.rpe}`, "done");
    return JSON.stringify({ set_number: r.set_number, logged: r.logged, sets_today: r.sets.length });
  },

  async edit_set({ set_number, ...fields }) {
    const body = { set_number: Number(set_number) };
    for (const k of ["exercise", "weight_lb", "reps", "rpe"]) if (fields[k] !== undefined && fields[k] !== null && fields[k] !== "") body[k] = k === "exercise" ? fields[k] : Number(fields[k]);
    const r = await post("/api/edit_set", body);
    renderSets(r.sets, Number(set_number));
    if (r.error) return `Error: ${r.error}`;
    log(`Edited set ${set_number}`, "done");
    return JSON.stringify({ edited: Number(set_number), sets: r.sets });
  },

  async delete_set({ set_number }) {
    const r = await post("/api/delete_set", { set_number: Number(set_number) });
    renderSets(r.sets);
    if (r.error) return `Error: ${r.error}`;
    log(`Deleted set ${set_number}`, "done");
    return `Deleted set ${set_number}.`;
  },

  async next_set({ exercise, reps = 5, rpe = 8 }) {
    const li = log(`Daytona: analysing ${esc(exercise)}…`, "running");
    const r = await post("/api/next_set", { exercise, reps: Number(reps) || 5, rpe: Number(rpe) || 8 });
    if (r.error) {
      li.className = "error";
      li.textContent = "Analysis failed";
      return `Error: ${r.error}`;
    }
    li.className = "done";
    li.textContent = `Daytona: analysed ${r.exercise} (${r.sandbox_seconds}s)`;
    if (r.prescription) {
      $("next-weight").textContent = `${r.prescription.weight_lb} lb`;
      $("next-weight").classList.remove("flash");
      void $("next-weight").offsetWidth;
      $("next-weight").classList.add("flash");
      $("next-detail").textContent = `${r.exercise} · ${r.prescription.reps} reps @ RPE ${r.prescription.rpe}`;
    }
    const bits = [];
    if (r.today_best_e1rm) bits.push(`Est. max today ${r.today_best_e1rm} lb (${r.vs_last_session_pct >= 0 ? "+" : ""}${r.vs_last_session_pct}% vs last session)`);
    if (r.fatigue_drop_pct > 7) bits.push(`fatigue −${r.fatigue_drop_pct}%`);
    if (r.plateau) bits.push("plateau: last 3 sessions flat");
    $("next-insight").textContent = r.note || bits.join(" · ");
    showPlot(r.plots);
    const { plots, ...forAgent } = r;
    return JSON.stringify(forAgent);
  },

  async start_rest({ seconds = 120 }) {
    startRest(Number(seconds) || 120);
    log(`Rest ${seconds}s`, "done");
    return "Timer started.";
  },

  async finish_workout() {
    const li = log("Daytona: summarising workout and writing next plan…", "running");
    const r = await post("/api/finish");
    if (r.error) {
      li.className = "error";
      li.textContent = r.error;
      return `Error: ${r.error}`;
    }
    li.className = "done";
    li.innerHTML = `Saved <code>${esc(r.saved.session)}</code> and <code>${esc(r.saved.plan)}</code>`;
    showPlot(r.plots);
    const rows = r.exercises
      .map((e) => `<tr><td>${esc(e.exercise)}</td><td>${e.today_best_e1rm} lb${e.personal_record ? ' <span class="pr">PR</span>' : ""}</td><td>${e.next_session.sets}×${e.next_session.reps} @ ${e.next_session.weight_lb} lb</td></tr>`)
      .join("");
    $("summary").innerHTML = `<div class="label">Workout saved · next session planned</div><h3>${Math.round(r.total_volume_lb).toLocaleString()} lb total volume</h3><table><thead><tr><th>Lift</th><th>Best est. max</th><th>Next session</th></tr></thead><tbody>${rows}</tbody></table>`;
    $("summary").hidden = false;
    renderSets([]);
    const { plots, plan_table, ...forAgent } = r;
    return JSON.stringify(forAgent);
  },
};

// ---------- conversation ----------
async function start() {
  $("start").disabled = true;
  $("status").textContent = "connecting…";
  try {
    await navigator.mediaDevices.getUserMedia({ audio: true });
    fetch("/api/warmup", { method: "POST" });
    const auth = await fetch("/api/session").then(async (r) => {
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    });
    conversation = await Conversation.startSession({
      conversationToken: auth.conversation_token,
      connectionType: "webrtc",
      clientTools,
      onConnect: () => {
        $("status").textContent = "live";
        $("status").classList.add("live");
        $("start").textContent = "End workout";
        $("start").disabled = false;
      },
      onDisconnect: () => {
        $("status").textContent = "offline";
        $("status").classList.remove("live");
        $("mode").textContent = "";
        $("start").textContent = "Start workout";
        $("start").disabled = false;
        conversation = null;
      },
      onError: (e) => log(`Error: ${esc(e?.message || e)}`, "error"),
      onModeChange: ({ mode }) => ($("mode").textContent = mode === "speaking" ? "speaking" : "listening"),
      onMessage: (m) => {
        const who = m.source || m.role;
        if (m.message) say(who === "ai" || who === "agent" ? "ai" : "user", m.message);
      },
    });
  } catch (e) {
    $("status").textContent = "offline";
    $("start").disabled = false;
    log(`Could not start: ${esc(e?.message || e)}`, "error");
  }
}

$("start").onclick = async () => {
  if (conversation) {
    $("start").disabled = true;
    await conversation.endSession();
  } else start();
};

fetch("/api/state").then((r) => r.json()).then((s) => renderSets(s.sets));
if (import.meta.env.DEV) window.tools = clientTools; // try tools from the console without talking
