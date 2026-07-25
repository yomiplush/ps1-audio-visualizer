#version 300 es
precision mediump float;
in vec2 vUv;
uniform float uTime, uEnergy, uBeat;
out vec4 FragColor;
void main(){
  vec2 p = vUv - 0.5;
  float r = length(p);
  vec3 col = mix(vec3(0.012,0.018,0.040), vec3(0.03,0.015,0.08), smoothstep(0.0,0.85,r));
  float yBand = exp(-pow(p.y / (0.09 + uEnergy*0.04 + uBeat*0.03), 2.0));
  float xFall = 1.0 - smoothstep(0.05, 0.72, abs(p.x));
  vec3 hCol = mix(vec3(0.18,0.42,0.85), vec3(0.12,0.55,0.80), smoothstep(0.0,0.55,p.x*0.5+0.5));
  col += hCol * yBand * xFall * (0.12 + uEnergy*0.22 + uBeat*0.18);
  FragColor = vec4(col, 1.0);
}
