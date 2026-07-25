#version 300 es
precision mediump float;
in vec2 vUv;
uniform float uTime, uEnergy, uBeat;
out vec4 FragColor;
void main(){
  vec2 p = vUv - 0.5;
  float r = length(p);
  vec3 col = mix(vec3(0.008,0.022,0.055), vec3(0.02,0.02,0.10), smoothstep(0.0,0.85,r));
  col = mix(col, vec3(0.0,0.06,0.12), 0.28 + 0.18*sin(uTime*0.28));
  float yBand = exp(-pow(p.y/(0.09+uEnergy*0.04+uBeat*0.03), 2.0));
  float xFall = 1.0 - smoothstep(0.05, 0.72, abs(p.x));
  float xGrad = p.x*0.5+0.5;
  vec3 hCol = mix(vec3(0.14,0.48,0.95), vec3(0.10,0.58,0.90), smoothstep(0.0,0.55,xGrad));
  hCol = mix(hCol, vec3(0.20,0.72,0.78), smoothstep(0.45,1.0,xGrad));
  float pulse = 0.12 + uEnergy*0.24 + uBeat*0.18;
  float wave = 0.88 + 0.12*sin(p.x*10.0 - uTime*1.4 + uBeat*2.0);
  col += hCol * yBand * xFall * pulse * wave;
  col += vec3(0.14,0.52,0.88) * exp(-r*r*7.0) * (0.07+uEnergy*0.14+uBeat*0.09);
  FragColor = vec4(col, 1.0);
}
