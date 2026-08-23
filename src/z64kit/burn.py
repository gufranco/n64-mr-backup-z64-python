"""Writing an image to a physical Zip disk, and refusing when that looks unwise.

Two obligations shape everything here, and neither is about speed.

A Zip drive that cannot find a track retracts the head and seeks again, over and
over. That is the click, and it can wreck the disk, then the drive, then every
disk put in that drive afterwards. Nothing in software can hear it. What it can
see is a transfer that fails outright, or one that collapses against what the
same drive managed a moment earlier, and both are what the clicking does to the
bus. Either one stops the run and ejects, because the cheapest moment to take a
suspect disk out is before the next block goes near it.

The disk is never mounted. Everything goes through the raw device, and the disk
is unmounted again between the write and the read, because macOS mounts a new
filesystem the moment it appears and then writes Spotlight and FSEvents data
onto media meant for a console.

The decisions are pure functions and a small state machine. The dd calls are the
shell around them, so the part that decides whether to abort a write can be
tested without a drive.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

CHUNK_BYTES = 8 * 1024 * 1024
CEILING_SECONDS = 60
SLOW_FACTOR = 6
WARMUP_CHUNKS = 3

SIZE_IN_BYTES = re.compile(r"Disk Size:.*?\((\d+) Bytes\)")
EXTERNAL_TRANSPORTS = frozenset({"usb", "ieee1394", "fw", "firewire"})


class DeviceError(ValueError):
    """The device could not be read, or is not one this will write to."""


class WriteFailedError(RuntimeError):
    """The write stopped part way, and the disk was ejected."""


@dataclass(frozen=True)
class Device:
    """A whole disk, described the same way whichever system reported it.

    `raw` is the node every transfer goes through. macOS has a character device
    that reads and writes without mounting; Linux has no separate node, and its
    block device does not mount by being written to, so there `raw` and `block`
    are the same. Both are set by whichever reader built this, rather than
    derived here, so the difference lives in one place.
    """

    node: str
    size: int
    media: str
    removable: bool
    external: bool
    virtual: bool
    block: str
    raw: str


def _field(text: str, label: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{label}:"):
            return stripped.split(":", 1)[1].strip()
    return ""


def parse_macos(node: str, text: str) -> Device:
    """Read what `diskutil info` says about a device."""
    size = SIZE_IN_BYTES.search(text)
    if not size:
        raise DeviceError(f"could not read the size of {node} from diskutil")
    return Device(
        node=node,
        size=int(size.group(1)),
        media=_field(text, "Device / Media Name"),
        removable="removable" in _field(text, "Removable Media").lower(),
        external=_field(text, "Device Location").lower() == "external",
        virtual=_field(text, "Virtual").lower() == "yes",
        block=f"/dev/{node}",
        raw=f"/dev/r{node}",
    )


def _truthy(value: object) -> bool:
    return value in (True, 1, "1", "true", "True")


def parse_linux(node: str, text: str) -> Device:
    """Read what `lsblk --bytes --json` says about a device.

    util-linux moved these fields from strings to real JSON types, and both
    shapes are still shipping, so either is accepted.
    """
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise DeviceError(f"lsblk output for {node} could not be read: {error}") from error

    listed = payload.get("blockdevices") or []
    if not listed:
        raise DeviceError(f"lsblk did not report a device for {node}")

    entry = listed[0]
    if str(entry.get("type", "disk")).lower() != "disk":
        raise DeviceError(f"{node} is not a whole disk, it is a {entry.get('type')}")

    removable = _truthy(entry.get("rm"))
    transport = str(entry.get("tran") or "").lower()
    return Device(
        node=node,
        size=int(entry.get("size") or 0),
        media=str(entry.get("model") or "").strip(),
        removable=removable,
        external=removable or transport in EXTERNAL_TRANSPORTS,
        virtual=False,
        block=f"/dev/{node}",
        raw=f"/dev/{node}",
    )


def refusals(device: Device, expected_bytes: int) -> tuple[str, ...]:
    """Every reason not to write to this device, rather than only the first.

    Reporting one at a time turns a wrong target into a guessing game, and the
    target here is a whole disk being erased.
    """
    reasons = []
    if device.size != expected_bytes:
        reasons.append(f"{device.node} is {device.size} bytes, a Zip 100 is {expected_bytes}")
    if not device.external:
        reasons.append(f"{device.node} is not an external device")
    if not device.removable:
        reasons.append(f"{device.node} is not removable media")
    if device.virtual:
        reasons.append(f"{device.node} is a virtual device")
    return tuple(reasons)


@dataclass
class StallWatch:
    """Throughput as a proxy for a drive that has stopped finding its tracks."""

    ceiling_seconds: int = CEILING_SECONDS
    slow_factor: int = SLOW_FACTOR
    warmup_chunks: int = WARMUP_CHUNKS
    fastest: int = 0

    def reset(self) -> None:
        self.fastest = 0

    def observe(self, direction: str, index: int, total: int, seconds: int) -> str | None:
        """Why this chunk means stop, or None to carry on."""
        if seconds > self.ceiling_seconds:
            return (
                f"the {direction} of chunk {index} of {total} took {seconds}s, over the "
                f"{self.ceiling_seconds}s limit. A transfer that slows this far has stopped "
                f"making progress, which is what a head re-seeking on a bad track looks like."
            )
        if (
            self.fastest > 0
            and index >= self.warmup_chunks
            and seconds > self.fastest * self.slow_factor
        ):
            return (
                f"the {direction} of chunk {index} of {total} took {seconds}s against a best "
                f"of {self.fastest}s. Throughput collapsed by more than {self.slow_factor} "
                f"times on the same drive and disk."
            )
        if seconds > 0 and (self.fastest == 0 or seconds < self.fastest):
            self.fastest = seconds
        return None


def chunks(*, total: int, size: int) -> Iterator[tuple[int, int]]:
    """Every chunk as an index and a length, the last one short rather than over.

    Reading a whole block for a partial final chunk and comparing it against the
    short one that was written fails on a healthy disk, which is a false alarm on
    the one check meant to catch a real fault.
    """
    index = 0
    while index * size < total:
        yield index, min(size, total - index * size)
        index += 1


SUDO = ("sudo",)


def privileged(command: list[str]) -> list[str]:
    """Writing to a raw device needs root, and asking once beats asking per chunk."""
    return [*SUDO, *command]


def have_privilege() -> bool:
    """Whether sudo will run without stopping to ask, checked before the first write."""
    return _run(["sudo", "-n", "true"]).returncode == 0


def _run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, capture_output=True, check=False, **kwargs)  # type: ignore[call-overload,no-any-return]


def on_macos() -> bool:
    return sys.platform == "darwin"


def read_device(node: str) -> Device:
    """Ask the system about a device, through whichever tool it has."""
    if on_macos():
        if shutil.which("diskutil") is None:
            raise DeviceError("diskutil was not found, so this device cannot be inspected")
        done = _run(["diskutil", "info", node])
        if done.returncode != 0:
            raise DeviceError(f"no such device: {node}")
        return parse_macos(node, done.stdout.decode("utf-8", "replace"))

    if shutil.which("lsblk") is None:
        raise DeviceError("lsblk was not found. Install util-linux to write disks")
    done = _run(
        [
            "lsblk",
            "--bytes",
            "--json",
            "--nodeps",
            "-o",
            "NAME,SIZE,RM,MODEL,TRAN,TYPE",
            f"/dev/{node}",
        ]
    )
    if done.returncode != 0:
        raise DeviceError(f"no such device: {node}")
    return parse_linux(node, done.stdout.decode("utf-8", "replace"))


def unmount_command(device: Device) -> list[str]:
    """Take every filesystem on the disk offline before touching it.

    macOS unmounts the whole disk in one call. Linux mounts partitions rather
    than disks, so umount is pointed at the device and told to detach whatever
    hangs off it.
    """
    if on_macos():
        return ["diskutil", "unmountDisk", "force", device.block]
    return ["umount", "--all-targets", "--quiet", device.block]


def eject_command(device: Device) -> list[str]:
    if on_macos():
        return ["diskutil", "eject", device.block]
    return ["eject", device.block]


def unmount(device: Device) -> None:
    _run(privileged(unmount_command(device)))


def eject(device: Device) -> bool:
    return _run(privileged(eject_command(device))).returncode == 0


@dataclass(frozen=True)
class Written:
    chunks: int
    seconds: int
    ejected: bool


def write_image(
    payload: Path,
    device: Device,
    *,
    total_bytes: int,
    watch: StallWatch | None = None,
    chunk_bytes: int = CHUNK_BYTES,
    say: object = None,
    run: object = None,
) -> Written:
    """Write, read back, compare every chunk, and eject however it ends.

    A fault anywhere ejects before raising. Leaving a suspect disk in a drive is
    the one outcome worth avoiding more than a failed write.

    `run` is the way out to dd and diskutil. It is injected so the decisions
    here, which are the ones that protect the drive, can be exercised against a
    drive that fails on cue rather than against a real one that may never fail.
    """
    announce = say if callable(say) else (lambda _message: None)
    execute = run if callable(run) else _run
    watching = watch or StallWatch()
    spans = list(chunks(total=total_bytes, size=chunk_bytes))

    def stop(reason: str) -> None:
        execute(privileged(eject_command(device)))
        raise WriteFailedError(reason)

    execute(privileged(unmount_command(device)))
    announce(f"writing     {len(spans)} chunks of {chunk_bytes // 1024 // 1024} MiB")
    started = time.monotonic()
    with payload.open("rb") as source:
        for index, length in spans:
            source.seek(index * chunk_bytes)
            block = source.read(length)
            at = time.monotonic()
            done = execute(
                privileged(
                    [
                        "dd",
                        f"of={device.raw}",
                        f"bs={chunk_bytes}",
                        f"seek={index}",
                        "conv=notrunc",
                    ]
                ),
                input=block,
            )
            if done.returncode != 0:
                stop(
                    f"the write failed on chunk {index} of {len(spans)}. An I/O error at "
                    f"this level means the drive could not complete the transfer."
                )
            fault = watching.observe("write", index, len(spans), round(time.monotonic() - at))
            if fault:
                stop(fault)
    elapsed = round(time.monotonic() - started)

    execute(privileged(unmount_command(device)))
    announce(f"verifying   reading back through {device.raw}, never mounted")
    watching.reset()
    with payload.open("rb") as source:
        for index, length in spans:
            at = time.monotonic()
            done = execute(
                privileged(
                    ["dd", f"if={device.raw}", f"bs={chunk_bytes}", f"skip={index}", "count=1"]
                )
            )
            if done.returncode != 0:
                stop(
                    f"the read failed on chunk {index} of {len(spans)}. The bytes went down "
                    f"but will not come back, so the disk cannot be trusted."
                )
            fault = watching.observe("read", index, len(spans), round(time.monotonic() - at))
            if fault:
                stop(fault)
            source.seek(index * chunk_bytes)
            if done.stdout[:length] != source.read(length):
                stop(
                    f"chunk {index} of {len(spans)} came back different from what was "
                    f"written. The write reported success, so the disk is not holding "
                    f"what it was given."
                )

    ejected = execute(privileged(eject_command(device))).returncode == 0
    return Written(chunks=len(spans), seconds=elapsed, ejected=ejected)
