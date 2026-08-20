# Supplied artifacts

Files this project needs, cannot distribute, and cannot regenerate. Put them
in this folder. Everything here is ignored by git except this document and the
ignore rules beside it, so a payload dropped in cannot be committed by accident.

This file is generated from the manifest the code checks against. Do not edit it
by hand: run `z64kit artifacts --write-readme` after the manifest changes.

## How a file is accepted

**SHA-256 alone decides.** Size is a cheap pre-filter and CRC32 is there so a
file can be cross-referenced against a public database. Neither one accepts or
rejects anything.

A file whose digest does not match is reported with the reason, not just a
failure. Wrong size, right size with altered content, and a recognised file
under the wrong name are three different problems with three different fixes.

```
z64kit artifacts            # what is here, what is missing, what is wrong
```

## Expected files

15 files. The checksum pair is the ROM each patch is bound to, which
is how a patch built for another revision is refused rather than applied.

| File | Game | Purpose | Bytes | Target CRC1 / CRC2 |
|:-----|:-----|:--------|------:|:-------------------|
| `cc-usa.aps` | Command & Conquer (USA) | No save fix | 92,484 | `95286EB4` / `B76AD58F` |
| `dk64-usa.aps` | Donkey Kong 64 (USA) | Boot and save fix | 74,656 | `EC58EABF` / `AD7C7169` |
| `dk64-usa.ram` |  | Boot and save fix | 65,536 |  |
| `dx-btusc.aps` | Banjo-Tooie (USA) | Crack and save fix | 121,964 | `C2E9AA9A` / `475D70AA` |
| `ebikeusa.aps` | Excitebike 64 (USA) | Boot and save fix | 24,666 | `07861842` / `A12EBC9F` |
| `jfg-usa.aps` | Jet Force Gemini (USA) | Boot and save fix | 62,109 | `8A6009B6` / `94ACE150` |
| `jfg-usa.ram` |  | Boot and save fix | 65,536 |  |
| `kgsgood.aps` | Ken Griffey Jr.'s Slugfest (USA) | Boot fix for the good dump | 101,253 | `36281F23` / `009756CF` |
| `mglf-usa.aps` | Mario Golf (USA) | Save fix | 92,660 | `664BA3D4` / `678A80B7` |
| `mten-usa.aps` | Mario Tennis (USA) | Boot and save fix | 47,638 | `5001CF4F` / `F30CB3BD` |
| `nbac2usa.aps` | NBA Courtside 2 featuring Kobe Bryant (USA) | No save fix | 217 | `916852D8` / `73DBEAEF` |
| `swep1rus.aps` | Star Wars Episode I - Racer (USA) | Save fix | 46,818 | `72F70398` / `6556A98B` |
| `swep1rus.eep` |  | Save fix | 512 |  |
| `zmm-usa.aps` | Legend of Zelda, The - Majora's Mask (USA) | Boot and save fix | 108,432 | `5354631C` / `03A2DEF0` |
| `zoot-usa.aps` | Legend of Zelda, The - Ocarina of Time (USA) | Boot and save fix | 128,135 | `EC7011B7` / `7616D72B` |

### Digests

```
e40a39ce5542bfd5aaeb240c267a6e9f5de3a92916090b42b4bd83b850108222  cc-usa.aps
7ec44b4f51a253235d045f69a3015f26c60101669644be1db8ed604b38c1e0ca  dk64-usa.aps
82a2a771e4f3ef0dbcd6972e616dbc0abf5c2c0eac679a6fba44de2294597ba9  dk64-usa.ram
472e75d223bbb94591e96b93212dc14f6bf9923dc316956b1ab7f2f883456e86  dx-btusc.aps
662719b82363def506933186762688e71a0ddc1adfffaa02b0fc29ffde922fcb  ebikeusa.aps
82bcd67e020f43d69b4c9f5295d9c5e022b3df7d301000849e95dc3f2278f9a1  jfg-usa.aps
6fe933595ae50f308ef242d7dd507d2bba81bf2ddf80f39120ad038605e19239  jfg-usa.ram
ea65c20e8cc2c4b3afba34fa7b8097f8bfaa88004efdf122b9f20684c27b837f  kgsgood.aps
f8b6177bf18e04ace451924d335c3b22a35f33cfeb9f58878da66e4747de4223  mglf-usa.aps
7b8a994005b87a326fce02aa8e6af1f0b300d31472d679fb8904492324e1053c  mten-usa.aps
e6ddf1d5f11173dbb34d106e70e349ea6db9bab6f2b813ebac3c7086f0da39da  nbac2usa.aps
5a0f443c2d7fc187008e9c7cf60747cd1d4b24d2bb7da698bb8b36db377dbe75  swep1rus.aps
d6d0ceb8c2dd5d9da39c31052786acd60a0743ea61cd40012f2d7a620c305919  swep1rus.eep
52b8cf4ae0f4d7f597a6b222c420a403b9e65b8593027bd2958268f0e12df71c  zmm-usa.aps
84fe75fffe406d5c74b3f2e55bf39988465f48226c7349d11ca4ea58763674fc  zoot-usa.aps
```

