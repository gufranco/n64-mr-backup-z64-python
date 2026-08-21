#!/bin/bash
set -euo pipefail

EXPECTED_BYTES=100663296
IMG="${IMG:-z64-master.img}"
ASSUME_YES=0
FULL=0
DISK=""
LABEL=""

usage() {
  cat <<'USAGE'
usage: write-zip.sh <diskN> [LABEL] [-y] [--full]

  <diskN>   target device, for example disk8. Never /dev/diskN, just diskN.
  LABEL     optional FAT volume label, up to 11 characters.
  -y        skip the confirmation prompt.
  --full    write all 96 MB instead of only the filesystem metadata.

  Every disk gets a fresh volume serial. An image carries none, so without one
  every disk would look identical to real mode DOS, which uses the serial to
  notice that the media changed. Two disks sharing one can make it serve a cached
  FAT from the previous disk after a swap, which reads as corruption.

  IMG=other.img write-zip.sh disk8    use a different master image.
USAGE
  exit 1
}

for arg in "$@"; do
  case "$arg" in
    -y) ASSUME_YES=1 ;;
    --full) FULL=1 ;;
    -h | --help) usage ;;
    disk*) DISK="$arg" ;;
    *) LABEL="$arg" ;;
  esac
done

[ -n "$DISK" ] || usage
[ -f "$IMG" ] || {
  echo "error: image not found: $IMG" >&2
  exit 1
}

DEV="/dev/$DISK"
RAW="/dev/r$DISK"

INFO="$(diskutil info "$DISK" 2>/dev/null)" || {
  echo "error: no such device: $DISK" >&2
  exit 1
}

SIZE="$(printf '%s\n' "$INFO" | awk -F'[()]' '/^ *Disk Size:/ {print $2}' | awk '{print $1}')"
REMOVABLE="$(printf '%s\n' "$INFO" | awk -F': *' '/Removable Media:/ {print $2}')"
LOCATION="$(printf '%s\n' "$INFO" | awk -F': *' '/Device Location:/ {print $2}')"
MEDIANAME="$(printf '%s\n' "$INFO" | awk -F': *' '/Device \/ Media Name:/ {print $2}')"
VIRTUAL="$(printf '%s\n' "$INFO" | awk -F': *' '/^ *Virtual:/ {print $2}')"

fail() {
  echo "REFUSING TO WRITE: $1" >&2
  exit 1
}

[ "$SIZE" = "$EXPECTED_BYTES" ] || fail "$DISK is $SIZE bytes, a Zip 100 is $EXPECTED_BYTES"
[ "$LOCATION" = "External" ] || fail "$DISK is not an external device (Device Location: $LOCATION)"
printf '%s\n' "$REMOVABLE" | grep -qi removable || fail "$DISK is not removable media (Removable Media: $REMOVABLE)"
[ "$VIRTUAL" = "No" ] || fail "$DISK is a virtual device"

echo "target      $DEV"
echo "media       $MEDIANAME"
echo "size        $SIZE bytes, external, removable"
echo "image       $IMG"

TMP="$(mktemp "${TMPDIR:-/tmp}/z64payload.XXXXXX")"
trap 'rm -f "$TMP"' EXIT

PREP="$(python3 z64_prep.py "$IMG" "$TMP" ${LABEL:+"$LABEL"})"

if [ "$FULL" = "1" ]; then
  cp "$IMG" "$TMP.full"
  dd if="$TMP" of="$TMP.full" conv=notrunc 2>/dev/null
  mv "$TMP.full" "$TMP"
  SECTORS=$((EXPECTED_BYTES / 512))
  BYTES="$EXPECTED_BYTES"
else
  SECTORS="$(printf '%s\n' "$PREP" | awk -F= '/^SECTORS=/{print $2}')"
  BYTES="$(printf '%s\n' "$PREP" | awk -F= '/^BYTES=/{print $2}')"
fi

SERIAL="$(printf '%s\n' "$PREP" | awk -F= '/^SERIAL=/{print $2}')"
HIGH="$(printf '%s\n' "$PREP" | awk -F= '/^HIGHEST_CLUSTER=/{print $2}')"

echo "payload     $SECTORS sectors, $BYTES bytes (highest used cluster $HIGH)"
echo "serial      $SERIAL (fresh for this disk, the image carries none)"
[ -n "$LABEL" ] && echo "label       $LABEL"

if [ "$ASSUME_YES" != "1" ]; then
  printf 'Write to %s and destroy its contents? type YES: ' "$DEV"
  read -r reply
  [ "$reply" = "YES" ] || {
    echo "aborted"
    exit 1
  }
fi

sudo -v
diskutil unmountDisk force "$DEV" >/dev/null

BLOCK_BYTES_ACCEPTED_BY_BSD_AND_GNU_DD=1048576
BLOCKS=$(((BYTES + BLOCK_BYTES_ACCEPTED_BY_BSD_AND_GNU_DD - 1) / BLOCK_BYTES_ACCEPTED_BY_BSD_AND_GNU_DD))

START=$(date +%s)
sudo dd if="$TMP" of="$RAW" bs="$BLOCK_BYTES_ACCEPTED_BY_BSD_AND_GNU_DD" 2>&1 | tail -1
sync
END=$(date +%s)

WANT="$(shasum -a 256 <"$TMP" | awk '{print $1}')"
GOT="$(sudo dd if="$RAW" bs="$BLOCK_BYTES_ACCEPTED_BY_BSD_AND_GNU_DD" count="$BLOCKS" 2>/dev/null | head -c "$BYTES" | shasum -a 256 | awk '{print $1}')"

sudo diskutil eject "$DEV" >/dev/null 2>&1 && echo "ejected     $DEV, safe to remove"

if [ "$WANT" = "$GOT" ]; then
  echo "verify      OK, sha256 $WANT"
  echo "elapsed     $((END - START))s"
else
  echo "verify      FAILED" >&2
  echo "  expected  $WANT" >&2
  echo "  read back $GOT" >&2
  exit 1
fi
