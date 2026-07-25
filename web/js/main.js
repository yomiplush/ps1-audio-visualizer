/**
 * SoundOrbit WebGL2 Demo
 * Static site — Cloudflare Pages: root/output directory = web/
 */
import { DemoAudio } from "./audio.js";
import { VisualizerRenderer } from "./renderer.js";

const canvas = document.getElementById("c");
const ui = document.getElementById("ui");
const startBtn = document.getElementById("start");
const statusEl = document.getElementById("status");
const hud = document.getElementById("hud");

const params = new URLSearchParams(location.search);
const debug = params.has("debug");

function setStatus(msg) {
  statusEl.textContent = msg;
}

function resize() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.floor(canvas.clientWidth * dpr);
  const h = Math.floor(canvas.clientHeight * dpr);
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
    if (renderer) renderer.resize(w, h);
  }
}

const gl = canvas.getContext("webgl2", {
  alpha: false,
  antialias: false,
  depth: true,
  powerPreference: "high-performance",
});

if (!gl) {
  setStatus("WebGL2 not available — use a modern browser");
  startBtn.disabled = true;
  throw new Error("WebGL2 required");
}

const audio = new DemoAudio();
let renderer = null;
let running = false;
let lastFrame = 0;
const targetFps = 18;
const frameMs = 1000 / targetFps;
let frames = 0;
let fpsT = performance.now();
let fps = 0;

async function boot() {
  setStatus("Loading shaders…");
  renderer = new VisualizerRenderer(gl);
  await renderer.init();
  resize();
  setStatus("Click Start Demo");
  if (debug) hud.hidden = false;
}

function hideUi() {
  ui.classList.add("hidden");
}

function loop(now) {
  requestAnimationFrame(loop);
  if (!running || !renderer) return;
  if (now - lastFrame < frameMs - 0.5) return;
  lastFrame = now;
  resize();
  audio.update();
  try {
    renderer.render(audio);
  } catch (e) {
    console.error(e);
    setStatus(`Render error: ${e.message}`);
    running = false;
  }
  frames++;
  if (now - fpsT > 500) {
    fps = (frames * 1000) / (now - fpsT);
    frames = 0;
    fpsT = now;
    if (debug) {
      hud.textContent = `${fps.toFixed(0)} fps · ${audio.mode} · B${audio.bass.toFixed(2)} M${audio.mid.toFixed(2)} T${audio.treble.toFixed(2)}`;
    }
  }
}

startBtn.addEventListener("click", async () => {
  startBtn.disabled = true;
  setStatus("Starting audio…");
  try {
    try {
      await audio.startMic();
      setStatus("Mic active — make some noise");
    } catch (micErr) {
      console.warn("mic failed, synth fallback", micErr);
      await audio.startSynth();
      setStatus("Mic denied — synth demo mode");
    }
    running = true;
    hideUi();
    lastFrame = performance.now();
  } catch (e) {
    console.error(e);
    setStatus(`Audio failed: ${e.message}`);
    startBtn.disabled = false;
  }
});

// click canvas to toggle UI after start
canvas.addEventListener("click", () => {
  if (!running) return;
  ui.classList.toggle("hidden");
});

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" || e.key === "h" || e.key === "H") {
    ui.classList.toggle("hidden");
  }
});

window.addEventListener("resize", resize);
resize();
boot()
  .then(() => requestAnimationFrame(loop))
  .catch((e) => {
    console.error(e);
    setStatus(`Init failed: ${e.message}`);
  });