### CRC32, for looking a file up elsewhere

| File | CRC32 |
|:-----|:------|
| `cc-usa.aps` | `bfcb4bc0` |
| `dk64-usa.aps` | `72acc470` |
| `dk64-usa.ram` | `8fa0cc19` |
| `dx-btusc.aps` | `0e4b563a` |
| `ebikeusa.aps` | `ebb7ca3c` |
| `jfg-usa.aps` | `ecd4d394` |
| `jfg-usa.ram` | `4c94501d` |
| `kgsgood.aps` | `5a224733` |
| `mglf-usa.aps` | `89bfc0af` |
| `mten-usa.aps` | `ca75d772` |
| `nbac2usa.aps` | `52ee7875` |
| `swep1rus.aps` | `e8049c29` |
| `swep1rus.eep` | `b701479b` |
| `zmm-usa.aps` | `8dd87884` |
| `zoot-usa.aps` | `39d27d56` |

## Files that travel in pairs

Some patches need a save file present as well, and the unit expects both to
carry the ROM's name once they reach a disk. The tool renames them together,
so here they keep the names below.

| Patch | Also needs |
|:------|:-----------|
| `dk64-usa.aps` | `dk64-usa.ram` |
| `jfg-usa.aps` | `jfg-usa.ram` |
| `swep1rus.aps` | `swep1rus.eep` |

## Checking a file yourself

macOS and any system with Perl:

```bash
shasum -a 256 *.aps *.ram *.eep
```

Linux:

```bash
sha256sum *.aps *.ram *.eep
```

Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 *.aps, *.ram, *.eep
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
| `z64patch.dat` | Unofficial Z64 patch database v3.0U |

Game images never belong here either. This folder is for the small files that
make a game run on the unit, not for the games.

## Provenance

| File | Recorded source |
|:-----|:----------------|
| `cc-usa.aps` | Unofficial Z64 Patch File v3.0U |
| `dk64-usa.aps` | Unofficial Z64 Patch File v3.0U |
| `dk64-usa.ram` | Unofficial Z64 Patch File v3.0U |
| `dx-btusc.aps` | Standalone dextrose release dx-btusc |
| `ebikeusa.aps` | Unofficial Z64 Patch File v3.0U |
| `jfg-usa.aps` | Unofficial Z64 Patch File v3.0U |
| `jfg-usa.ram` | Unofficial Z64 Patch File v3.0U |
| `kgsgood.aps` | Unofficial Z64 Patch File v3.0U, extra folder |
| `mglf-usa.aps` | Unofficial Z64 Patch File v3.0U |
| `mten-usa.aps` | Unofficial Z64 Patch File v3.0U |
| `nbac2usa.aps` | Unofficial Z64 Patch File v3.0U |
| `swep1rus.aps` | Unofficial Z64 Patch File v3.0U |
| `swep1rus.eep` | Unofficial Z64 Patch File v3.0U |
| `zmm-usa.aps` | Unofficial Z64 Patch File v3.0U |
| `zoot-usa.aps` | Unofficial Z64 Patch File v3.0U |

A recorded source says where the digest came from. It is not a claim that the
file is correct, safe, or what it says it is. Every one of these was verified
against the ROM it targets before being trusted, and so should any replacement.
