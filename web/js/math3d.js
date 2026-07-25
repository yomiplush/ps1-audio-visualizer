/** Column-major 4×4 matrices for WebGL */

export function perspective(fovyDeg, aspect, zNear, zFar) {
  const f = 1 / Math.tan((fovyDeg * Math.PI) / 360);
  const nf = 1 / (zNear - zFar);
  const m = new Float32Array(16);
  m[0] = f / Math.max(aspect, 1e-6);
  m[5] = f;
  m[10] = (zFar + zNear) * nf;
  m[11] = -1;
  m[14] = 2 * zFar * zNear * nf;
  return m;
}

/** eye → target, Y-up. Column-major view matrix. */
export function lookAt(ex, ey, ez, tx, ty, tz, ux = 0, uy = 1, uz = 0) {
  // zaxis = normalize(eye - center)  [camera looks down -Z in view space]
  let zx = ex - tx, zy = ey - ty, zz = ez - tz;
  let len = Math.hypot(zx, zy, zz) || 1;
  zx /= len; zy /= len; zz /= len;
  // xaxis = normalize(cross(up, zaxis))
  let xx = uy * zz - uz * zy;
  let xy = uz * zx - ux * zz;
  let xz = ux * zy - uy * zx;
  len = Math.hypot(xx, xy, xz) || 1;
  xx /= len; xy /= len; xz /= len;
  // yaxis = cross(zaxis, xaxis)
  const yx = zy * xz - zz * xy;
  const yy = zz * xx - zx * xz;
  const yz = zx * xy - zy * xx;
  const m = new Float32Array(16);
  m[0] = xx; m[4] = xy; m[8] = xz; m[12] = -(xx * ex + xy * ey + xz * ez);
  m[1] = yx; m[5] = yy; m[9] = yz; m[13] = -(yx * ex + yy * ey + yz * ez);
  m[2] = zx; m[6] = zy; m[10] = zz; m[14] = -(zx * ex + zy * ey + zz * ez);
  m[3] = 0; m[7] = 0; m[11] = 0; m[15] = 1;
  return m;
}

export function mul(a, b) {
  const r = new Float32Array(16);
  for (let c = 0; c < 4; c++) {
    for (let row = 0; row < 4; row++) {
      r[c * 4 + row] =
        a[row] * b[c * 4] +
        a[4 + row] * b[c * 4 + 1] +
        a[8 + row] * b[c * 4 + 2] +
        a[12 + row] * b[c * 4 + 3];
    }
  }
  return r;
}
