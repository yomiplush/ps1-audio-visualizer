/** SoundOrbit WebGL2 renderer — PS1 CRT visualizer */

import { perspective, lookAt, mul } from "./math3d.js";
import { programFromUrls, createTexture, createFbo, createDepthRb } from "./gl.js";
import { BANDS } from "./audio.js";

const INTERNAL_W = 200;
const INTERNAL_H = 150;

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
    const idx = [0,1,2, 0,2,3];
    for (const i of idx) {
      const p = f[i];
      out.push(p[0]*0.22, p[1], p[2]*0.22, n[0], n[1], n[2]);
    }
  }
  return new Float32Array(out);
}

export class VisualizerRenderer {
  constructor(gl) {
    this.gl = gl;
    this.ready = false;
    this.viewW = 1;
    this.viewH = 1;
    this.angle = 0;
    this.frameI = 0;
    this.lockedFps = 18;
    this.fixedDt = 1 / 18;
    this.spectrum = new Float32Array(BANDS);
    this.instances = new Float32Array(BANDS * 4);
    const R = 3.2;
    for (let i = 0; i < BANDS; i++) {
      const ang = (i / BANDS) * Math.PI * 2 - Math.PI * 0.5;
      this.instances[i*4] = Math.cos(ang) * R;
      this.instances[i*4+1] = Math.sin(ang) * R;
      this.instances[i*4+2] = 0.05;
      this.instances[i*4+3] = i;
    }
    this.barVerts = unitBox();
    this.barVertexCount = this.barVerts.length / 6;
  }

  async init() {
    const gl = this.gl;
    const base = new URL("../shaders/", import.meta.url);
    this.progBg = await programFromUrls(gl, new URL("bg.vert", base), new URL("bg.frag", base));
    this.progBar = await programFromUrls(gl, new URL("bar.vert", base), new URL("bar.frag", base));
    this.progPost = await programFromUrls(gl, new URL("post.vert", base), new URL("post.frag", base));
    this.progTrail = await programFromUrls(gl, new URL("post.vert", base), new URL("trail.frag", base));

    // quad
    this.quadVao = gl.createVertexArray();
    gl.bindVertexArray(this.quadVao);
    this.quadVbo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadVbo);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

