"""Windows OpenGL 3.3 visualizer (GLFW context — no GTK)."""

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
    GL_LINES,
    GL_LINE_STRIP,
    GL_LINK_STATUS,
    GL_NEAREST,
    GL_ONE,
    GL_ONE_MINUS_SRC_ALPHA,
    GL_POINTS,
    GL_PROGRAM_POINT_SIZE,
    GL_RENDERBUFFER,
    GL_RGBA,
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
    GL_UNSIGNED_BYTE,
    GL_VERTEX_SHADER,
    glActiveTexture,
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
    glLinkProgram,
    glRenderbufferStorage,
    glShaderSource,
    glTexImage2D,
    glTexParameteri,
    glUniform1f,
    glUniform1i,
    glUniform2f,
    glUniform3f,
    glUniformMatrix4fv,
    glUseProgram,
    glVertexAttribDivisor,
    glVertexAttribPointer,
    glViewport,
)

from sound_orbit_win.audio import BANDS, AudioAnalysis
from sound_orbit_win.math3d import look_at, mul, perspective, rotation_y, scale, translation

# ---------------------------------------------------------------------------
# Shaders (subset + CRT post)
# ---------------------------------------------------------------------------

BAR_VERT = """
#version 330 core
layout(location=0) in vec3 aPos;
layout(location=1) in vec3 aNormal;
layout(location=2) in vec4 aInstance;
uniform mat4 uMVP;
uniform mat4 uModel;
uniform float uTime;
uniform float uBass;
out vec3 vNormal;
out vec3 vWorldPos;
out float vHeight;
out float vBand;
void main(){
    float h=max(aInstance.z,0.02);
    vec3 pos=aPos;
    pos.y=(aPos.y+0.5)*h;
    pos.x+=aInstance.x;
    pos.z+=aInstance.y;
    pos.y+=sin(uTime*2.0+aInstance.w*0.4)*0.02*uBass;
    vec4 world=uModel*vec4(pos,1.0);
    vWorldPos=world.xyz;
    vNormal=mat3(uModel)*aNormal;
    vHeight=h;
    vBand=aInstance.w;
    gl_Position=uMVP*vec4(pos,1.0);
}
"""

BAR_FRAG = """
#version 330 core
in vec3 vNormal; in vec3 vWorldPos; in float vHeight; in float vBand;
uniform vec3 uCamPos; uniform float uBands; uniform float uBeat;
out vec4 FragColor;
vec3 palette(float t){
    vec3 a=vec3(0.10,0.48,0.92), b=vec3(0.78,0.18,0.88), c=vec3(0.95,0.48,0.12);
    float s=smoothstep(0.0,1.0,t);
    vec3 col=mix(a,b,smoothstep(0.0,0.55,s));
    return mix(col,c,smoothstep(0.45,1.0,s));
}
void main(){
    vec3 N=normalize(vNormal);
    vec3 V=normalize(uCamPos-vWorldPos);
    vec3 L=normalize(vec3(0.4,1.0,0.3));
    float diff=max(dot(N,L),0.0);
    float rim=pow(1.0-max(dot(N,V),0.0),3.0);
    float t=vBand/max(uBands-1.0,1.0);
    vec3 base=palette(t);
    float hNorm=clamp(vHeight/4.5,0.0,1.0);
    vec3 col=base*(0.28+diff*0.55+hNorm*0.18+uBeat*0.06)+base*rim*0.28;
    float peak=max(col.r,max(col.g,col.b));
    if(peak>0.92) col*=0.92/peak;
    FragColor=vec4(col,0.92);
}
"""

ORB_VERT = """
#version 330 core
layout(location=0) in vec3 aPos;
layout(location=1) in vec3 aNormal;
uniform mat4 uMVP; uniform mat4 uModel; uniform float uPulse; uniform float uTime;
out vec3 vNormal; out vec3 vWorldPos; out vec3 vLocal;
void main(){
    float noise=sin(aPos.x*6.0+uTime*3.0)*cos(aPos.y*5.0-uTime*2.5)*sin(aPos.z*7.0+uTime)*0.08*uPulse;
    vec3 pos=aPos*(1.0+uPulse*0.35+noise);
    vec4 world=uModel*vec4(pos,1.0);
    vWorldPos=world.xyz; vNormal=normalize(mat3(uModel)*aNormal); vLocal=aPos;
    gl_Position=uMVP*vec4(pos,1.0);
}
"""

