#!/bin/bash
set -euo pipefail

EXPECTED_BYTES=100663296
IMG="${IMG:-z64-master.img}"
Z64KIT="${Z64KIT:-python3 -m z64kit.cli}"
ASSUME_YES=0
FULL=0
EMPTY_OK=0
DISK=""

usage() {
  cat <<'USAGE'
usage: write-zip.sh <diskN> [-y] [--full] [--empty]

  <diskN>   target device, for example disk8. Never /dev/diskN, just diskN.
  -y        skip the confirmation prompt.
  --full    write all 96 MB instead of only the filesystem metadata.
  --empty   allow an image that holds no files. Refused otherwise, because
            writing one erases the disk and leaves nothing on it.

  Images carry no volume label and no serial, so two of them holding the same
  files are the same bytes. A disk gets a fresh serial on the way out. Real mode
  DOS, which is what the unit runs, uses the serial to notice that the media
  changed, and two disks sharing one can make it serve a cached FAT from the
  previous disk after a swap, which reads as corruption. There is no label
  option, by design.

  The disk is never mounted. It is written and read back through the raw
  device, so macOS never puts Spotlight or FSEvents data on it.

  Every chunk is timed on the way out and on the way back. A failed transfer,
  or one that collapses in speed, stops the run and ejects at once. That is as
  close to catching a click of death as software gets: the clicking itself is
  not visible here, but an I/O error and a sudden loss of throughput are, and
  both are what it does to the bus. Continuing past either risks the disk, the
  drive, and every disk put in that drive afterwards.

  Each chunk is also compared against what was written, so a disk that accepts
  bytes and returns different ones is caught at the chunk that failed.

  STALL_SECONDS=60 write-zip.sh disk8  per-chunk ceiling before stopping.
  SLOW_FACTOR=6 write-zip.sh disk8     stop when a chunk is this much slower
                                       than the fastest one so far.
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
    --empty) EMPTY_OK=1 ;;
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
trap 'rm -f "$TMP" "$TMP.back"' EXIT

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

if [ "$HIGH" -lt 2 ] && [ "$EMPTY_OK" != "1" ]; then
  fail "$IMG holds no files. Writing it would erase $DISK and leave a blank volume.
  If a blank disk is what you want, pass --empty. Otherwise you probably meant a
  built image: IMG=path/to/Zip_Disk_NN.img write-zip.sh $DISK"
fi

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

CHUNK_BYTES=$((8 * 1024 * 1024))
CHUNKS=$(((BYTES + CHUNK_BYTES - 1) / CHUNK_BYTES))
STALL_SECONDS="${STALL_SECONDS:-60}"
SLOW_FACTOR="${SLOW_FACTOR:-6}"
FASTEST=0

eject_now() {
  sync
  sudo diskutil eject "$DEV" >/dev/null 2>&1 && echo "  ejected $DEV" >&2
}

fault() {
  echo "" >&2
  echo "STOPPED: $1" >&2
  echo "  Ejecting immediately rather than continuing." >&2
  eject_now
  echo "" >&2
  echo "  A drive that clicks can damage the next disk it is given, and a disk" >&2
  echo "  that caused it can damage the next drive. Try neither again until you" >&2
  echo "  have tested each against something you are willing to lose." >&2
  exit 1
}

watch_for_stall() {
  local what="$1" index="$2" took="$3"
  if [ "$took" -gt "$STALL_SECONDS" ]; then
    fault "$what chunk $index of $CHUNKS took ${took}s, over the ${STALL_SECONDS}s limit.
  A transfer that slows this far has stopped making progress, which is what a
  head re-seeking on a bad track looks like from here."
  fi
  if [ "$FASTEST" -gt 0 ] && [ "$index" -gt 2 ] &&
    [ "$took" -gt $((FASTEST * SLOW_FACTOR)) ]; then
    fault "$what chunk $index of $CHUNKS took ${took}s against a best of ${FASTEST}s.
  Throughput collapsed by more than ${SLOW_FACTOR}x on the same drive and disk."
  fi
  if [ "$took" -gt 0 ] && { [ "$FASTEST" -eq 0 ] || [ "$took" -lt "$FASTEST" ]; }; then
    FASTEST="$took"
  fi
}

echo "writing     $CHUNKS chunks of $((CHUNK_BYTES / 1024 / 1024)) MiB, watching for stalls"
START=$(date +%s)
index=0
while [ "$index" -lt "$CHUNKS" ]; do
  chunk_started=$(date +%s)
  if ! sudo dd if="$TMP" of="$RAW" bs="$CHUNK_BYTES" skip="$index" seek="$index" \
    count=1 conv=notrunc 2>/dev/null; then
    fault "the write failed on chunk $index of $CHUNKS.
  An I/O error at this level means the drive could not complete the transfer."
  fi
  watch_for_stall "write" "$index" $(($(date +%s) - chunk_started))
  index=$((index + 1))
done
sync
END=$(date +%s)

diskutil unmountDisk force "$DEV" >/dev/null 2>&1 || true

echo "verifying   reading back through $RAW, never mounted"
FASTEST=0
index=0
while [ "$index" -lt "$CHUNKS" ]; do
  remaining=$((BYTES - index * CHUNK_BYTES))
  this_chunk=$((remaining < CHUNK_BYTES ? remaining : CHUNK_BYTES))
  chunk_started=$(date +%s)
  if ! sudo dd if="$RAW" bs="$CHUNK_BYTES" skip="$index" count=1 2>/dev/null |
    head -c "$this_chunk" >"$TMP.back"; then
    fault "the read failed on chunk $index of $CHUNKS.
  The bytes went down but will not come back, so the disk cannot be trusted."
  fi
  watch_for_stall "read" "$index" $(($(date +%s) - chunk_started))

  written="$(sudo dd if="$TMP" bs="$CHUNK_BYTES" skip="$index" count=1 2>/dev/null |
    shasum -a 256 | awk '{print $1}')"
  read_back="$(shasum -a 256 <"$TMP.back" | awk '{print $1}')"
  if [ "$written" != "$read_back" ]; then
    fault "chunk $index of $CHUNKS came back different from what was written.
  The write reported success, so the disk is not holding what it was given."
  fi
  index=$((index + 1))
done
rm -f "$TMP.back"

sudo diskutil eject "$DEV" >/dev/null 2>&1 && echo "ejected     $DEV, safe to remove"

echo "verify      OK, every chunk matched, sha256 $(shasum -a 256 <"$TMP" | awk '{print $1}')"
echo "elapsed     $((END - START))s"
