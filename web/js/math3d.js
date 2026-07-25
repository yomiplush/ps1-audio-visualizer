/** Column-major 4x4 helpers (WebGL). */

export function perspective(fovyDeg, aspect, zNear, zFar) {
  const f = 1 / Math.tan((fovyDeg * Math.PI) / 360);
  const m = new Float32Array(16);
  m[0] = f / Math.max(aspect, 1e-6);
  m[5] = f;
  m[10] = (zFar + zNear) / (zNear - zFar);
  m[11] = -1;
  m[14] = (2 * zFar * zNear) / (zNear - zFar);
  return m;
}

export function lookAt(ex, ey, ez, tx, ty, tz) {
  let fx = tx - ex, fy = ty - ey, fz = tz - ez;
  let fl = Math.hypot(fx, fy, fz) + 1e-9;
  fx /= fl; fy /= fl; fz /= fl;
  // cross(f, up=0,1,0) for s — actually right = normalize(cross(f, up)) wait
  // OpenGL lookAt: zaxis = normalize(eye-center) = -f if f is center-eye
  // Standard: forward = normalize(center - eye)
  let sx = fy * 0 - fz * 1, sy = fz * 0 - fx * 0, sz = fx * 1 - fy * 0;
  let sl = Math.hypot(sx, sy, sz) + 1e-9;
  sx /= sl; sy /= sl; sz /= sl;
  const ux = sy * fz - sz * fy, uy = sz * fx - sx * fz, uz = sx * fy - sy * fx;
  const m = new Float32Array(16);
  m[0] = sx; m[4] = sy; m[8] = sz; m[12] = -(sx * ex + sy * ey + sz * ez);
  m[1] = ux; m[5] = uy; m[9] = uz; m[13] = -(ux * ex + uy * ey + uz * ez);
  m[2] = -fx; m[6] = -fy; m[10] = -fz; m[14] = fx * ex + fy * ey + fz * ez;
  m[3] = 0; m[7] = 0; m[11] = 0; m[15] = 1;
  return m;
}

export function mul(a, b) {
  const r = new Float32Array(16);
  for (let c = 0; c < 4; c++) {
    for (let row = 0; row < 4; row++) {
      r[c * 4 + row] =
        a[0 * 4 + row] * b[c * 4 + 0] +
        a[1 * 4 + row] * b[c * 4 + 1] +
        a[2 * 4 + row] * b[c * 4 + 2] +
        a[3 * 4 + row] * b[c * 4 + 3];
    }
  }
  return r;
}
