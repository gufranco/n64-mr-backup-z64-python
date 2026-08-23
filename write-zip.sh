#!/bin/bash
set -euo pipefail

IMG="${IMG:-z64-master.img}"
Z64KIT="${Z64KIT:-python3 -m z64kit.cli}"

usage() {
  cat <<'USAGE'
usage: write-zip.sh <device> [-y] [--full] [--empty]

  <device>  the disk to write to. disk8 on macOS, sdb on Linux.
  -y        skip the confirmation prompt.
  --full    write the whole image rather than only the part holding data.
  --empty   allow an image that holds no files.

  A thin wrapper over `z64kit write`, kept so an existing habit still works.
  Everything it does lives in the package, which is what a pip install gets and
  what runs on both macOS and Linux.

  The disk is never mounted, every chunk is compared against what was written,
  and a transfer that fails or collapses in speed stops the run and ejects.

  IMG=other.img write-zip.sh disk8    choose the image.
  Z64KIT=z64kit write-zip.sh sdb      use an installed z64kit.
USAGE
  exit 1
}

DEVICE=""
PASS_THROUGH=()

for arg in "$@"; do
  case "$arg" in
    -h | --help) usage ;;
    -y | --full | --empty) PASS_THROUGH+=("$arg") ;;
    -*)
      echo "error: unknown option: $arg" >&2
      usage
      ;;
    *) DEVICE="$arg" ;;
  esac
done

[ -n "$DEVICE" ] || usage
[ -f "$IMG" ] || {
  echo "error: image not found: $IMG" >&2
  exit 1
}

exec $Z64KIT write "$IMG" "$DEVICE" ${PASS_THROUGH[@]+"${PASS_THROUGH[@]}"}
