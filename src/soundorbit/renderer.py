"""Gtk.GLArea 用 OpenGL 3.3 コア 3D サウンドビジュアライザー。"""

from __future__ import annotations

import math
import time
from typing import Optional

import numpy as np
from OpenGL.GL import (
    GL_ARRAY_BUFFER,
    GL_BLEND,
    GL_CLAMP_TO_EDGE,
    GL_COLOR_ATTACHMENT0,
    GL_COLOR_BUFFER_BIT,
    GL_COMPILE_STATUS,
    GL_CULL_FACE,
    GL_DEPTH_ATTACHMENT,
    GL_DEPTH_BUFFER_BIT,
    GL_DEPTH_COMPONENT24,
    GL_DEPTH_TEST,
    GL_DYNAMIC_DRAW,
    GL_FALSE,
    GL_FLOAT,
    GL_FRAGMENT_SHADER,
    GL_FRAMEBUFFER,
    GL_FRAMEBUFFER_COMPLETE,
    GL_LEQUAL,
    GL_LESS,
    GL_LINEAR,
    GL_NEAREST,
    GL_LINES,
    GL_LINE_STRIP,
    GL_LINK_STATUS,
    GL_ONE,
    GL_ONE_MINUS_SRC_ALPHA,
    GL_POINTS,
    GL_PROGRAM_POINT_SIZE,
    GL_RENDERBUFFER,
    GL_REPEAT,
    GL_RGBA,
    GL_RGBA16F,
    GL_SRC_ALPHA,
    GL_STATIC_DRAW,
    GL_TEXTURE0,
    GL_TEXTURE1,
    GL_TEXTURE_2D,
    GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_MIN_FILTER,
    GL_TEXTURE_WRAP_S,
    GL_TEXTURE_WRAP_T,
    GL_TRIANGLE_STRIP,
    GL_TRIANGLES,
    GL_TRUE,
    GL_UNSIGNED_BYTE,
    GL_VERTEX_SHADER,
    GL_DRAW_FRAMEBUFFER_BINDING,
    glActiveTexture,
    glGetIntegerv,
    glAttachShader,
    glBindBuffer,
    glBindFramebuffer,
    glBindRenderbuffer,
    glBindTexture,
    glBindVertexArray,
    glBlendFunc,
    glBufferData,
    glBufferSubData,
    glCheckFramebufferStatus,
    glClear,
    glClearColor,
    glCompileShader,
    glCreateProgram,
    glCreateShader,
    glDeleteFramebuffers,
    glDeleteRenderbuffers,
    glDeleteTextures,
    glDepthFunc,
    glDepthMask,
    glDisable,
    glDrawArrays,
    glDrawArraysInstanced,
    glEnable,
    glEnableVertexAttribArray,
    glFramebufferRenderbuffer,
    glFramebufferTexture2D,
    glGenBuffers,
    glGenFramebuffers,
    glGenRenderbuffers,
    glGenTextures,
    glGenVertexArrays,
    glGetProgramInfoLog,
    glGetProgramiv,
    glGetShaderInfoLog,
    glGetShaderiv,
    glGetUniformLocation,
    glLineWidth,
    glLinkProgram,
    glRenderbufferStorage,
    glShaderSource,
    glTexImage2D,
    glTexParameteri,
    glTexSubImage2D,
    glUniform1f,
    glUniform1i,
    glUniform2f,
    glUniform3f,
    glUniform4f,
    glUniformMatrix4fv,
    glUseProgram,
    glVertexAttribDivisor,
    glVertexAttribPointer,
    glViewport,
)

from soundorbit.audio import AudioAnalysis, BANDS
from soundorbit.math3d import look_at, mul, perspective, rotation_y, scale, translation
from soundorbit.quality import QualityProfile, detect_quality


# ---------------------------------------------------------------------------
# Shaders
# ---------------------------------------------------------------------------

BAR_VERT = """
#version 330 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec4 aInstance; // x,z position, height, band index

uniform mat4 uMVP;
uniform mat4 uModel;
uniform float uTime;
uniform float uBass;

out vec3 vNormal;
out vec3 vWorldPos;
out float vHeight;
out float vBand;

void main() {
    float h = max(aInstance.z, 0.02);
    vec3 pos = aPos;
    pos.y = (aPos.y + 0.5) * h; // base at y=0
    pos.x += aInstance.x;
    pos.z += aInstance.y;

    // 軽い波打ち
    pos.y += sin(uTime * 2.0 + aInstance.w * 0.4) * 0.02 * uBass;

    vec4 world = uModel * vec4(pos, 1.0);
    vWorldPos = world.xyz;
    vNormal = mat3(uModel) * aNormal;
    vHeight = h;
    vBand = aInstance.w;
    gl_Position = uMVP * vec4(pos, 1.0);
}
"""

# Shared GLSL (Linux + Windows). PS1 look = low-res quantize / UV snap in post,
# NOT Sega Saturn mesh transparency.
_GLSL_COMMON = """
// amt>0 boost chroma, amt<0 desaturate (PS1-muted)
vec3 boostSat(vec3 c, float amt) {
    float l = dot(c, vec3(0.299, 0.587, 0.114));
    return clamp(mix(vec3(l), c, 1.0 + amt), 0.0, 1.35);
}
// Hard alpha cut (no stipple mesh) — PS1 often just on/off or flat blend
float ps1Alpha(float a) {
    if (a < 0.04) discard;
    // slight posterize of alpha channel for chunky edges
    return floor(clamp(a, 0.0, 1.0) * 4.0 + 0.5) / 4.0;
}
"""

BAR_FRAG = """
#version 330 core
in vec3 vNormal;
in vec3 vWorldPos;
in float vHeight;
in float vBand;

uniform vec3 uCamPos;
uniform float uBands;
uniform float uBeat;
uniform float uTime;

out vec4 FragColor;

""" + _GLSL_COMMON + """
vec3 palette(float t) {
    // PS1: ややくすんだシアン → マゼンタ → アンバー
    vec3 a = vec3(0.18, 0.42, 0.72);
    vec3 b = vec3(0.72, 0.22, 0.68);
    vec3 c = vec3(0.82, 0.48, 0.22);
    float s = smoothstep(0.0, 1.0, t);
    vec3 col = mix(a, b, smoothstep(0.0, 0.55, s));
    col = mix(col, c, smoothstep(0.45, 1.0, s));
    return boostSat(col, -0.08); // 彩度を少し落とす
}

void main() {
    vec3 N = normalize(vNormal);
    vec3 V = normalize(uCamPos - vWorldPos);
    vec3 L = normalize(vec3(0.4, 1.0, 0.3));
    float diff = max(dot(N, L), 0.0);
    float rim = pow(1.0 - max(dot(N, V), 0.0), 3.0);
    float t = vBand / max(uBands - 1.0, 1.0);
    vec3 base = palette(t);

    float hNorm = clamp(vHeight / 4.5, 0.0, 1.0);
    float body = 0.28 + diff * 0.55 + hNorm * 0.18 + uBeat * 0.06;
    vec3 col = base * body;
    col += base * rim * 0.22;
    float top = smoothstep(0.78, 1.0, vWorldPos.y / max(vHeight, 0.01));
    col += base * top * 0.14;
    col = boostSat(col, -0.06);

    float peak = max(col.r, max(col.g, col.b));
    if (peak > 0.95) {
        col *= 0.95 / peak;
    }

    float alpha = ps1Alpha(0.90 + rim * 0.06);
    FragColor = vec4(col, alpha);
}
"""

ORB_VERT = """
#version 330 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNormal;

uniform mat4 uMVP;
uniform mat4 uModel;
uniform float uPulse;
uniform float uTime;

out vec3 vNormal;
out vec3 vWorldPos;
out vec3 vLocal;

void main() {
    float noise = sin(aPos.x * 6.0 + uTime * 3.0) * cos(aPos.y * 5.0 - uTime * 2.5)
                * sin(aPos.z * 7.0 + uTime) * 0.08 * uPulse;
    vec3 pos = aPos * (1.0 + uPulse * 0.35 + noise);
    vec4 world = uModel * vec4(pos, 1.0);
    vWorldPos = world.xyz;
    vNormal = normalize(mat3(uModel) * aNormal);
    vLocal = aPos;
    gl_Position = uMVP * vec4(pos, 1.0);
}
"""

ORB_FRAG = """
#version 330 core
in vec3 vNormal;
in vec3 vWorldPos;
in vec3 vLocal;

uniform vec3 uCamPos;
uniform float uBass;
uniform float uMid;
uniform float uTreble;
uniform float uBeat;
uniform float uTime;

out vec4 FragColor;

""" + _GLSL_COMMON + """
void main() {
    vec3 N = normalize(vNormal);
    vec3 V = normalize(uCamPos - vWorldPos);
    float fres = pow(1.0 - max(dot(N, V), 0.0), 2.2);
    vec3 c1 = vec3(0.05, 0.75, 1.0);
    vec3 c2 = vec3(1.00, 0.12, 0.92);
    vec3 c3 = vec3(1.00, 0.62, 0.05);
    vec3 base = c1 * uBass + c2 * uMid + c3 * uTreble;
    base = max(base, vec3(0.05, 0.10, 0.22));
    float bands = abs(sin(vLocal.y * 12.0 + uTime * 4.0 + uBeat * 3.0));
    base += vec3(0.15, 0.70, 1.0) * bands * 0.18 * uTreble;
    vec3 col = base * (0.35 + fres * 1.2) + base * fres * 0.45 * (0.4 + uBeat);
    col = boostSat(col, -0.08);
    float a = ps1Alpha(0.92);
    FragColor = vec4(col, a);
}
"""

# Thick ribbon rings (Windows reverse-port) — TRIANGLE_STRIP, always visible
RING_VERT = """
#version 330 core
layout(location = 0) in vec3 aPos;   // world x,y,z on vertical band
layout(location = 1) in float aT;    // 0..1 around ring
uniform mat4 uMVP;
uniform float uTime;
uniform float uEnergy;
uniform float uPhase;
out float vAlpha;
out float vT;
void main() {
    vT = aT;
    float wave = sin(aT * 40.0 - uTime * 6.0 + uPhase) * 0.18 * uEnergy;
    vec3 pos = aPos + vec3(0.0, wave, 0.0);
    vAlpha = 0.55 + uEnergy * 0.45;
    gl_Position = uMVP * vec4(pos, 1.0);
}
"""

RING_FRAG = """
#version 330 core
in float vAlpha;
in float vT;
uniform float uHue;
out vec4 FragColor;
""" + _GLSL_COMMON + """
vec3 hsv2rgb(vec3 c) {
    vec3 p = abs(fract(c.xxx + vec3(0.0, 2.0/3.0, 1.0/3.0)) * 6.0 - 3.0);
    return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
}
void main() {
    float edge = smoothstep(0.0, 0.15, vT) * smoothstep(1.0, 0.85, vT);
    float dash = 0.65 + 0.35 * smoothstep(0.2, 0.5, abs(sin(vT * 3.14159265 * 48.0)));
    // high S for punchy ribbon hues
    vec3 col = hsv2rgb(vec3(fract(uHue + vT * 0.15), 0.72, 0.92));
    col = boostSat(col, -0.10);
    float a = vAlpha * dash * (0.7 + 0.3 * edge);
    a = ps1Alpha(a);
    FragColor = vec4(col, a);
}
"""

