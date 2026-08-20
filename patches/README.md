# Supplied artifacts

Files this project needs, cannot distribute, and cannot regenerate. Put them in
this folder. Everything here is ignored by git except this document and the ignore
rules beside it, so a payload dropped in cannot be committed by accident.

This file is generated from the manifest the code checks against. Do not edit it by
hand: run `z64kit artifacts --write-readme` after the manifest changes.

## You almost certainly do not need all of these

Beyond the patch database, only 13 files are ever needed, covering
6 games. Which of those matter depends entirely on which games you own, so
ask the tool rather than reading the whole table:

```
z64kit artifacts --source YOUR-GAME-FOLDER
```

That reports only the files the games in that folder actually need, and says which
are missing, which are present but wrong, and which are correct under the wrong
name. Without `--source` every file below is treated as required.

## Scope

| | |
|:--|:--|
| Region | USA releases only |
| Games needing a separate file | 6 |
| Files expected here | 14 |
| Patches the database already covers | 75 |
| Filenames | lowercase throughout |
| Decides acceptance | SHA-256, and nothing else |

Size is a cheap pre-filter and CRC32 is there so a file can be cross-referenced
against a public database. Neither one accepts or rejects anything.

## What the checksum column means

Every patch was applied to the ROM it targets, and the header checksum of the
result was then recomputed.

| Value | Meaning |
|:------|:--------|
| `valid-6102` | The patched ROM verifies under boot chip 6102 |
| `no boot chip` | The patched ROM verifies under no boot chip this tool knows |
| `not checked` | The ROM it targets was not available to test against |

A `no boot chip` result is a measurement, not a verdict. The unit emulates the
boot chip rather than holding a real one, so whether it enforces that check is
untested on hardware here. Treat those patches as unverified rather than broken.

Even a patch that verifies is only proven to start. A protection check that lets
the game boot and then degrades play later cannot be detected by any test in this
project, and that failure mode was real on this platform.

## Start with one file

`z64patch.dat` is the unit's own patch database, and it already covers
75 of the patches known for this platform. The unit reads it
directly and finds the right patch inside it, so you supply one file instead of
dozens.

| | |
|:--|:--|
| File | `z64patch.dat` |
| Bytes | 657,092 |
| SHA-256 | `f9e8c296ab12a38fb92e69bf3c50d9827cbad1e82005f7a7838925abd5e0e7a5` |

**It has to be on every disk, in the root, beside the games.** The tool copies it
there for you whenever it is in this folder, and says so when it is not. Without
it a game that needs a patch loads unpatched, which usually means it cannot save
and sometimes means it will not boot at all.

It costs about 0.6 MB of a 100 MB disk and takes nothing away from the games: a
disk holds 23 of them at 4 MB granularity and still has roughly 3 MB spare.

## The patch database

One file the unit reads itself. It belongs in the root of every disk.

1 files.

| File | Bytes |
|:-----|------:|
| `z64patch.dat` | 657,092 |

## Save and boot fixes

Without one of these the game either cannot write a save or will not start.

2 files.

| File | Game | Bytes | Target CRC1 / CRC2 | Checksum after |
|:-----|:-----|------:|:-------------------|:---------------|
| `dx-btusc.aps` | Banjo-Tooie (USA) | 121,964 | `C2E9AA9A` / `475D70AA` | valid-6102 |
| `kgsgood.aps` | Ken Griffey Jr.'s Slugfest (USA) | 101,253 | `36281F23` / `009756CF` | no boot chip |

## Copy protection removal

These games check for a real cartridge and refuse to run from a disk.

4 files.

