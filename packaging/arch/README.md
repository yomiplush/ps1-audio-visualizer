# Arch / CachyOS package (Octopi)

Builds a real **pacman** package so Octopi can list and uninstall SoundOrbit.

## Why

| Install method | Octopi に出る？ |
|----------------|-----------------|
| `./install.sh` → `~/.local` | No |
| AppImage → `~/.local/bin` | No |
| **`pacman -U soundorbit-*.pkg.tar.zst`** | **Yes** |

## Build

```bash
# from repo root
./packaging/arch/build.sh
# → dist/soundorbit-<version>-1-any.pkg.tar.zst
```

## Install

```bash
./install-pacman.sh
# or
sudo pacman -U dist/soundorbit-*.pkg.tar.zst
```

## Uninstall

```bash
sudo pacman -R soundorbit
```

Octopi: search **`soundorbit`** → 削除.

## Package layout

| Path | Content |
|------|---------|
| `/usr/bin/sound-orbit` | launcher |
| `/usr/share/sound-orbit/` | Python app |
| `/usr/share/applications/io.github.yomiplush.SoundOrbit.desktop` | menu entry |
| `/usr/share/icons/hicolor/scalable/apps/io.github.yomiplush.SoundOrbit.svg` | icon |