ORB_FRAG = """
#version 330 core
in vec3 vNormal; in vec3 vWorldPos; in vec3 vLocal;
uniform vec3 uCamPos; uniform float uBass; uniform float uMid; uniform float uTreble;
uniform float uBeat; uniform float uTime;
out vec4 FragColor;
void main(){
    vec3 N=normalize(vNormal); vec3 V=normalize(uCamPos-vWorldPos);
    float fres=pow(1.0-max(dot(N,V),0.0),2.2);
    vec3 base=vec3(0.2,0.7,1.0)*uBass+vec3(0.95,0.3,0.85)*uMid+vec3(1.0,0.7,0.2)*uTreble;
    base=max(base,vec3(0.08,0.12,0.2));
    float bands=abs(sin(vLocal.y*12.0+uTime*4.0+uBeat*3.0));
    base+=vec3(0.3,0.6,1.0)*bands*0.15*uTreble;
    vec3 col=base*(0.35+fres*1.2)+vec3(1.0)*fres*0.35*(0.4+uBeat);
    FragColor=vec4(col,0.92);
}
"""

GRID_VERT = """
#version 330 core
layout(location=0) in vec3 aPos;
uniform mat4 uMVP; uniform float uBass;
out float vDist;
void main(){
    vec3 pos=aPos;
    pos.y+=sin(length(aPos.xz)*1.5-uBass*8.0)*uBass*0.15;
    vDist=length(aPos.xz);
    gl_Position=uMVP*vec4(pos,1.0);
}
"""

GRID_FRAG = """
#version 330 core
in float vDist; uniform float uEnergy; uniform float uBeat;
out vec4 FragColor;
void main(){
    float fade=1.0-smoothstep(1.5,13.0,vDist);
    vec3 col=mix(vec3(0.20,0.55,1.0),vec3(0.35,0.85,1.0),clamp(uEnergy*0.55+uBeat*0.25,0.0,1.0));
    float core=1.0-smoothstep(0.0,6.0,vDist);
    float a=(0.22+uEnergy*0.28+uBeat*0.12+core*0.18)*fade;
    FragColor=vec4(col*(0.85+core*0.45+uEnergy*0.25),clamp(a,0.0,0.95));
}
"""

BG_VERT = """
#version 330 core
layout(location=0) in vec2 aPos; out vec2 vUv;
void main(){ vUv=aPos*0.5+0.5; gl_Position=vec4(aPos,0.999,1.0); }
"""

BG_FRAG = """
#version 330 core
in vec2 vUv; uniform float uTime; uniform float uEnergy; uniform float uBeat;
out vec4 FragColor;
void main(){
    vec2 p=vUv-0.5; float r=length(p);
    vec3 col=mix(vec3(0.012,0.018,0.040),vec3(0.03,0.015,0.08),smoothstep(0.0,0.85,r));
    float yBand=exp(-pow(p.y/(0.09+uEnergy*0.04+uBeat*0.03),2.0));
    float xFall=1.0-smoothstep(0.05,0.72,abs(p.x));
    vec3 hCol=mix(vec3(0.18,0.42,0.85),vec3(0.12,0.55,0.80),smoothstep(0.0,0.55,p.x*0.5+0.5));
    col+=hCol*yBand*xFall*(0.10+uEnergy*0.22+uBeat*0.18);
    FragColor=vec4(col,1.0);
}
"""

PART_VERT = """
#version 330 core
layout(location=0) in vec3 aPos; layout(location=1) in vec4 aData;
uniform mat4 uVP; out float vLife; out float vHue;
void main(){
    vLife=aData.x; vHue=aData.z;
    gl_Position=uVP*vec4(aPos,1.0);
    gl_PointSize=aData.y*(0.5+vLife)*(180.0/max(gl_Position.w,0.1));
}
"""