PART_VERT = """
#version 330 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec4 aData; // life, size, hue, unused

uniform mat4 uVP;
uniform float uTime;

out float vLife;
out float vHue;

void main() {
    vLife = aData.x;
    vHue = aData.z;
    gl_Position = uVP * vec4(aPos, 1.0);
    gl_PointSize = aData.y * (0.5 + vLife) * (180.0 / max(gl_Position.w, 0.1));
}
"""

PART_FRAG = """
#version 330 core
in float vLife;
in float vHue;
out vec4 FragColor;

""" + _GLSL_COMMON + """
vec3 hsv2rgb(vec3 c) {
    vec3 p = abs(fract(c.xxx + vec3(0.0, 2.0/3.0, 1.0/3.0)) * 6.0 - 3.0);
    return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
}

void main() {
    vec2 p = gl_PointCoord * 2.0 - 1.0;
    float d = dot(p, p);
    if (d > 1.0) discard;
    float soft = exp(-d * 3.2);
    vec3 col = hsv2rgb(vec3(fract(vHue), 0.70, 0.92));
    col = boostSat(col, -0.08);
    // Soft edges → Saturn mesh dots (not smooth alpha fade)
    float a = ps1Alpha(soft * vLife * 0.9);
    FragColor = vec4(col, a);
}
"""

GRID_VERT = """
#version 330 core
layout(location = 0) in vec3 aPos;
uniform mat4 uMVP;
uniform float uBass;
out float vDist;
void main() {
    vec3 pos = aPos;
    pos.y += sin(length(aPos.xz) * 1.5 - uBass * 8.0) * uBass * 0.15;
    vDist = length(aPos.xz);
    gl_Position = uMVP * vec4(pos, 1.0);
}
"""

GRID_FRAG = """
#version 330 core
in float vDist;
uniform float uEnergy;
uniform float uBeat;
out vec4 FragColor;
""" + _GLSL_COMMON + """
void main() {
    float fade = 1.0 - smoothstep(1.5, 13.0, vDist);
    // 中心だけシアン、外側はほぼ消える
    vec3 blue = vec3(0.14, 0.32, 0.52);
    vec3 cyan = vec3(0.18, 0.48, 0.58);
    vec3 col = mix(blue, cyan, clamp(uEnergy * 0.45 + uBeat * 0.20, 0.0, 1.0));
    col = boostSat(col, -0.10);
    float core = 1.0 - smoothstep(0.0, 4.5, vDist);
    float a = (0.10 + uEnergy * 0.18 + uBeat * 0.08 + core * 0.22) * fade * (0.35 + core * 0.65);
    col *= 0.55 + core * 0.55 + uEnergy * 0.15;
    a = ps1Alpha(clamp(a, 0.0, 0.85));
    FragColor = vec4(col, a);
}
"""

BG_VERT = """
#version 330 core
layout(location = 0) in vec2 aPos;
out vec2 vUv;
void main() {
    vUv = aPos * 0.5 + 0.5;
    gl_Position = vec4(aPos, 0.999, 1.0);
}
"""

BG_FRAG = """
#version 330 core
in vec2 vUv;
uniform float uTime;
uniform float uEnergy;
uniform float uBeat;
out vec4 FragColor;
""" + _GLSL_COMMON + """
void main() {
    vec2 p = vUv - 0.5;
    float r = length(p);
    // 外周はほぼ黒、中心付近だけ青み
    vec3 black = vec3(0.004, 0.005, 0.010);
    vec3 mid = vec3(0.012, 0.018, 0.040);
    vec3 coreBlue = vec3(0.04, 0.10, 0.22);
    float coreMask = exp(-r * r * 14.0);           // 中心に強く寄せる
    float midMask = exp(-r * r * 5.5);
    vec3 col = black;
    col = mix(col, mid, midMask * 0.85);
    col = mix(col, coreBlue, coreMask * (0.55 + uEnergy * 0.25));

    // 中央水平の淡い発光（幅を狭く）
    float yBand = exp(-pow(p.y / (0.055 + uEnergy * 0.025 + uBeat * 0.02), 2.0));
    float xFall = 1.0 - smoothstep(0.02, 0.42, abs(p.x));
    vec3 hCol = vec3(0.12, 0.32, 0.55);
    float pulse = 0.06 + uEnergy * 0.14 + uBeat * 0.10;
    float wave = 0.90 + 0.10 * sin(p.x * 10.0 - uTime * 1.4 + uBeat * 2.0);
    col += hCol * yBand * xFall * pulse * wave * coreMask;

    col += vec3(0.08, 0.22, 0.40) * coreMask * (0.04 + uEnergy * 0.10 + uBeat * 0.06);
    col += vec3(0.25, 0.06, 0.28) * uBeat * 0.03 * coreMask;
    // 外側をさらに黒へ
    col *= mix(0.15, 1.0, midMask);
    col = boostSat(col, -0.12);

    FragColor = vec4(col, 1.0);
}
"""

# 緑の外枠 — 太いリボン（Windows 逆移植）
FRAME_VERT = """
#version 330 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in float aT;
uniform mat4 uMVP;
uniform float uEnergy;
uniform float uTime;
uniform float uPhase;
out float vT;
out float vPulse;
void main() {
    vT = aT;
    float wave = sin(aT * 48.0 - uTime * 3.5 + uPhase) * 0.02 * (0.5 + uEnergy);
    vec3 pos = aPos + vec3(0.0, wave, 0.0);
    vPulse = 0.8 + 0.2 * sin(uTime * 4.0 + aT * 20.0);
    gl_Position = uMVP * vec4(pos, 1.0);
}
"""

FRAME_FRAG = """
#version 330 core
in float vT;
in float vPulse;
uniform vec3 uColor;
uniform float uAlpha;
uniform float uBeat;
out vec4 FragColor;
""" + _GLSL_COMMON + """
void main() {
    float dash = 0.6 + 0.4 * smoothstep(0.12, 0.4, abs(sin(vT * 3.14159265 * 40.0)));
    float a = clamp(uAlpha * vPulse * dash * (0.9 + uBeat * 0.25), 0.0, 1.0);
    vec3 col = boostSat(uColor, -0.05) * (0.85 + vPulse * 0.35 + uBeat * 0.15);
    a = ps1Alpha(a);
    FragColor = vec4(col, a);
}
"""

# 円周上テキスト帯
LABEL_VERT = """
#version 330 core
layout(location = 0) in vec3 aPos;  // xyz
layout(location = 1) in vec2 aUv;
uniform mat4 uMVP;
uniform float uYOffset;
out vec2 vUv;
void main() {
    vUv = aUv;
    vec3 pos = aPos;
    pos.y += uYOffset;
    gl_Position = uMVP * vec4(pos, 1.0);
}
"""

LABEL_FRAG = """
#version 330 core
// Premultiplied RGBA — blend with ONE, ONE_MINUS_SRC_ALPHA
// PS1: hard alpha cut, no mesh stipple
in vec2 vUv;
uniform sampler2D uTex;
uniform float uAlpha;
uniform float uBeat;
uniform float uEnergy;
out vec4 FragColor;
""" + _GLSL_COMMON + """
void main() {
    vec4 t = texture(uTex, vUv);
    float vFade = smoothstep(0.0, 0.12, vUv.y) * smoothstep(1.0, 0.88, vUv.y);
    float a = ps1Alpha(t.a * uAlpha * vFade);
    float glow = 0.90 + uEnergy * 0.18 + uBeat * 0.22;
    vec3 rgb = boostSat(t.rgb, -0.06) * glow * uAlpha * vFade;
    // premultiplied
    FragColor = vec4(rgb, a);
}
"""

# フルスクリーン post: 残像合成 + RGB ずらし
POST_VERT = """
#version 330 core
layout(location = 0) in vec2 aPos;
out vec2 vUv;
void main() {
    vUv = aPos * 0.5 + 0.5;
    gl_Position = vec4(aPos, 0.0, 1.0);
}
"""

# 残像バッファ更新: 画面全体の強いフォスファー持続
TRAIL_FRAG = """
#version 330 core
in vec2 vUv;
uniform sampler2D uScene;
uniform sampler2D uPrev;
uniform float uDecay;
uniform float uSceneGain;
uniform float uZoom;   // 1.0 付近。>1 で過去フレームがわずかに拡大
out vec4 FragColor;
void main() {
    vec2 centered = vUv - 0.5;
    vec2 uvPrev = centered * uZoom + 0.5;
    uvPrev = clamp(uvPrev, 0.001, 0.999);

    vec3 scene = texture(uScene, vUv).rgb;
    vec3 prev  = texture(uPrev, uvPrev).rgb;

    // 画面全体を軽く蓄積（視認性優先）
    float lum = dot(scene, vec3(0.299, 0.587, 0.114));
    float hiBoost = 1.0 + smoothstep(0.20, 0.80, lum) * 0.25;
    vec3 col = prev * uDecay + scene * uSceneGain * hiBoost;
    // 蓄積しすぎないよう少し強めに圧縮
    col = col / (1.0 + col * 0.45);
    FragColor = vec4(clamp(col, 0.0, 1.2), 1.0);
}
"""

