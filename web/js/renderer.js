/** SoundOrbit WebGL2 — PS1 CRT visualizer (robust path) */

import { perspective, lookAt, mul } from "./math3d.js";
import { programFromUrls, createTexture, createFbo, createDepthRb } from "./gl.js";
import { BANDS } from "./audio.js";

const INTERNAL_W = 240;
const INTERNAL_H = 180;

function unitBox() {
  const faces = [
    [[-0.5,0.5,-0.5],[0.5,0.5,-0.5],[0.5,0.5,0.5],[-0.5,0.5,0.5],[0,1,0]],
    [[-0.5,-0.5,0.5],[0.5,-0.5,0.5],[0.5,-0.5,-0.5],[-0.5,-0.5,-0.5],[0,-1,0]],
    [[-0.5,-0.5,0.5],[-0.5,0.5,0.5],[0.5,0.5,0.5],[0.5,-0.5,0.5],[0,0,1]],
    [[0.5,-0.5,-0.5],[0.5,0.5,-0.5],[-0.5,0.5,-0.5],[-0.5,-0.5,-0.5],[0,0,-1]],
    [[0.5,-0.5,0.5],[0.5,0.5,0.5],[0.5,0.5,-0.5],[0.5,-0.5,-0.5],[1,0,0]],
    [[-0.5,-0.5,-0.5],[-0.5,0.5,-0.5],[-0.5,0.5,0.5],[-0.5,-0.5,0.5],[-1,0,0]],
  ];
  const out = [];
  for (const f of faces) {
    const n = f[4];
    for (const i of [0, 1, 2, 0, 2, 3]) {
      const p = f[i];
      out.push(p[0] * 0.22, p[1], p[2] * 0.22, n[0], n[1], n[2]);
    }
  }
  return new Float32Array(out);
}

function u1f(gl, prog, name, v) {
  const loc = gl.getUniformLocation(prog, name);
  if (loc !== null) gl.uniform1f(loc, v);
}
function u1i(gl, prog, name, v) {
  const loc = gl.getUniformLocation(prog, name);
  if (loc !== null) gl.uniform1i(loc, v);
}
function u2f(gl, prog, name, x, y) {
  const loc = gl.getUniformLocation(prog, name);
  if (loc !== null) gl.uniform2f(loc, x, y);
}
function uMat4(gl, prog, name, m) {
  const loc = gl.getUniformLocation(prog, name);
  if (loc !== null) gl.uniformMatrix4fv(loc, false, m);
}

export class VisualizerRenderer {
  constructor(gl) {
    this.gl = gl;
    this.ready = false;
    this.viewW = 1;
    this.viewH = 1;
    this.angle = 0.4;
    this.frameI = 0;
    this.fixedDt = 1 / 20;
    this.spectrum = new Float32Array(BANDS);
    this.instances = new Float32Array(BANDS * 4);
    const R = 3.2;
    for (let i = 0; i < BANDS; i++) {
      const ang = (i / BANDS) * Math.PI * 2 - Math.PI * 0.5;
      this.instances[i * 4] = Math.cos(ang) * R;
      this.instances[i * 4 + 1] = Math.sin(ang) * R;
      this.instances[i * 4 + 2] = 0.3;
      this.instances[i * 4 + 3] = i;
    }
    this.barVerts = unitBox();
    this.barVertexCount = this.barVerts.length / 6;
    this._instanceBuf = new Float32Array(this.instances.length);
  }

  async init() {
    const gl = this.gl;
    // Prefer root-relative shader paths (Cloudflare-safe)
    const base = "/shaders/";
    const load = async (v, f) => {
      try {
        return await programFromUrls(gl, base + v, base + f);
      } catch (e1) {
        // fallback relative to this module
        const b = new URL("../shaders/", import.meta.url);
        return programFromUrls(gl, new URL(v, b), new URL(f, b));
      }
    };
    this.progBg = await load("bg.vert", "bg.frag");
    this.progBar = await load("bar.vert", "bar.frag");
    this.progPost = await load("post.vert", "post.frag");
    this.progTrail = await load("post.vert", "trail.frag");

    this.quadVao = gl.createVertexArray();
    gl.bindVertexArray(this.quadVao);
    this.quadVbo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadVbo);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