PART_FRAG = """
#version 330 core
in float vLife; in float vHue; out vec4 FragColor;
vec3 hsv2rgb(vec3 c){
    vec3 p=abs(fract(c.xxx+vec3(0.,2./3.,1./3.))*6.-3.);
    return c.z*mix(vec3(1.),clamp(p-1.,0.,1.),c.y);
}
void main(){
    vec2 p=gl_PointCoord*2.-1.; float d=dot(p,p);
    if(d>1.) discard;
    FragColor=vec4(hsv2rgb(vec3(fract(vHue),0.7,1.)),exp(-d*3.2)*vLife*0.9);
}
"""

POST_VERT = """
#version 330 core
layout(location=0) in vec2 aPos; out vec2 vUv;
void main(){ vUv=aPos*0.5+0.5; gl_Position=vec4(aPos,0.0,1.0); }
"""

TRAIL_FRAG = """
#version 330 core
in vec2 vUv; uniform sampler2D uScene; uniform sampler2D uPrev;
uniform float uDecay; uniform float uSceneGain; uniform float uZoom;
out vec4 FragColor;
void main(){
    vec2 uvPrev=clamp((vUv-0.5)*uZoom+0.5,0.001,0.999);
    vec3 scene=texture(uScene,vUv).rgb;
    vec3 prev=texture(uPrev,uvPrev).rgb;
    float lum=dot(scene,vec3(0.299,0.587,0.114));
    float stamp=smoothstep(0.08,0.55,lum);
    vec3 col=prev*uDecay+scene*uSceneGain*stamp;
    col=col/(1.0+col*0.45);
    FragColor=vec4(clamp(col,0.0,1.2),1.0);
}
"""

POST_FRAG = """
#version 330 core
in vec2 vUv;
uniform sampler2D uScene; uniform sampler2D uTrail;
uniform float uTrailMix; uniform float uEnergy; uniform float uBeat;
uniform float uTime; uniform float uExposure; uniform float uBarrel;
uniform float uScanline; uniform float uVignette; uniform vec2 uResolution; uniform vec2 uInternal;
out vec4 FragColor;
vec2 crtBarrel(vec2 uv,float amount){
    if(amount<1e-5) return uv;
    vec2 cc=uv*2.0-1.0;
    float r2=dot(cc,cc);
    float f=1.0+r2*(amount+amount*0.35*r2);
    return cc*f*0.5+0.5;
}
vec3 tonemap(vec3 x){
    x=max(x,0.0);
    float a=2.51,b=0.03,c=2.43,d=0.59,e=0.14;
    return clamp((x*(a*x+b))/(x*(c*x+d)+e),0.0,1.0);
}
vec3 quantize256(vec3 c){
    c=clamp(c,0.0,1.0);
    return vec3(floor(c.r*7.0+0.5)/7.0, floor(c.g*7.0+0.5)/7.0, floor(c.b*3.0+0.5)/3.0);
}
void main(){
    float barrel=uBarrel*(1.0+uEnergy*0.04+uBeat*0.03);
    vec2 uv=crtBarrel(vUv,barrel);
    vec2 edge=smoothstep(vec2(-0.015),vec2(0.035),uv)*smoothstep(vec2(-0.015),vec2(0.035),1.0-uv);
    float inScreen=edge.x*edge.y;
    if(inScreen<1e-4){ FragColor=vec4(0.0,0.0,0.0,1.0); return; }
    vec2 ires=max(uInternal,vec2(64.0,48.0));
    vec2 uvS=clamp(uv,0.0,1.0);
    uvS=(floor(uvS*ires)+0.5)/ires;
    vec3 scene=texture(uScene,uvS).rgb;
    vec3 trail=texture(uTrail,uvS).rgb*vec3(0.82,0.96,1.05);
    float mixAmt=clamp(uTrailMix,0.0,1.0)*(0.85+uEnergy*0.06);
    vec3 col=mix(scene,trail,mixAmt*0.42);
    col+=max(trail-scene*0.55,0.0)*mixAmt*0.28;
    col=mix(col,max(col,scene),0.45)*uExposure;
    float py=gl_FragCoord.y;
    float mask=1.0-step(2.0,mod(floor(py),4.0));
    float s=clamp(uScanline,0.0,1.0);
    col*=mix(1.0,mix(1.0,0.06,s),mask);
    vec2 vc=uvS*2.0-1.0;
    float soft=smoothstep(0.82,1.28,length(vc));
    float vig=1.0-uVignette*soft*0.45;
    col*=vig;
    col=quantize256(tonemap(col));
    float frameA=smoothstep(0.0,0.12,inScreen);
    FragColor=vec4(col*frameA,1.0);
}
"""