# 最終出力: 残像 + RGB ずらし + CRT（バレル歪み / スキャンライン / 四隅ビネット）
POST_FRAG = """
#version 330 core
in vec2 vUv;
uniform sampler2D uScene;
uniform sampler2D uTrail;
uniform float uAberr;      // RGB ずらし量（UV 単位）
uniform float uTrailMix;   // 残像の乗せ量
uniform float uEnergy;
uniform float uBeat;
uniform float uTime;
uniform float uExposure;   // 全体露出（1.0 前後）
uniform float uBarrel;     // ブラウン管バレル歪み（0=なし）
uniform float uScanline;   // スキャンライン強度 0..1
uniform float uVignette;   // 四隅ビネット強度 0..1
uniform vec2  uResolution; // 出力解像度（スキャンライン密度用）
uniform vec2  uInternal;   // 内部描画解像度（ジャギ用 UV 量子化）
out vec4 FragColor;

// ブラウン管の画面湾曲: 中心から外側へ UV を押し出し、四隅は枠外→透過
vec2 crtBarrel(vec2 uv, float amount) {
    if (amount < 1e-5) {
        return uv;
    }
    vec2 cc = uv * 2.0 - 1.0;
    // わずかに横長を補正（管面の曲率っぽく）
    cc.x *= 1.0 + abs(cc.y) * amount * 0.08;
    cc.y *= 1.0 + abs(cc.x) * amount * 0.08;
    float r2 = dot(cc, cc);
    // 2 次 + 弱い 4 次で四隅を強く曲げる
    float f = 1.0 + r2 * (amount + amount * 0.35 * r2);
    cc *= f;
    return cc * 0.5 + 0.5;
}

vec3 sampleSplit(sampler2D tex, vec2 uv, float amount) {
    if (amount < 1e-6) {
        return texture(tex, uv).rgb;
    }
    vec2 dir = uv - 0.5;
    float dist = length(dir);
    vec2 radial = (dist > 1e-5) ? normalize(dir) : vec2(1.0, 0.0);
    vec2 shift = radial * amount * (0.35 + dist * 1.4)
               + vec2(amount * 1.15, 0.0);

    float r = texture(tex, clamp(uv + shift, 0.0, 1.0)).r;
    float g = texture(tex, clamp(uv, 0.0, 1.0)).g;
    float b = texture(tex, clamp(uv - shift, 0.0, 1.0)).b;
    return vec3(r, g, b);
}

vec3 tonemap(vec3 x) {
    // 簡易 ACES 風 + ソフトニー
    x = max(x, 0.0);
    float a = 2.51;
    float b = 0.03;
    float c = 2.43;
    float d = 0.59;
    float e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

// PS1-ish: coarse RGB posterization (chunky gradients)
vec3 quantizePS1(vec3 c) {
    c = clamp(c, 0.0, 1.0);
    // ~5/5/5 style banding (PlayStation VRAM feel)
    float r = floor(c.r * 5.0 + 0.5) / 5.0;
    float g = floor(c.g * 5.0 + 0.5) / 5.0;
    float b = floor(c.b * 5.0 + 0.5) / 5.0;
    return vec3(r, g, b);
}

vec3 boostSat(vec3 c, float amt) {
    float l = dot(c, vec3(0.299, 0.587, 0.114));
    return clamp(mix(vec3(l), c, 1.0 + amt), 0.0, 1.0);
}

// Bayer 2x2 ordered dither — for banding/jaggies, NOT mesh transparency
float bayer2(vec2 p) {
    int x = int(mod(floor(p.x), 2.0));
    int y = int(mod(floor(p.y), 2.0));
    int i = x + y * 2;
    // 0,2,3,1 → 0..1
    float m[4];
    m[0]=0.0; m[1]=0.5; m[2]=0.75; m[3]=0.25;
    return m[i];
}

void main() {
    // 1) ブラウン管の画面歪曲（四隅が外側へ曲がる）
    float barrel = uBarrel * (1.0 + uEnergy * 0.04 + uBeat * 0.03);
    vec2 uv = crtBarrel(vUv, barrel);

    // ベゼルは薄く（四隅の黒領域を小さく）
    vec2 edge = smoothstep(vec2(-0.008), vec2(0.018), uv)
              * smoothstep(vec2(-0.008), vec2(0.018), 1.0 - uv);
    float inScreen = edge.x * edge.y;
    if (inScreen < 1e-4) {
        FragColor = vec4(0.0);
        return;
    }

    vec2 ires = max(uInternal, vec2(64.0, 48.0));
    vec2 uvS = clamp(uv, 0.0, 1.0);
    uvS = (floor(uvS * ires) + 0.5) / ires;

    // 色収差: 微妙に（端ほどわずかに強め）
    float edgeDist = length(uvS - 0.5);
    float aberr = max(uAberr, 0.00055);
    aberr *= (1.0 + uEnergy * 0.12 + uBeat * 0.10);
    aberr *= 0.98 + 0.02 * sin(uTime * 4.0);
    aberr *= 1.0 + edgeDist * 0.55;
    aberr = max(aberr, 0.75 / ires.x);

    vec3 scene = sampleSplit(uScene, uvS, aberr);
    vec3 trail = sampleSplit(uTrail, uvS, aberr * 1.08);

    // 残像（フォスファー）を少し強めに
    trail *= vec3(0.78, 0.94, 1.02);
    float mixAmt = clamp(uTrailMix, 0.0, 1.0);
    mixAmt *= 0.92 + uEnergy * 0.08 + uBeat * 0.06;
    vec3 col = mix(scene, trail, mixAmt * 0.52);
    vec3 ghost = max(trail - scene * 0.48, 0.0);
    col += ghost * mixAmt * 0.36;
    col = mix(col, max(col, scene), 0.38);

    col *= uExposure;

    // スキャンライン
    float py = gl_FragCoord.y;
    float slot = mod(floor(py), 4.0);
    float mask = 1.0 - step(2.0, slot);
    float scanEdge = abs(mod(py, 4.0) - 1.5);
    float softMask = mix(mask, mask * 0.85, smoothstep(0.5, 1.5, scanEdge));
    float s = clamp(uScanline, 0.0, 1.0);
    float darkKeep = mix(1.0, 0.04, s);
    col *= mix(1.0, darkKeep, softMask);
    float roll = 0.97 + 0.03 * sin(py * 0.35 - uTime * 1.6 + uBeat * 2.0);
    col *= roll;
    col *= mix(1.0, 0.90, step(1.0, mod(floor(py), 2.0)) * s * 0.45);

    // 四隅ビネット: より外側だけ（＝四隅を小さく）
    vec2 vc = uvS * 2.0 - 1.0;
    float soft = smoothstep(0.92, 1.22, length(vc));
    float corner = pow(max(abs(vc.x), abs(vc.y)), 4.0);
    corner = smoothstep(0.88, 1.08, corner);
    float vigShape = clamp(soft * 0.40 + corner * 0.60, 0.0, 1.0);
    float vigA = 1.0 - uVignette * vigShape * 0.72;
    float vigRgb = 1.0 - uVignette * vigShape * 0.10;
    col *= vigRgb;

    float frameA = smoothstep(0.0, 0.08, inScreen);
    float alpha = clamp(frameA * vigA, 0.0, 1.0);

    col *= mix(vec3(1.0), vec3(0.94, 0.98, 0.96), edgeDist * 0.06 * uVignette);

    col = tonemap(col);
    // PS1: muted chroma + dither-before-quantize (jagged banding, not mesh)
    col = boostSat(col, -0.14);
    float dith = (bayer2(gl_FragCoord.xy) - 0.5) * (1.0 / 5.0);
    col = quantizePS1(col + dith);
    if (alpha < 0.03) {
        FragColor = vec4(0.0);
        return;
    }
    float outA = clamp(alpha, 0.0, 1.0);
    FragColor = vec4(col * outA, outA);
}
"""


def _compile_shader(src: str, stype) -> int:
    sh = glCreateShader(stype)
    glShaderSource(sh, src)
    glCompileShader(sh)
    if not glGetShaderiv(sh, GL_COMPILE_STATUS):
        log = glGetShaderInfoLog(sh)
        raise RuntimeError(f"Shader compile error: {log}")
    return sh


def _link_program(vs_src: str, fs_src: str) -> int:
    vs = _compile_shader(vs_src, GL_VERTEX_SHADER)
    fs = _compile_shader(fs_src, GL_FRAGMENT_SHADER)
    prog = glCreateProgram()
    glAttachShader(prog, vs)
    glAttachShader(prog, fs)
    glLinkProgram(prog)
    if not glGetProgramiv(prog, GL_LINK_STATUS):
        log = glGetProgramInfoLog(prog)
        raise RuntimeError(f"Program link error: {log}")
    return prog


