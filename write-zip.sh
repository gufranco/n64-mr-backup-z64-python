#!/bin/bash
set -euo pipefail

EXPECTED_BYTES=100663296
IMG="${IMG:-z64-master.img}"
Z64KIT="${Z64KIT:-python3 -m z64kit.cli}"
ASSUME_YES=0
FULL=0
DISK=""

usage() {
  cat <<'USAGE'
usage: write-zip.sh <diskN> [-y] [--full]

  <diskN>   target device, for example disk8. Never /dev/diskN, just diskN.
  -y        skip the confirmation prompt.
  --full    write all 96 MB instead of only the filesystem metadata.

  Images carry no volume label and no serial, so two of them holding the same
  files are the same bytes. A disk gets a fresh serial on the way out. Real mode
  DOS, which is what the unit runs, uses the serial to notice that the media
  changed, and two disks sharing one can make it serve a cached FAT from the
  previous disk after a swap, which reads as corruption. There is no label
  option, by design.

  IMG=other.img write-zip.sh disk8    use a different master image.
  Z64KIT=z64kit write-zip.sh disk8    use an installed z64kit rather than the
                                      module in this checkout.
USAGE
  exit 1
}

for arg in "$@"; do
  case "$arg" in
    -y) ASSUME_YES=1 ;;
    --full) FULL=1 ;;
    -h | --help) usage ;;
    disk*) DISK="$arg" ;;
    *)
      echo "error: unknown argument: $arg" >&2
      usage
      ;;
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

PREP="$($Z64KIT payload "$IMG" "$TMP")" || {
  echo "$PREP" >&2
  exit 1
}

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
