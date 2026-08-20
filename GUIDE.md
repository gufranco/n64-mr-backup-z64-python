# Getting your games onto Zip disks

This guide assumes you have never opened a terminal. It takes about twenty minutes
the first time, and about two minutes for every disk after that.

You will need a Mr. Backup Z64, a Nintendo 64, at least one real N64 game
cartridge, some Zip 100 disks, and your own copies of the games you want to play.

---

## What this program does, in one paragraph

The Z64 reads games from Zip 100 disks. Those disks have to be laid out in a way
the Z64 understands, with short filenames, in a specific disk format, and packed so
you do not waste space and end up buying more disks than you need. Doing that by
hand for a hundred games is miserable. This program does it, tells you which games
will need something extra, and prints a catalogue you can keep with the disks.

**It does not include any games.** You supply those.

---

## Step 1: check you have Python

The program is written in Python, so your computer needs Python 3.11 or newer.
Most Macs and Linux machines already have it. Windows usually does not.

### Open a terminal

| Your computer | How |
|:--------------|:----|
| **Mac** | Press `Cmd` + `Space`, type `Terminal`, press Enter |
| **Windows** | Press the Windows key, type `powershell`, press Enter |
| **Linux** | Press `Ctrl` + `Alt` + `T` |

A window with a text cursor appears. This is where you type commands. When this
guide shows a line in a grey box, type it and press Enter.

### Check the version

```
python3 --version
```

If you see `Python 3.11` or higher, skip to Step 2.

