# SoundOrbit WebGL Demo

Static **WebGL2** PS1 CRT visualizer for **Cloudflare Pages** (or any static host).

## Features

- Low internal resolution + nearest upscale (chunky pixels)
- CRT post: scanlines, barrel, vignette, 256-color quantize
- Phosphor trail, ring spectrum bars, orbit camera
- **Mic-driven** via Web Audio API (or synth fallback if denied)
- ~18 fps PS1-style lock
- **No build step**

## Local

```bash
cd web
python3 -m http.server 8080
# open http://localhost:8080
```

Mic needs a **secure context** (localhost or HTTPS).

## Cloudflare Pages

| Setting | Value |
|---------|--------|
| Framework preset | None |
| Build command | *(leave empty)* |
| Build output directory | `web` |
| Root directory | `/` (repo root) |

Connect the GitHub repo `yomiplush/ps1-audio-visualizer`, branch `main`.  
Every push to `web/**` redeploys.

CLI (optional):

```bash
npx wrangler pages deploy web --project-name soundorbit-web
```

## Query params

- `?debug=1` — show FPS / band HUD

## Limits

Browsers cannot capture other apps’ system audio like desktop WASAPI/PipeWire.  
This demo uses the **microphone** (or a silent synth analyser if permission is denied).

## Files

```
web/
  index.html
  css/demo.css
  js/{main,audio,renderer,gl,math3d}.js
  shaders/*.{vert,frag}
```