    this.barVao = gl.createVertexArray();
    gl.bindVertexArray(this.barVao);
    this.barVbo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.barVbo);
    gl.bufferData(gl.ARRAY_BUFFER, this.barVerts, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 24, 0);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 24, 12);
    this.barInstanceVbo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.barInstanceVbo);
    gl.bufferData(gl.ARRAY_BUFFER, this.instances, gl.DYNAMIC_DRAW);
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 4, gl.FLOAT, false, 16, 0);
    gl.vertexAttribDivisor(2, 1);
    gl.bindVertexArray(null);

    this._allocTargets();
    // Sanity: draw one clear so context is warm
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, 1, 1);
    gl.clearColor(0.05, 0.08, 0.12, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    this.ready = true;
  }

  _allocTargets() {
    const gl = this.gl;
    const w = INTERNAL_W;
    const h = INTERNAL_H;
    this.texScene = createTexture(gl, w, h);
    this.rboDepth = createDepthRb(gl, w, h);
    this.fboScene = createFbo(gl, this.texScene, this.rboDepth);
    this.texTrail = [createTexture(gl, w, h), createTexture(gl, w, h)];
    this.fboTrail = [createFbo(gl, this.texTrail[0]), createFbo(gl, this.texTrail[1])];
    for (let i = 0; i < 2; i++) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.fboTrail[i]);
      gl.viewport(0, 0, w, h);
      gl.clearColor(0, 0, 0, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    this.trailIdx = 0;
  }

  resize(w, h) {
    this.viewW = Math.max(1, w | 0);
    this.viewH = Math.max(1, h | 0);
  }

  render(audio) {
    if (!this.ready) return;
    const gl = this.gl;
    const a = audio || {
      spectrum: this.spectrum,
      bass: 0.25,
      mid: 0.2,
      treble: 0.15,
      rms: 0.2,
      beat: 0.1,
    };

    for (let i = 0; i < BANDS; i++) {
      const s = a.spectrum && a.spectrum[i] != null ? a.spectrum[i] : 0.15;
      this.spectrum[i] = this.spectrum[i] * 0.35 + s * 0.65;
    }
    const energy = Math.min(1.5, (a.rms || 0) * 0.7 + (a.bass || 0) * 0.5 + (a.mid || 0) * 0.3);
    const beat = a.beat || 0;
    this.angle += this.fixedDt * (0.22 + energy * 0.4 + beat * 0.55);
    const t = this.frameI * this.fixedDt;
    this.frameI++;

    // Ensure visible bars even with quiet mic (floor)
    for (let i = 0; i < BANDS; i++) {
      let h = this.spectrum[i];
      h = h * h * 2.8 + h * 1.2;
      const floor = 0.12 + 0.08 * Math.abs(Math.sin(t * 1.7 + i * 0.3));
      this.instances[i * 4 + 2] = Math.max(floor, Math.min(4.5, h * (0.9 + (a.bass || 0) * 0.4) + floor * 0.5));
    }
    this._instanceBuf.set(this.instances);

    // ---- 1) Scene FBO ----
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fboScene);
    gl.viewport(0, 0, INTERNAL_W, INTERNAL_H);
    gl.clearColor(0.02, 0.03, 0.06, 1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.CULL_FACE);
    gl.useProgram(this.progBg);
    u1f(gl, this.progBg, "uTime", t);
    u1f(gl, this.progBg, "uEnergy", Math.max(0.15, energy));
    u1f(gl, this.progBg, "uBeat", beat);
    gl.bindVertexArray(this.quadVao);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LEQUAL);
    const aspect = INTERNAL_W / INTERNAL_H;
    const proj = perspective(50, aspect, 0.2, 80);
    const camR = 9.2 - energy * 0.8;
    const camH = 4.0 + (a.mid || 0) * 0.6;
    const ex = Math.cos(this.angle) * camR;
    const ez = Math.sin(this.angle) * camR;
    const view = lookAt(ex, camH, ez, 0, 1.0 + (a.bass || 0) * 0.3, 0);
    const vp = mul(proj, view);

    gl.bindVertexArray(this.barVao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.barInstanceVbo);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, this._instanceBuf);
    gl.useProgram(this.progBar);
    uMat4(gl, this.progBar, "uMVP", vp);
    u1f(gl, this.progBar, "uTime", t);
    u1f(gl, this.progBar, "uBass", a.bass || 0);
    u1f(gl, this.progBar, "uBands", BANDS);
    u1f(gl, this.progBar, "uBeat", beat);
    gl.drawArraysInstanced(gl.TRIANGLES, 0, this.barVertexCount, BANDS);

    // ---- 2) Trail ----
    const src = this.trailIdx;
    const dst = 1 - src;
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fboTrail[dst]);
    gl.viewport(0, 0, INTERNAL_W, INTERNAL_H);
    gl.disable(gl.DEPTH_TEST);
    gl.useProgram(this.progTrail);
    u1f(gl, this.progTrail, "uDecay", 0.78);
    u1f(gl, this.progTrail, "uSceneGain", 0.34);
    u1f(gl, this.progTrail, "uZoom", 0.997);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.texScene);
    u1i(gl, this.progTrail, "uScene", 0);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.texTrail[src]);
    u1i(gl, this.progTrail, "uPrev", 1);
    gl.bindVertexArray(this.quadVao);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    this.trailIdx = dst;

    // ---- 3) CRT post → screen ----
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, this.viewW, this.viewH);
    gl.disable(gl.DEPTH_TEST);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(this.progPost);
    const trailMix = Math.min(0.55, Math.max(0.28, 0.38 + energy * 0.06 + beat * 0.06));
    u1f(gl, this.progPost, "uTrailMix", trailMix);
    u1f(gl, this.progPost, "uEnergy", Math.max(0.1, energy));
    u1f(gl, this.progPost, "uBeat", beat);
    u1f(gl, this.progPost, "uTime", t);
    u1f(gl, this.progPost, "uExposure", 1.05);
    u1f(gl, this.progPost, "uBarrel", 0.08);
    u1f(gl, this.progPost, "uScanline", 0.85);
    u1f(gl, this.progPost, "uVignette", 0.38);
    u2f(gl, this.progPost, "uInternal", INTERNAL_W, INTERNAL_H);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.texScene);
    u1i(gl, this.progPost, "uScene", 0);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.texTrail[this.trailIdx]);
    u1i(gl, this.progPost, "uTrail", 1);
    gl.bindVertexArray(this.quadVao);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

    // cleanup texture units
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, null);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, null);
  }
}
