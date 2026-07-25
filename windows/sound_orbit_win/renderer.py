"""Windows OpenGL 3.3 visualizer — visual parity with Linux CRT / PS1 look."""

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
    GL_REPEAT,
    GL_RGBA,
    GL_UNPACK_ALIGNMENT,
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
    glLinkProgram,
    glRenderbufferStorage,
    glShaderSource,
    glTexImage2D,
    glPixelStorei,
    glTexParameteri,
    glTexSubImage2D,
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
# Shaders (aligned with Linux)
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
    float body=0.28+diff*0.55+hNorm*0.18+uBeat*0.06;
    vec3 col=base*body;
    col+=base*rim*0.28;
    float top=smoothstep(0.78,1.0,vWorldPos.y/max(vHeight,0.01));
    col+=base*top*0.18;
    float peak=max(col.r,max(col.g,col.b));
    if(peak>0.92) col*=0.92/peak;
    FragColor=vec4(col,0.90+rim*0.06);
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

# Ribbon rings/frames (TRIANGLE_STRIP) — Windows Core GL often drops thin GL_LINES.
RING_VERT = """
#version 330 core
layout(location=0) in vec3 aPos;   // world x,y,z on vertical band
layout(location=1) in float aT;    // 0..1 around ring
uniform mat4 uMVP; uniform float uTime; uniform float uEnergy; uniform float uPhase;
out float vAlpha; out float vT;
void main(){
    vT=aT;
    float wave=sin(aT*40.0-uTime*6.0+uPhase)*0.18*uEnergy;
    vec3 pos=aPos+vec3(0.0,wave,0.0);
    vAlpha=0.55+uEnergy*0.45;
    gl_Position=uMVP*vec4(pos,1.0);
}
"""

RING_FRAG = """
#version 330 core
in float vAlpha; in float vT; uniform float uHue; out vec4 FragColor;
vec3 hsv2rgb(vec3 c){
    vec3 p=abs(fract(c.xxx+vec3(0.,2./3.,1./3.))*6.-3.);
    return c.z*mix(vec3(1.),clamp(p-1.,0.,1.),c.y);
}
void main(){
    float edge=smoothstep(0.0,0.15,vT)*smoothstep(1.0,0.85,vT);
    float dash=0.65+0.35*smoothstep(0.2,0.5,abs(sin(vT*3.14159265*48.0)));
    vec3 col=hsv2rgb(vec3(fract(uHue+vT*0.15),0.85,1.0));
    FragColor=vec4(col,vAlpha*dash*(0.7+0.3*edge));
}
"""

FRAME_VERT = """
#version 330 core
layout(location=0) in vec3 aPos;
layout(location=1) in float aT;
uniform mat4 uMVP; uniform float uEnergy; uniform float uTime; uniform float uPhase;
out float vT; out float vPulse;
void main(){
    vT=aT;
    float wave=sin(aT*48.0-uTime*3.5+uPhase)*0.02*(0.5+uEnergy);
    vec3 pos=aPos+vec3(0.0,wave,0.0);
    vPulse=0.8+0.2*sin(uTime*4.0+aT*20.0);
    gl_Position=uMVP*vec4(pos,1.0);
}
"""

FRAME_FRAG = """
#version 330 core
in float vT; in float vPulse;
uniform vec3 uColor; uniform float uAlpha; uniform float uBeat;
out vec4 FragColor;
void main(){
    float dash=0.6+0.4*smoothstep(0.12,0.4,abs(sin(vT*3.14159265*40.0)));
    float a=clamp(uAlpha*vPulse*dash*(0.9+uBeat*0.25),0.0,1.0);
    vec3 col=uColor*(0.85+vPulse*0.4+uBeat*0.2);
    FragColor=vec4(col,a);
}
"""

LABEL_VERT = """
#version 330 core
layout(location=0) in vec3 aPos;
layout(location=1) in vec2 aUv;
uniform mat4 uMVP; uniform float uYOffset;
out vec2 vUv;
void main(){
    vUv=aUv;
    vec3 pos=aPos; pos.y+=uYOffset;
    gl_Position=uMVP*vec4(pos,1.0);
}
"""

LABEL_FRAG = """
#version 330 core
// Texture is premultiplied RGBA (rgb already * a). Blend with ONE, ONE_MINUS_SRC_ALPHA.
in vec2 vUv;
uniform sampler2D uTex;
uniform float uAlpha; uniform float uBeat; uniform float uEnergy;
out vec4 FragColor;
void main(){
    vec4 t=texture(uTex,vUv);
    // Soft vertical fade so the band mesh edges don't show as a hard quad
    float vFade=smoothstep(0.0,0.12,vUv.y)*smoothstep(1.0,0.88,vUv.y);
    float a=t.a*uAlpha*vFade;
    if(a<0.02) discard;
    float glow=0.90+uEnergy*0.18+uBeat*0.22;
    // Premultiplied output
    FragColor=vec4(t.rgb*glow*uAlpha*vFade, a);
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
    vec3 blue=vec3(0.20,0.55,1.0);
    vec3 cyan=vec3(0.35,0.85,1.0);
    vec3 col=mix(blue,cyan,clamp(uEnergy*0.55+uBeat*0.25,0.0,1.0));
    float core=1.0-smoothstep(0.0,6.0,vDist);
    float a=(0.22+uEnergy*0.28+uBeat*0.12+core*0.18)*fade;
    col*=0.85+core*0.45+uEnergy*0.25;
    FragColor=vec4(col,clamp(a,0.0,0.95));
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
    vec3 c0=vec3(0.012,0.018,0.040);
    vec3 c1=vec3(0.03,0.015,0.08);
    vec3 c2=vec3(0.0,0.045,0.075);
    vec3 col=mix(c0,c1,smoothstep(0.0,0.85,r));
    col=mix(col,c2,0.25+0.18*sin(uTime*0.28));
    float yBand=exp(-pow(p.y/(0.09+uEnergy*0.04+uBeat*0.03),2.0));
    float xFall=1.0-smoothstep(0.05,0.72,abs(p.x));
    float xGrad=p.x*0.5+0.5;
    vec3 cyanA=vec3(0.12,0.55,0.80);
    vec3 cyanB=vec3(0.18,0.42,0.85);
    vec3 cyanC=vec3(0.25,0.70,0.68);
    vec3 hCol=mix(cyanB,cyanA,smoothstep(0.0,0.55,xGrad));
    hCol=mix(hCol,cyanC,smoothstep(0.45,1.0,xGrad));
    float pulse=0.10+uEnergy*0.22+uBeat*0.18;
    float wave=0.88+0.12*sin(p.x*10.0-uTime*1.4+uBeat*2.0);
    col+=hCol*yBand*xFall*pulse*wave;
    float core=exp(-r*r*7.5)*(0.05+uEnergy*0.12+uBeat*0.08);
    col+=vec3(0.18,0.48,0.75)*core;
    col+=vec3(0.35,0.12,0.40)*uBeat*0.05*(yBand*0.5+(1.0-r)*0.3);
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
in vec2 vUv;
uniform sampler2D uScene; uniform sampler2D uPrev;
uniform float uDecay; uniform float uSceneGain; uniform float uZoom;
out vec4 FragColor;
void main(){
    vec2 centered=vUv-0.5;
    vec2 uvPrev=clamp(centered*uZoom+0.5,0.001,0.999);
    vec3 scene=texture(uScene,vUv).rgb;
    vec3 prev=texture(uPrev,uvPrev).rgb;
    float lum=dot(scene,vec3(0.299,0.587,0.114));
    float hiBoost=1.0+smoothstep(0.20,0.80,lum)*0.25;
    vec3 col=prev*uDecay+scene*uSceneGain*hiBoost;
    col=col/(1.0+col*0.45);
    FragColor=vec4(clamp(col,0.0,1.2),1.0);
}
"""