| File | Game | Bytes | Target CRC1 / CRC2 | Checksum after |
|:-----|:-----|------:|:-------------------|:---------------|
| `1080_j.zps` | 1080 SNOWBOARDING | 22,703 | `1FBAF161` / `2C1C54F1` | no boot chip |
| `banjo.zps` | Banjo-Kazooie | 7,634 | `A4BF9306` / `BF0CDFD1` | no boot chip |
| `nba_cs.zps` | NBA COURTSIDE | 16,466 | `616B8494` / `8A509210` | no boot chip |
| `yoshi_e.zps` | YOSHI STORY | 4,600 | `2337D8E8` / `6B8E7CEC` | no boot chip |

## Save data

Shipped alongside a patch, and meaningless without it.

3 files.

| File | Game | Bytes | Target CRC1 / CRC2 | Checksum after |
|:-----|:-----|------:|:-------------------|:---------------|
| `dk64-usa.ram` | Donkey Kong 64 (USA) | 65,536 | matched by its own digest |  |
| `jfg-usa.ram` | Jet Force Gemini (USA) | 65,536 | matched by its own digest |  |
| `swep1rus.eep` | Star Wars Episode I - Racer (USA) | 512 | matched by its own digest |  |

## Target ROM headers

64 bytes identifying the ROM a patch belongs to. Only a non-APS patch needs one: an APS carries its own binding at a fixed offset.

4 files.

| File | Belongs to |
|:-----|:-----------|
| `1080_j.hdr` | `1080_j.zps` |
| `banjo.hdr` | `banjo.zps` |
| `nba_cs.hdr` | `nba_cs.zps` |
| `yoshi_e.hdr` | `yoshi_e.zps` |

## Already inside the patch database

You do not need separate copies of these 75 files. They are listed
so you can confirm that `z64patch.dat` covers the game you care about, and
so a copy found loose somewhere can be identified. Supplying the database is
enough.

