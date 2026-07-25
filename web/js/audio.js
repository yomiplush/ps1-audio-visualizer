/** Mic + AnalyserNode, with procedural fallback when mic denied. */

export const BANDS = 48;

export class DemoAudio {
  constructor() {
    this.ctx = null;
    this.analyser = null;
    this.stream = null;
    this.mode = "idle"; // idle | mic | synth
    this._freq = null;
    this._smooth = new Float32Array(BANDS);
    this._beatEnv = 0;
    this.bass = 0;
    this.mid = 0;
    this.treble = 0;
    this.rms = 0;
    this.beat = 0;
    this.spectrum = new Float32Array(BANDS);
    this._osc = null;
    this._lfo = null;
    this._t0 = performance.now();
  }

  async startMic() {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      video: false,
    });
    this.stream = stream;
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    await this.ctx.resume();
    const src = this.ctx.createMediaStreamSource(stream);
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 2048;
    this.analyser.smoothingTimeConstant = 0.65;
    src.connect(this.analyser);
    this._freq = new Uint8Array(this.analyser.frequencyBinCount);
    this.mode = "mic";
  }

  async startSynth() {
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    await this.ctx.resume();
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 2048;
    this.analyser.smoothingTimeConstant = 0.5;
    const osc = this.ctx.createOscillator();
    const lfo = this.ctx.createOscillator();
    const lfoGain = this.ctx.createGain();
    const gain = this.ctx.createGain();
    osc.type = "sawtooth";
    osc.frequency.value = 110;
    lfo.frequency.value = 2.2;
    lfoGain.gain.value = 40;
    gain.gain.value = 0.12;
    lfo.connect(lfoGain);
    lfoGain.connect(osc.frequency);
    osc.connect(gain);
    gain.connect(this.analyser);
    // Don't connect to destination to avoid loud noise; analysis only
    // gain.connect(this.ctx.destination);
    osc.start();
    lfo.start();
    this._osc = osc;
    this._lfo = lfo;
    this._freq = new Uint8Array(this.analyser.frequencyBinCount);
    this.mode = "synth";
  }

  stop() {
    try { this._osc?.stop(); } catch (_) {}
    try { this._lfo?.stop(); } catch (_) {}
    this.stream?.getTracks().forEach((t) => t.stop());
    this.ctx?.close();
    this.mode = "idle";
  }

  update() {
    if (!this.analyser || !this._freq) {
      // pure procedural without audio graph
      const t = (performance.now() - this._t0) * 0.001;
      for (let i = 0; i < BANDS; i++) {
        const x = i / BANDS;
        this.spectrum[i] = 0.15 + 0.35 * Math.abs(Math.sin(t * 2.1 + x * 8)) * (1 - x * 0.5);
      }
      this.bass = 0.3 + 0.25 * Math.sin(t * 3);
      this.mid = 0.25 + 0.2 * Math.sin(t * 5.1);
      this.treble = 0.2 + 0.2 * Math.sin(t * 7.3);
      this.rms = 0.25;
      this.beat = Math.max(0, Math.sin(t * 4) * 0.5);
      return;
    }
    this.analyser.getByteFrequencyData(this._freq);
    const n = this._freq.length;
    let sumSq = 0;
    for (let b = 0; b < BANDS; b++) {
      const t0 = b / BANDS;
      const t1 = (b + 1) / BANDS;
      const i0 = Math.max(1, Math.floor(Math.pow(n, t0)));
      const i1 = Math.min(n - 1, Math.max(i0 + 1, Math.floor(Math.pow(n, t1))));
      let acc = 0;
      for (let i = i0; i < i1; i++) acc += this._freq[i];
      const v = (acc / (i1 - i0) / 255) * 1.4;
      this._smooth[b] = this._smooth[b] * 0.55 + v * 0.45;
      this.spectrum[b] = this._smooth[b];
      sumSq += this._smooth[b] * this._smooth[b];
    }
    const n3 = (BANDS / 3) | 0;
    let bass = 0, mid = 0, treble = 0;
    for (let i = 0; i < n3; i++) bass += this.spectrum[i];
    for (let i = n3; i < 2 * n3; i++) mid += this.spectrum[i];
    for (let i = 2 * n3; i < BANDS; i++) treble += this.spectrum[i];
    this.bass = Math.min(1.5, (bass / n3) * 1.2);
    this.mid = Math.min(1.5, (mid / n3) * 1.1);
    this.treble = Math.min(1.5, (treble / Math.max(1, BANDS - 2 * n3)) * 1.1);
    this.rms = Math.min(1.5, Math.sqrt(sumSq / BANDS));
    const energy = this.bass * 0.5 + this.rms * 0.7;
    this._beatEnv = energy > this._beatEnv ? energy : this._beatEnv * 0.92;
    this.beat = Math.max(0, Math.min(1, energy - this._beatEnv * 0.85));
  }
}
