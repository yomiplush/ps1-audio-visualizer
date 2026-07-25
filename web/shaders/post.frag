#version 300 es
precision mediump float;
in vec2 vUv;
uniform sampler2D uScene, uTrail;
uniform float uTrailMix, uEnergy, uBeat, uTime, uExposure, uBarrel, uScanline, uVignette;
uniform vec2 uInternal;
out vec4 FragColor;
vec2 crtBarrel(vec2 uv, float amount){
  if(amount < 1e-5) return uv;
  vec2 cc = uv*2.0-1.0;
  cc.x *= 1.0 + abs(cc.y)*amount*0.06;
  cc.y *= 1.0 + abs(cc.x)*amount*0.06;
  float r2 = dot(cc,cc);
  float f = 1.0 + r2*(amount + amount*0.25*r2);
  return cc*f*0.5+0.5;
}
vec3 quantize256(vec3 c){
  c=clamp(c,0.0,1.0);
  return vec3(floor(c.r*7.0+0.5)/7.0, floor(c.g*7.0+0.5)/7.0, floor(c.b*3.0+0.5)/3.0);
}
void main(){
  float barrel = uBarrel*(1.0+uEnergy*0.03);
  vec2 uv = crtBarrel(vUv, barrel);
  // Soft clamp instead of full black discard (was causing empty frame)
  vec2 edge = smoothstep(vec2(-0.02), vec2(0.02), uv) * smoothstep(vec2(-0.02), vec2(0.02), 1.0-uv);
  float inScreen = edge.x * edge.y;
  uv = clamp(uv, 0.001, 0.999);
  vec2 ires = max(uInternal, vec2(64.0,48.0));
  vec2 uvS = (floor(uv*ires)+0.5)/ires;
  vec3 scene = texture(uScene, uvS).rgb;
  vec3 trail = texture(uTrail, uvS).rgb * vec3(0.82,0.96,1.05);
  float mixAmt = clamp(uTrailMix,0.0,1.0)*(0.85+uEnergy*0.06);
  vec3 col = mix(scene, trail, mixAmt*0.40);
  col += max(trail-scene*0.55, 0.0)*mixAmt*0.25;
  col = mix(col, max(col, scene), 0.4);
  col *= uExposure;
  // Always keep a little lift so silent frames aren't pure black
  col = max(col, vec3(0.02, 0.025, 0.04));
  float py = gl_FragCoord.y;
  float mask = 1.0 - step(2.0, mod(floor(py), 4.0));
  float s = clamp(uScanline,0.0,1.0);
  col *= mix(1.0, mix(1.0,0.08,s), mask);
  col *= 0.97 + 0.03*sin(py*0.35 - uTime*1.6);
  vec2 vc = uvS*2.0-1.0;
  col *= 1.0 - uVignette*smoothstep(0.85,1.35,length(vc))*0.3;
  col = quantize256(col);
  col *= mix(0.15, 1.0, clamp(inScreen, 0.0, 1.0));
  FragColor = vec4(col, 1.0);
}
