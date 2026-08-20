# Supplied artifacts

Files this project needs, cannot distribute, and cannot regenerate. Put them in
this folder. Everything here is ignored by git except this document and the ignore
rules beside it, so a payload dropped in cannot be committed by accident.

This file is generated from the manifest the code checks against. Do not edit it by
hand: run `z64kit artifacts --write-readme` after the manifest changes.

## You almost certainly do not need all of these

The list below covers 51 games. Which files matter depends entirely on which
games you own, so ask the tool rather than reading the whole table:

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
| Games covered | 51 |
| Files expected | 88 |
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

## Save and boot fixes

Without one of these the game either cannot write a save or will not start.

49 files.

| File | Game | Bytes | Target CRC1 / CRC2 | Checksum after |
|:-----|:-----|------:|:-------------------|:---------------|
| `bam99.ips` | Bust A Move '99 | 3,232 | `4222D89F` / `AFE0B637` | no boot chip |
| `bass.aps` | In-Fisherman - Bass Hunter 64 (USA) | 3,052 | `8C138BE0` / `95700E46` | valid-6102 |
| `bh.ips` | BODY HARVEST | 46 | `5326696F` / `FE9A99C3` | no boot chip |
| `bos99.ips` | BLADES OF STEEL '99 | 3,879 | `82EFDC30` / `806A2461` | no boot chip |
| `btanxvfx.ips` | BATTLETANX | 3,207 | `6AA4DDE7` / `E3E2F4E7` | no boot chip |
| `buckpfx.ips` | BUCK BUMBLE | 3,288 | `85AE781A` / `C756F05D` | no boot chip |
| `cali.aps` | CAL SPEED | 95 | `AC16400E` / `CF5D071A` | no boot chip |
| `cc-usa.aps` | Command & Conquer (USA) | 92,484 | `95286EB4` / `B76AD58F` | no boot chip |
| `chmtwst2.ips` | Chameleon Twist2 | 79 | `CD538CE4` / `618AFCF9` | no boot chip |
| `davfx.ips` | DeadlyArts | 2,939 | `F5363349` / `DBF9D21B` | no boot chip |
| `dk64-usa.aps` | Donkey Kong 64 (USA) | 74,656 | `EC58EABF` / `AD7C7169` | valid-6102 |
| `dx-btusc.aps` | Banjo-Tooie (USA) | 121,964 | `C2E9AA9A` / `475D70AA` | valid-6102 |
| `ebikeusa.aps` | Excitebike 64 (USA) | 24,666 | `07861842` / `A12EBC9F` | valid-6102 |
| `fdvfx.ips` | FLYING DRAGON | 4,249 | `A92D52E5` / `1D26B655` | no boot chip |
| `fsh99sfx.ips` | Fox Sports Hoops 99 | 29 | `3261D479` / `ED0DBC25` | no boot chip |
| `fzerousa.ips` | F-ZERO X | 39,141 | `B30ED978` / `3003C9F9` | no boot chip |
| `gnvfx.ips` | GOLDEN NUGGET 64 | 239 | `4690FB1C` / `4CD56D44` | no boot chip |
| `iss98vfx.ips` | I.S.S.98 | 3,214 | `7F0FDA09` / `6061CE0B` | no boot chip |
| `jfg-usa.aps` | Jet Force Gemini (USA) | 62,109 | `8A6009B6` / `94ACE150` | valid-6102 |
| `kgs-ags.ips` | KEN GRIFFEY SLUGFEST | 94,382 | `36281F23` / `009756CF` | no boot chip |
| `kgsgood.aps` | Ken Griffey Jr.'s Slugfest (USA) | 101,253 | `36281F23` / `009756CF` | no boot chip |
| `kombat4.ips` | MORTAL KOMBAT 4 | 71 | `417DD4F4` / `1B482FE2` | no boot chip |
| `mglf-usa.aps` | Mario Golf (USA) | 92,660 | `664BA3D4` / `678A80B7` | no boot chip |
| `micromac.ips` | MICROMACHINES64TURBO | 3,873 | `F1850C35` / `ACE07912` | no boot chip |
| `mlb-kgjr.ips` | MLB FEATURING K G JR | 27 | `80C1C05C` / `EA065EF4` | no boot chip |
| `mpusa.ips` | MarioParty | 3,879 | `2829657E` / `A0621877` | no boot chip |
| `mten-usa.aps` | Mario Tennis (USA) | 47,638 | `5001CF4F` / `F30CB3BD` | valid-6102 |
| `mtr.aps` | Monster Truck Madness 64 (USA) | 3,056 | `B19AD999` / `7E585118` | valid-6102 |
| `nascar99.ips` | NASCAR 99 | 31,630 | `23749578` / `80DC58FD` | no boot chip |
| `nba99.ips` | NBA IN THE ZONE '99 | 3,879 | `A292524F` / `3D6C2A49` | no boot chip |
| `nba99sfx.ips` | NBA JAM 99 | 41 | `810729F6` / `E03FCFC1` | no boot chip |
| `nbac2usa.aps` | NBA Courtside 2 featuring Kobe Bryant (USA) | 217 | `916852D8` / `73DBEAEF` | no boot chip |
| `ncpfx.ips` | NIGHTMARE CREATURES | 146 | `2857674D` / `CC4337DA` | no boot chip |
| `newtetr.aps` | New Tetris, The (USA) | 4,015 | `2153143F` / `992D6351` | no boot chip |
| `quake2.aps` | Quake II (USA) | 3,036 | `BDA8F143` / `B1AF2D62` | valid-6102 |
| `rugrt.ips` | RUGRATSSCAVENGERHUNT | 106 | `0C02B3C5` / `9E2511B8` | no boot chip |
| `scarspfx.ips` | SCARS | 191 | `769147F3` / `2033C10E` | no boot chip |
| `smbus.aps` | SMASH BROTHERS | 8,722 | `916B8B5B` / `780B85A4` | no boot chip |
| `snobo2us.aps` | SNOWBOARD KIDS2 | 136 | `930C29EA` / `939245BF` | no boot chip |
| `ssvfx.ips` | STAR SOLDIER | 3,879 | `DDD93C85` / `DAE381E8` | no boot chip |
| `starntsc.aps` | STAR WARS EP1 RACER | 18,232 | `72F70398` / `6556A98B` | no boot chip |
| `swep1rus.aps` | Star Wars Episode I - Racer (USA) | 46,818 | `72F70398` / `6556A98B` | no boot chip |
| `vchess.ips` | VIRTUALCHESS | 42 | `82B3248B` / `E73E244D` | no boot chip |
| `vil8.aps` | VIGILANTE 8 | 168 | `EA71056A` / `E4214847` | valid-6102 |
| `wcwn.ips` | NITRO64 | 3,272 | `D4C45A1A` / `F425B25E` | no boot chip |
| `wcwpfx.ips` | WCW / nWo  REVENGE | 87 | `DEE596AB` / `AF3B7AE7` | no boot chip |
| `wg3dvfx.ips` | W.G. 3DHOCKEY98 | 29 | `5A9D3859` / `97AAE710` | no boot chip |
| `zmm-usa.aps` | Legend of Zelda, The - Majora's Mask (USA) | 108,432 | `5354631C` / `03A2DEF0` | valid-6102 |
| `zoot-usa.aps` | Legend of Zelda, The - Ocarina of Time (USA) | 128,135 | `EC7011B7` / `7616D72B` | no boot chip |

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