If you see `Python 3.10` or lower, or `command not found`, install Python from
[python.org/downloads](https://www.python.org/downloads/). On Windows, **tick "Add
python.exe to PATH"** on the first screen of the installer. If you miss that box,
nothing below will work and you will have to run the installer again.

On Windows, type `python` instead of `python3` everywhere in this guide.

---

## Step 2: install the program

It is not on the Python package index yet, so it installs from the source. Download
the repository as a ZIP from
[the project page](https://github.com/gufranco/n64-mr-backup-z64-python), unzip it,
then in the terminal move into the unzipped folder and run:

```
pip install .
```

To move into a folder, type `cd ` with a space after it, then drag the folder from
Finder or Explorer into the terminal window and press Enter.

Then check it worked:

```
z64kit doctor
```

You should see a list starting with `artifact manifest`. If you instead see
`command not found`, try this longer form, which works even when the short name
is not on your PATH:

```
python3 -m z64kit.cli doctor
```

If that works, use `python3 -m z64kit.cli` everywhere this guide says `z64kit`.

---

## Step 3: put your games in one folder

Make a folder and put your game files in it. The program accepts files ending in
`.z64`, `.v64`, `.n64` and `.rom`.

You do not need to rename anything. Long names with spaces, brackets and
punctuation are all fine. Shortening them for the Z64 is one of the things the
program does for you.

If you already know how you want the games split across disks, make one folder per
disk inside your main folder and name them however you like. The program will
respect that grouping instead of working out its own.

---

## Step 4: run it

```
z64kit
```

That is the whole command. No options, no paths. It asks you five questions, one
screen at a time, and nothing is written to your computer until you say yes on the
last one. Your game files are never modified.

At any question you can type `q` and press Enter to leave.

### What it asks

**Where are your games?** It offers folders that look right. Type the number next
to the one you want. If yours is not listed, pick the last option and then drag the
folder from Finder or Explorer straight into the terminal window. That pastes the
path for you, and the program understands the quotes that come with it.

**The extra files.** Some games need a small extra file to save or even to boot.
This screen tells you which ones you have and which are missing. Missing files are
not fatal: every other game still works. See Step 6 if you want to fix it.

**What this will take.** How many games, how many disks, and a plain-language line
for every game that needs something beyond the disk. Read this part. It is where
you find out that a game needs a particular cartridge in the slot.

**Folders or disk images?**

| Choice | Pick this when |
|:-------|:---------------|
| **Folders** | You want to copy files to a Zip disk yourself, using Finder or Explorer. Simpler, and easier to check before you commit |
| **Disk images** | You want a single file per disk to write to the drive in one go. Faster once you are set up |

**Confirm.** It shows you where it is reading from, where it is writing to, and
what it is about to make. Nothing has happened yet. Say yes.

---

## Step 5: get it onto a Zip disk

### If you chose folders

Copy the contents of each folder onto its own Zip disk with Finder or Explorer.
One folder, one disk. Do not copy the folder itself. Copy what is *inside* it, so
the files sit at the top level of the disk.

### If you chose disk images

Each image is one whole disk as a single file. Writing one replaces everything on
that Zip disk. On macOS and Linux the repository includes a helper script,
`write-zip.sh`. On Windows, use a disk-imaging tool.

> **Careful.** Writing an image erases the target disk completely. Check twice
> that you have named the Zip drive and not your hard disk. This is the one step
> in the whole process that can lose data.

---

## Step 6: the extra files

A handful of games cannot save on the Z64 without a small extra file, and two or
three will not boot without one. The program cannot include these files, so you
have to supply them yourself.

Run this to see exactly what is expected:

```
z64kit artifacts
```

It lists every file by name, size and checksum, and separates three different
problems, because they need three different fixes:

| What it says | What to do |
|:-------------|:-----------|
| **missing** | You do not have the file. Nothing to do but find it |
| **present but not what the manifest expects** | You have a file of that name but different content. It is a different version |
| **right file, wrong name** | You already have it. Just rename it, nothing to find |

Put the files in a folder called `patches` next to where you are running the
command. The file [`patches/README.md`](patches/README.md) lists every one with its
exact size and checksum so you can confirm a file is the right one before using it.

**This program will not help you find these files, and does not say where they come
from.** That is deliberate.

---

## Step 7: which cartridges do you need

The Z64 has no save chip of its own for some save types. Those games write their
save to whichever real cartridge is sitting in the slot, so that cartridge has to
carry the right kind of chip. One cartridge holds one game's save.

The guided flow offers to do this for you at the end. To do it separately, name the
folder holding your games:

```
z64kit inventory YOUR-GAME-FOLDER --ask
```

It shows a list with checkboxes. Type numbers to tick and untick, then press Enter.
It remembers your answers, so run it again any time to change them.

Once it knows what you own, it stops nagging you about gaps you have already
filled, and tells you what is still outstanding. Where a single cartridge solves two
problems at once, the right save chip and the right boot chip together, it says so.
That can save you a purchase.

---

## Step 8: print a catalogue

The guided flow offers to do this for you at the end. To do it separately, name the
folder holding your games and a folder to write into:

```
z64kit report YOUR-GAME-FOLDER WHERE-TO-PUT-IT
```

This writes a printable document listing every disk, every game on it, its short
name on the disk, and a section naming exactly what each affected game needs. Keep
it with the disks. It is much faster than plugging disks in to find out what is on
them.

If a program called `tectonic` is installed you get a PDF. Otherwise you get a
`.tex` file, which any LaTeX tool can turn into a PDF later. The document is
designed for a black-and-white laser printer.

---

## When something goes wrong

**`command not found: z64kit`**
The install worked but the short name is not on your PATH. Use
`python3 -m z64kit.cli` instead of `z64kit`.

**`command not found: python3`** (Windows)
Type `python` instead. If that also fails, Python was installed without the "Add
to PATH" box ticked. Run the installer again.

**`No game files found`**
The folder you chose has no `.z64`, `.v64`, `.n64` or `.rom` files directly inside
it. If your games are in sub-folders, choose the folder *above* them.

**`the patch folder ... does not exist`**
A folder you named is not there, usually a typo. The program stops rather than
carrying on, because carrying on would quietly build disks with no patches at all.

**A game does not boot on the Z64**
Check the catalogue for that game. Games needing a 6103 or 6106 boot chip need a
setting changed in the Z64's own Game Setup menu, which is on the unit, not in this
program. Games marked as needing a donor cartridge need that cartridge in the slot.

**A game boots but will not save**
Almost always the save chip. The catalogue names which cartridge that game needs.

**Something asked a question and I want out**
Type `q` and press Enter. Nothing is written unless you reached the final
confirmation and said yes.

---

## What this program never does

- Change your game files. It reads them and writes copies.
- Send anything over the network, except `z64kit db-update`, which downloads a
  public list of which cartridge used which save chip. Nothing else in this
  program touches the internet.
- Include, fetch, or tell you where to get games, firmware or patches.
- Write anything without asking first.

---

## Words this guide uses

| Word | What it means here |
|:-----|:-------------------|
| **ROM** | A game file, one per game |
| **Patch** | A small file that changes how a game behaves on the Z64, usually so it can save |
| **Donor cartridge** | A real N64 game whose cartridge carries the save chip another game needs. It goes in the slot, and you are borrowing its chip rather than its game |
| **Boot chip** / **CIC** | A security chip. The Z64 imitates several kinds, and some games need a specific one selected in Game Setup |
| **Disk image** | One file holding the entire contents of one Zip disk |
| **Checksum** | A long string of letters and numbers that identifies a file exactly. Two files with the same checksum are the same file |
| **8.3 name** | The old-style short filename the Z64 needs: up to eight characters, a dot, then three |