| File | Game | Checksum after |
|:-----|:-----|:---------------|
| `bam99.hdr` | Bust A Move '99 |  |
| `bam99.ips` | Bust A Move '99 | no boot chip |
| `bass.aps` | In-Fisherman - Bass Hunter 64 (USA) | valid-6102 |
| `bh.hdr` | BODY HARVEST |  |
| `bh.ips` | BODY HARVEST | no boot chip |
| `bos99.hdr` | BLADES OF STEEL '99 |  |
| `bos99.ips` | BLADES OF STEEL '99 | no boot chip |
| `btanxvfx.hdr` | BATTLETANX |  |
| `btanxvfx.ips` | BATTLETANX | no boot chip |
| `buckpfx.hdr` | BUCK BUMBLE |  |
| `buckpfx.ips` | BUCK BUMBLE | no boot chip |
| `cali.aps` | CAL SPEED | no boot chip |
| `cc-usa.aps` | Command & Conquer (USA) | no boot chip |
| `chmtwst2.hdr` | Chameleon Twist2 |  |
| `chmtwst2.ips` | Chameleon Twist2 | no boot chip |
| `davfx.hdr` | DeadlyArts |  |
| `davfx.ips` | DeadlyArts | no boot chip |
| `dk64-usa.aps` | Donkey Kong 64 (USA) | valid-6102 |
| `ebikeusa.aps` | Excitebike 64 (USA) | valid-6102 |
| `fdvfx.hdr` | FLYING DRAGON |  |
| `fdvfx.ips` | FLYING DRAGON | no boot chip |
| `fsh99sfx.hdr` | Fox Sports Hoops 99 |  |
| `fsh99sfx.ips` | Fox Sports Hoops 99 | no boot chip |
| `fzerousa.hdr` | F-ZERO X |  |
| `fzerousa.ips` | F-ZERO X | no boot chip |
| `gnvfx.hdr` | GOLDEN NUGGET 64 |  |
| `gnvfx.ips` | GOLDEN NUGGET 64 | no boot chip |
| `iss98vfx.hdr` | I.S.S.98 |  |
| `iss98vfx.ips` | I.S.S.98 | no boot chip |
| `jfg-usa.aps` | Jet Force Gemini (USA) | valid-6102 |
| `kgs-ags.hdr` | KEN GRIFFEY SLUGFEST |  |
| `kgs-ags.ips` | KEN GRIFFEY SLUGFEST | no boot chip |
| `kombat4.hdr` | MORTAL KOMBAT 4 |  |
| `kombat4.ips` | MORTAL KOMBAT 4 | no boot chip |
| `mglf-usa.aps` | Mario Golf (USA) | no boot chip |
| `micromac.hdr` | MICROMACHINES64TURBO |  |
| `micromac.ips` | MICROMACHINES64TURBO | no boot chip |
| `mlb-kgjr.hdr` | MLB FEATURING K G JR |  |
| `mlb-kgjr.ips` | MLB FEATURING K G JR | no boot chip |
| `mpusa.hdr` | MarioParty |  |
| `mpusa.ips` | MarioParty | no boot chip |
| `mten-usa.aps` | Mario Tennis (USA) | valid-6102 |
| `mtr.aps` | Monster Truck Madness 64 (USA) | valid-6102 |
| `nascar99.hdr` | NASCAR 99 |  |
| `nascar99.ips` | NASCAR 99 | no boot chip |
| `nba99.hdr` | NBA IN THE ZONE '99 |  |
| `nba99.ips` | NBA IN THE ZONE '99 | no boot chip |
| `nba99sfx.hdr` | NBA JAM 99 |  |
| `nba99sfx.ips` | NBA JAM 99 | no boot chip |
| `nbac2usa.aps` | NBA Courtside 2 featuring Kobe Bryant (USA) | no boot chip |
| `ncpfx.hdr` | NIGHTMARE CREATURES |  |
| `ncpfx.ips` | NIGHTMARE CREATURES | no boot chip |
| `newtetr.aps` | New Tetris, The (USA) | no boot chip |
| `quake2.aps` | Quake II (USA) | valid-6102 |
| `rugrt.hdr` | RUGRATSSCAVENGERHUNT |  |
| `rugrt.ips` | RUGRATSSCAVENGERHUNT | no boot chip |
| `scarspfx.hdr` | SCARS |  |
| `scarspfx.ips` | SCARS | no boot chip |
| `smbus.aps` | SMASH BROTHERS | no boot chip |
| `snobo2us.aps` | SNOWBOARD KIDS2 | no boot chip |
| `ssvfx.hdr` | STAR SOLDIER |  |
| `ssvfx.ips` | STAR SOLDIER | no boot chip |
| `starntsc.aps` | STAR WARS EP1 RACER | no boot chip |
| `swep1rus.aps` | Star Wars Episode I - Racer (USA) | no boot chip |
| `vchess.hdr` | VIRTUALCHESS |  |
| `vchess.ips` | VIRTUALCHESS | no boot chip |
| `vil8.aps` | VIGILANTE 8 | valid-6102 |
| `wcwn.hdr` | NITRO64 |  |
| `wcwn.ips` | NITRO64 | no boot chip |
| `wcwpfx.hdr` | WCW / nWo  REVENGE |  |
| `wcwpfx.ips` | WCW / nWo  REVENGE | no boot chip |
| `wg3dvfx.hdr` | W.G. 3DHOCKEY98 |  |
| `wg3dvfx.ips` | W.G. 3DHOCKEY98 | no boot chip |
| `zmm-usa.aps` | Legend of Zelda, The - Majora's Mask (USA) | valid-6102 |
| `zoot-usa.aps` | Legend of Zelda, The - Ocarina of Time (USA) | no boot chip |

## Digests