def _compile(src: str, stype) -> int:
    sh = glCreateShader(stype)
    glShaderSource(sh, src)
    glCompileShader(sh)
    if not glGetShaderiv(sh, GL_COMPILE_STATUS):
        raise RuntimeError(glGetShaderInfoLog(sh))
    return sh


def _link(vs: str, fs: str) -> int:
    prog = glCreateProgram()
    glAttachShader(prog, _compile(vs, GL_VERTEX_SHADER))
    glAttachShader(prog, _compile(fs, GL_FRAGMENT_SHADER))
    glLinkProgram(prog)
    if not glGetProgramiv(prog, GL_LINK_STATUS):
        raise RuntimeError(glGetProgramInfoLog(prog))
    return prog


def _ctypes_offset(n: int):
    import ctypes

    return ctypes.c_void_p(n)


def _unit_box() -> np.ndarray:
    faces = [
        ((-0.5, 0.5, -0.5), (0.5, 0.5, -0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5), (0, 1, 0)),
        ((-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, -0.5, -0.5), (-0.5, -0.5, -0.5), (0, -1, 0)),
        ((-0.5, -0.5, 0.5), (-0.5, 0.5, 0.5), (0.5, 0.5, 0.5), (0.5, -0.5, 0.5), (0, 0, 1)),
        ((0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5), (-0.5, -0.5, -0.5), (0, 0, -1)),
        ((0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (0.5, 0.5, -0.5), (0.5, -0.5, -0.5), (1, 0, 0)),
        ((-0.5, -0.5, -0.5), (-0.5, 0.5, -0.5), (-0.5, 0.5, 0.5), (-0.5, -0.5, 0.5), (-1, 0, 0)),
    ]
    verts = []
    for a, b, c, d, n in faces:
        for p in (a, b, c, a, c, d):
            verts.extend([*p, *n])
    data = np.array(verts, dtype=np.float32)
    data[0::6] *= 0.22
    data[2::6] *= 0.22
    return data


def _uv_sphere(stacks: int = 16, slices: int = 22) -> np.ndarray:
    verts = []
    for i in range(stacks):
        for j in range(slices):
            def sp(ii, jj):
                th = (ii / stacks) * math.pi
                ph = (jj / slices) * 2 * math.pi
                x = math.sin(th) * math.cos(ph)
                y = math.cos(th)
                z = math.sin(th) * math.sin(ph)
                return (x, y, z)
            p00, p10, p01, p11 = sp(i, j), sp(i + 1, j), sp(i, j + 1), sp(i + 1, j + 1)
            for p in (p00, p10, p11, p00, p11, p01):
                verts.extend([*p, *p])
    return np.array(verts, dtype=np.float32)


def _grid_lines(half: int = 12, spacing: float = 0.85) -> np.ndarray:
    verts = []
    extent = half * spacing
    for i in range(-half, half + 1):
        d = i * spacing
        verts.extend([-extent, 0.0, d, extent, 0.0, d, d, 0.0, -extent, d, 0.0, extent])
    return np.array(verts, dtype=np.float32)


class ParticleSystem:
    def __init__(self, count: int = 400) -> None:
        self.count = count
        self.pos = np.zeros((count, 3), dtype=np.float32)
        self.vel = np.zeros((count, 3), dtype=np.float32)
        self.life = np.zeros(count, dtype=np.float32)
        self.size = np.ones(count, dtype=np.float32) * 0.08
        self.hue = np.zeros(count, dtype=np.float32)
        self._cursor = 0

    def emit(self, n: int, energy: float, beat: float) -> None:
        for _ in range(max(0, min(n, self.count))):
            i = self._cursor % self.count
            self._cursor += 1
            ang = np.random.random() * math.pi * 2
            elev = (np.random.random() - 0.3) * 0.8
            speed = 1.2 + energy * 3.5 + beat * 2.0
            self.pos[i] = [math.cos(ang) * 0.3, 0.4 + np.random.random() * 0.4, math.sin(ang) * 0.3]
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
        out = np.zeros((self.count, 7), dtype=np.float32)
        out[:, 0:3] = self.pos
        out[:, 3] = self.life
        out[:, 4] = self.size
        out[:, 5] = self.hue
        return out


class VisualizerRenderer:
    def __init__(self, band_count: int = BANDS) -> None:
        self.bands = band_count
        self.width = 1280
        self.height = 720
        self.internal_w = 240
        self.internal_h = 180
        self._t0 = time.perf_counter()
        self._last_t = self._t0
        self._angle = 0.0
        self._auto_rotate = True
        self._ready = False
        self.particles = ParticleSystem(400)
        self._spectrum = np.zeros(band_count, dtype=np.float32)
        self._analysis = AudioAnalysis()
        self.trail_decay = 0.78
        self.trail_scene_gain = 0.28
        self.trail_mix = 0.32
        self.trail_zoom = 0.998
        self.crt_barrel = 0.09
        self.crt_scanline = 0.92
        self.crt_vignette = 0.42
        self.exposure = 0.88
        self._fbo_scene = 0
        self._tex_scene = 0
        self._rbo_depth = 0
        self._fbo_trail = [0, 0]
        self._tex_trail = [0, 0]
        self._trail_idx = 0
        self._fbo_w = 0
        self._fbo_h = 0

    def init_gl(self) -> None:
        self.prog_bar = _link(BAR_VERT, BAR_FRAG)
        self.prog_orb = _link(ORB_VERT, ORB_FRAG)
        self.prog_grid = _link(GRID_VERT, GRID_FRAG)
        self.prog_bg = _link(BG_VERT, BG_FRAG)
        self.prog_part = _link(PART_VERT, PART_FRAG)
        self.prog_trail = _link(POST_VERT, TRAIL_FRAG)
        self.prog_post = _link(POST_VERT, POST_FRAG)

        bar = _unit_box()
        self.bar_vao = glGenVertexArrays(1)
        self.bar_vbo = glGenBuffers(1)
        self.bar_instance_vbo = glGenBuffers(1)
        glBindVertexArray(self.bar_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.bar_vbo)
        glBufferData(GL_ARRAY_BUFFER, bar.nbytes, bar, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 24, None)
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 24, _ctypes_offset(12))
        self._bar_instances = np.zeros((self.bands, 4), dtype=np.float32)
        radius = 3.2
        for i in range(self.bands):
            ang = (i / self.bands) * math.pi * 2.0 - math.pi * 0.5
            self._bar_instances[i] = [math.cos(ang) * radius, math.sin(ang) * radius, 0.05, float(i)]
        glBindBuffer(GL_ARRAY_BUFFER, self.bar_instance_vbo)
        glBufferData(GL_ARRAY_BUFFER, self._bar_instances.nbytes, self._bar_instances, GL_DYNAMIC_DRAW)
        glEnableVertexAttribArray(2)
        glVertexAttribPointer(2, 4, GL_FLOAT, GL_FALSE, 16, None)
        glVertexAttribDivisor(2, 1)
        self.bar_vertex_count = bar.shape[0] // 6

        orb = _uv_sphere(16, 22)
        self.orb_vao = glGenVertexArrays(1)
        self.orb_vbo = glGenBuffers(1)
        glBindVertexArray(self.orb_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.orb_vbo)
        glBufferData(GL_ARRAY_BUFFER, orb.nbytes, orb, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 24, None)
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 24, _ctypes_offset(12))
        self.orb_vertex_count = orb.shape[0] // 6

        grid = _grid_lines()
        self.grid_vao = glGenVertexArrays(1)
        self.grid_vbo = glGenBuffers(1)
        glBindVertexArray(self.grid_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.grid_vbo)
        glBufferData(GL_ARRAY_BUFFER, grid.nbytes, grid, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 12, None)
        self.grid_vertex_count = grid.shape[0] // 3

        self.part_vao = glGenVertexArrays(1)
        self.part_vbo = glGenBuffers(1)
        glBindVertexArray(self.part_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.part_vbo)
        empty = np.zeros((self.particles.count, 7), dtype=np.float32)
        glBufferData(GL_ARRAY_BUFFER, empty.nbytes, empty, GL_DYNAMIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 28, None)
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 4, GL_FLOAT, GL_FALSE, 28, _ctypes_offset(12))

        quad = np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype=np.float32)
        self.bg_vao = glGenVertexArrays(1)
        self.bg_vbo = glGenBuffers(1)
        glBindVertexArray(self.bg_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.bg_vbo)
        glBufferData(GL_ARRAY_BUFFER, quad.nbytes, quad, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 8, None)

        glUseProgram(self.prog_trail)
        glUniform1i(glGetUniformLocation(self.prog_trail, "uScene"), 0)
        glUniform1i(glGetUniformLocation(self.prog_trail, "uPrev"), 1)
        glUseProgram(self.prog_post)
        glUniform1i(glGetUniformLocation(self.prog_post, "uScene"), 0)
        glUniform1i(glGetUniformLocation(self.prog_post, "uTrail"), 1)
        glUseProgram(0)

        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_PROGRAM_POINT_SIZE)
        glEnable(GL_CULL_FACE)

        self._alloc_targets(self.internal_w, self.internal_h)
        self._ready = True

    def _make_tex(self, w: int, h: int) -> int:
        tex = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D, tex)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glBindTexture(GL_TEXTURE_2D, 0)
        return tex

    def _alloc_targets(self, w: int, h: int) -> None:
        tw, th = max(1, w), max(1, h)
        if tw == self._fbo_w and th == self._fbo_h and self._fbo_scene:
            return
        if self._fbo_scene:
            glDeleteFramebuffers(1, [self._fbo_scene])
            glDeleteTextures(1, [self._tex_scene])
            glDeleteRenderbuffers(1, [self._rbo_depth])
            for i in range(2):
                if self._fbo_trail[i]:
                    glDeleteFramebuffers(1, [self._fbo_trail[i]])
                    glDeleteTextures(1, [self._tex_trail[i]])

        self._tex_scene = self._make_tex(tw, th)
        self._rbo_depth = int(glGenRenderbuffers(1))
        glBindRenderbuffer(GL_RENDERBUFFER, self._rbo_depth)
        glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, tw, th)
        self._fbo_scene = int(glGenFramebuffers(1))
        glBindFramebuffer(GL_FRAMEBUFFER, self._fbo_scene)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self._tex_scene, 0)
        glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, self._rbo_depth)
        if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError("Scene FBO incomplete")

        for i in range(2):
            self._tex_trail[i] = self._make_tex(tw, th)
            self._fbo_trail[i] = int(glGenFramebuffers(1))
            glBindFramebuffer(GL_FRAMEBUFFER, self._fbo_trail[i])
            glFramebufferTexture2D(
                GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self._tex_trail[i], 0
            )
            glClearColor(0, 0, 0, 1)
            glClear(GL_COLOR_BUFFER_BIT)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        self._fbo_w, self._fbo_h = tw, th
        self._trail_idx = 0

    def resize(self, w: int, h: int) -> None:
        self.width = max(1, w)
        self.height = max(1, h)

    def set_analysis(self, analysis: AudioAnalysis) -> None:
        self._analysis = analysis
        if analysis.spectrum is not None and analysis.spectrum.size == self.bands:
            self._spectrum = self._spectrum * 0.35 + analysis.spectrum * 0.65

    def toggle_rotation(self) -> None:
        self._auto_rotate = not self._auto_rotate

    def render(self) -> None:
        if not self._ready:
            return
        now = time.perf_counter()
        dt = min(0.05, now - self._last_t)
        self._last_t = now
        t = now - self._t0
        a = self._analysis
        energy = float(np.clip(a.rms * 0.7 + a.bass * 0.5 + a.mid * 0.3, 0.0, 1.5))
        beat = float(a.beat)

        if self._auto_rotate:
            self._angle += dt * (0.18 + energy * 0.35 + beat * 0.5)

        emit_n = 0
        if beat > 0.25:
            emit_n += int(8 + beat * 40)
        if a.treble > 0.35:
            emit_n += int(a.treble * 12)
        emit_n = int(emit_n * 0.55)
        if emit_n:
            self.particles.emit(emit_n, energy, beat)
        self.particles.update(dt)

        for i in range(self.bands):
            h = float(self._spectrum[i])
            h = h * h * 2.8 + h * 1.2
            self._bar_instances[i, 2] = max(0.04, min(4.5, h * (0.9 + a.bass * 0.4)))

        aspect = self._fbo_w / max(self._fbo_h, 1)
        proj = perspective(52.0, aspect, 0.1, 80.0)
        cam_r = 9.5 - energy * 1.2 - beat * 0.8
        cam_h = 4.2 + a.mid * 0.8 + math.sin(t * 0.4) * 0.3
        eye = np.array(
            [math.cos(self._angle) * cam_r, cam_h, math.sin(self._angle) * cam_r],
            dtype=np.float32,
        )
        target = np.array([0.0, 0.9 + a.bass * 0.4, 0.0], dtype=np.float32)
        view = look_at(eye, target, np.array([0.0, 1.0, 0.0], dtype=np.float32))
        vp = mul(proj, view)
        model_i = np.eye(4, dtype=np.float32)

        # Scene offscreen
        glBindFramebuffer(GL_FRAMEBUFFER, self._fbo_scene)
        glViewport(0, 0, self._fbo_w, self._fbo_h)
        glClearColor(0.02, 0.03, 0.06, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glDisable(GL_DEPTH_TEST)
        glUseProgram(self.prog_bg)
        glUniform1f(glGetUniformLocation(self.prog_bg, "uTime"), t)
        glUniform1f(glGetUniformLocation(self.prog_bg, "uEnergy"), energy)
        glUniform1f(glGetUniformLocation(self.prog_bg, "uBeat"), beat)
        glBindVertexArray(self.bg_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)

        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glUseProgram(self.prog_grid)
        glUniformMatrix4fv(
            glGetUniformLocation(self.prog_grid, "uMVP"), 1, GL_TRUE, mul(vp, translation(0, -0.02, 0))
        )
        glUniform1f(glGetUniformLocation(self.prog_grid, "uBass"), a.bass)
        glUniform1f(glGetUniformLocation(self.prog_grid, "uEnergy"), energy)
        glUniform1f(glGetUniformLocation(self.prog_grid, "uBeat"), beat)
        glBindVertexArray(self.grid_vao)
        glDrawArrays(GL_LINES, 0, self.grid_vertex_count)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_DEPTH_TEST)

        glBindBuffer(GL_ARRAY_BUFFER, self.bar_instance_vbo)
        glBufferSubData(GL_ARRAY_BUFFER, 0, self._bar_instances.nbytes, self._bar_instances)
        glUseProgram(self.prog_bar)
        glUniformMatrix4fv(glGetUniformLocation(self.prog_bar, "uMVP"), 1, GL_TRUE, vp)
        glUniformMatrix4fv(glGetUniformLocation(self.prog_bar, "uModel"), 1, GL_TRUE, model_i)
        glUniform1f(glGetUniformLocation(self.prog_bar, "uTime"), t)
        glUniform1f(glGetUniformLocation(self.prog_bar, "uBass"), a.bass)
        glUniform3f(glGetUniformLocation(self.prog_bar, "uCamPos"), float(eye[0]), float(eye[1]), float(eye[2]))
        glUniform1f(glGetUniformLocation(self.prog_bar, "uBands"), float(self.bands))
        glUniform1f(glGetUniformLocation(self.prog_bar, "uBeat"), beat)
        glBindVertexArray(self.bar_vao)
        glDrawArraysInstanced(GL_TRIANGLES, 0, self.bar_vertex_count, self.bands)

        orb_s = 0.55 + a.bass * 0.45 + beat * 0.25
        orb_model = mul(translation(0.0, 1.1 + a.bass * 0.2, 0.0), scale(orb_s, orb_s, orb_s))
        glUseProgram(self.prog_orb)
        glUniformMatrix4fv(glGetUniformLocation(self.prog_orb, "uMVP"), 1, GL_TRUE, mul(vp, orb_model))
        glUniformMatrix4fv(glGetUniformLocation(self.prog_orb, "uModel"), 1, GL_TRUE, orb_model)
        glUniform1f(glGetUniformLocation(self.prog_orb, "uPulse"), float(np.clip(a.bass + beat, 0, 1.5)))
        glUniform1f(glGetUniformLocation(self.prog_orb, "uTime"), t)
        glUniform3f(glGetUniformLocation(self.prog_orb, "uCamPos"), float(eye[0]), float(eye[1]), float(eye[2]))
        glUniform1f(glGetUniformLocation(self.prog_orb, "uBass"), a.bass)
        glUniform1f(glGetUniformLocation(self.prog_orb, "uMid"), a.mid)
        glUniform1f(glGetUniformLocation(self.prog_orb, "uTreble"), a.treble)
        glUniform1f(glGetUniformLocation(self.prog_orb, "uBeat"), beat)
        glBindVertexArray(self.orb_vao)
        glDrawArrays(GL_TRIANGLES, 0, self.orb_vertex_count)

        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        pdata = self.particles.buffer_data()
        glBindBuffer(GL_ARRAY_BUFFER, self.part_vbo)
        glBufferSubData(GL_ARRAY_BUFFER, 0, pdata.nbytes, pdata)
        glUseProgram(self.prog_part)
        glUniformMatrix4fv(glGetUniformLocation(self.prog_part, "uVP"), 1, GL_TRUE, vp)
        glBindVertexArray(self.part_vao)
        glDrawArrays(GL_POINTS, 0, self.particles.count)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        # Trails
        src, dst = self._trail_idx, 1 - self._trail_idx
        decay = float(np.clip(self.trail_decay + energy * 0.008, 0.65, 0.88))
        gain = float(np.clip(self.trail_scene_gain + beat * 0.03, 0.18, 0.40))
        glBindFramebuffer(GL_FRAMEBUFFER, self._fbo_trail[dst])
        glViewport(0, 0, self._fbo_w, self._fbo_h)
        glDisable(GL_DEPTH_TEST)
        glUseProgram(self.prog_trail)
        glUniform1f(glGetUniformLocation(self.prog_trail, "uDecay"), decay)
        glUniform1f(glGetUniformLocation(self.prog_trail, "uSceneGain"), gain)
        glUniform1f(glGetUniformLocation(self.prog_trail, "uZoom"), self.trail_zoom)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self._tex_scene)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, self._tex_trail[src])
        glBindVertexArray(self.bg_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)
        self._trail_idx = dst
        trail_mix = float(np.clip(self.trail_mix + energy * 0.03, 0.18, 0.48))

        # Post to window
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glViewport(0, 0, self.width, self.height)
        glClearColor(0, 0, 0, 1)
        glClear(GL_COLOR_BUFFER_BIT)
        glUseProgram(self.prog_post)
        glUniform1f(glGetUniformLocation(self.prog_post, "uTrailMix"), trail_mix)
        glUniform1f(glGetUniformLocation(self.prog_post, "uEnergy"), energy)
        glUniform1f(glGetUniformLocation(self.prog_post, "uBeat"), beat)
        glUniform1f(glGetUniformLocation(self.prog_post, "uTime"), t)
        glUniform1f(glGetUniformLocation(self.prog_post, "uExposure"), self.exposure)
        glUniform1f(glGetUniformLocation(self.prog_post, "uBarrel"), self.crt_barrel)
        glUniform1f(glGetUniformLocation(self.prog_post, "uScanline"), self.crt_scanline)
        glUniform1f(glGetUniformLocation(self.prog_post, "uVignette"), self.crt_vignette)
        glUniform2f(glGetUniformLocation(self.prog_post, "uResolution"), float(self.width), float(self.height))
        glUniform2f(
            glGetUniformLocation(self.prog_post, "uInternal"),
            float(self._fbo_w),
            float(self._fbo_h),
        )
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self._tex_scene)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, self._tex_trail[self._trail_idx])
        glBindVertexArray(self.bg_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)
        glEnable(GL_DEPTH_TEST)