32 files.

| File | Belongs to |
|:-----|:-----------|
| `1080_j.hdr` | `1080_j.zps` |
| `bam99.hdr` | `bam99.ips` |
| `banjo.hdr` | `banjo.zps` |
| `bh.hdr` | `bh.ips` |
| `bos99.hdr` | `bos99.ips` |
| `btanxvfx.hdr` | `btanxvfx.ips` |
| `buckpfx.hdr` | `buckpfx.ips` |
| `chmtwst2.hdr` | `chmtwst2.ips` |
| `davfx.hdr` | `davfx.ips` |
| `fdvfx.hdr` | `fdvfx.ips` |
| `fsh99sfx.hdr` | `fsh99sfx.ips` |
| `fzerousa.hdr` | `fzerousa.ips` |
| `gnvfx.hdr` | `gnvfx.ips` |
| `iss98vfx.hdr` | `iss98vfx.ips` |
| `kgs-ags.hdr` | `kgs-ags.ips` |
| `kombat4.hdr` | `kombat4.ips` |
| `micromac.hdr` | `micromac.ips` |
| `mlb-kgjr.hdr` | `mlb-kgjr.ips` |
| `mpusa.hdr` | `mpusa.ips` |
| `nascar99.hdr` | `nascar99.ips` |
| `nba99.hdr` | `nba99.ips` |
| `nba99sfx.hdr` | `nba99sfx.ips` |
| `nba_cs.hdr` | `nba_cs.zps` |
| `ncpfx.hdr` | `ncpfx.ips` |
| `rugrt.hdr` | `rugrt.ips` |
| `scarspfx.hdr` | `scarspfx.ips` |
| `ssvfx.hdr` | `ssvfx.ips` |
| `vchess.hdr` | `vchess.ips` |
| `wcwn.hdr` | `wcwn.ips` |
| `wcwpfx.hdr` | `wcwpfx.ips` |
| `wg3dvfx.hdr` | `wg3dvfx.ips` |
| `yoshi_e.hdr` | `yoshi_e.zps` |