```
29a81157e4620b56f4bddf2555ca2bb4caabecd2d3fa67fb282053163ebf0fb3  1080_j.hdr
f178ddff087ffb9e5f5b0a3fa385aa9deedb0c1875084e836d28c524baea02cb  1080_j.zps
473d0e8c503e0fded99a5c6c229264ed20ec4392728e523de260b6101c5b077c  banjo.hdr
91fd085ffe98f5c8aaecc8cf2b056767ef2910af3e847368c09b821c2cc142ec  banjo.zps
82a2a771e4f3ef0dbcd6972e616dbc0abf5c2c0eac679a6fba44de2294597ba9  dk64-usa.ram
472e75d223bbb94591e96b93212dc14f6bf9923dc316956b1ab7f2f883456e86  dx-btusc.aps
6fe933595ae50f308ef242d7dd507d2bba81bf2ddf80f39120ad038605e19239  jfg-usa.ram
ea65c20e8cc2c4b3afba34fa7b8097f8bfaa88004efdf122b9f20684c27b837f  kgsgood.aps
c9bea7caab8217d4f980bde0cb95628eaf01c0bc8c3852537ffab8fa4c42a202  nba_cs.hdr
4510745d41130f9d24fef4d2210534a205e1d28dc15fc12c78d85434eda791f1  nba_cs.zps
d6d0ceb8c2dd5d9da39c31052786acd60a0743ea61cd40012f2d7a620c305919  swep1rus.eep
4ad1361c4e8e725e3f9e3b56a6c9087f72a9f4f1124af85f27d46de2106d47ee  yoshi_e.hdr
c91ff1f7425223c68427e80cf56becbf0d06f31e6a94003143d67e19318342ad  yoshi_e.zps
f9e8c296ab12a38fb92e69bf3c50d9827cbad1e82005f7a7838925abd5e0e7a5  z64patch.dat
```

### CRC32, for looking a file up elsewhere

```
abbeb3c4  1080_j.hdr
56d4db3b  1080_j.zps
e39ab1eb  banjo.hdr
11e7242f  banjo.zps
8fa0cc19  dk64-usa.ram
0e4b563a  dx-btusc.aps
4c94501d  jfg-usa.ram
5a224733  kgsgood.aps
194ece3f  nba_cs.hdr
17fe451c  nba_cs.zps
b701479b  swep1rus.eep
f2323426  yoshi_e.hdr
afb188b8  yoshi_e.zps
73a6180b  z64patch.dat
```

## Checking a file yourself

macOS, and any system with Perl:

```bash
shasum -a 256 *
```

Linux:

```bash
sha256sum *
```

Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 *
```

Compare the result against the digest list above. A digest that appears in the
list under a different filename means the file is right and the name is wrong,
which is the one failure that needs no new file to fix.

## What does not belong here

These are named in the manifest so the tool can recognise them, and they are
not part of building a disk. Keep them wherever you keep unit firmware.

| File | Purpose |
|:-----|:--------|
| `z64bios220.zip` | Unofficial CF Edition BIOS 2.20, based on 2.18d |

Game images never belong here either. This folder is for the small files that make
a game run on the unit, not for the games.

## Provenance

| File | Recorded source |
|:-----|:----------------|
| `1080_j.hdr` | ships beside its patch |
| `1080_j.zps` | CRACK.ZIP |
| `banjo.hdr` | ships beside its patch |
| `banjo.zps` | CRACK.ZIP |
| `dk64-usa.ram` | Unofficial Z64 Patch File v3.0U |
| `dx-btusc.aps` | Standalone dextrose release dx-btusc |
| `jfg-usa.ram` | Unofficial Z64 Patch File v3.0U |
| `kgsgood.aps` | Unofficial Z64 Patch File v3.0U, extra folder |
| `nba_cs.hdr` | ships beside its patch |
| `nba_cs.zps` | CRACK.ZIP |
| `swep1rus.eep` | Unofficial Z64 Patch File v3.0U |
| `yoshi_e.hdr` | ships beside its patch |
| `yoshi_e.zps` | CRACK.ZIP |
| `z64patch.dat` | fab at elitendo.com |

A recorded source says where the digest came from. It is not a claim that the file
is correct, safe, or what it says it is. Every one of these was verified against
the ROM it targets before being trusted, and so should any replacement.
