#version 300 es
precision mediump float;
in vec2 vUv;
uniform float uTime, uEnergy, uBeat;
out vec4 FragColor;
void main(){
  vec2 p = vUv - 0.5;
  float r = length(p);
  vec3 col = mix(vec3(0.012,0.018,0.040), vec3(0.03,0.015,0.08), smoothstep(0.0,0.85,r));
  col = mix(col, vec3(0.0,0.045,0.075), 0.25 + 0.18*sin(uTime*0.28));
  float yBand = exp(-pow(p.y/(0.09+uEnergy*0.04+uBeat*0.03), 2.0));
  float xFall = 1.0 - smoothstep(0.05, 0.72, abs(p.x));
  float xGrad = p.x*0.5+0.5;
  vec3 hCol = mix(vec3(0.18,0.42,0.85), vec3(0.12,0.55,0.80), smoothstep(0.0,0.55,xGrad));
  hCol = mix(hCol, vec3(0.25,0.70,0.68), smoothstep(0.45,1.0,xGrad));
  float pulse = 0.10 + uEnergy*0.22 + uBeat*0.18;
  float wave = 0.88 + 0.12*sin(p.x*10.0 - uTime*1.4 + uBeat*2.0);
  col += hCol * yBand * xFall * pulse * wave;
  col += vec3(0.18,0.48,0.75) * exp(-r*r*7.5) * (0.05+uEnergy*0.12+uBeat*0.08);
  FragColor = vec4(col, 1.0);
}