## Digests

```
29a81157e4620b56f4bddf2555ca2bb4caabecd2d3fa67fb282053163ebf0fb3  1080_j.hdr
f178ddff087ffb9e5f5b0a3fa385aa9deedb0c1875084e836d28c524baea02cb  1080_j.zps
d37b4019dcc0e397c00e9fd0b7abf4615d0b52c3332e38e142f1f5a9d5ef5ffe  bam99.hdr
19b1364a461ffbc6976a2586a7861ae1580f3676607771ba0afa7467850f5bd7  bam99.ips
473d0e8c503e0fded99a5c6c229264ed20ec4392728e523de260b6101c5b077c  banjo.hdr
91fd085ffe98f5c8aaecc8cf2b056767ef2910af3e847368c09b821c2cc142ec  banjo.zps
916e27e81b694f8562b24e7ac02e65cd9a793cae4657fd456e705df3cffb22f9  bass.aps
512591bfacbf450928e86905607762b9544e96e9d69c602ec2f6ddf7bc60237c  bh.hdr
3263aaae6d0f484129c2197a78b2a4456b04eadc7718a400b97e274097a6a758  bh.ips
4577b01c68f8ef1e09f491519e3c30fbd25dc43d340f612ad98595c08460a47b  bos99.hdr
0b8971d46cf1f835eb7ab7f53edf76b7a1c6c82f9bcf6809f4918d6aa06b0ff3  bos99.ips
198cdff3e1500b00101e4d5ad5889e60f2da012427b59deca95dcecc6dc935b8  btanxvfx.hdr
d66bc6eaff7e35e361f19a5b66259d15204f7271c7fb8f9a042710087e5d4265  btanxvfx.ips
61aef3d0660c0a7ff1d7a1cce47f00594a3e4f2ad54a91592ca71dfbaa0ab9bc  buckpfx.hdr
c70ea6aa22cadae708ae3fc1aba13f000b62068c5be6a34dbb4f4bd3eb37bfbd  buckpfx.ips
06498ee097bf81bb2a185f77c12b4217ff5ee333030c9ccd559d6ea8fc717a07  cali.aps
e40a39ce5542bfd5aaeb240c267a6e9f5de3a92916090b42b4bd83b850108222  cc-usa.aps
8ce8cf1f0182ca477a2a8bf441b5b86c40558e21824cf711cb44f3df301bcfac  chmtwst2.hdr
fb5c5a5b3fe1208289ff5ebd770ab97e6c15efcaa206954216dd4a7df1561c65  chmtwst2.ips
ae8047daeabbc09ea649f658c706b14ca9e276dc8e1b22e30d75ce684b2df743  davfx.hdr
fc42b05bc540b3a9c84ee78d24c68ffaade735691582f24c64bd465d5baf53b8  davfx.ips
7ec44b4f51a253235d045f69a3015f26c60101669644be1db8ed604b38c1e0ca  dk64-usa.aps
82a2a771e4f3ef0dbcd6972e616dbc0abf5c2c0eac679a6fba44de2294597ba9  dk64-usa.ram
472e75d223bbb94591e96b93212dc14f6bf9923dc316956b1ab7f2f883456e86  dx-btusc.aps
662719b82363def506933186762688e71a0ddc1adfffaa02b0fc29ffde922fcb  ebikeusa.aps
80c01d16453c275c2cea73a1b48e7aae77d89ccaa2069f0136bbb32c93ea3a39  fdvfx.hdr
095c77332a63c4f994f853858f1e95592694a056199e3e10cd620c4366d2eff8  fdvfx.ips
af58a13d5fc417786715baa9f781f259d1e6c7d956f14f428fc7be60cd0a992b  fsh99sfx.hdr
210444eed464ec3b4ce972bb6b25dbdfbcf19148a32c9d844dae4a8924946bb0  fsh99sfx.ips
722d7053b718fa62558f052ae34ab9fa2eed2a2642c1ae826e70ff321cce204d  fzerousa.hdr
f23128aad6fc04a4f517339553511d879f596f7770e423bca417f086820a6f65  fzerousa.ips
ee8cd8e64700dd0125ac6eb96df35082707f3f03c10ea0b30cfe2ea949673a61  gnvfx.hdr
71978fb55ebda301ff6b389199c28fbc3a6cfd83860af61cf5b9a59cf2e4d199  gnvfx.ips
fba2bade95c0c5aeda70fded7e56558a247e2ecadd828d3047d3f17fe369b947  iss98vfx.hdr
417997a3a5615ca5d749100d3589b821bef5e9c2a7c1e787f43d4bd17d55a524  iss98vfx.ips
82bcd67e020f43d69b4c9f5295d9c5e022b3df7d301000849e95dc3f2278f9a1  jfg-usa.aps
6fe933595ae50f308ef242d7dd507d2bba81bf2ddf80f39120ad038605e19239  jfg-usa.ram
3c5a4e1319ccb4bcba3dafe89f4d12d8ab81f791d4e7d7c535702a0a815bbc10  kgs-ags.hdr
1a2498aa7043af8f541ff751badd6cc07474c4695d70c76802fcac5448e3f84c  kgs-ags.ips
ea65c20e8cc2c4b3afba34fa7b8097f8bfaa88004efdf122b9f20684c27b837f  kgsgood.aps
23a78d9a8e7f8519c29f0277785867c901915fe04daf5b9905e4f06a375c951f  kombat4.hdr
d746d679b017c66ad682493a783e235397bb25cad7d5c6ec20d1b0ba78db0cfc  kombat4.ips
f8b6177bf18e04ace451924d335c3b22a35f33cfeb9f58878da66e4747de4223  mglf-usa.aps
90df92a5a3a6c40dfb39720af61479dda6eff5ae7ac323f055469a5c85842067  micromac.hdr
8aadad4fad239e31eefd4979157afbfcf54455ffaadeef1b957cc6c6a184a555  micromac.ips
7dc18751c660a66d21babea39e7af7d1478e0290a603286ab394cabbc6bacf55  mlb-kgjr.hdr
80a94bedf3455570a3e11b830844485644a7968b6819ed0c925d3cebbc3123a5  mlb-kgjr.ips
cf86e63eb42cc6a3b1e3ea7e93b520db5eefd69acf9d25910e29ceb29d08bcb1  mpusa.hdr
d658aa476d18f7d66621e9e7e2a2c4219513c5dadfb2a314f78d60883df85497  mpusa.ips
7b8a994005b87a326fce02aa8e6af1f0b300d31472d679fb8904492324e1053c  mten-usa.aps
3eeb85c9020db2d1a31f1a94f6b9903533ee971002e1f49107d1b81426fa79fb  mtr.aps
23163c29e414141b8733b44f6dafe38cc5503ff669f0e17e1f0cb1092af5d497  nascar99.hdr
66b7894cdd2705968c398d4b3a66c37d7e5d0c7b7e7222f076231db937b526b2  nascar99.ips
b1f836660cfa9843e4708a805a6a498901987cc1102f92023b4b19421907bf23  nba99.hdr
45dbec1c924de2bc342a99883f011715e9d0539a323832a7493c895abd13de19  nba99.ips
026b3428553204f11e24c25b0dbffd2c68fdcf81ae7ae9dceadf7d3fe070ef2f  nba99sfx.hdr
6bf5a95682dc12de246d6cfabe3e652fa4a87c272ab3bcd232160a0e1aa7751b  nba99sfx.ips
c9bea7caab8217d4f980bde0cb95628eaf01c0bc8c3852537ffab8fa4c42a202  nba_cs.hdr
4510745d41130f9d24fef4d2210534a205e1d28dc15fc12c78d85434eda791f1  nba_cs.zps
e6ddf1d5f11173dbb34d106e70e349ea6db9bab6f2b813ebac3c7086f0da39da  nbac2usa.aps
eb1c2656c3569b5aec7f7292b067f82d7da81dd5ed6940ffa70c869544207fdf  ncpfx.hdr
b19ed295e46d4848b7f35ee14e8ec49905818a72fb6252cdf5361261548be001  ncpfx.ips
7503e7558b490eaf7311b13a09d4437ac52c97e0e79d50fb187f216570d4a541  newtetr.aps
e0fe194d6e278a26f42d36eaf21c84f19ab195dccf541b0e9688aac8e841d92b  quake2.aps
627c4bb6159c8e1e0e434ec5d5e56cd92de966f729981d63df17513ecdcc9dc5  rugrt.hdr
928a9c4632893399df2b06c30b8b01e526b2c923a73b77fc441ce0272a973afd  rugrt.ips
ca13998d2ab9c221f558f545ebfbfb7f4f02de0014b8c5d16f80becf4ac2737b  scarspfx.hdr
9acc623243547c80a898e23edabacb23827e5a7a478eaaed4a74739e62701ef1  scarspfx.ips
28db79602868170363aeea31e2fc29ae8dd55d8481afa8bb9c37c5cb1891e423  smbus.aps
915705ec9983db401d70fbd70f6729a46c0239213a602f230d1fc3703ab3d5c6  snobo2us.aps
372249e6e6b509f3640248222529a85502ddfcbb9c3396d73254b1dd5f3ce506  ssvfx.hdr
964707ceff06da9179691fe23e8d4d5688cb38836963b4666ee271e22fc23473  ssvfx.ips
eb48a9ef07ec0729cf21c6b1588ff51e1f75eaada694aab9d6c59f40cc861f54  starntsc.aps
5a0f443c2d7fc187008e9c7cf60747cd1d4b24d2bb7da698bb8b36db377dbe75  swep1rus.aps
d6d0ceb8c2dd5d9da39c31052786acd60a0743ea61cd40012f2d7a620c305919  swep1rus.eep
1a2a59a4f4286e7a9168863b3dd5169c1fa0923c5ccfc67a99d226dba767cbfa  vchess.hdr
f3aea0214e3350eecf99434c04a0276f584fe4e18fb1922ee1bfa383c0238c73  vchess.ips
0753ca05b6afb4dc70c3b1e4306947431f5dd15c80de7fb2d03e912add52ef85  vil8.aps
97476a60070050adcf846494e549ecee40d1b6f3bf2aeb6d56ea2d0c65f31d58  wcwn.hdr
bedeff28e1537013c76c43cf338c2b9dc016e22a3a2a440020e74c4e603e383f  wcwn.ips
7a8836fd3fbecff3d4e891dfa0a341b8e2f047158a54a7bd2d34ccd9ab40b9d6  wcwpfx.hdr
b222838ba5cf43043e71388f01b4657cc34553ba41a54dae6deac23680fbb0cc  wcwpfx.ips
2eba23b94d4c432796e31af02cead6ddd170c4d89e3875dec061b6dc41a1646a  wg3dvfx.hdr
3a34bc16a6a602bbb2961970456916a7258610c28d033ec9eb9fee022b36f5c4  wg3dvfx.ips
4ad1361c4e8e725e3f9e3b56a6c9087f72a9f4f1124af85f27d46de2106d47ee  yoshi_e.hdr
c91ff1f7425223c68427e80cf56becbf0d06f31e6a94003143d67e19318342ad  yoshi_e.zps
52b8cf4ae0f4d7f597a6b222c420a403b9e65b8593027bd2958268f0e12df71c  zmm-usa.aps
84fe75fffe406d5c74b3f2e55bf39988465f48226c7349d11ca4ea58763674fc  zoot-usa.aps
```