POST_FRAG = """
#version 330 core
in vec2 vUv;
uniform sampler2D uScene; uniform sampler2D uTrail;
uniform float uAberr; uniform float uTrailMix;
uniform float uEnergy; uniform float uBeat; uniform float uTime;
uniform float uExposure; uniform float uBarrel; uniform float uScanline;
uniform float uVignette; uniform vec2 uResolution; uniform vec2 uInternal;
out vec4 FragColor;

vec2 crtBarrel(vec2 uv,float amount){
    if(amount<1e-5) return uv;
    vec2 cc=uv*2.0-1.0;
    cc.x*=1.0+abs(cc.y)*amount*0.08;
    cc.y*=1.0+abs(cc.x)*amount*0.08;
    float r2=dot(cc,cc);
    float f=1.0+r2*(amount+amount*0.35*r2);
    cc*=f;
    return cc*0.5+0.5;
}

vec3 sampleSplit(sampler2D tex,vec2 uv,float amount){
    if(amount<1e-6) return texture(tex,uv).rgb;
    vec2 dir=uv-0.5;
    float dist=length(dir);
    vec2 radial=(dist>1e-5)?normalize(dir):vec2(1.0,0.0);
    vec2 shift=radial*amount*(0.35+dist*1.4)+vec2(amount*1.15,0.0);
    float r=texture(tex,clamp(uv+shift,0.0,1.0)).r;
    float g=texture(tex,clamp(uv,0.0,1.0)).g;
    float b=texture(tex,clamp(uv-shift,0.0,1.0)).b;
    return vec3(r,g,b);
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
    vec2 edge=smoothstep(vec2(-0.015),vec2(0.035),uv)
             *smoothstep(vec2(-0.015),vec2(0.035),1.0-uv);
    float inScreen=edge.x*edge.y;
    if(inScreen<1e-4){ FragColor=vec4(0.0,0.0,0.0,1.0); return; }

    vec2 ires=max(uInternal,vec2(64.0,48.0));
    vec2 uvS=clamp(uv,0.0,1.0);
    uvS=(floor(uvS*ires)+0.5)/ires;

    float edgeDist=length(uvS-0.5);
    float aberr=uAberr*(1.0+uEnergy*0.22+uBeat*0.30);
    aberr*=0.97+0.03*sin(uTime*5.5+uBeat*4.0);
    aberr*=1.0+edgeDist*0.8;
    if(aberr>1e-6) aberr=max(aberr,1.0/ires.x);

    vec3 scene=sampleSplit(uScene,uvS,aberr);
    vec3 trail=sampleSplit(uTrail,uvS,aberr*1.05);
    trail*=vec3(0.82,0.96,1.05);
    float mixAmt=clamp(uTrailMix,0.0,1.0)*(0.85+uEnergy*0.06+uBeat*0.05);
    vec3 col=mix(scene,trail,mixAmt*0.42);
    col+=max(trail-scene*0.55,0.0)*mixAmt*0.28;
    col=mix(col,max(col,scene),0.45);
    col*=uExposure;

    float py=gl_FragCoord.y;
    float slot=mod(floor(py),4.0);
    float mask=1.0-step(2.0,slot);
    float scanEdge=abs(mod(py,4.0)-1.5);
    float softMask=mix(mask,mask*0.85,smoothstep(0.5,1.5,scanEdge));
    float s=clamp(uScanline,0.0,1.0);
    // Hard CRT scanlines (very visible on Windows window framebuffer)
    col*=mix(1.0,mix(1.0,0.02,s),softMask);
    col*=0.97+0.03*sin(py*0.35-uTime*1.6+uBeat*2.0);
    // Extra phosphor strip every other line
    col*=mix(1.0,0.88,step(1.0,mod(floor(py),2.0))*s*0.5);

    vec2 vc=uvS*2.0-1.0;
    float soft=smoothstep(0.82,1.28,length(vc));
    float corner=pow(max(abs(vc.x),abs(vc.y)),3.0);
    corner=smoothstep(0.78,1.12,corner);
    float vigShape=clamp(soft*0.55+corner*0.45,0.0,1.0);
    col*=1.0-uVignette*vigShape*0.12;
    float frameA=smoothstep(0.0,0.12,inScreen);
    float vigA=1.0-uVignette*vigShape*0.55;
    float alpha=clamp(frameA*vigA,0.0,1.0);
    col*=mix(vec3(1.0),vec3(0.92,1.0,0.95),edgeDist*0.10*uVignette);

    col=quantize256(tonemap(col));
    FragColor=vec4(col*alpha,1.0);
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _ring_ribbon(segments: int = 192, radius: float = 3.5, half_h: float = 0.10) -> np.ndarray:
    """
    Vertical ribbon around Y axis — TRIANGLE_STRIP.
    Vertex: pos.xyz + t (float)  →  stride 16 bytes.
    Visible on all Windows GL drivers (unlike 1px lines).
    """
    verts: list[float] = []
    for i in range(segments + 1):
        t = i / segments
        ang = t * 2 * math.pi
        c, s = math.cos(ang), math.sin(ang)
        x, z = c * radius, s * radius
        verts.extend([x, -half_h, z, t, x, half_h, z, t])
    return np.array(verts, dtype=np.float32)


def _frame_ticks_ribbon(segments: int, radius: float, tick_len: float = 0.14, half_h: float = 0.035) -> np.ndarray:
    """Radial tick marks as tiny quads (triangles). Vertex: pos.xyz + t."""
    verts: list[float] = []
    for i in range(segments):
        t = i / segments
        ang = t * math.pi * 2.0
        c, s = math.cos(ang), math.sin(ang)
        x0, z0 = c * radius, s * radius
        x1, z1 = c * (radius + tick_len), s * (radius + tick_len)
        # two triangles (quad) in XZ with slight Y thickness
        # v0 bottom-in, v1 bottom-out, v2 top-out, v3 top-in
        y0, y1 = -half_h, half_h
        # tri1
        verts.extend([x0, y0, z0, t, x1, y0, z1, t, x1, y1, z1, t])
        # tri2
        verts.extend([x0, y0, z0, t, x1, y1, z1, t, x0, y1, z0, t])
    return np.array(verts, dtype=np.float32)


def _label_ring_band(segments: int = 160, radius: float = 4.45, half_h: float = 0.14) -> np.ndarray:
    verts = []
    for i in range(segments + 1):
        t = i / segments
        ang = t * math.pi * 2.0
        c, s = math.cos(ang), math.sin(ang)
        x, z = c * radius, s * radius
        verts.extend([x, -half_h, z, t, 0.0, x, half_h, z, t, 1.0])
    return np.array(verts, dtype=np.float32)


def _u_mat4(prog: int, name: str, mat: np.ndarray) -> None:
    loc = glGetUniformLocation(prog, name)
    if loc < 0:
        return
    m = np.ascontiguousarray(mat, dtype=np.float32)
    glUniformMatrix4fv(loc, 1, GL_TRUE, m)


def _u1f(prog: int, name: str, v: float) -> None:
    loc = glGetUniformLocation(prog, name)
    if loc >= 0:
        glUniform1f(loc, float(v))


def _u3f(prog: int, name: str, x: float, y: float, z: float) -> None:
    loc = glGetUniformLocation(prog, name)
    if loc >= 0:
        glUniform3f(loc, float(x), float(y), float(z))


def _unit_billboard_quad(w: float = 1.15, h: float = 0.48) -> np.ndarray:
    hw, hh = w * 0.5, h * 0.5
    return np.array(
        [
            -hw, -hh, 0.0, 0.0, 0.0,
             hw, -hh, 0.0, 1.0, 0.0,
             hw,  hh, 0.0, 1.0, 1.0,
            -hw, -hh, 0.0, 0.0, 0.0,
             hw,  hh, 0.0, 1.0, 1.0,
            -hw,  hh, 0.0, 0.0, 1.0,
        ],
        dtype=np.float32,
    )


# Tiny 5x7 bitmap font (A-Z, 0-9, space, punctuation) for green neon labels
_FONT: dict[str, tuple[str, ...]] = {
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01110"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01110", "10001", "10000", "01110", "00001", "10001", "01110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("01110", "10001", "00001", "00110", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ",": ("00000", "00000", "00000", "00000", "01100", "00100", "01000"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "/": ("00001", "00010", "00100", "01000", "10000", "00000", "00000"),
    "·": ("00000", "00000", "00100", "01110", "00100", "00000", "00000"),
    "™": ("11101", "01001", "01011", "00000", "01110", "00100", "00100"),
}


def _draw_glyph(rgba: np.ndarray, ch: str, ox: int, oy: int, scale: int, color: tuple[int, int, int, int]) -> int:
    rows = _FONT.get(ch.upper() if ch.isalpha() else ch, _FONT.get(ch, _FONT[" "]))
    h, w = rgba.shape[:2]
    for row, bits in enumerate(rows):
        for col, bit in enumerate(bits):
            if bit != "1":
                continue
            for dy in range(scale):
                for dx in range(scale):
                    y = oy + row * scale + dy
                    x = ox + col * scale + dx
                    if 0 <= y < h and 0 <= x < w:
                        rgba[y, x] = color
    return 5 * scale + scale  # advance


def _premultiply_rgba(rgba: np.ndarray) -> np.ndarray:
    """
    Convert straight RGBA → premultiplied RGBA (uint8).
    Prevents black fringes when LINEAR-filtering transparent text on Windows GL.
    """
    out = np.ascontiguousarray(rgba, dtype=np.uint8).copy()
    a = out[:, :, 3:4].astype(np.float32) * (1.0 / 255.0)
    rgb = out[:, :, :3].astype(np.float32)
    out[:, :, :3] = np.clip(rgb * a + 0.5, 0, 255).astype(np.uint8)
    return out


def _render_text_rgba(
    text: str,
    width: int,
    height: int,
    *,
    scale: int = 2,
    rgb: tuple[int, int, int] = (120, 255, 140),
    repeats: int = 1,
) -> np.ndarray:
    """
    CPU bitmap-font texture (no cairo). Fully transparent background —
    only glyphs have alpha (straight, then premultiplied by caller).
    """
    phrase = text if repeats <= 1 else (("  " + text + "  · ") * repeats)
    # Fully transparent — NO solid band (that broke transparency on Windows)
    rgba = np.zeros((height, width, 4), dtype=np.uint8)

    glyph_w = 5 * scale + scale
    ox = 4
    oy = max(1, (height - 7 * scale) // 2)
    # Straight alpha colors (premultiply later)
    color = (rgb[0], rgb[1], rgb[2], 255)
    glow = (min(255, rgb[0] // 2 + 20), min(255, rgb[1]), min(255, rgb[2] // 2 + 20), 90)

    x = ox
    guard = 0
    while x < width - glyph_w and guard < 4000:
        for ch in phrase:
            # Soft glow first (lower alpha), then solid glyph
            _draw_glyph(rgba, ch, x + 1, oy + 1, scale, glow)
            adv = _draw_glyph(rgba, ch, x, oy, scale, color)
            x += adv
            guard += 1
            if x >= width - 4:
                break
        if repeats <= 1:
            break
    # OpenGL bottom-left origin
    return np.ascontiguousarray(np.flipud(rgba))


def _make_label_texture(text: str, width: int, height: int, repeats: int = 2) -> tuple[np.ndarray, int, int]:
    """Build orbiting-label texture → premultiplied RGBA."""
    # Prefer cairo if present (dev machines), else bitmap font
    try:
        import cairo  # type: ignore

        phrase = f"  {text}  · " * repeats
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surface)
        ctx.set_operator(cairo.OPERATOR_CLEAR)
        ctx.paint()
        ctx.set_operator(cairo.OPERATOR_OVER)
        ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        font_size = height * 0.78
        ctx.set_font_size(font_size)
        xb, yb, tw, th, _dx, _dy = ctx.text_extents(phrase)
        if tw > width * 0.98:
            font_size *= (width * 0.98) / max(tw, 1.0)
            ctx.set_font_size(font_size)
            xb, yb, tw, th, _dx, _dy = ctx.text_extents(phrase)
        x = (width - tw) * 0.5 - xb
        y = height * 0.5 - (yb + th * 0.5)
        for blur_a, grow in ((0.12, 3.0), (0.22, 1.5), (0.55, 0.0)):
            ctx.set_source_rgba(0.15, 1.0, 0.35, blur_a)
            ctx.move_to(x, y + grow * 0.15)
            ctx.set_font_size(font_size + grow)
            ctx.show_text(phrase)
            ctx.set_font_size(font_size)
        ctx.set_source_rgba(0.55, 1.0, 0.65, 1.0)
        ctx.move_to(x, y)
        ctx.show_text(phrase)
        buf = surface.get_data()
        img = np.ndarray(shape=(height, width, 4), dtype=np.uint8, buffer=buf).copy()
        b, g, r, a = img[:, :, 0], img[:, :, 1], img[:, :, 2], img[:, :, 3]
        rgba = np.ascontiguousarray(np.flipud(np.stack([r, g, b, a], axis=-1)))
        return _premultiply_rgba(rgba), width, height
    except Exception:
        sc = max(2, height // 28)
        straight = _render_text_rgba(text, width, height, scale=sc, repeats=repeats)
        return _premultiply_rgba(straight), width, height


def _param_text_rgba(lines: list[str], width: int = 320, height: int = 120) -> np.ndarray:
    """Param billboard texture → premultiplied RGBA, transparent background."""
    try:
        import cairo  # type: ignore

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surface)
        ctx.set_operator(cairo.OPERATOR_CLEAR)
        ctx.paint()
        ctx.set_operator(cairo.OPERATOR_OVER)
        ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        n = max(1, len(lines))
        font_size = height * 0.38 / max(1.0, n * 0.55)
        ctx.set_font_size(font_size)
        line_h = font_size * 1.15
        y0 = (height - line_h * n) * 0.5 + font_size * 0.85
        for i, line in enumerate(lines):
            xb, yb, tw, th, _dx, _dy = ctx.text_extents(line)
            x = (width - tw) * 0.5 - xb
            y = y0 + i * line_h
            for blur_a, grow in ((0.15, 2.0), (0.35, 0.8), (0.9, 0.0)):
                ctx.set_source_rgba(0.45, 1.0, 0.55, blur_a)
                ctx.set_font_size(font_size + grow)
                ctx.move_to(x, y)
                ctx.show_text(line)
            ctx.set_font_size(font_size)
        buf = surface.get_data()
        img = np.ndarray(shape=(height, width, 4), dtype=np.uint8, buffer=buf).copy()
        b, g, r, a = img[:, :, 0], img[:, :, 1], img[:, :, 2], img[:, :, 3]
        rgba = np.ascontiguousarray(np.flipud(np.stack([r, g, b, a], axis=-1)))
        return _premultiply_rgba(rgba)
    except Exception:
        rgba = np.zeros((height, width, 4), dtype=np.uint8)
        sc = max(2, height // 40)
        for i, line in enumerate(lines[:2]):
            y = 8 + i * (height // 2)
            _render_into(rgba, line.upper(), 8, y, sc)
        return _premultiply_rgba(np.ascontiguousarray(np.flipud(rgba)))


def _render_into(rgba: np.ndarray, text: str, ox: int, oy: int, scale: int) -> None:
    x = ox
    color = (115, 255, 140, 255)
    glow = (40, 120, 50, 100)
    for ch in text:
        _draw_glyph(rgba, ch, x + 1, oy + 1, scale, glow)
        x += _draw_glyph(rgba, ch, x, oy, scale, color)


def _upload_rgba_texture(
    tex: int,
    rgba: np.ndarray,
    *,
    nearest: bool = False,
    wrap_s=None,
) -> None:
    """Upload premultiplied RGBA with correct unpack alignment."""
    if wrap_s is None:
        wrap_s = GL_CLAMP_TO_EDGE
    h, w = rgba.shape[:2]
    data = np.ascontiguousarray(rgba, dtype=np.uint8)
    glBindTexture(GL_TEXTURE_2D, tex)
    try:
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
    except Exception:
        pass
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
    filt = GL_NEAREST if nearest else GL_LINEAR
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, filt)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, filt)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, wrap_s)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)


PARAM_SPECS: list[tuple[str, str]] = [
    ("bass", "BASS"),
    ("mid", "MID"),
    ("treble", "TREBLE"),
    ("rms", "RMS"),
    ("peak", "PEAK"),
    ("beat", "BEAT"),
]


class ParticleSystem:
    def __init__(self, count: int = 400) -> None:
        self.count = count
        self.pos = np.zeros((count, 3), dtype=np.float32)
        self.vel = np.zeros((count, 3), dtype=np.float32)
        self.life = np.zeros(count, dtype=np.float32)
        self.size = np.ones(count, dtype=np.float32) * 0.08
        self.hue = np.zeros(count, dtype=np.float32)
        self._cursor = 0
        # Reused every frame — never allocate in the hot path
        self._buf = np.zeros((count, 7), dtype=np.float32)

    def clear(self) -> None:
        self.life[:] = 0.0
        self.pos[:] = 0.0
        self.vel[:] = 0.0

    def emit(self, n: int, energy: float, beat: float) -> None:
        n = max(0, min(int(n), self.count))
        for _ in range(n):
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
        out = self._buf
        out[:, 0:3] = self.pos
        out[:, 3] = self.life
        out[:, 4] = self.size
        out[:, 5] = self.hue
        out[:, 6] = 0.0
        return out


class VisualizerRenderer:
    def __init__(self, band_count: int = BANDS, profile: Optional[object] = None) -> None:
        self.bands = band_count
        self.width = 1280
        self.height = 720
        self.internal_w = 240
        self.internal_h = 180
        self.particle_emit_scale = 0.55
        self.orb_stacks = 16
        self.orb_slices = 22
        self.ring_segments = 160
        self.ring_radii = (2.0, 4.0, 5.5)
        self.grid_half = 12
        self.grid_spacing = 0.85
        self._t0 = time.perf_counter()
        self._last_t = self._t0
        self._angle = 0.0
        self._frame_angle = 0.0
        self._label_angle = 0.0
        self._auto_rotate = True
        self._ready = False
        particle_n = 400
        # Strong CRT defaults (must be obvious on Windows)
        self.trail_decay = 0.82
        self.trail_scene_gain = 0.36
        self.trail_mix = 0.42
        self.trail_zoom = 0.997
        self.aberration = 0.0014
        self.crt_barrel = 0.11
        self.crt_scanline = 0.98
        self.crt_vignette = 0.48
        self.exposure = 0.90
        self.enable_trails = True
        self.frame_radius = 3.85
        self.label_radius = 4.55
        self.outer_radius = 5.9
        self.outer_y = 0.55
        self.param_radius = 5.2
        self.param_y = 2.85
        self._param_timer = 0.0
        self._param_interval = 0.10
        self._param_last = [""] * len(PARAM_SPECS)
        self._param_texs: list[int] = []
        self._param_tw, self._param_th = 320, 120
        # Resource guardian knobs (updated every tick)
        self._runtime_throttle = 1.0
        self._runtime_trails_ok = True
        self._runtime_labels_ok = True
        self._runtime_param_scale = 1.0
        self._skip_heavy_frame = False
        self._frame_i = 0

        if profile is not None:
            self.internal_w = int(getattr(profile, "internal_w", self.internal_w))
            self.internal_h = int(getattr(profile, "internal_h", self.internal_h))
            particle_n = int(getattr(profile, "particle_count", particle_n))
            self.particle_emit_scale = float(getattr(profile, "particle_emit_scale", self.particle_emit_scale))
            self.trail_decay = float(getattr(profile, "trail_decay", self.trail_decay))
            self.trail_scene_gain = float(getattr(profile, "trail_scene_gain", self.trail_scene_gain))
            self.trail_mix = float(getattr(profile, "trail_mix", self.trail_mix))
            self.crt_barrel = float(getattr(profile, "crt_barrel", self.crt_barrel))
            self.crt_scanline = float(getattr(profile, "crt_scanline", self.crt_scanline))
            self.crt_vignette = float(getattr(profile, "crt_vignette", self.crt_vignette))
            self.exposure = float(getattr(profile, "exposure", self.exposure))
            self.aberration = float(getattr(profile, "aberration", self.aberration))
            self.orb_stacks = int(getattr(profile, "orb_stacks", self.orb_stacks))
            self.orb_slices = int(getattr(profile, "orb_slices", self.orb_slices))
            self.ring_segments = int(getattr(profile, "ring_segments", self.ring_segments))
            radii = getattr(profile, "ring_radii", None)
            if radii:
                self.ring_radii = tuple(radii)
            self.grid_half = int(getattr(profile, "grid_half", self.grid_half))
            self.grid_spacing = float(getattr(profile, "grid_spacing", self.grid_spacing))
            if getattr(profile, "trails", True) is False:
                self.trail_mix = min(self.trail_mix, 0.22)
            if getattr(profile, "rgb_shift", True) is False:
                self.aberration = max(self.aberration * 0.35, 0.0004)
            self.crt_scanline = max(self.crt_scanline, 0.75)
            self.crt_barrel = max(self.crt_barrel, 0.06)
            self.enable_trails = True

        self.particles = ParticleSystem(particle_n)

    def apply_resource_state(
        self,
        *,
        throttle: float = 1.0,
        trails_allowed: bool = True,
        labels_allowed: bool = True,
        param_update_scale: float = 1.0,
    ) -> None:
        """Called by ResourceGuardian — scales GPU/CPU work without reallocating GL."""
        self._runtime_throttle = float(np.clip(throttle, 0.25, 1.0))
        self._runtime_trails_ok = bool(trails_allowed)
        self._runtime_labels_ok = bool(labels_allowed)
        self._runtime_param_scale = float(np.clip(param_update_scale, 0.15, 1.0))

    def purge_runtime(self) -> None:
        """
        Memory pressure release: kill particles, clear trail FBOs, drop param cache.
        Safe to call with GL context current.
        """
        try:
            self.particles.clear()
        except Exception:
            pass
        # Clear trail accumulation (large GPU textures)
        if self._ready and self._fbo_trail[0]:
            try:
                for i in range(2):
                    if self._fbo_trail[i]:
                        glBindFramebuffer(GL_FRAMEBUFFER, self._fbo_trail[i])
                        glClearColor(0.0, 0.0, 0.0, 1.0)
                        glClear(GL_COLOR_BUFFER_BIT)
                glBindFramebuffer(GL_FRAMEBUFFER, 0)
            except Exception:
                try:
                    glBindFramebuffer(GL_FRAMEBUFFER, 0)
                except Exception:
                    pass
        self._param_last = [""] * len(PARAM_SPECS)
        self._param_timer = 0.0
        self._trail_idx = 0
        self._spectrum = np.zeros(band_count, dtype=np.float32)
        self._analysis = AudioAnalysis()
        self._fbo_scene = 0
        self._tex_scene = 0
        self._rbo_depth = 0
        self._fbo_trail = [0, 0]
        self._tex_trail = [0, 0]
        self._trail_idx = 0
        self._fbo_w = 0
        self._fbo_h = 0
        self._label_tex = 0
        self._outer_tex = 0

    def init_gl(self) -> None:
        self.prog_bar = _link(BAR_VERT, BAR_FRAG)
        self.prog_orb = _link(ORB_VERT, ORB_FRAG)
        self.prog_ring = _link(RING_VERT, RING_FRAG)
        self.prog_frame = _link(FRAME_VERT, FRAME_FRAG)
        self.prog_label = _link(LABEL_VERT, LABEL_FRAG)
        self.prog_grid = _link(GRID_VERT, GRID_FRAG)
        self.prog_bg = _link(BG_VERT, BG_FRAG)
        self.prog_part = _link(PART_VERT, PART_FRAG)
        self.prog_trail = _link(POST_VERT, TRAIL_FRAG)
        self.prog_post = _link(POST_VERT, POST_FRAG)

        # Bars
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

        # Orb
        orb = _uv_sphere(self.orb_stacks, self.orb_slices)
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

        # Energy rings (thick ribbons — always visible on Windows)
        self.ring_vaos = []
        self.ring_counts = []
        segs_r = max(96, int(self.ring_segments))
        for ri, r in enumerate(self.ring_radii):
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
            glVertexAttribPointer(1, 1, GL_FLOAT, GL_FALSE, 16, _ctypes_offset(12))
            self.ring_vaos.append(vao)
            self.ring_counts.append(ring.shape[0] // 4)  # verts (pos3+t)

        # Green frame ribbons + tick quads
        segs = max(128, segs_r)
        self.frame_vaos = []
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
            glVertexAttribPointer(1, 1, GL_FLOAT, GL_FALSE, 16, _ctypes_offset(12))
            self.frame_vaos.append(vao)
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
        glVertexAttribPointer(1, 1, GL_FLOAT, GL_FALSE, 16, _ctypes_offset(12))
        self.frame_vaos.append(vao)
        self.frame_counts.append(ticks.shape[0] // 4)
        self.frame_modes.append(GL_TRIANGLES)

        # Labels
        label_mesh = _label_ring_band(192, self.label_radius, 0.28)
        self.label_vao = glGenVertexArrays(1)
        self.label_vbo = glGenBuffers(1)
        glBindVertexArray(self.label_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.label_vbo)
        glBufferData(GL_ARRAY_BUFFER, label_mesh.nbytes, label_mesh, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 20, None)
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 20, _ctypes_offset(12))
        self.label_vertex_count = label_mesh.shape[0] // 5
        rgba, tw, th = _make_label_texture("AUDIO VISUALIZER", 2048, 160, repeats=2)
        self._label_tex = int(glGenTextures(1))
        # LINEAR + premultiplied avoids black fringes; REPEAT for cylinder UV
        _upload_rgba_texture(self._label_tex, rgba, nearest=False, wrap_s=GL_REPEAT)

        outer_mesh = _label_ring_band(160, self.outer_radius, 0.20)
        self.outer_vao = glGenVertexArrays(1)
        self.outer_vbo = glGenBuffers(1)
        glBindVertexArray(self.outer_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.outer_vbo)
        glBufferData(GL_ARRAY_BUFFER, outer_mesh.nbytes, outer_mesh, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 20, None)
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 20, _ctypes_offset(12))
        self.outer_vertex_count = outer_mesh.shape[0] // 5
        slogan = "Visualized Audio World for better future"
        rgba_o, tw_o, th_o = _make_label_texture(slogan, 2560, 140, repeats=2)
        self._outer_tex = int(glGenTextures(1))
        _upload_rgba_texture(self._outer_tex, rgba_o, nearest=False, wrap_s=GL_REPEAT)

        # Param billboards
        pq = _unit_billboard_quad(1.15, 0.48)
        self.param_vao = glGenVertexArrays(1)
        self.param_vbo = glGenBuffers(1)
        glBindVertexArray(self.param_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.param_vbo)
        glBufferData(GL_ARRAY_BUFFER, pq.nbytes, pq, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 20, None)
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 20, _ctypes_offset(12))
        self.param_vertex_count = 6
        self._param_texs = []
        self._param_last = []
        for _key, label in PARAM_SPECS:
            tex = int(glGenTextures(1))
            rgba0 = _param_text_rgba([label, "0.00"], self._param_tw, self._param_th)
            _upload_rgba_texture(tex, rgba0, nearest=False, wrap_s=GL_CLAMP_TO_EDGE)
            self._param_texs.append(tex)
            self._param_last.append(f"{label}|0.00")

        # Grid / particles / bg quad
        grid = _grid_lines(self.grid_half, self.grid_spacing)
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
        glUseProgram(self.prog_label)
        glUniform1i(glGetUniformLocation(self.prog_label, "uTex"), 0)
        glUseProgram(0)

        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_PROGRAM_POINT_SIZE)
        glEnable(GL_CULL_FACE)

        try:
            glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        except Exception:
            pass

        self._alloc_targets(self.internal_w, self.internal_h)
        self._ready = True
        # Marker string must appear in shipped exe for verification
        print(
            f"[SoundOrbit-Win] visual stack READY "
            f"CRT+trails+ribbons+frames+labels  "
            f"internal={self.internal_w}x{self.internal_h}  "
            f"rings={len(self.ring_vaos)} frames={len(self.frame_vaos)}  "
            f"scan={self.crt_scanline:.2f} trail={self.trail_mix:.2f} aberr={self.aberration:.4f}",
            flush=True,
        )

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

    def _upload_param(self, index: int, label: str, value: float) -> None:
        txt = f"{value:.3f}" if label == "PEAK" else f"{value:.2f}"
        key = f"{label}|{txt}"
        if key == self._param_last[index]:
            return
        self._param_last[index] = key
        rgba = _param_text_rgba([label, txt], self._param_tw, self._param_th)
        glBindTexture(GL_TEXTURE_2D, self._param_texs[index])
        try:
            glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        except Exception:
            pass
        glTexSubImage2D(
            GL_TEXTURE_2D,
            0,
            0,
            0,
            self._param_tw,
            self._param_th,
            GL_RGBA,
            GL_UNSIGNED_BYTE,
            np.ascontiguousarray(rgba, dtype=np.uint8),
        )

    def _update_params(self, a: AudioAnalysis) -> None:
        values = {
            "bass": a.bass,
            "mid": a.mid,
            "treble": a.treble,
            "rms": a.rms,
            "peak": min(a.peak, 9.999),
            "beat": a.beat,
        }
        for i, (key, label) in enumerate(PARAM_SPECS):
            self._upload_param(i, label, float(values.get(key, 0.0)))

    @staticmethod
    def _billboard_model(pos: np.ndarray, view: np.ndarray, scale_s: float = 1.0) -> np.ndarray:
        right = view[0, 0:3].astype(np.float32)
        up = view[1, 0:3].astype(np.float32)
        rn = float(np.linalg.norm(right)) + 1e-9
        un = float(np.linalg.norm(up)) + 1e-9
        right = right / rn
        up = up / un
        fwd = np.cross(right, up)
        fn = float(np.linalg.norm(fwd)) + 1e-9
        fwd = fwd / fn
        m = np.eye(4, dtype=np.float32)
        m[0, 0:3] = right * scale_s
        m[1, 0:3] = up * scale_s
        m[2, 0:3] = fwd * scale_s
        m[0:3, 3] = pos
        return m

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
        thr = float(self._runtime_throttle)
        self._frame_i = (self._frame_i + 1) & 0x7FFFFFFF

        if self._auto_rotate:
            self._angle += dt * (0.18 + energy * 0.35 + beat * 0.5)
        self._frame_angle += dt * (0.22 + energy * 0.15 + beat * 0.35)
        self._label_angle -= dt * (0.07 + energy * 0.04 + beat * 0.06)

        emit_n = 0
        if beat > 0.25:
            emit_n += int(8 + beat * 40)
        if a.treble > 0.35:
            emit_n += int(a.treble * 12)
        # Throttle particle spawn under memory/CPU pressure
        emit_n = int(emit_n * float(self.particle_emit_scale) * thr)
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

        # ---- Scene offscreen (PS1 internal res) ----
        glBindFramebuffer(GL_FRAMEBUFFER, self._fbo_scene)
        glViewport(0, 0, self._fbo_w, self._fbo_h)
        glClearColor(0.02, 0.03, 0.06, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        glUseProgram(self.prog_bg)
        glUniform1f(glGetUniformLocation(self.prog_bg, "uTime"), t)
        glUniform1f(glGetUniformLocation(self.prog_bg, "uEnergy"), energy)
        glUniform1f(glGetUniformLocation(self.prog_bg, "uBeat"), beat)
        glBindVertexArray(self.bg_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)
        glEnable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)

        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glUseProgram(self.prog_grid)
        _u_mat4(self.prog_grid, "uMVP", mul(vp, translation(0, -0.02, 0)))
        _u1f(self.prog_grid, "uBass", a.bass)
        _u1f(self.prog_grid, "uEnergy", energy)
        _u1f(self.prog_grid, "uBeat", beat)
        glBindVertexArray(self.grid_vao)
        glDrawArrays(GL_LINES, 0, self.grid_vertex_count)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        # Bars
        glBindBuffer(GL_ARRAY_BUFFER, self.bar_instance_vbo)
        glBufferSubData(GL_ARRAY_BUFFER, 0, self._bar_instances.nbytes, self._bar_instances)
        glUseProgram(self.prog_bar)
        _u_mat4(self.prog_bar, "uMVP", vp)
        _u_mat4(self.prog_bar, "uModel", model_i)
        _u1f(self.prog_bar, "uTime", t)
        _u1f(self.prog_bar, "uBass", a.bass)
        _u3f(self.prog_bar, "uCamPos", float(eye[0]), float(eye[1]), float(eye[2]))
        _u1f(self.prog_bar, "uBands", float(self.bands))
        _u1f(self.prog_bar, "uBeat", beat)
        glBindVertexArray(self.bar_vao)
        glDrawArraysInstanced(GL_TRIANGLES, 0, self.bar_vertex_count, self.bands)

        # Orb
        orb_s = 0.55 + a.bass * 0.45 + beat * 0.25
        orb_model = mul(translation(0.0, 1.1 + a.bass * 0.2, 0.0), scale(orb_s, orb_s, orb_s))
        glUseProgram(self.prog_orb)
        _u_mat4(self.prog_orb, "uMVP", mul(vp, orb_model))
        _u_mat4(self.prog_orb, "uModel", orb_model)
        _u1f(self.prog_orb, "uPulse", float(np.clip(a.bass + beat, 0, 1.5)))
        _u1f(self.prog_orb, "uTime", t)
        _u3f(self.prog_orb, "uCamPos", float(eye[0]), float(eye[1]), float(eye[2]))
        _u1f(self.prog_orb, "uBass", a.bass)
        _u1f(self.prog_orb, "uMid", a.mid)
        _u1f(self.prog_orb, "uTreble", a.treble)
        _u1f(self.prog_orb, "uBeat", beat)
        glBindVertexArray(self.orb_vao)
        glDrawArrays(GL_TRIANGLES, 0, self.orb_vertex_count)

        # ---- Overlays: rings / green frame / labels (NO depth — always visible) ----
        glDisable(GL_DEPTH_TEST)
        glDepthMask(GL_FALSE)
        glDisable(GL_CULL_FACE)

        # Energy ribbons
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glUseProgram(self.prog_ring)
        for idx, vao in enumerate(self.ring_vaos):
            r_model = translation(0.0, 0.20 + idx * 0.38 + a.bass * 0.25, 0.0)
            _u_mat4(self.prog_ring, "uMVP", mul(vp, r_model))
            _u1f(self.prog_ring, "uTime", t)
            _u1f(
                self.prog_ring,
                "uEnergy",
                float(np.clip(0.35 + energy * (1.0 - idx * 0.15) + a.treble * 0.4, 0, 1.8)),
            )
            _u1f(self.prog_ring, "uPhase", idx * 1.7)
            _u1f(self.prog_ring, "uHue", 0.55 + idx * 0.08 + t * 0.02)
            glBindVertexArray(vao)
            glDrawArrays(GL_TRIANGLE_STRIP, 0, self.ring_counts[idx])

        # Green neon frame ribbons
        frame_rot = rotation_y(self._frame_angle)
        frame_y = 0.15 + a.bass * 0.18
        green = (0.20, 1.0, 0.35)
        glUseProgram(self.prog_frame)
        for idx, vao in enumerate(self.frame_vaos):
            y_off = frame_y + (0.0 if idx >= 3 else idx * 0.05)
            mvp = mul(vp, mul(frame_rot, translation(0.0, y_off, 0.0)))
            _u_mat4(self.prog_frame, "uMVP", mvp)
            _u1f(self.prog_frame, "uEnergy", energy)
            _u1f(self.prog_frame, "uTime", t)
            _u1f(self.prog_frame, "uPhase", idx * 1.3)
            _u3f(self.prog_frame, "uColor", *green)
            alpha = 0.70 if idx == 3 else (1.0 if idx == 1 else 0.75)
            _u1f(self.prog_frame, "uAlpha", alpha)
            _u1f(self.prog_frame, "uBeat", beat)
            glBindVertexArray(vao)
            glDrawArrays(self.frame_modes[idx], 0, self.frame_counts[idx])

        # Orbiting labels — skip entirely under EMERGENCY / labels_allowed=False
        draw_labels = bool(self._runtime_labels_ok)
        # Under heavy throttle, draw text every other frame (cheap skip)
        if draw_labels and thr < 0.55 and (self._frame_i & 1):
            draw_labels = False
        if draw_labels:
            glEnable(GL_BLEND)
            glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
            glUseProgram(self.prog_label)
            label_y = 1.55 + a.bass * 0.22 + beat * 0.10
            label_model = mul(translation(0.0, label_y, 0.0), rotation_y(self._label_angle))
            _u_mat4(self.prog_label, "uMVP", mul(vp, label_model))
            _u1f(self.prog_label, "uYOffset", 0.0)
            _u1f(self.prog_label, "uAlpha", float(0.95 + beat * 0.04))
            _u1f(self.prog_label, "uBeat", beat)
            _u1f(self.prog_label, "uEnergy", energy)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self._label_tex)
            glBindVertexArray(self.label_vao)
            glDrawArrays(GL_TRIANGLE_STRIP, 0, self.label_vertex_count)

            outer_model = mul(
                translation(0.0, self.outer_y + a.bass * 0.10, 0.0),
                rotation_y(-self._frame_angle),
            )
            _u_mat4(self.prog_label, "uMVP", mul(vp, outer_model))
            _u1f(self.prog_label, "uAlpha", float(0.90 + beat * 0.06))
            glBindTexture(GL_TEXTURE_2D, self._outer_tex)
            glBindVertexArray(self.outer_vao)
            glDrawArrays(GL_TRIANGLE_STRIP, 0, self.outer_vertex_count)

            # Param billboards (CPU: cairo/bitmap only when interval hits)
            interval = self._param_interval / max(self._runtime_param_scale, 0.15)
            self._param_timer += dt
            if self._param_timer >= interval:
                self._param_timer = 0.0
                self._update_params(a)
            n_params = len(PARAM_SPECS)
            if self._param_texs and n_params > 0:
                glUseProgram(self.prog_label)
                _u1f(self.prog_label, "uYOffset", 0.0)
                _u1f(self.prog_label, "uBeat", beat)
                _u1f(self.prog_label, "uEnergy", energy)
                _u1f(self.prog_label, "uAlpha", float(0.92 + beat * 0.05))
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
                    _u_mat4(self.prog_label, "uMVP", mul(vp, model))
                    glActiveTexture(GL_TEXTURE0)
                    glBindTexture(GL_TEXTURE_2D, self._param_texs[i])
                    glDrawArrays(GL_TRIANGLES, 0, self.param_vertex_count)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        glEnable(GL_CULL_FACE)
        glDepthMask(GL_TRUE)
        glEnable(GL_DEPTH_TEST)

        # Particles
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        pdata = self.particles.buffer_data()
        glBindBuffer(GL_ARRAY_BUFFER, self.part_vbo)
        glBufferSubData(GL_ARRAY_BUFFER, 0, pdata.nbytes, pdata)
        glUseProgram(self.prog_part)
        _u_mat4(self.prog_part, "uVP", vp)
        glBindVertexArray(self.part_vao)
        glDrawArrays(GL_POINTS, 0, self.particles.count)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        # ---- Trails (disabled under HARD/EMERGENCY memory pressure) ----
        use_trails = bool(self.enable_trails and self._runtime_trails_ok)
        if use_trails:
            src, dst = self._trail_idx, 1 - self._trail_idx
            decay = float(np.clip(self.trail_decay + energy * 0.01 + beat * 0.015, 0.70, 0.92))
            gain = float(np.clip(self.trail_scene_gain + beat * 0.05 + energy * 0.02, 0.28, 0.55))
            zoom = float(self.trail_zoom - beat * 0.0008 - energy * 0.0004)
            glBindFramebuffer(GL_FRAMEBUFFER, self._fbo_trail[dst])
            glViewport(0, 0, self._fbo_w, self._fbo_h)
            glDisable(GL_DEPTH_TEST)
            glDisable(GL_BLEND)
            glUseProgram(self.prog_trail)
            _u1f(self.prog_trail, "uDecay", decay)
            _u1f(self.prog_trail, "uSceneGain", gain)
            _u1f(self.prog_trail, "uZoom", zoom)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self._tex_scene)
            glActiveTexture(GL_TEXTURE1)
            glBindTexture(GL_TEXTURE_2D, self._tex_trail[src])
            glBindVertexArray(self.bg_vao)
            glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)
            self._trail_idx = dst
            trail_tex = self._tex_trail[self._trail_idx]
            trail_mix = float(np.clip(self.trail_mix + energy * 0.05 + beat * 0.05, 0.30, 0.62))
        else:
            trail_tex = self._tex_scene
            trail_mix = 0.0

        # ---- CRT post to window (always — scanlines are cheap) ----
        aberr = float(max(self.aberration, 0.0005) * (1.0 + energy * 0.25 + beat * 0.15))
        if thr < 0.5:
            aberr *= 0.5  # slightly cheaper sampling when pressured
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glViewport(0, 0, self.width, self.height)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        glClearColor(0, 0, 0, 1)
        glClear(GL_COLOR_BUFFER_BIT)
        glUseProgram(self.prog_post)
        _u1f(self.prog_post, "uAberr", aberr)
        _u1f(self.prog_post, "uTrailMix", trail_mix)
        _u1f(self.prog_post, "uEnergy", energy)
        _u1f(self.prog_post, "uBeat", beat)
        _u1f(self.prog_post, "uTime", t)
        _u1f(self.prog_post, "uExposure", self.exposure)
        _u1f(self.prog_post, "uBarrel", max(self.crt_barrel, 0.06))
        _u1f(self.prog_post, "uScanline", max(self.crt_scanline, 0.85))
        _u1f(self.prog_post, "uVignette", max(self.crt_vignette, 0.35))
        glUniform2f(glGetUniformLocation(self.prog_post, "uResolution"), float(self.width), float(self.height))
        glUniform2f(
            glGetUniformLocation(self.prog_post, "uInternal"),
            float(max(1, self._fbo_w)),
            float(max(1, self._fbo_h)),
        )
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self._tex_scene)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, trail_tex)
        glBindVertexArray(self.bg_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBindVertexArray(0)
        glUseProgram(0)
