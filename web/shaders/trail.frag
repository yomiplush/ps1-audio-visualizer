#version 300 es
precision mediump float;
in vec2 vUv;
uniform sampler2D uScene, uPrev;
uniform float uDecay, uSceneGain, uZoom;
out vec4 FragColor;
void main(){
  vec2 uvPrev = clamp((vUv-0.5)*uZoom+0.5, 0.001, 0.999);
  vec3 scene = texture(uScene, vUv).rgb;
  vec3 prev = texture(uPrev, uvPrev).rgb;
  float lum = dot(scene, vec3(0.299,0.587,0.114));
  float hi = 1.0 + smoothstep(0.20,0.80,lum)*0.25;
  vec3 col = prev*uDecay + scene*uSceneGain*hi;
  col = col/(1.0+col*0.45);
  FragColor = vec4(clamp(col,0.0,1.2), 1.0);
}