### CRC32, for looking a file up elsewhere

```
abbeb3c4  1080_j.hdr
56d4db3b  1080_j.zps
20433960  bam99.hdr
e02b5b29  bam99.ips
e39ab1eb  banjo.hdr
11e7242f  banjo.zps
49ec1ad5  bass.aps
65d53f49  bh.hdr
72fd4ac5  bh.ips
8ded548e  bos99.hdr
c614b3cf  bos99.ips
da00b37b  btanxvfx.hdr
d473ec79  btanxvfx.ips
cf45b9e9  buckpfx.hdr
9eba2826  buckpfx.ips
a60a366d  cali.aps
bfcb4bc0  cc-usa.aps
f49934d8  chmtwst2.hdr
567c51aa  chmtwst2.ips
0c5defd1  davfx.hdr
835ab43f  davfx.ips
72acc470  dk64-usa.aps
8fa0cc19  dk64-usa.ram
0e4b563a  dx-btusc.aps
ebb7ca3c  ebikeusa.aps
7c7a66af  fdvfx.hdr
028422e1  fdvfx.ips
bbb1a852  fsh99sfx.hdr
3419c0c1  fsh99sfx.ips
ed13e955  fzerousa.hdr
0e44e843  fzerousa.ips
3189734b  gnvfx.hdr
c24f3f9d  gnvfx.ips
4d7243a3  iss98vfx.hdr
9115267b  iss98vfx.ips
ecd4d394  jfg-usa.aps
4c94501d  jfg-usa.ram
72d14c8c  kgs-ags.hdr
0ab13f12  kgs-ags.ips
5a224733  kgsgood.aps
028a5328  kombat4.hdr
4139dc43  kombat4.ips
89bfc0af  mglf-usa.aps
ace0e21b  micromac.hdr
281be6b2  micromac.ips
0d3d9e84  mlb-kgjr.hdr
5cdcb3c9  mlb-kgjr.ips
7807ac3e  mpusa.hdr
bcb4d68f  mpusa.ips
ca75d772  mten-usa.aps
a5c62d18  mtr.aps
20482a8e  nascar99.hdr
d1457bd0  nascar99.ips
34049b4f  nba99.hdr
e1c5bd8d  nba99.ips
866ec7ff  nba99sfx.hdr
25c78db1  nba99sfx.ips
194ece3f  nba_cs.hdr
17fe451c  nba_cs.zps
52ee7875  nbac2usa.aps
cdc6ec24  ncpfx.hdr
c6579188  ncpfx.ips
cdd87db0  newtetr.aps
5a90b8de  quake2.aps
ad7538e6  rugrt.hdr
ef324a06  rugrt.ips
31eab48c  scarspfx.hdr
8c5eaa20  scarspfx.ips
825069d5  smbus.aps
9a72b3c6  snobo2us.aps
df97ad09  ssvfx.hdr
7dbcfd14  ssvfx.ips
4a6f7bb3  starntsc.aps
e8049c29  swep1rus.aps
b701479b  swep1rus.eep
2db81299  vchess.hdr
433c5e94  vchess.ips
51b75501  vil8.aps
bed0e0d1  wcwn.hdr
b22a8b42  wcwn.ips
e67be363  wcwpfx.hdr
e349696d  wcwpfx.ips
8422410e  wg3dvfx.hdr
a1d886e0  wg3dvfx.ips
f2323426  yoshi_e.hdr
afb188b8  yoshi_e.zps
8dd87884  zmm-usa.aps
39d27d56  zoot-usa.aps
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
| `z64patch.dat` | Unofficial Z64 patch database v3.0U |

Game images never belong here either. This folder is for the small files that make
a game run on the unit, not for the games.

## Provenance

| File | Recorded source |
|:-----|:----------------|
| `1080_j.hdr` | ships beside its patch |
| `1080_j.zps` | CRACK.ZIP |
| `bam99.hdr` | ships beside its patch |
| `bam99.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `banjo.hdr` | ships beside its patch |
| `banjo.zps` | CRACK.ZIP |
| `bass.aps` | z64patch27P-unofficial.zip z64patch.dat |
| `bh.hdr` | ships beside its patch |
| `bh.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `bos99.hdr` | ships beside its patch |
| `bos99.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `btanxvfx.hdr` | ships beside its patch |
| `btanxvfx.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `buckpfx.hdr` | ships beside its patch |
| `buckpfx.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `cali.aps` | z64patch27P-unofficial.zip z64patch.dat |
| `cc-usa.aps` | Unofficial Z64 Patch File v3.0U |
| `chmtwst2.hdr` | ships beside its patch |
| `chmtwst2.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `davfx.hdr` | ships beside its patch |
| `davfx.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `dk64-usa.aps` | Unofficial Z64 Patch File v3.0U |
| `dk64-usa.ram` | Unofficial Z64 Patch File v3.0U |
| `dx-btusc.aps` | Standalone dextrose release dx-btusc |
| `ebikeusa.aps` | Unofficial Z64 Patch File v3.0U |
| `fdvfx.hdr` | ships beside its patch |
| `fdvfx.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `fsh99sfx.hdr` | ships beside its patch |
| `fsh99sfx.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `fzerousa.hdr` | ships beside its patch |
| `fzerousa.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `gnvfx.hdr` | ships beside its patch |
| `gnvfx.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `iss98vfx.hdr` | ships beside its patch |
| `iss98vfx.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `jfg-usa.aps` | Unofficial Z64 Patch File v3.0U |
| `jfg-usa.ram` | Unofficial Z64 Patch File v3.0U |
| `kgs-ags.hdr` | ships beside its patch |
| `kgs-ags.ips` | z64patch.dat, z64patch30UP-unofficial.zip z64patch.dat, z64pf30u.zip z64patch.dat |
| `kgsgood.aps` | Unofficial Z64 Patch File v3.0U, extra folder |
| `kombat4.hdr` | ships beside its patch |
| `kombat4.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `mglf-usa.aps` | Unofficial Z64 Patch File v3.0U |
| `micromac.hdr` | ships beside its patch |
| `micromac.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `mlb-kgjr.hdr` | ships beside its patch |
| `mlb-kgjr.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `mpusa.hdr` | ships beside its patch |
| `mpusa.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `mten-usa.aps` | Unofficial Z64 Patch File v3.0U |
| `mtr.aps` | z64patch27P-unofficial.zip z64patch.dat |
| `nascar99.hdr` | ships beside its patch |
| `nascar99.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `nba99.hdr` | ships beside its patch |
| `nba99.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `nba99sfx.hdr` | ships beside its patch |
| `nba99sfx.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `nba_cs.hdr` | ships beside its patch |
| `nba_cs.zps` | CRACK.ZIP |
| `nbac2usa.aps` | Unofficial Z64 Patch File v3.0U |
| `ncpfx.hdr` | ships beside its patch |
| `ncpfx.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `newtetr.aps` | z64patch27P-unofficial.zip z64patch.dat |
| `quake2.aps` | z64patch27P-unofficial.zip z64patch.dat |
| `rugrt.hdr` | ships beside its patch |
| `rugrt.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `scarspfx.hdr` | ships beside its patch |
| `scarspfx.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `smbus.aps` | z64patch27P-unofficial.zip z64patch.dat |
| `snobo2us.aps` | z64patch27P-unofficial.zip z64patch.dat |
| `ssvfx.hdr` | ships beside its patch |
| `ssvfx.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `starntsc.aps` | z64patch27P-unofficial.zip z64patch.dat |
| `swep1rus.aps` | Unofficial Z64 Patch File v3.0U |
| `swep1rus.eep` | Unofficial Z64 Patch File v3.0U |
| `vchess.hdr` | ships beside its patch |
| `vchess.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `vil8.aps` | z64patch27P-unofficial.zip z64patch.dat |
| `wcwn.hdr` | ships beside its patch |
| `wcwn.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `wcwpfx.hdr` | ships beside its patch |
| `wcwpfx.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `wg3dvfx.hdr` | ships beside its patch |
| `wg3dvfx.ips` | z64patch27P-unofficial.zip z64patch.dat |
| `yoshi_e.hdr` | ships beside its patch |
| `yoshi_e.zps` | CRACK.ZIP |
| `zmm-usa.aps` | Unofficial Z64 Patch File v3.0U |
| `zoot-usa.aps` | Unofficial Z64 Patch File v3.0U |

A recorded source says where the digest came from. It is not a claim that the file
is correct, safe, or what it says it is. Every one of these was verified against
the ROM it targets before being trusted, and so should any replacement.
