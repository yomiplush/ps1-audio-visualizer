#!/usr/bin/env bash
# GPU vendor detection for SoundOrbit AppImage / installer.
# shellcheck shell=bash
# Outputs space-separated tokens: AMD NVIDIA INTEL UNKNOWN (can be multiple for hybrid).

soundorbit_gpu_detect() {
  local found=()
  local pci="" drm="" mods=""

  if command -v lspci >/dev/null 2>&1; then
    pci="$(lspci -nn 2>/dev/null | grep -iE 'VGA|3D|Display' || true)"
  fi

  # DRM kernel drivers (reliable when lspci names are vague)
  local card driver vendor
  for card in /sys/class/drm/card[0-9]; do
    [[ -e "$card/device" ]] || continue
    driver="$(readlink -f "$card/device/driver" 2>/dev/null | xargs basename 2>/dev/null || true)"
    vendor="$(tr -d '\n' <"$card/device/vendor" 2>/dev/null || true)"
    drm+=" ${driver}:${vendor}"
    case "$driver" in
      amdgpu|radeon) found+=(AMD) ;;
      nvidia|nvidia_drm) found+=(NVIDIA) ;;
      i915|xe|xe_gpu) found+=(INTEL) ;;
    esac
    # PCI vendor IDs
    case "$vendor" in
      0x1002) found+=(AMD) ;;
      0x10de) found+=(NVIDIA) ;;
      0x8086) found+=(INTEL) ;;
    esac
  done

  # Loaded modules
  if [[ -r /proc/modules ]]; then
    mods="$(cut -d' ' -f1 /proc/modules 2>/dev/null || true)"
    echo "$mods" | grep -qx 'nvidia' && found+=(NVIDIA)
    echo "$mods" | grep -qx 'amdgpu' && found+=(AMD)
    echo "$mods" | grep -qx 'i915' && found+=(INTEL)
    echo "$mods" | grep -qx 'xe' && found+=(INTEL)
  fi
  [[ -e /dev/nvidia0 ]] && found+=(NVIDIA)

  # lspci text fallback
  local low
  low="$(printf '%s\n' "$pci" | tr '[:upper:]' '[:lower:]')"
  if echo "$low" | grep -qE 'nvidia|geforce|quadro|rtx |gtx '; then
    found+=(NVIDIA)
  fi
  if echo "$low" | grep -qE 'amd|ati |radeon|advanced micro devices'; then
    found+=(AMD)
  fi
  if echo "$low" | grep -qE 'intel'; then
    found+=(INTEL)
  fi

  # Unique preserve order
  local u=() x
  for x in "${found[@]+"${found[@]}"}"; do
    local seen=0 y
    for y in "${u[@]+"${u[@]}"}"; do
      [[ "$x" == "$y" ]] && seen=1 && break
    done
    [[ $seen -eq 0 ]] && u+=("$x")
  done

  if [[ ${#u[@]} -eq 0 ]]; then
    echo "UNKNOWN"
  else
    printf '%s\n' "${u[*]}"
  fi
}

# Primary GPU for env defaults (prefer discrete NVIDIA, else AMD, else INTEL)
soundorbit_gpu_primary() {
  local all
  all="$(soundorbit_gpu_detect)"
  if echo " $all " | grep -q ' NVIDIA '; then
    echo NVIDIA
  elif echo " $all " | grep -q ' AMD '; then
    echo AMD
  elif echo " $all " | grep -q ' INTEL '; then
    echo INTEL
  else
    echo UNKNOWN
  fi
}

soundorbit_gpu_describe() {
  local all primary
  all="$(soundorbit_gpu_detect)"
  primary="$(soundorbit_gpu_primary)"
  echo "GPUs: ${all} (primary=${primary})"
  if command -v lspci >/dev/null 2>&1; then
    lspci 2>/dev/null | grep -iE 'VGA|3D|Display' | sed 's/^/  /' || true
  fi
}