    // bars
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
    gl.enable(gl.DEPTH_TEST);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    this._allocTargets();
    this.ready = true;
  }

  _allocTargets() {
    const gl = this.gl;
    const w = INTERNAL_W, h = INTERNAL_H;
    this.texScene = createTexture(gl, w, h);
    this.rboDepth = createDepthRb(gl, w, h);
    this.fboScene = createFbo(gl, this.texScene, this.rboDepth);
    this.texTrail = [createTexture(gl, w, h), createTexture(gl, w, h)];
    this.fboTrail = [createFbo(gl, this.texTrail[0]), createFbo(gl, this.texTrail[1])];
    for (let i = 0; i < 2; i++) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.fboTrail[i]);
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
    const a = audio;
    for (let i = 0; i < BANDS; i++) {
      this.spectrum[i] = this.spectrum[i] * 0.35 + a.spectrum[i] * 0.65;
    }
    const energy = Math.min(1.5, a.rms * 0.7 + a.bass * 0.5 + a.mid * 0.3);
    const beat = a.beat;
    const dt = this.fixedDt;
    this.angle += dt * (0.18 + energy * 0.35 + beat * 0.5);
    const t = this.frameI * this.fixedDt;
    this.frameI++;

    for (let i = 0; i < BANDS; i++) {
      let h = this.spectrum[i];
      h = h * h * 2.8 + h * 1.2;
      this.instances[i * 4 + 2] = Math.max(0.04, Math.min(4.5, h * (0.9 + a.bass * 0.4)));
    }

    // scene
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fboScene);
    gl.viewport(0, 0, INTERNAL_W, INTERNAL_H);
    gl.clearColor(0.02, 0.03, 0.06, 1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

    gl.disable(gl.DEPTH_TEST);
    gl.useProgram(this.progBg);
    gl.uniform1f(gl.getUniformLocation(this.progBg, "uTime"), t);
    gl.uniform1f(gl.getUniformLocation(this.progBg, "uEnergy"), energy);
    gl.uniform1f(gl.getUniformLocation(this.progBg, "uBeat"), beat);
    gl.bindVertexArray(this.quadVao);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

    gl.enable(gl.DEPTH_TEST);
    const aspect = INTERNAL_W / INTERNAL_H;
    const proj = perspective(52, aspect, 0.1, 80);
    const camR = 9.5 - energy * 1.2 - beat * 0.8;
    const camH = 4.2 + a.mid * 0.8;
    const ex = Math.cos(this.angle) * camR;
    const ez = Math.sin(this.angle) * camR;
    const view = lookAt(ex, camH, ez, 0, 0.9 + a.bass * 0.4, 0);
    const vp = mul(proj, view);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.barInstanceVbo);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.instances);
    gl.useProgram(this.progBar);
    gl.uniformMatrix4fv(gl.getUniformLocation(this.progBar, "uMVP"), false, vp);
    gl.uniform1f(gl.getUniformLocation(this.progBar, "uTime"), t);
    gl.uniform1f(gl.getUniformLocation(this.progBar, "uBass"), a.bass);
    gl.uniform1f(gl.getUniformLocation(this.progBar, "uBands"), BANDS);
    gl.uniform1f(gl.getUniformLocation(this.progBar, "uBeat"), beat);
    gl.bindVertexArray(this.barVao);
    gl.drawArraysInstanced(gl.TRIANGLES, 0, this.barVertexCount, BANDS);

    // trail
    const src = this.trailIdx;
    const dst = 1 - src;
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fboTrail[dst]);
    gl.viewport(0, 0, INTERNAL_W, INTERNAL_H);
    gl.disable(gl.DEPTH_TEST);
    gl.useProgram(this.progTrail);
    gl.uniform1f(gl.getUniformLocation(this.progTrail, "uDecay"), 0.80);
    gl.uniform1f(gl.getUniformLocation(this.progTrail, "uSceneGain"), 0.32);
    gl.uniform1f(gl.getUniformLocation(this.progTrail, "uZoom"), 0.997);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.texScene);
    gl.uniform1i(gl.getUniformLocation(this.progTrail, "uScene"), 0);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.texTrail[src]);
    gl.uniform1i(gl.getUniformLocation(this.progTrail, "uPrev"), 1);
    gl.bindVertexArray(this.quadVao);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    this.trailIdx = dst;

    // CRT post
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, this.viewW, this.viewH);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(this.progPost);
    const trailMix = Math.min(0.55, Math.max(0.25, 0.36 + energy * 0.05 + beat * 0.05));
    gl.uniform1f(gl.getUniformLocation(this.progPost, "uTrailMix"), trailMix);
    gl.uniform1f(gl.getUniformLocation(this.progPost, "uEnergy"), energy);
    gl.uniform1f(gl.getUniformLocation(this.progPost, "uBeat"), beat);
    gl.uniform1f(gl.getUniformLocation(this.progPost, "uTime"), t);
    gl.uniform1f(gl.getUniformLocation(this.progPost, "uExposure"), 0.90);
    gl.uniform1f(gl.getUniformLocation(this.progPost, "uBarrel"), 0.10);
    gl.uniform1f(gl.getUniformLocation(this.progPost, "uScanline"), 0.95);
    gl.uniform1f(gl.getUniformLocation(this.progPost, "uVignette"), 0.45);
    gl.uniform2f(gl.getUniformLocation(this.progPost, "uInternal"), INTERNAL_W, INTERNAL_H);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.texScene);
    gl.uniform1i(gl.getUniformLocation(this.progPost, "uScene"), 0);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.texTrail[this.trailIdx]);
    gl.uniform1i(gl.getUniformLocation(this.progPost, "uTrail"), 1);
    gl.bindVertexArray(this.quadVao);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }
}