def _unit_box() -> tuple[np.ndarray, np.ndarray]:
    """原点中心・辺長 1 の直方体（底面 y=-0.5）。"""
    # 8 corners used via faces
    faces = [
        # +Y
        ((-0.5, 0.5, -0.5), (0.5, 0.5, -0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5), (0, 1, 0)),
        # -Y
        ((-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, -0.5, -0.5), (-0.5, -0.5, -0.5), (0, -1, 0)),
        # +Z
        ((-0.5, -0.5, 0.5), (-0.5, 0.5, 0.5), (0.5, 0.5, 0.5), (0.5, -0.5, 0.5), (0, 0, 1)),
        # -Z
        ((0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5), (-0.5, -0.5, -0.5), (0, 0, -1)),
        # +X
        ((0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (0.5, 0.5, -0.5), (0.5, -0.5, -0.5), (1, 0, 0)),
        # -X
        ((-0.5, -0.5, -0.5), (-0.5, 0.5, -0.5), (-0.5, 0.5, 0.5), (-0.5, -0.5, 0.5), (-1, 0, 0)),
    ]
    verts = []
    for a, b, c, d, n in faces:
        for p in (a, b, c, a, c, d):
            verts.extend([*p, *n])
    data = np.array(verts, dtype=np.float32)
    return data, data  # noqa — single interleaved buffer


def _uv_sphere(stacks: int = 24, slices: int = 32) -> np.ndarray:
    verts = []
    for i in range(stacks):
        v0 = i / stacks
        v1 = (i + 1) / stacks
        theta0 = v0 * math.pi
        theta1 = v1 * math.pi
        for j in range(slices):
            u0 = j / slices
            u1 = (j + 1) / slices
            phi0 = u0 * 2 * math.pi
            phi1 = u1 * 2 * math.pi

            def sp(theta, phi):
                x = math.sin(theta) * math.cos(phi)
                y = math.cos(theta)
                z = math.sin(theta) * math.sin(phi)
                return (x, y, z)

            p00, p10, p01, p11 = sp(theta0, phi0), sp(theta1, phi0), sp(theta0, phi1), sp(theta1, phi1)
            for p in (p00, p10, p11, p00, p11, p01):
                verts.extend([*p, *p])  # pos + normal
    return np.array(verts, dtype=np.float32)


def _ring_line(segments: int = 256, radius: float = 3.5) -> np.ndarray:
    """Legacy thin ring (kept for reference). Prefer _ring_ribbon."""
    verts = []
    for i in range(segments + 1):
        t = i / segments
        ang = t * 2 * math.pi
        x = math.cos(ang) * radius
        z = math.sin(ang) * radius
        verts.extend([x, z, t])
    return np.array(verts, dtype=np.float32)


def _ring_ribbon(segments: int = 192, radius: float = 3.5, half_h: float = 0.10) -> np.ndarray:
    """
    Vertical ribbon around Y — TRIANGLE_STRIP.
    Vertex: pos.xyz + t  (stride 16 bytes).
    """
    verts: list[float] = []
    for i in range(segments + 1):
        t = i / segments
        ang = t * 2 * math.pi
        c, s = math.cos(ang), math.sin(ang)
        x, z = c * radius, s * radius
        verts.extend([x, -half_h, z, t, x, half_h, z, t])
    return np.array(verts, dtype=np.float32)


def _grid_lines(half: int = 16, spacing: float = 0.75) -> np.ndarray:
    verts = []
    extent = half * spacing
    for i in range(-half, half + 1):
        d = i * spacing
        verts.extend([-extent, 0.0, d, extent, 0.0, d])
        verts.extend([d, 0.0, -extent, d, 0.0, extent])
    return np.array(verts, dtype=np.float32)


def _frame_ticks_ribbon(
    segments: int, radius: float, tick_len: float = 0.14, half_h: float = 0.035
) -> np.ndarray:
    """Radial ticks as quads (TRIANGLES). Vertex: pos.xyz + t."""
    verts: list[float] = []
    for i in range(segments):
        t = i / segments
        ang = t * math.pi * 2.0
        c, s = math.cos(ang), math.sin(ang)
        x0, z0 = c * radius, s * radius
        x1, z1 = c * (radius + tick_len), s * (radius + tick_len)
        y0, y1 = -half_h, half_h
        verts.extend([x0, y0, z0, t, x1, y0, z1, t, x1, y1, z1, t])
        verts.extend([x0, y0, z0, t, x1, y1, z1, t, x0, y1, z0, t])
    return np.array(verts, dtype=np.float32)


def _premultiply_rgba(rgba: np.ndarray) -> np.ndarray:
    """Straight RGBA → premultiplied (avoids dark fringes on transparent text)."""
    out = np.ascontiguousarray(rgba, dtype=np.uint8).copy()
    a = out[:, :, 3:4].astype(np.float32) * (1.0 / 255.0)
    rgb = out[:, :, :3].astype(np.float32)
    out[:, :, :3] = np.clip(rgb * a + 0.5, 0, 255).astype(np.uint8)
    return out


def _label_ring_band(
    segments: int = 160,
    radius: float = 4.45,
    half_h: float = 0.14,
) -> np.ndarray:
    """
    円周テキスト用の帯メッシュ。
    頂点: pos.xyz + uv (triangle strip, 2*(segments+1) verts)
    外側を向く薄い帯。文字は上向き（ベースラインが下側）。
    """
    verts = []
    for i in range(segments + 1):
        t = i / segments
        ang = t * math.pi * 2.0
        c, s = math.cos(ang), math.sin(ang)
        x, z = c * radius, s * radius
        # 下辺 = テクスチャ下 (v=0) → 文字の足元
        verts.extend([x, -half_h, z, t, 0.0])
        # 上辺 = テクスチャ上 (v=1) → 文字の頭
        verts.extend([x, half_h, z, t, 1.0])
    return np.array(verts, dtype=np.float32)


def _make_audio_label_texture(
    text: str = "AUDIO VISUALIZER",
    width: int = 2048,
    height: int = 160,
    repeats: int = 2,
) -> tuple[np.ndarray, int, int]:
    """
    緑ネオン風の周回ラベルテクスチャ (RGBA uint8, 行は下から上ではない → GL は flip)。
    Cairo があれば使用、なければ簡易ドットフォント風。
    """
    phrase = f"  {text}  · "
    full = phrase * repeats

    try:
        import cairo  # type: ignore

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surface)
        ctx.set_operator(cairo.OPERATOR_CLEAR)
        ctx.paint()
        ctx.set_operator(cairo.OPERATOR_OVER)

        # わずかなグロー下地
        ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        # 帯いっぱいに大きく（以前 0.55 → 0.78）
        font_size = height * 0.78
        ctx.set_font_size(font_size)
        xb, yb, tw, th, dx, dy = ctx.text_extents(full)
        # 横幅に収まるよう調整（少し余裕を残す）
        if tw > width * 0.98:
            font_size *= (width * 0.98) / max(tw, 1.0)
            ctx.set_font_size(font_size)
            xb, yb, tw, th, dx, dy = ctx.text_extents(full)

        x = (width - tw) * 0.5 - xb
        y = height * 0.5 - (yb + th * 0.5)

        # soft glow layers
        for blur_a, grow in ((0.12, 3.0), (0.22, 1.5), (0.55, 0.0)):
            ctx.set_source_rgba(0.15, 1.0, 0.35, blur_a)
            ctx.move_to(x, y + grow * 0.15)
            ctx.set_font_size(font_size + grow)
            ctx.show_text(full)
            ctx.set_font_size(font_size)

        ctx.set_source_rgba(0.55, 1.0, 0.65, 1.0)
        ctx.move_to(x, y)
        ctx.show_text(full)

        buf = surface.get_data()
        img = np.ndarray(shape=(height, width, 4), dtype=np.uint8, buffer=buf).copy()
        # Cairo ARGB32 little-endian → BGRA 並び。RGBA に並べ替え
        b, g, r, a = img[:, :, 0], img[:, :, 1], img[:, :, 2], img[:, :, 3]
        rgba = np.stack([r, g, b, a], axis=-1)
        # OpenGL は下原点なので縦反転
        rgba = np.flipud(rgba)
        return _premultiply_rgba(np.ascontiguousarray(rgba)), width, height
    except Exception:
        # フォールバック: 透過背景 + 緑ブロック文字（ベタ帯なし）
        rgba = np.zeros((height, width, 4), dtype=np.uint8)
        for i, ch in enumerate(full):
            if ch == " ":
                continue
            x0 = int((i / max(len(full), 1)) * width)
            x1 = min(width, x0 + max(3, width // 80))
            y0, y1 = height // 4, height * 3 // 4
            rgba[y0:y1, x0:x1, 0] = 80
            rgba[y0:y1, x0:x1, 1] = 255
            rgba[y0:y1, x0:x1, 2] = 100
            rgba[y0:y1, x0:x1, 3] = 220
        rgba = np.flipud(rgba)
        return _premultiply_rgba(np.ascontiguousarray(rgba)), width, height


def _cairo_rgba_text(
    lines: list[str],
    width: int = 320,
    height: int = 120,
    *,
    font_scale: float = 0.38,
    rgb: tuple[float, float, float] = (0.45, 1.0, 0.55),
) -> np.ndarray:
    """複数行テキストを緑ネオン風 RGBA 画像に（失敗時は空）。"""
    try:
        import cairo  # type: ignore

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surface)
        ctx.set_operator(cairo.OPERATOR_CLEAR)
        ctx.paint()
        ctx.set_operator(cairo.OPERATOR_OVER)
        ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)

        n = max(1, len(lines))
        font_size = height * font_scale / max(1.0, n * 0.55)
        ctx.set_font_size(font_size)

        # 行の高さ見積もり
        line_h = font_size * 1.15
        total_h = line_h * n
        y0 = (height - total_h) * 0.5 + font_size * 0.85

        for i, line in enumerate(lines):
            xb, yb, tw, th, _dx, _dy = ctx.text_extents(line)
            x = (width - tw) * 0.5 - xb
            y = y0 + i * line_h
            for blur_a, grow in ((0.15, 2.0), (0.35, 0.8), (0.9, 0.0)):
                ctx.set_source_rgba(rgb[0], rgb[1], rgb[2], blur_a)
                ctx.set_font_size(font_size + grow)
                ctx.move_to(x, y)
                ctx.show_text(line)
            ctx.set_font_size(font_size)

        buf = surface.get_data()
        img = np.ndarray(shape=(height, width, 4), dtype=np.uint8, buffer=buf).copy()
        b, g, r, a = img[:, :, 0], img[:, :, 1], img[:, :, 2], img[:, :, 3]
        rgba = np.stack([r, g, b, a], axis=-1)
        return _premultiply_rgba(np.ascontiguousarray(np.flipud(rgba)))
    except Exception:
        rgba = np.zeros((height, width, 4), dtype=np.uint8)
        rgba[height // 3 : height // 3 + 4, 20:-20, 1] = 200
        rgba[height // 3 : height // 3 + 4, 20:-20, 3] = 180
        return _premultiply_rgba(rgba)


def _unit_billboard_quad(w: float = 1.0, h: float = 0.38) -> np.ndarray:
    """原点中心の XY ビルボード四角（pos.xyz + uv）。TRIANGLES 6 頂点。"""
    hw, hh = w * 0.5, h * 0.5
    #  CCW, 上向き UV（v=1 が上）
    verts = [
        -hw, -hh, 0.0, 0.0, 0.0,
         hw, -hh, 0.0, 1.0, 0.0,
         hw,  hh, 0.0, 1.0, 1.0,
        -hw, -hh, 0.0, 0.0, 0.0,
         hw,  hh, 0.0, 1.0, 1.0,
        -hw,  hh, 0.0, 0.0, 1.0,
    ]
    return np.array(verts, dtype=np.float32)


# 表示する音声パラメータ（キー, ラベル, 値の取り方）
PARAM_SPECS: list[tuple[str, str]] = [
    ("bass", "BASS"),
    ("mid", "MID"),
    ("treble", "TREBLE"),
    ("rms", "RMS"),
    ("peak", "PEAK"),
    ("beat", "BEAT"),
]


class ParticleSystem:
    def __init__(self, count: int = 800) -> None:
        self.count = count
        self.pos = np.zeros((count, 3), dtype=np.float32)
        self.vel = np.zeros((count, 3), dtype=np.float32)
        self.life = np.zeros(count, dtype=np.float32)
        self.size = np.ones(count, dtype=np.float32) * 0.08
        self.hue = np.zeros(count, dtype=np.float32)
        self._cursor = 0

    def emit(self, n: int, energy: float, beat: float) -> None:
        n = max(0, min(n, self.count))
        for _ in range(n):
            i = self._cursor % self.count
            self._cursor += 1
            ang = np.random.random() * math.pi * 2
            elev = (np.random.random() - 0.3) * 0.8
            speed = 1.2 + energy * 3.5 + beat * 2.0
            self.pos[i] = [
                math.cos(ang) * 0.3,
                0.4 + np.random.random() * 0.4,
                math.sin(ang) * 0.3,
            ]
            self.vel[i] = [
                math.cos(ang) * speed * (0.6 + np.random.random()),
                elev * speed + 1.5 + energy * 2.0,
                math.sin(ang) * speed * (0.6 + np.random.random()),
            ]
            self.life[i] = 0.7 + np.random.random() * 0.5
            self.size[i] = 0.05 + np.random.random() * 0.12 + beat * 0.05
            self.hue[i] = (0.55 + energy * 0.25 + np.random.random() * 0.15) % 1.0

    def update(self, dt: float) -> None:
        alive = self.life > 0
        self.vel[alive, 1] -= 2.8 * dt
        self.pos[alive] += self.vel[alive] * dt
        self.life[alive] -= dt * 0.55
        self.life[self.life < 0] = 0

    def buffer_data(self) -> np.ndarray:
        # interleaved pos.xyz + life,size,hue,0
        out = np.zeros((self.count, 7), dtype=np.float32)
        out[:, 0:3] = self.pos
        out[:, 3] = self.life
        out[:, 4] = self.size
        out[:, 5] = self.hue
        return out


class VisualizerRenderer:
    """OpenGL 描画本体。realize 後に init_gl() を呼ぶ。"""

    def __init__(
        self,
        band_count: int = BANDS,
        quality: Optional[QualityProfile] = None,
    ) -> None:
        self.bands = band_count
        self.width = 1
        self.height = 1
        self._t0 = time.perf_counter()
        self._last_t = self._t0
        self._angle = 0.0
        self._auto_rotate = True
        # Mouse follow (normalized 0..1); smooth lerp each frame
        self._mouse_nx = 0.5
        self._mouse_ny = 0.5
        self._cam_h_bias = 0.0
        self._pointer_active = False
        self._ready = False
        self.quality = quality or detect_quality()
        self.particles = ParticleSystem(self.quality.particle_count)
        self._spectrum = np.zeros(band_count, dtype=np.float32)
        self._analysis = AudioAnalysis()

        # GL handles
        self.prog_bar = 0
        self.prog_orb = 0
        self.prog_ring = 0
        self.prog_part = 0
        self.prog_grid = 0
        self.prog_bg = 0
        self.prog_trail = 0
        self.prog_post = 0
        self.prog_frame = 0
        self.prog_label = 0

        # オフスクリーン（シーン + 残像 ping-pong）
        self._fbo_scene = 0
        self._tex_scene = 0
        self._rbo_depth = 0
        self._fbo_trail = [0, 0]
        self._tex_trail = [0, 0]
        self._trail_idx = 0
        self._fbo_w = 0
        self._fbo_h = 0
        self._gtk_fbo = 0  # Gtk.GLArea の描画先（0 は無効）
        # 緑外枠 + 周回ラベル（内側 AV は別角速度）
        self._frame_angle = 0.0
        self._label_angle = 0.0
        self._label_tex = 0
        self._outer_tex = 0
        self.frame_radius = 3.85  # バー(3.2)の外側
        self.label_radius = 4.45
        # 外側回転軸（緑枠と同じ _frame_angle）のスローガン
        self.outer_radius = 5.85
        self.outer_y = 0.62
        # パラメータ数値パネル（BASS/MID/…）
        self._param_texs: list[int] = []
        self._param_last: list[str] = [""] * len(PARAM_SPECS)
        self._param_timer = 0.0
        self._param_interval = 0.10  # 秒（GPU 負荷軽減でやや疎に）
        self.param_radius = 5.15
        # AUDIO VISUALIZER（~1.75）より上・中間よりさらに高め
        self.param_y = 3.15
        # ランタイムスロットル（ResourceGuardian が更新）
        self._runtime_throttle = 1.0
        self._runtime_trails_ok = True
        self._runtime_param_scale = 1.0
        # 内部解像度（低め固定 + ニアレストでジャギを強調）
        self.ps1_mode = True
        self.internal_w = 240
        self.internal_h = 180
        # PS1 時間方向のジャギ: 固定ステップ dt
        self._frame_i = 0
        self._locked_fps: float | None = None
        self._fixed_dt: float | None = None
        try:
            from soundorbit.frametime import fixed_dt, ps1_target_fps

            fps = float(ps1_target_fps(self.quality.target_fps))
            self._locked_fps = fps
            self._fixed_dt = fixed_dt(fps)
        except Exception:
            self._locked_fps = 18.0
            self._fixed_dt = 1.0 / 18.0
        self._apply_quality_params(self.quality)
        self._apply_internal_res_from_env()

    def _apply_internal_res_from_env(self) -> None:
        """SOUNDORBIT_INTERNAL=240x180 などで上書き。off でスケール方式に戻す。"""
        import os

        # 既定を低めにしてブロック感を出す
        raw = (os.environ.get("SOUNDORBIT_INTERNAL") or "240x180").strip().lower()
        if raw in ("off", "0", "false", "native"):
            self.ps1_mode = False
            return
        self.ps1_mode = True
        if "x" in raw:
            try:
                a, b = raw.split("x", 1)
                # 下限を下げてよりジャギにできるように
                self.internal_w = max(96, min(640, int(a)))
                self.internal_h = max(72, min(480, int(b)))
            except ValueError:
                self.internal_w, self.internal_h = 200, 150
        else:
            # PS1-ish chunky default
            self.internal_w, self.internal_h = 200, 150

    def _apply_quality_params(self, q: QualityProfile) -> None:
        self.trail_decay = q.trail_decay
        self.trail_scene_gain = q.trail_scene_gain
        self.trail_mix = q.trail_mix
        self.trail_zoom = 0.9975
        # 常に微妙な色収差（rgb_shift 品質なら少し強め）
        base_aberr = 0.0007
        self.aberration = max(base_aberr, float(q.aberration) if q.rgb_shift else base_aberr)
        self.enable_trails = True
        self.fbo_scale = float(np.clip(q.fbo_scale, 0.35, 1.0))
        self.particle_emit_scale = q.particle_emit_scale
        self.exposure = 0.90
        self._apply_crt_from_env()
        self._apply_trail_from_env()

    def _apply_trail_from_env(self) -> None:
        """残像の強さを環境変数で上書き。SOUNDORBIT_TRAIL=0 で無効。"""
        import os

        raw = (os.environ.get("SOUNDORBIT_TRAIL") or "1").strip().lower()
        if raw in ("0", "off", "false", "no"):
            self.enable_trails = False
            return

        def _f(name: str, default: float) -> float:
            v = os.environ.get(name)
            if v is None or not str(v).strip():
                return default
            try:
                return float(v)
            except ValueError:
                return default

        # 残像を少し強め（フォスファー感）
        self.trail_decay = float(np.clip(_f("SOUNDORBIT_TRAIL_DECAY", 0.86), 0.5, 0.97))
        self.trail_scene_gain = float(np.clip(_f("SOUNDORBIT_TRAIL_GAIN", 0.40), 0.1, 0.85))
        self.trail_mix = float(np.clip(_f("SOUNDORBIT_TRAIL_MIX", 0.52), 0.0, 0.95))

    def _apply_crt_from_env(self) -> None:
        """
        CRT 効果の既定値。SOUNDORBIT_CRT=0 で無効化。
        SOUNDORBIT_CRT_BARREL / SCANLINE / VIGNETTE で個別上書き可。
        """
        import os

        raw = (os.environ.get("SOUNDORBIT_CRT") or "1").strip().lower()
        if raw in ("0", "off", "false", "no"):
            self.crt_barrel = 0.0
            self.crt_scanline = 0.0
            self.crt_vignette = 0.0
            return

        def _f(name: str, default: float) -> float:
            v = os.environ.get(name)
            if v is None or not str(v).strip():
                return default
            try:
                return float(v)
            except ValueError:
                return default

        # 四隅を小さく: バレル弱め・ビネットはシェーダ側で外側寄り
        self.crt_barrel = float(np.clip(_f("SOUNDORBIT_CRT_BARREL", 0.08), 0.0, 0.45))
        self.crt_scanline = float(np.clip(_f("SOUNDORBIT_CRT_SCANLINE", 0.92), 0.0, 1.0))
        self.crt_vignette = float(np.clip(_f("SOUNDORBIT_CRT_VIGNETTE", 0.38), 0.0, 1.0))

    def apply_resource_state(
        self,
        *,
        throttle: float = 1.0,
        trails_allowed: bool = True,
        param_update_scale: float = 1.0,
    ) -> None:
        """メモリ/発熱監視からの動的スロットル。"""
        self._runtime_throttle = float(np.clip(throttle, 0.3, 1.0))
        self._runtime_trails_ok = bool(trails_allowed)
        self._runtime_param_scale = float(np.clip(param_update_scale, 0.25, 1.0))

    def purge_runtime(self) -> None:
        """
        メモリ圧迫時のランタイム解放。
        粒子リセット・残像 FBO クリア・数値キャッシュ破棄。
        """
        # 粒子を全死させる
        self.particles.life[:] = 0.0
        self.particles.pos[:] = 0.0
        self.particles.vel[:] = 0.0
        # 残像バッファを黒に戻す（蓄積テクスチャのゴミを捨てる）
        if self._ready and self._fbo_trail[0]:
            restore = self._current_draw_fbo()
            for i in range(2):
                if self._fbo_trail[i]:
                    glBindFramebuffer(GL_FRAMEBUFFER, self._fbo_trail[i])
                    glClearColor(0.0, 0.0, 0.0, 1.0)
                    glClear(GL_COLOR_BUFFER_BIT)
            if restore > 0:
                glBindFramebuffer(GL_FRAMEBUFFER, restore)
            else:
                glBindFramebuffer(GL_FRAMEBUFFER, 0)
        # パラメータ表示キャッシュを無効化 → 次回再描画
        self._param_last = [""] * len(PARAM_SPECS)
        self._param_timer = 0.0

    @property
    def target_fps(self) -> int:
        # PS1 lock applied in window; expose raw quality floor for UI
        try:
            from soundorbit.frametime import ps1_target_fps

            return int(ps1_target_fps(self.quality.target_fps))
        except Exception:
            return max(12, min(24, int(self.quality.target_fps)))

    @property
    def quality_label(self) -> str:
        q = self.quality
        return f"{q.label}（{q.key}）"

    def init_gl(self) -> None:
        q = self.quality
        self.prog_bar = _link_program(BAR_VERT, BAR_FRAG)
        self.prog_orb = _link_program(ORB_VERT, ORB_FRAG)
        self.prog_ring = _link_program(RING_VERT, RING_FRAG)
        self.prog_part = _link_program(PART_VERT, PART_FRAG)
        self.prog_grid = _link_program(GRID_VERT, GRID_FRAG)
        self.prog_bg = _link_program(BG_VERT, BG_FRAG)
        self.prog_trail = _link_program(POST_VERT, TRAIL_FRAG)
        self.prog_post = _link_program(POST_VERT, POST_FRAG)
        self.prog_frame = _link_program(FRAME_VERT, FRAME_FRAG)
        self.prog_label = _link_program(LABEL_VERT, LABEL_FRAG)

        # --- bar unit mesh ---
        bar_data, _ = _unit_box()
        # scale x/z thinner
        bar_data = bar_data.copy()
        bar_data[0::6] *= 0.22
        bar_data[2::6] *= 0.22

        self.bar_vao = glGenVertexArrays(1)
        self.bar_vbo = glGenBuffers(1)
        self.bar_instance_vbo = glGenBuffers(1)
        glBindVertexArray(self.bar_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.bar_vbo)
        glBufferData(GL_ARRAY_BUFFER, bar_data.nbytes, bar_data, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 24, None)
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 24, ctypes_offset(12))
        # instance buffer: x, z, height, band
        self._bar_instances = np.zeros((self.bands, 4), dtype=np.float32)
        radius = 3.2
        for i in range(self.bands):
            ang = (i / self.bands) * math.pi * 2.0 - math.pi * 0.5
            self._bar_instances[i, 0] = math.cos(ang) * radius
            self._bar_instances[i, 1] = math.sin(ang) * radius
            self._bar_instances[i, 2] = 0.05
            self._bar_instances[i, 3] = float(i)
        glBindBuffer(GL_ARRAY_BUFFER, self.bar_instance_vbo)
        glBufferData(
            GL_ARRAY_BUFFER,
            self._bar_instances.nbytes,
            self._bar_instances,
            GL_DYNAMIC_DRAW,
        )
        glEnableVertexAttribArray(2)
        glVertexAttribPointer(2, 4, GL_FLOAT, GL_FALSE, 16, None)
        glVertexAttribDivisor(2, 1)
        self.bar_vertex_count = bar_data.shape[0] // 6

        # --- orb ---
        orb = _uv_sphere(q.orb_stacks, q.orb_slices)
        self.orb_vao = glGenVertexArrays(1)
        self.orb_vbo = glGenBuffers(1)
        glBindVertexArray(self.orb_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.orb_vbo)
        glBufferData(GL_ARRAY_BUFFER, orb.nbytes, orb, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 24, None)
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 24, ctypes_offset(12))
        self.orb_vertex_count = orb.shape[0] // 6

        # --- energy ribbons (thick, Windows reverse-port) ---
        self.ring_vaos = []
        self.ring_vbos = []
        self.ring_counts = []
        segs_r = max(96, int(q.ring_segments))
        for ri, r in enumerate(q.ring_radii):
            half_h = 0.07 + ri * 0.015
            ring = _ring_ribbon(segs_r, float(r), half_h=half_h)
            vao = glGenVertexArrays(1)
            vbo = glGenBuffers(1)
            glBindVertexArray(vao)
            glBindBuffer(GL_ARRAY_BUFFER, vbo)
            glBufferData(GL_ARRAY_BUFFER, ring.nbytes, ring, GL_STATIC_DRAW)
            glEnableVertexAttribArray(0)
            glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 16, None)
            glEnableVertexAttribArray(1)
            glVertexAttribPointer(1, 1, GL_FLOAT, GL_FALSE, 16, ctypes_offset(12))
            self.ring_vaos.append(vao)
            self.ring_vbos.append(vbo)
            self.ring_counts.append(ring.shape[0] // 4)

        # --- particles ---
        self.part_vao = glGenVertexArrays(1)
        self.part_vbo = glGenBuffers(1)
        glBindVertexArray(self.part_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.part_vbo)
        empty = np.zeros((self.particles.count, 7), dtype=np.float32)
        glBufferData(GL_ARRAY_BUFFER, empty.nbytes, empty, GL_DYNAMIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 28, None)
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 4, GL_FLOAT, GL_FALSE, 28, ctypes_offset(12))

        # --- grid ---
        grid = _grid_lines(q.grid_half, q.grid_spacing)
        self.grid_vao = glGenVertexArrays(1)
        self.grid_vbo = glGenBuffers(1)
        glBindVertexArray(self.grid_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.grid_vbo)
        glBufferData(GL_ARRAY_BUFFER, grid.nbytes, grid, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 12, None)
        self.grid_vertex_count = grid.shape[0] // 3

        # --- fullscreen bg ---
        quad = np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype=np.float32)
        self.bg_vao = glGenVertexArrays(1)
        self.bg_vbo = glGenBuffers(1)
        glBindVertexArray(self.bg_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.bg_vbo)
        glBufferData(GL_ARRAY_BUFFER, quad.nbytes, quad, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 8, None)

        # --- green frame ribbons + tick quads ---
        segs = max(128, segs_r)
        self.frame_vaos = []
        self.frame_vbos = []
        self.frame_counts = []
        self.frame_modes = []
        for r, hh in (
            (self.frame_radius * 0.97, 0.06),
            (self.frame_radius, 0.10),
            (self.frame_radius * 1.05, 0.06),
        ):
            ring = _ring_ribbon(segs, r, half_h=hh)
            vao = glGenVertexArrays(1)
            vbo = glGenBuffers(1)
            glBindVertexArray(vao)
            glBindBuffer(GL_ARRAY_BUFFER, vbo)
            glBufferData(GL_ARRAY_BUFFER, ring.nbytes, ring, GL_STATIC_DRAW)
            glEnableVertexAttribArray(0)
            glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 16, None)
            glEnableVertexAttribArray(1)
            glVertexAttribPointer(1, 1, GL_FLOAT, GL_FALSE, 16, ctypes_offset(12))
            self.frame_vaos.append(vao)
            self.frame_vbos.append(vbo)
            self.frame_counts.append(ring.shape[0] // 4)
            self.frame_modes.append(GL_TRIANGLE_STRIP)

        ticks = _frame_ticks_ribbon(56, self.frame_radius * 1.03, 0.16, half_h=0.04)
        vao = glGenVertexArrays(1)
        vbo = glGenBuffers(1)
        glBindVertexArray(vao)
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBufferData(GL_ARRAY_BUFFER, ticks.nbytes, ticks, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 16, None)
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 1, GL_FLOAT, GL_FALSE, 16, ctypes_offset(12))
        self.frame_vaos.append(vao)
        self.frame_vbos.append(vbo)
        self.frame_counts.append(ticks.shape[0] // 4)
        self.frame_modes.append(GL_TRIANGLES)

        # --- AUDIO VISUALIZER label band ---
        label_mesh = _label_ring_band(192, self.label_radius, 0.28)
        self.label_vao = glGenVertexArrays(1)
        self.label_vbo = glGenBuffers(1)
        glBindVertexArray(self.label_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.label_vbo)
        glBufferData(GL_ARRAY_BUFFER, label_mesh.nbytes, label_mesh, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 20, None)
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 20, ctypes_offset(12))
        self.label_vertex_count = label_mesh.shape[0] // 5

        rgba, tw, th = _make_audio_label_texture("AUDIO VISUALIZER", 2048, 160, repeats=2)
        self._label_tex = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D, self._label_tex)
        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_RGBA, tw, th, 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba
        )
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glBindTexture(GL_TEXTURE_2D, 0)

        # --- 外側回転軸スローガン ---
        outer_mesh = _label_ring_band(160, self.outer_radius, 0.20)
        self.outer_vao = glGenVertexArrays(1)
        self.outer_vbo = glGenBuffers(1)
        glBindVertexArray(self.outer_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.outer_vbo)
        glBufferData(GL_ARRAY_BUFFER, outer_mesh.nbytes, outer_mesh, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 20, None)
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 20, ctypes_offset(12))
        self.outer_vertex_count = outer_mesh.shape[0] // 5

        slogan = "Visualized Audio World for better future™"
        rgba_o, tw_o, th_o = _make_audio_label_texture(slogan, 2560, 140, repeats=2)
        self._outer_tex = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D, self._outer_tex)
        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_RGBA, tw_o, th_o, 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba_o
        )
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glBindTexture(GL_TEXTURE_2D, 0)

        # --- パラメータ数値ビルボード ---
        pq = _unit_billboard_quad(1.15, 0.48)
        self.param_vao = glGenVertexArrays(1)
        self.param_vbo = glGenBuffers(1)
        glBindVertexArray(self.param_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.param_vbo)
        glBufferData(GL_ARRAY_BUFFER, pq.nbytes, pq, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 20, None)
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 20, ctypes_offset(12))
        self.param_vertex_count = 6

        self._param_texs = []
        self._param_tw, self._param_th = 320, 120
        for i, (_key, label) in enumerate(PARAM_SPECS):
            tex = int(glGenTextures(1))
            glBindTexture(GL_TEXTURE_2D, tex)
            rgba0 = _cairo_rgba_text([label, "0.00"], self._param_tw, self._param_th)
            glTexImage2D(
                GL_TEXTURE_2D,
                0,
                GL_RGBA,
                self._param_tw,
                self._param_th,
                0,
                GL_RGBA,
                GL_UNSIGNED_BYTE,
                rgba0,
            )
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            self._param_texs.append(tex)
            self._param_last[i] = f"{label}|0.00"
        glBindTexture(GL_TEXTURE_2D, 0)

        glBindVertexArray(0)
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_PROGRAM_POINT_SIZE)
        glEnable(GL_CULL_FACE)

        # サンプラー uniform を固定
        glUseProgram(self.prog_trail)
        glUniform1i(glGetUniformLocation(self.prog_trail, "uScene"), 0)
        glUniform1i(glGetUniformLocation(self.prog_trail, "uPrev"), 1)
        glUseProgram(self.prog_post)
        glUniform1i(glGetUniformLocation(self.prog_post, "uScene"), 0)
        glUniform1i(glGetUniformLocation(self.prog_post, "uTrail"), 1)
        glUseProgram(self.prog_label)
        glUniform1i(glGetUniformLocation(self.prog_label, "uTex"), 0)
        glUseProgram(0)

        self._alloc_targets(max(1, self.width), max(1, self.height))
        self._ready = True

    def _delete_targets(self) -> None:
        if self._fbo_scene:
            glDeleteFramebuffers(1, [self._fbo_scene])
            self._fbo_scene = 0
        if self._tex_scene:
            glDeleteTextures(1, [self._tex_scene])
            self._tex_scene = 0
        if self._rbo_depth:
            glDeleteRenderbuffers(1, [self._rbo_depth])
            self._rbo_depth = 0
        for i in range(2):
            if self._fbo_trail[i]:
                glDeleteFramebuffers(1, [self._fbo_trail[i]])
                self._fbo_trail[i] = 0
            if self._tex_trail[i]:
                glDeleteTextures(1, [self._tex_trail[i]])
                self._tex_trail[i] = 0
        self._fbo_w = self._fbo_h = 0

    def _make_color_tex(self, w: int, h: int, *, nearest: bool = False) -> int:
        tex = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D, tex)
        # GPU 帯域・発熱を抑えるため 8bit 固定（16F は使わない）
        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, None
        )
        # PS1 風: 拡大時はニアレストでジャギを残す（FSR/バイリニアは使わない）
        filt = GL_NEAREST if nearest else GL_LINEAR
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, filt)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, filt)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glBindTexture(GL_TEXTURE_2D, 0)
        return tex

    @staticmethod
    def _current_draw_fbo() -> int:
        bound = glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING)
        try:
            return int(bound)
        except Exception:
            return int(bound[0])

    def _alloc_targets(self, w: int, h: int) -> None:
        """内部描画解像度の FBO を確保（PS1 モード時は固定低解像度）。"""
        win_w, win_h = max(1, int(w)), max(1, int(h))
        if self.ps1_mode:
            # プレステ1 級の固定解像度。ウィンドウに比例させない＝熱も一定寄り
            tw = int(self.internal_w)
            th = int(self.internal_h)
        else:
            scale = self.fbo_scale
            tw = max(1, int(win_w * scale))
            th = max(1, int(win_h * scale))
        tw = max(1, tw)
        th = max(1, th)
        if tw == self._fbo_w and th == self._fbo_h and self._fbo_scene:
            return
        # Gtk.GLArea の FBO を壊さないよう、終了時に復元する
        restore_fbo = self._current_draw_fbo()
        self._delete_targets()

        nearest = bool(self.ps1_mode)
        self._tex_scene = self._make_color_tex(tw, th, nearest=nearest)
        self._rbo_depth = int(glGenRenderbuffers(1))
        glBindRenderbuffer(GL_RENDERBUFFER, self._rbo_depth)
        # 低解像度では 16bit depth で十分（帯域節約）
        try:
            from OpenGL.GL import GL_DEPTH_COMPONENT16

            depth_fmt = GL_DEPTH_COMPONENT16 if self.ps1_mode else GL_DEPTH_COMPONENT24
        except Exception:
            depth_fmt = GL_DEPTH_COMPONENT24
        glRenderbufferStorage(GL_RENDERBUFFER, depth_fmt, tw, th)
        glBindRenderbuffer(GL_RENDERBUFFER, 0)

        self._fbo_scene = int(glGenFramebuffers(1))
        glBindFramebuffer(GL_FRAMEBUFFER, self._fbo_scene)
        glFramebufferTexture2D(
            GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self._tex_scene, 0
        )
        glFramebufferRenderbuffer(
            GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, self._rbo_depth
        )
        if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
            glBindFramebuffer(GL_FRAMEBUFFER, restore_fbo)
            raise RuntimeError("Scene FBO incomplete")

        for i in range(2):
            self._tex_trail[i] = self._make_color_tex(tw, th, nearest=nearest)
            self._fbo_trail[i] = int(glGenFramebuffers(1))
            glBindFramebuffer(GL_FRAMEBUFFER, self._fbo_trail[i])
            glFramebufferTexture2D(
                GL_FRAMEBUFFER,
                GL_COLOR_ATTACHMENT0,
                GL_TEXTURE_2D,
                self._tex_trail[i],
                0,
            )
            if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                glBindFramebuffer(GL_FRAMEBUFFER, restore_fbo)
                raise RuntimeError(f"Trail FBO {i} incomplete")

        # 残像テクスチャを黒で初期化（未定義画素のゴミ防止）
        for i in range(2):
            glBindFramebuffer(GL_FRAMEBUFFER, self._fbo_trail[i])
            glClearColor(0.0, 0.0, 0.0, 1.0)
            glClear(GL_COLOR_BUFFER_BIT)

        glBindFramebuffer(GL_FRAMEBUFFER, restore_fbo)
        self._fbo_w, self._fbo_h = tw, th
        self._trail_idx = 0

    def resize(self, w: int, h: int) -> None:
        self.width = max(1, w)
        self.height = max(1, h)
        if self._ready:
            self._alloc_targets(self.width, self.height)
        glViewport(0, 0, self.width, self.height)

    def set_analysis(self, analysis: AudioAnalysis) -> None:
        self._analysis = analysis
        if analysis.spectrum is not None and analysis.spectrum.size == self.bands:
            # 追加平滑
            self._spectrum = self._spectrum * 0.35 + analysis.spectrum * 0.65

    def toggle_rotation(self) -> None:
        self._auto_rotate = not self._auto_rotate

    def set_pointer(self, nx: float, ny: float) -> None:
        """Window-normalized pointer (0..1). Camera yaw/pitch slowly follow."""
        self._mouse_nx = float(np.clip(nx, 0.0, 1.0))
        self._mouse_ny = float(np.clip(ny, 0.0, 1.0))
        self._pointer_active = True

    def _upload_param_texture(self, index: int, label: str, value: float) -> None:
        """数値が変わったときだけ Cairo で描き直してアップロード。"""
        # peak は振幅が 1 超えることがあるので表示用に整形
        if label == "PEAK":
            txt = f"{value:.3f}"
        else:
            txt = f"{value:.2f}"
        key = f"{label}|{txt}"
        if key == self._param_last[index]:
            return
        self._param_last[index] = key
        rgba = _cairo_rgba_text([label, txt], self._param_tw, self._param_th)
        glBindTexture(GL_TEXTURE_2D, self._param_texs[index])
        glTexSubImage2D(
            GL_TEXTURE_2D,
            0,
            0,
            0,
            self._param_tw,
            self._param_th,
            GL_RGBA,
            GL_UNSIGNED_BYTE,
            rgba,
        )

    def _update_param_textures(self, a: AudioAnalysis, energy: float) -> None:
        values = {
            "bass": a.bass,
            "mid": a.mid,
            "treble": a.treble,
            "rms": a.rms,
            "peak": min(a.peak, 9.999),
            "beat": a.beat,
        }
        for i, (key, label) in enumerate(PARAM_SPECS):
            self._upload_param_texture(i, label, float(values.get(key, 0.0)))

    @staticmethod
    def _billboard_model(pos: np.ndarray, view: np.ndarray, scale_s: float = 1.0) -> np.ndarray:
        """カメラ向きのビルボード（view の right/up を使用）。"""
        right = view[0, 0:3].astype(np.float32)
        up = view[1, 0:3].astype(np.float32)
        rn = float(np.linalg.norm(right)) + 1e-9
        un = float(np.linalg.norm(up)) + 1e-9
        right = right / rn
        up = up / un
        # 前方 = right × up（ビルボード法線がカメラ側を向く）
        fwd = np.cross(right, up)
        fn = float(np.linalg.norm(fwd)) + 1e-9
        fwd = fwd / fn
        m = np.eye(4, dtype=np.float32)
        m[0, 0:3] = right * scale_s
        m[1, 0:3] = up * scale_s
        m[2, 0:3] = fwd * scale_s
        m[0:3, 3] = pos
        return m

    def render(self) -> bool:
        if not self._ready:
            return False

        now = time.perf_counter()
        # PS1: fixed dt → コマ送りの動き（スムーズ補間なし）
        if self._fixed_dt is not None:
            dt = float(self._fixed_dt)
        else:
            dt = min(0.08, now - self._last_t)
        self._last_t = now
        if self._locked_fps:
            t = float(self._frame_i) * (1.0 / float(self._locked_fps))
        else:
            t = now - self._t0
        self._frame_i = getattr(self, "_frame_i", 0) + 1
        a = self._analysis

        energy = float(np.clip(a.rms * 0.7 + a.bass * 0.5 + a.mid * 0.3, 0.0, 1.5))
        beat = float(a.beat)

        # カメラ: マウス位置へゆっくり追従（X=ヨー, Y=高さバイアス）
        # nx=0 → 左周り, nx=1 → 右周り（約 ±180°）
        target_yaw = (self._mouse_nx - 0.5) * (math.pi * 1.85)
        if self._pointer_active:
            # shortest-path lerp
            dyaw = (target_yaw - self._angle + math.pi) % (math.pi * 2.0) - math.pi
            follow = min(1.0, dt * 1.35)  # ゆっくり
            self._angle += dyaw * follow
            target_h = (0.5 - self._mouse_ny) * 2.4  # 上に上げるとカメラ上昇
            self._cam_h_bias += (target_h - self._cam_h_bias) * min(1.0, dt * 1.2)
        if self._auto_rotate:
            # 追従中は弱いドリフトのみ、未検出時は従来どおり公転
            spin = 0.06 + energy * 0.12 + beat * 0.18 if self._pointer_active else (
                0.18 + energy * 0.35 + beat * 0.5
            )
            self._angle += dt * spin

        # 緑外枠・数値パネルは中心軸まわりに回転（音で少し加速）
        self._frame_angle += dt * (0.22 + energy * 0.15 + beat * 0.35)
        # AUDIO VISUALIZER は外枠と逆回転（弱めの公転）
        self._label_angle -= dt * (0.07 + energy * 0.04 + beat * 0.06)

        # パーティクル（品質 + ランタイムスロットルで発生量を抑制）
        emit_n = 0
        if beat > 0.25:
            emit_n += int(8 + beat * 40)
        if a.treble > 0.35:
            emit_n += int(a.treble * 12)
        emit_n = int(emit_n * self.particle_emit_scale * self._runtime_throttle)
        if emit_n:
            self.particles.emit(emit_n, energy, beat)
        self.particles.update(dt)

        # インスタンス高さ更新
        for i in range(self.bands):
            h = float(self._spectrum[i])
            h = h * h * 2.8 + h * 1.2  # 強調
            h = min(4.5, h * (0.9 + a.bass * 0.4))
            self._bar_instances[i, 2] = max(0.04, h)

        # 内部 FBO のアスペクトで投影（PS1 固定解像度時は 4:3）
        aspect = self._fbo_w / max(self._fbo_h, 1)
        proj = perspective(52.0, aspect, 0.1, 80.0)
        cam_r = 9.5 - energy * 1.2 - beat * 0.8
        cam_h = 4.2 + a.mid * 0.8 + math.sin(t * 0.4) * 0.3 + float(self._cam_h_bias)
        eye = np.array(
            [
                math.cos(self._angle) * cam_r,
                cam_h,
                math.sin(self._angle) * cam_r,
            ],
            dtype=np.float32,
        )
        target = np.array([0.0, 0.9 + a.bass * 0.4, 0.0], dtype=np.float32)
        view = look_at(eye, target, np.array([0.0, 1.0, 0.0], dtype=np.float32))
        vp = mul(proj, view)

        # Gtk.GLArea がバインドしている FB を保持（最終合成先）
        # Wayland / EGL では FBO 0 が incomplete なので、非ゼロの GTK FBO を覚える。
        # render シグナル中は通常すでに正しい FBO が bind されている。
        bound = int(self._current_draw_fbo())
        offscreen = {
            int(self._fbo_scene or 0),
            int(self._fbo_trail[0] or 0),
            int(self._fbo_trail[1] or 0),
        }
        if bound > 0 and bound not in offscreen:
            self._gtk_fbo = bound
        prev_fbo = int(self._gtk_fbo) if self._gtk_fbo > 0 else bound
        # オフスクリーンに「最終出力」してしまうのを防ぐ。0 は Wayland では incomplete。
        if prev_fbo <= 0 or prev_fbo in offscreen:
            return False

        # ---- 1) シーンをオフスクリーンへ ----
        glBindFramebuffer(GL_FRAMEBUFFER, self._fbo_scene)
        glViewport(0, 0, self._fbo_w, self._fbo_h)
        glClearColor(0.02, 0.03, 0.06, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # Background
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        glUseProgram(self.prog_bg)
        glUniform1f(glGetUniformLocation(self.prog_bg, "uTime"), t)
        glUniform1f(glGetUniformLocation(self.prog_bg, "uEnergy"), energy)
        glUniform1f(glGetUniformLocation(self.prog_bg, "uBeat"), beat)
        glBindVertexArray(self.bg_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_DEPTH_TEST)

        model_i = np.eye(4, dtype=np.float32)
        mvp_grid = mul(vp, translation(0, -0.02, 0))

        # Grid（青ネオンが視認しやすいよう加算ブレンド）
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glUseProgram(self.prog_grid)
        glUniformMatrix4fv(glGetUniformLocation(self.prog_grid, "uMVP"), 1, GL_TRUE, mvp_grid)
        glUniform1f(glGetUniformLocation(self.prog_grid, "uBass"), a.bass)
        glUniform1f(glGetUniformLocation(self.prog_grid, "uEnergy"), energy)
        glUniform1f(glGetUniformLocation(self.prog_grid, "uBeat"), beat)
        glBindVertexArray(self.grid_vao)
        glDrawArrays(GL_LINES, 0, self.grid_vertex_count)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        # Bars (instanced)
        glBindBuffer(GL_ARRAY_BUFFER, self.bar_instance_vbo)
        glBufferSubData(GL_ARRAY_BUFFER, 0, self._bar_instances.nbytes, self._bar_instances)

        glUseProgram(self.prog_bar)
        glUniformMatrix4fv(glGetUniformLocation(self.prog_bar, "uMVP"), 1, GL_TRUE, vp)
        glUniformMatrix4fv(glGetUniformLocation(self.prog_bar, "uModel"), 1, GL_TRUE, model_i)
        glUniform1f(glGetUniformLocation(self.prog_bar, "uTime"), t)
        glUniform1f(glGetUniformLocation(self.prog_bar, "uBass"), a.bass)
        glUniform3f(
            glGetUniformLocation(self.prog_bar, "uCamPos"),
            float(eye[0]), float(eye[1]), float(eye[2]),
        )
        glUniform1f(glGetUniformLocation(self.prog_bar, "uBands"), float(self.bands))
        glUniform1f(glGetUniformLocation(self.prog_bar, "uBeat"), beat)
        glBindVertexArray(self.bar_vao)
        glDrawArraysInstanced(GL_TRIANGLES, 0, self.bar_vertex_count, self.bands)

        # Orb
        orb_s = 0.55 + a.bass * 0.45 + beat * 0.25
        orb_model = mul(translation(0.0, 1.1 + a.bass * 0.2, 0.0), scale(orb_s, orb_s, orb_s))
        orb_mvp = mul(vp, orb_model)
        glUseProgram(self.prog_orb)
        glUniformMatrix4fv(glGetUniformLocation(self.prog_orb, "uMVP"), 1, GL_TRUE, orb_mvp)
        glUniformMatrix4fv(glGetUniformLocation(self.prog_orb, "uModel"), 1, GL_TRUE, orb_model)
        glUniform1f(
            glGetUniformLocation(self.prog_orb, "uPulse"),
            float(np.clip(a.bass + beat, 0, 1.5)),
        )
        glUniform1f(glGetUniformLocation(self.prog_orb, "uTime"), t)
        glUniform3f(
            glGetUniformLocation(self.prog_orb, "uCamPos"),
            float(eye[0]), float(eye[1]), float(eye[2]),
        )
        glUniform1f(glGetUniformLocation(self.prog_orb, "uBass"), a.bass)
        glUniform1f(glGetUniformLocation(self.prog_orb, "uMid"), a.mid)
        glUniform1f(glGetUniformLocation(self.prog_orb, "uTreble"), a.treble)
        glUniform1f(glGetUniformLocation(self.prog_orb, "uBeat"), beat)
        glBindVertexArray(self.orb_vao)
        glDrawArrays(GL_TRIANGLES, 0, self.orb_vertex_count)

        # ---- Overlays (match Windows): depth OFF so ribbons/labels always show ----
        glDisable(GL_DEPTH_TEST)
        glDepthMask(GL_FALSE)
        glDisable(GL_CULL_FACE)

        # Energy ribbons
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glUseProgram(self.prog_ring)
        for idx, vao in enumerate(self.ring_vaos):
            r_model = translation(0.0, 0.20 + idx * 0.38 + a.bass * 0.25, 0.0)
            mvp = mul(vp, r_model)
            glUniformMatrix4fv(glGetUniformLocation(self.prog_ring, "uMVP"), 1, GL_TRUE, mvp)
            glUniform1f(glGetUniformLocation(self.prog_ring, "uTime"), t)
            glUniform1f(
                glGetUniformLocation(self.prog_ring, "uEnergy"),
                float(np.clip(0.35 + energy * (1.0 - idx * 0.15) + a.treble * 0.4, 0, 1.8)),
            )
            glUniform1f(glGetUniformLocation(self.prog_ring, "uPhase"), idx * 1.7)
            glUniform1f(glGetUniformLocation(self.prog_ring, "uHue"), 0.55 + idx * 0.08 + t * 0.02)
            glBindVertexArray(vao)
            glDrawArrays(GL_TRIANGLE_STRIP, 0, self.ring_counts[idx])

        # Green neon frame ribbons
        frame_rot = rotation_y(self._frame_angle)
        frame_y = 0.15 + a.bass * 0.18
        green = (0.05, 1.0, 0.22)  # higher chroma neon green
        glUseProgram(self.prog_frame)
        for idx, vao in enumerate(self.frame_vaos):
            y_off = frame_y + (0.0 if idx >= 3 else idx * 0.05)
            mvp = mul(vp, mul(frame_rot, translation(0.0, y_off, 0.0)))
            glUniformMatrix4fv(glGetUniformLocation(self.prog_frame, "uMVP"), 1, GL_TRUE, mvp)
            glUniform1f(glGetUniformLocation(self.prog_frame, "uEnergy"), energy)
            glUniform1f(glGetUniformLocation(self.prog_frame, "uTime"), t)
            glUniform1f(glGetUniformLocation(self.prog_frame, "uPhase"), idx * 1.3)
            glUniform3f(glGetUniformLocation(self.prog_frame, "uColor"), *green)
            alpha = 0.70 if idx == 3 else (1.0 if idx == 1 else 0.75)
            glUniform1f(glGetUniformLocation(self.prog_frame, "uAlpha"), alpha)
            glUniform1f(glGetUniformLocation(self.prog_frame, "uBeat"), beat)
            glBindVertexArray(vao)
            glDrawArrays(self.frame_modes[idx], 0, self.frame_counts[idx])

        # Orbiting labels — premultiplied alpha
        glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
        glUseProgram(self.prog_label)
        label_y = 1.55 + a.bass * 0.22 + beat * 0.10
        label_model = mul(
            translation(0.0, label_y, 0.0),
            rotation_y(self._label_angle),
        )
        label_mvp = mul(vp, label_model)
        glUniformMatrix4fv(glGetUniformLocation(self.prog_label, "uMVP"), 1, GL_TRUE, label_mvp)
        glUniform1f(glGetUniformLocation(self.prog_label, "uYOffset"), 0.0)
        glUniform1f(
            glGetUniformLocation(self.prog_label, "uAlpha"),
            float(0.95 + beat * 0.04),
        )
        glUniform1f(glGetUniformLocation(self.prog_label, "uBeat"), beat)
        glUniform1f(glGetUniformLocation(self.prog_label, "uEnergy"), energy)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self._label_tex)
        glBindVertexArray(self.label_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, self.label_vertex_count)
        glBindTexture(GL_TEXTURE_2D, 0)

        outer_y = self.outer_y + a.bass * 0.10
        outer_model = mul(
            translation(0.0, outer_y, 0.0),
            rotation_y(-self._frame_angle),
        )
        outer_mvp = mul(vp, outer_model)
        glUniformMatrix4fv(glGetUniformLocation(self.prog_label, "uMVP"), 1, GL_TRUE, outer_mvp)
        glUniform1f(
            glGetUniformLocation(self.prog_label, "uAlpha"),
            float(0.90 + beat * 0.06),
        )
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self._outer_tex)
        glBindVertexArray(self.outer_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, self.outer_vertex_count)
        glBindTexture(GL_TEXTURE_2D, 0)

        # Param billboards
        interval = self._param_interval / max(self._runtime_param_scale, 0.25)
        self._param_timer += dt
        if self._param_timer >= interval:
            self._param_timer = 0.0
            self._update_param_textures(a, energy)

        n_params = len(PARAM_SPECS)
        if self._param_texs and n_params > 0:
            glUseProgram(self.prog_label)
            glUniform1f(glGetUniformLocation(self.prog_label, "uYOffset"), 0.0)
            glUniform1f(glGetUniformLocation(self.prog_label, "uBeat"), beat)
            glUniform1f(glGetUniformLocation(self.prog_label, "uEnergy"), energy)
            glUniform1f(
                glGetUniformLocation(self.prog_label, "uAlpha"),
                float(0.92 + beat * 0.05),
            )
            glBindVertexArray(self.param_vao)
            py = self.param_y + a.bass * 0.18 + a.mid * 0.10 + beat * 0.06
            for i in range(n_params):
                ang = self._frame_angle + (i / n_params) * math.pi * 2.0
                pos = np.array(
                    [
                        math.cos(ang) * self.param_radius,
                        py,
                        math.sin(ang) * self.param_radius,
                    ],
                    dtype=np.float32,
                )
                model = self._billboard_model(pos, view, scale_s=1.15)
                mvp = mul(vp, model)
                glUniformMatrix4fv(
                    glGetUniformLocation(self.prog_label, "uMVP"), 1, GL_TRUE, mvp
                )
                glActiveTexture(GL_TEXTURE0)
                glBindTexture(GL_TEXTURE_2D, self._param_texs[i])
                glDrawArrays(GL_TRIANGLES, 0, self.param_vertex_count)
            glBindTexture(GL_TEXTURE_2D, 0)

        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_CULL_FACE)
        glDepthMask(GL_TRUE)
        glEnable(GL_DEPTH_TEST)

        # Particles (additive)
        glDepthFunc(GL_LESS)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        pdata = self.particles.buffer_data()
        glBindBuffer(GL_ARRAY_BUFFER, self.part_vbo)
        glBufferSubData(GL_ARRAY_BUFFER, 0, pdata.nbytes, pdata)
        glUseProgram(self.prog_part)
        glUniformMatrix4fv(glGetUniformLocation(self.prog_part, "uVP"), 1, GL_TRUE, vp)
        glUniform1f(glGetUniformLocation(self.prog_part, "uTime"), t)
        glBindVertexArray(self.part_vao)
        glDrawArrays(GL_POINTS, 0, self.particles.count)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        # ---- 2) 残像バッファ更新（ping-pong）— 画面全体 ----
        use_trails = self.enable_trails and self._runtime_trails_ok
        if use_trails:
            src = self._trail_idx
            dst = 1 - src
            # 控えめな持続（尾は見えるが主役は現在画）
            decay = float(np.clip(self.trail_decay + energy * 0.008 + beat * 0.01, 0.72, 0.93))
            scene_gain = float(np.clip(self.trail_scene_gain + beat * 0.04, 0.28, 0.52))
            zoom = float(self.trail_zoom - beat * 0.0005 - energy * 0.00025)

            glBindFramebuffer(GL_FRAMEBUFFER, self._fbo_trail[dst])
            glViewport(0, 0, self._fbo_w, self._fbo_h)
            glDisable(GL_DEPTH_TEST)
            glDisable(GL_BLEND)
            glUseProgram(self.prog_trail)
            glUniform1f(glGetUniformLocation(self.prog_trail, "uDecay"), decay)
            glUniform1f(glGetUniformLocation(self.prog_trail, "uSceneGain"), scene_gain)
            glUniform1f(glGetUniformLocation(self.prog_trail, "uZoom"), zoom)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self._tex_scene)
            glActiveTexture(GL_TEXTURE1)
            glBindTexture(GL_TEXTURE_2D, self._tex_trail[src])
            glBindVertexArray(self.bg_vao)
            glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)
            self._trail_idx = dst
            trail_tex = self._tex_trail[self._trail_idx]
            trail_mix = float(np.clip(self.trail_mix + energy * 0.04 + beat * 0.04, 0.32, 0.68))
        else:
            trail_tex = self._tex_scene
            trail_mix = 0.0

        # ---- 3) 最終合成（RGB ずらし + CRT）→ GLArea の FB ----
        aberr = float(max(self.aberration, 0.00055) * (1.0 + energy * 0.12 + beat * 0.08))

        glBindFramebuffer(GL_FRAMEBUFFER, prev_fbo)
        glViewport(0, 0, self.width, self.height)
        glDisable(GL_DEPTH_TEST)
        # 端の透過ベゼル: クリアを透明に、ポストはアルファ書き込み
        glDisable(GL_BLEND)
        glClearColor(0.0, 0.0, 0.0, 0.0)
        glClear(GL_COLOR_BUFFER_BIT)
        glUseProgram(self.prog_post)
        glUniform1f(glGetUniformLocation(self.prog_post, "uAberr"), aberr)
        glUniform1f(glGetUniformLocation(self.prog_post, "uTrailMix"), trail_mix)
        glUniform1f(glGetUniformLocation(self.prog_post, "uEnergy"), energy)
        glUniform1f(glGetUniformLocation(self.prog_post, "uBeat"), beat)
        glUniform1f(glGetUniformLocation(self.prog_post, "uTime"), t)
        glUniform1f(glGetUniformLocation(self.prog_post, "uExposure"), self.exposure)
        glUniform1f(glGetUniformLocation(self.prog_post, "uBarrel"), float(self.crt_barrel))
        glUniform1f(glGetUniformLocation(self.prog_post, "uScanline"), float(self.crt_scanline))
        glUniform1f(glGetUniformLocation(self.prog_post, "uVignette"), float(self.crt_vignette))
        glUniform2f(
            glGetUniformLocation(self.prog_post, "uResolution"),
            float(self.width),
            float(self.height),
        )
        glUniform2f(
            glGetUniformLocation(self.prog_post, "uInternal"),
            float(max(1, self._fbo_w or self.internal_w)),
            float(max(1, self._fbo_h or self.internal_h)),
        )
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self._tex_scene)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, trail_tex)
        glBindVertexArray(self.bg_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)

        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, 0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBindVertexArray(0)
        glUseProgram(0)
        return True


def ctypes_offset(n: int):
    """OpenGL の pointer オフセット用。"""
    import ctypes

    return ctypes.c_void_p(n)
