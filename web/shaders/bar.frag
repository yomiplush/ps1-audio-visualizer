#version 300 es
precision mediump float;
in float vHeight, vBand;
in vec3 vN;
uniform float uBands, uBeat;
out vec4 FragColor;
vec3 palette(float t){
  vec3 a=vec3(0.10,0.48,0.92), b=vec3(0.78,0.18,0.88), c=vec3(0.95,0.48,0.12);
  float s=smoothstep(0.0,1.0,t);
  vec3 col=mix(a,b,smoothstep(0.0,0.55,s));
  return mix(col,c,smoothstep(0.45,1.0,s));
}
void main(){
  vec3 N=normalize(vN);
  float diff=max(dot(N, normalize(vec3(0.4,1.0,0.3))), 0.0);
  float t=vBand/max(uBands-1.0,1.0);
  vec3 base=palette(t);
  float hNorm=clamp(vHeight/4.5,0.0,1.0);
  vec3 col=base*(0.28+diff*0.55+hNorm*0.18+uBeat*0.06);
  float peak=max(col.r,max(col.g,col.b));
  if(peak>0.92) col*=0.92/peak;
  FragColor=vec4(col,0.92);
}
