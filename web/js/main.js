/**
 * SoundOrbit WebGL2 Demo
 */
import { DemoAudio } from "./audio.js";
import { VisualizerRenderer } from "./renderer.js";

const canvas = document.getElementById("c");
const ui = document.getElementById("ui");
const startBtn = document.getElementById("start");
const statusEl = document.getElementById("status");
const hud = document.getElementById("hud");

const params = new URLSearchParams(location.search);
const debug = params.has("debug") || true; // always show light HUD for debugging black screen

function setStatus(msg) {
  if (statusEl) statusEl.textContent = msg;
}

function sizeCanvas() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  // Prefer window size — more reliable than clientWidth on some mobile browsers
  const cssW = window.innerWidth || document.documentElement.clientWidth || 800;
  const cssH = window.innerHeight || document.documentElement.clientHeight || 600;
  const w = Math.max(2, Math.floor(cssW * dpr));
  const h = Math.max(2, Math.floor(cssH * dpr));
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  if (renderer) renderer.resize(w, h);
  return { w, h };
}

const gl = canvas.getContext("webgl2", {
  alpha: false,
  antialias: false,
  depth: true,
  stencil: false,
  premultipliedAlpha: false,
  powerPreference: "high-performance",
  preserveDrawingBuffer: true,
});

if (!gl) {
  setStatus("WebGL2 が使えません。Chrome / Firefox / Edge の最新版をどうぞ");
  if (startBtn) startBtn.disabled = true;
  throw new Error("WebGL2 required");
}

const audio = new DemoAudio();
let renderer = null;
let audioLive = false; // mic/synth started
let lastFrame = 0;
const frameMs = 1000 / 20;
let frames = 0;
let fpsT = performance.now();
let lastErr = "";

async function boot() {
  setStatus("シェーダー読み込み中…");
  sizeCanvas();
  renderer = new VisualizerRenderer(gl);
  await renderer.init();
  sizeCanvas();
  // Draw immediately (no audio) so page is never pure black
  audio.update();
  renderer.render(audio);
  setStatus("Start Demo を押すとマイクに反応します");
  if (debug) {
    hud.hidden = false;
    hud.textContent = "booted · WebGL2 OK";
  }
}

function hideUi() {
  ui.classList.add("hidden");
}

function loop(now) {
  requestAnimationFrame(loop);
  if (!renderer || !renderer.ready) return;
  if (now - lastFrame < frameMs - 1) return;
  lastFrame = now;

  sizeCanvas();
  try {
    audio.update();
    renderer.render(audio);
    lastErr = "";
  } catch (e) {
    console.error(e);
    lastErr = e.message || String(e);
    setStatus("描画エラー: " + lastErr);
    // keep trying next frames
  }

  frames++;
  if (now - fpsT > 400) {
    const fps = (frames * 1000) / (now - fpsT);
    frames = 0;
    fpsT = now;
    if (debug) {
      hud.hidden = false;
      hud.textContent =
        `${fps.toFixed(0)}fps · ${audio.mode} · ` +
        `B${audio.bass.toFixed(2)} M${audio.mid.toFixed(2)} T${audio.treble.toFixed(2)} · ` +
        `${canvas.width}x${canvas.height}` +
        (lastErr ? " · ERR " + lastErr : "");
    }
  }
}

startBtn.addEventListener("click", async () => {
  startBtn.disabled = true;
  setStatus("音声を開始…");
  try {
    try {
      await audio.startMic();
      setStatus("マイク ON — 声や音を出してみて");
    } catch (micErr) {
      console.warn(micErr);
      await audio.startSynth();
      setStatus("マイク不可 — デモ波形で表示中");
    }
    audioLive = true;
    hideUi();
    // force a frame
    audio.update();
    renderer.render(audio);
  } catch (e) {
    console.error(e);
    setStatus("音声エラー: " + e.message + "（映像はデモ波形で継続）");
    startBtn.disabled = false;
    // keep rendering with procedural audio.update fallback
  }
});

canvas.addEventListener("click", () => {
  if (audioLive) ui.classList.toggle("hidden");
});
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" || e.key === "h" || e.key === "H") ui.classList.toggle("hidden");
});
window.addEventListener("resize", sizeCanvas);

sizeCanvas();
boot()
  .then(() => {
    requestAnimationFrame(loop);
  })
  .catch((e) => {
    console.error(e);
    setStatus("初期化失敗: " + e.message);
    hud.hidden = false;
    hud.textContent = String(e);
  });
