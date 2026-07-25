#version 300 es
layout(location=0) in vec3 aPos;
layout(location=1) in vec3 aNormal;
layout(location=2) in vec4 aInstance; // x,z,height,band
uniform mat4 uMVP;
uniform float uTime, uBass;
out float vHeight;
out float vBand;
out vec3 vNormal;
void main(){
  float h = max(aInstance.z, 0.02);
  vec3 pos = aPos;
  pos.y = (aPos.y + 0.5) * h;
  pos.x += aInstance.x;
  pos.z += aInstance.y;
  pos.y += sin(uTime*2.0 + aInstance.w*0.4)*0.02*uBass;
  vHeight = h;
  vBand = aInstance.w;
  vNormal = aNormal;
  gl_Position = uMVP * vec4(pos, 1.0);
}
