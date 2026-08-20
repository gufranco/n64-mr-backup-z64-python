import json

import pytest
from tests.conftest import make_rom

from z64kit import cli


def write_rom(folder, name, **kw):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(make_rom(**kw))


@pytest.fixture
def collection(tmp_path):
    root = tmp_path / "roms"
    write_rom(root, "Wave Race 64 (USA).z64", cart="WR", size=8 * 1024 * 1024)
    write_rom(root, "Super Mario 64 (USA).z64", cart="SM", size=8 * 1024 * 1024)
    return root


class TestScanCommand:
    def test_reports_what_it_found(self, collection, capsys):
        code = cli.main(["scan", str(collection)])

        out = capsys.readouterr().out
        assert code == 0
        assert "2 games" in out

    def test_names_each_game(self, collection, capsys):
        cli.main(["scan", str(collection)])

        assert "Wave Race 64" in capsys.readouterr().out

    def test_json_output_is_machine_readable(self, collection, capsys):
        cli.main(["scan", str(collection), "--json"])

        payload = json.loads(capsys.readouterr().out)
        assert len(payload["games"]) == 2

    def test_a_missing_folder_exits_non_zero(self, tmp_path, capsys):
        code = cli.main(["scan", str(tmp_path / "nope")])

        assert code != 0
        assert "not a directory" in capsys.readouterr().err

    def test_reports_a_skipped_file(self, collection, capsys):
        (collection / "notes.txt").write_text("x", encoding="utf-8")

        cli.main(["scan", str(collection)])

        assert "skipped" in capsys.readouterr().out.lower()


class TestPlanCommand:
    def test_reports_the_disk_count_and_the_bound(self, collection, capsys):
        code = cli.main(["plan", str(collection)])

        out = capsys.readouterr().out
        assert code == 0
        assert "1 disk" in out
        assert "optimal" in out

    def test_honours_an_existing_curation(self, tmp_path, capsys):
        root = tmp_path / "curated"
        write_rom(root / "Zip Disk 01", "One (USA).z64", cart="AA")
        write_rom(root / "Zip Disk 02", "Two (USA).z64", cart="BB")

        cli.main(["plan", str(root)])

        assert "2 disks" in capsys.readouterr().out

    def test_names_the_8_3_name_each_game_will_get(self, collection, capsys):
        cli.main(["plan", str(collection)])

        assert "MARIO64" in capsys.readouterr().out


class TestBuildCommand:
    def test_writes_one_image_per_disk(self, collection, tmp_path, capsys):
        out_dir = tmp_path / "images"

        code = cli.main(["build", str(collection), str(out_dir)])

        assert code == 0
        assert len(list(out_dir.glob("*.img"))) == 1

    def test_each_image_is_the_media_size(self, collection, tmp_path):
        out_dir = tmp_path / "images"

        cli.main(["build", str(collection), str(out_dir)])

        image = next(out_dir.glob("*.img"))
        assert image.stat().st_size == 100_663_296

    def test_writes_a_manifest(self, collection, tmp_path):
        out_dir = tmp_path / "images"

        cli.main(["build", str(collection), str(out_dir)])

        assert (out_dir / "manifest.json").exists()

    def test_the_manifest_records_a_digest_per_image(self, collection, tmp_path):
        out_dir = tmp_path / "images"

        cli.main(["build", str(collection), str(out_dir)])
        payload = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

        assert payload["disks"][0]["sha256"]

    def test_the_build_is_reproducible(self, collection, tmp_path):
        first, second = tmp_path / "a", tmp_path / "b"

        cli.main(["build", str(collection), str(first)])
        cli.main(["build", str(collection), str(second)])

        a = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
        b = json.loads((second / "manifest.json").read_text(encoding="utf-8"))
        assert [d["sha256"] for d in a["disks"]] == [d["sha256"] for d in b["disks"]]

    def test_verification_runs_by_default(self, collection, tmp_path, capsys):
        cli.main(["build", str(collection), str(tmp_path / "images")])

        assert "verified" in capsys.readouterr().out.lower()


class TestOrganiseCommand:
    def test_writes_one_folder_per_disk(self, collection, tmp_path):
        out_dir = tmp_path / "organised"

        code = cli.main(["organise", str(collection), str(out_dir)])

        assert code == 0
        assert [p.name for p in sorted(out_dir.iterdir()) if p.is_dir()] == ["Disk 01"]

    def test_names_each_file_with_its_8_3_name(self, collection, tmp_path):
        out_dir = tmp_path / "organised"

        cli.main(["organise", str(collection), str(out_dir)])

        names = sorted(p.name for p in (out_dir / "Disk 01").iterdir())
        assert "MARIO64.Z64" in names

    def test_copies_the_content_faithfully(self, collection, tmp_path):
        out_dir = tmp_path / "organised"
        source = (collection / "Super Mario 64 (USA).z64").read_bytes()

        cli.main(["organise", str(collection), str(out_dir)])

        assert (out_dir / "Disk 01" / "MARIO64.Z64").read_bytes() == source

    def test_uses_the_true_extension_when_the_name_lies(self, tmp_path):
        root = tmp_path / "roms"
        write_rom(root, "Swapped (USA).z64", order="v64", cart="SW")

        cli.main(["organise", str(root), str(tmp_path / "out")])

        names = [p.name for p in (tmp_path / "out" / "Disk 01").iterdir()]
        assert any(n.endswith(".V64") for n in names)

    def test_honours_an_existing_curation(self, tmp_path):
        root = tmp_path / "curated"
        write_rom(root / "Zip Disk 01", "One (USA).z64", cart="AA")
        write_rom(root / "Zip Disk 02", "Two (USA).z64", cart="BB")

        cli.main(["organise", str(root), str(tmp_path / "out")])

        folders = [p.name for p in sorted((tmp_path / "out").iterdir()) if p.is_dir()]
        assert folders == ["Zip Disk 01", "Zip Disk 02"]

    def test_reports_what_it_wrote(self, collection, tmp_path, capsys):
        cli.main(["organise", str(collection), str(tmp_path / "out")])

        assert "1 folder" in capsys.readouterr().out

    def test_writes_a_manifest_beside_the_folders(self, collection, tmp_path):
        out_dir = tmp_path / "organised"

        cli.main(["organise", str(collection), str(out_dir)])

        assert (out_dir / "manifest.json").exists()

    def test_refuses_to_overwrite_without_permission(self, collection, tmp_path, capsys):
        out_dir = tmp_path / "organised"
        cli.main(["organise", str(collection), str(out_dir)])

        code = cli.main(["organise", str(collection), str(out_dir)])

        assert code != 0
        assert "already" in capsys.readouterr().err.lower()

    def test_force_allows_a_rewrite(self, collection, tmp_path):
        out_dir = tmp_path / "organised"
        cli.main(["organise", str(collection), str(out_dir)])

        code = cli.main(["organise", str(collection), str(out_dir), "--force"])

        assert code == 0

    def test_copies_a_companion_file_under_the_rom_name(self, tmp_path):
        root = tmp_path / "roms"
        write_rom(root, "Game (USA).z64", cart="GG")
        (root / "Game (USA).ram").write_bytes(bytes(1024))

        cli.main(["organise", str(root), str(tmp_path / "out")])

        names = sorted(p.name for p in (tmp_path / "out" / "Disk 01").iterdir())
        assert any(n.endswith(".RAM") for n in names)


class TestInventoryCommand:
    def test_lists_the_questions_without_prompting(self, collection, tmp_path, capsys):
        code = cli.main(
            ["inventory", str(collection), "--file", str(tmp_path / "inv.json"), "--show"]
        )

        assert code == 0
        assert "boot" in capsys.readouterr().out.lower()

    def test_records_what_is_owned(self, collection, tmp_path, capsys):
        path = tmp_path / "inv.json"

        cli.main(["inventory", str(collection), "--file", str(path), "--own", "boot"])

        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["owned"] == ["boot"]
        assert payload["recorded"] is True

    def test_reports_the_shopping_list(self, collection, tmp_path, capsys):
        cli.main(["inventory", str(collection), "--file", str(tmp_path / "inv.json"), "--show"])

        assert "boot cartridge" in capsys.readouterr().out.lower()


class TestReportCommand:
    def test_writes_the_latex_source(self, collection, tmp_path, capsys):
        out_dir = tmp_path / "reports"

        code = cli.main(["report", str(collection), str(out_dir), "--no-pdf"])

        assert code == 0
        assert (out_dir / "catalogue.tex").exists()

    def test_says_where_the_output_went(self, collection, tmp_path, capsys):
        cli.main(["report", str(collection), str(tmp_path / "reports"), "--no-pdf"])

        assert "catalogue.tex" in capsys.readouterr().out


class TestDoctorCommand:
    def test_reports_the_environment(self, capsys):
        code = cli.main(["doctor"])

        out = capsys.readouterr().out
        assert code == 0
        assert "manifest" in out.lower()

    def test_names_whether_a_tex_engine_is_available(self, capsys):
        cli.main(["doctor"])

        assert "tex" in capsys.readouterr().out.lower()


class TestNoArguments:
    def test_shows_usage_and_exits_non_zero(self, capsys):
        assert cli.main([]) != 0


class TestPatchLibrary:
    def test_no_folder_yields_no_patches(self):
        assert cli._patch_library(None) == {}

    def test_a_missing_folder_yields_no_patches(self, tmp_path):
        assert cli._patch_library(str(tmp_path / "nope")) == {}

    def test_indexes_a_patch_by_its_target_header(self, tmp_path):
        lib_dir = tmp_path / "patches"
        lib_dir.mkdir()
        target = make_rom(cart="GG")
        (lib_dir / "fix.hdr").write_bytes(target[:64])
        (lib_dir / "fix.aps").write_bytes(b"APS10" + bytes(0x60))

        found = cli._patch_library(str(lib_dir))

        assert target[:64] in found

    def test_carries_the_payload_and_its_extension(self, tmp_path):
        lib_dir = tmp_path / "patches"
        lib_dir.mkdir()
        target = make_rom(cart="GG")
        (lib_dir / "fix.hdr").write_bytes(target[:64])
        (lib_dir / "fix.aps").write_bytes(b"APS10" + bytes(0x60))

        entries = cli._patch_library(str(lib_dir))[target[:64]]

        assert entries[0][1] == "APS"
        assert entries[0][2].startswith(b"APS10")

    def test_attaches_a_companion_save_file(self, tmp_path):
        lib_dir = tmp_path / "patches"
        lib_dir.mkdir()
        target = make_rom(cart="GG")
        (lib_dir / "fix.hdr").write_bytes(target[:64])
        (lib_dir / "fix.aps").write_bytes(b"APS10" + bytes(0x60))
        (lib_dir / "fix.ram").write_bytes(bytes(2048))

        entries = cli._patch_library(str(lib_dir))[target[:64]]

        assert {e[1] for e in entries} == {"APS", "RAM"}

    def test_skips_a_payload_with_no_header(self, tmp_path):
        lib_dir = tmp_path / "patches"
        lib_dir.mkdir()
        (lib_dir / "orphan.aps").write_bytes(b"APS10" + bytes(0x60))

        assert cli._patch_library(str(lib_dir)) == {}

    def test_ignores_a_subdirectory(self, tmp_path):
        lib_dir = tmp_path / "patches"
        (lib_dir / "nested").mkdir(parents=True)

        assert cli._patch_library(str(lib_dir)) == {}

    def test_a_matched_patch_is_written_into_the_image(self, tmp_path):
        root = tmp_path / "roms"
        write_rom(root, "Game (USA).z64", cart="GG")
        lib_dir = tmp_path / "patches"
        lib_dir.mkdir()
        (lib_dir / "fix.hdr").write_bytes((root / "Game (USA).z64").read_bytes()[:64])
        (lib_dir / "fix.aps").write_bytes(b"APS10" + bytes(0x60))
        out_dir = tmp_path / "images"

        cli.main(["build", str(root), str(out_dir), "--patches", str(lib_dir)])
        payload = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

        names = [f["name"] for f in payload["disks"][0]["files"]]
        assert any(n.endswith(".APS") for n in names)

    def test_a_matched_patch_is_written_into_the_folder(self, tmp_path):
        root = tmp_path / "roms"
        write_rom(root, "Game (USA).z64", cart="GG")
        lib_dir = tmp_path / "patches"
        lib_dir.mkdir()
        (lib_dir / "fix.hdr").write_bytes((root / "Game (USA).z64").read_bytes()[:64])
        (lib_dir / "fix.aps").write_bytes(b"APS10" + bytes(0x60))
        out_dir = tmp_path / "organised"

        cli.main(["organise", str(root), str(out_dir), "--patches", str(lib_dir)])

        names = [p.name for p in (out_dir / "Disk 01").iterdir()]
        assert any(n.endswith(".APS") for n in names)

    def test_a_patch_for_another_revision_is_not_applied(self, tmp_path):
        root = tmp_path / "roms"
        write_rom(root, "Game (USA).z64", cart="GG", crc1=0x11111111)
        lib_dir = tmp_path / "patches"
        lib_dir.mkdir()
        (lib_dir / "fix.hdr").write_bytes(make_rom(cart="GG", crc1=0x99999999)[:64])
        (lib_dir / "fix.aps").write_bytes(b"APS10" + bytes(0x60))
        out_dir = tmp_path / "images"

        cli.main(["build", str(root), str(out_dir), "--patches", str(lib_dir)])
        payload = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

        names = [f["name"] for f in payload["disks"][0]["files"]]
        assert not any(n.endswith(".APS") for n in names)


class TestViCommand:
    def test_reports_a_rom_with_no_mode_table(self, collection, capsys):
        code = cli.main(["vi", str(collection)])

        out = capsys.readouterr().out
        assert code == 0
        assert "no video mode table" in out.lower()

    def test_reports_a_planted_mode_table(self, tmp_path, capsys):
        from tests.test_vi import mode_entry

        root = tmp_path / "roms"
        root.mkdir()
        (root / "Game (USA).z64").write_bytes(
            make_rom(cart="GG")[:0x1000] + mode_entry() + make_rom(cart="GG")[0x1000:]
        )

        cli.main(["vi", str(root)])
        out = capsys.readouterr().out

        assert "MODES" in out

    def test_json_output_is_machine_readable(self, collection, capsys):
        cli.main(["vi", str(collection), "--json"])

        payload = json.loads(capsys.readouterr().out)
        assert "roms" in payload

    def test_explains_that_the_dither_filter_is_runtime_set(self, collection, capsys):
        cli.main(["vi", str(collection)])

        assert "osViSetSpecialFeatures" in capsys.readouterr().out

    def test_a_missing_folder_exits_non_zero(self, tmp_path, capsys):
        assert cli.main(["vi", str(tmp_path / "nope")]) != 0

    def test_audit_never_writes_anything(self, collection, tmp_path):
        before = {p: p.read_bytes() for p in collection.iterdir()}

        cli.main(["vi", str(collection)])

        assert all(p.read_bytes() == b for p, b in before.items())


class TestViPatchCommand:
    def sealed_rom(self, path, ctrl=0x0000311E):
        from tests.test_vi import mode_entry

        from z64kit import vi

        base = bytearray(make_rom(size=vi.CHECKSUM_END + 0x2000, cart="GG"))
        entry = mode_entry(ctrl=ctrl)
        base[0x2000 : 0x2000 + len(entry)] = entry
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(vi.reseal(bytes(base)))

    def test_dry_run_is_the_default_and_writes_nothing(self, tmp_path, capsys):
        root = tmp_path / "roms"
        self.sealed_rom(root / "Game (USA).z64")
        out = tmp_path / "out"

        code = cli.main(["vi", str(root), "--no-aa", "--output", str(out)])

        assert code == 0
        assert not out.exists()
        assert "dry run" in capsys.readouterr().out.lower()

    def test_apply_writes_a_patched_copy(self, tmp_path):
        root = tmp_path / "roms"
        self.sealed_rom(root / "Game (USA).z64")
        out = tmp_path / "out"

        cli.main(["vi", str(root), "--no-aa", "--output", str(out), "--apply"])

        assert (out / "Game (USA).z64").exists()

    def test_the_source_rom_is_never_modified(self, tmp_path):
        root = tmp_path / "roms"
        target = root / "Game (USA).z64"
        self.sealed_rom(target)
        before = target.read_bytes()

        cli.main(["vi", str(root), "--no-aa", "--output", str(tmp_path / "out"), "--apply"])

        assert target.read_bytes() == before

    def test_the_patched_copy_has_anti_aliasing_off(self, tmp_path):
        from z64kit import vi

        root = tmp_path / "roms"
        self.sealed_rom(root / "Game (USA).z64")
        out = tmp_path / "out"

        cli.main(["vi", str(root), "--no-aa", "--output", str(out), "--apply"])

        assert vi.audit((out / "Game (USA).z64").read_bytes()).antialiasing_on == 0

    def test_the_patched_copy_carries_a_valid_checksum(self, tmp_path):
        from z64kit.rom import checksum

        root = tmp_path / "roms"
        self.sealed_rom(root / "Game (USA).z64")
        out = tmp_path / "out"

        cli.main(["vi", str(root), "--no-aa", "--output", str(out), "--apply"])

        assert checksum.verify((out / "Game (USA).z64").read_bytes())[0] is True

    def test_requires_an_output_folder_before_applying(self, tmp_path, capsys):
        root = tmp_path / "roms"
        self.sealed_rom(root / "Game (USA).z64")

        code = cli.main(["vi", str(root), "--no-aa", "--apply"])

        assert code != 0
        assert "output" in capsys.readouterr().err.lower()

    def test_reports_a_rom_it_refused_to_touch(self, tmp_path, capsys):
        root = tmp_path / "roms"
        root.mkdir()
        (root / "Plain (USA).z64").write_bytes(make_rom(cart="PL"))

        cli.main(["vi", str(root), "--no-aa", "--output", str(tmp_path / "o")])

        assert "refused" in capsys.readouterr().out.lower()

    def test_combines_several_switches(self, tmp_path):
        from z64kit import vi

        root = tmp_path / "roms"
        self.sealed_rom(root / "Game (USA).z64")
        out = tmp_path / "out"

        cli.main(
            [
                "vi",
                str(root),
                "--no-aa",
                "--no-divot",
                "--no-gamma-dither",
                "--output",
                str(out),
                "--apply",
            ]
        )
        report = vi.audit((out / "Game (USA).z64").read_bytes())

        assert (report.antialiasing_on, report.divot_on, report.gamma_dither_on) == (0, 0, 0)


class TestDbUpdateCommand:
    def test_the_command_the_error_message_names_exists(self):
        from z64kit import cli

        parser = cli.build_parser()

        assert parser.parse_args(["db-update"]).func is not None

    def test_reports_where_the_catalogue_was_cached(self, tmp_path, monkeypatch, capsys):
        import io
        import urllib.request

        from z64kit import cli

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        monkeypatch.setattr(
            urllib.request, "urlopen", lambda *a, **k: Response(b"ID:NSME cic6102|eeprom512 # X\n")
        )

        assert cli.main(["db-update"]) == 0
        assert "N64-database.txt" in capsys.readouterr().out

    def test_reports_a_download_failure_without_a_traceback(self, tmp_path, monkeypatch, capsys):
        import urllib.error
        import urllib.request

        from z64kit import cli

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

        def explode(*_a, **_k):
            raise urllib.error.URLError("no route to host")

        monkeypatch.setattr(urllib.request, "urlopen", explode)

        assert cli.main(["db-update"]) == 1
        assert "no route to host" in capsys.readouterr().out


class TestMergeCommand:
    def test_the_merge_command_is_registered(self):
        from z64kit import cli

        parser = cli.build_parser()

        assert parser.parse_args(["merge", "rom.z64", "patch.aps"]).func is not None

    def test_refuses_to_write_without_an_output_path(self, tmp_path, capsys):
        from z64kit import cli

        rom = tmp_path / "game.z64"
        rom.write_bytes(bytes(0x100))
        patch = tmp_path / "game.aps"
        patch.write_bytes(bytes(0x100))

        assert cli.main(["merge", str(rom), str(patch), "--no-aa", "--apply"]) == 2
        assert "--output" in capsys.readouterr().out

    def test_reports_a_refusal_in_plain_language(self, tmp_path, capsys):
        from z64kit import cli

        rom = tmp_path / "game.z64"
        rom.write_bytes(bytes(0x1000))
        patch = tmp_path / "game.aps"
        patch.write_bytes(b"not a patch at all")

        assert cli.main(["merge", str(rom), str(patch), "--no-aa"]) == 1
        assert "magic" in capsys.readouterr().out.lower()


class TestMergeCommandSuccess:
    def rom_and_patch(self, tmp_path):
        from tests.test_merge import rom_with_table, save_patch_for

        rom = rom_with_table()
        rom_path = tmp_path / "game.z64"
        rom_path.write_bytes(rom)
        patch_path = tmp_path / "game.aps"
        patch_path.write_bytes(save_patch_for(rom))
        return rom_path, patch_path

    def test_a_dry_run_writes_nothing_and_says_so(self, tmp_path, capsys):
        from z64kit import cli

        rom_path, patch_path = self.rom_and_patch(tmp_path)
        out_path = tmp_path / "merged.aps"

        code = cli.main(
            ["merge", str(rom_path), str(patch_path), "--no-aa", "--output", str(out_path)]
        )

        assert code == 0
        assert not out_path.exists()
        assert "dry run" in capsys.readouterr().out

    def test_reports_the_boot_chip_and_the_changed_words(self, tmp_path, capsys):
        from z64kit import cli

        rom_path, patch_path = self.rom_and_patch(tmp_path)

        cli.main(["merge", str(rom_path), str(patch_path), "--no-aa"])
        printed = capsys.readouterr().out

        assert "boot chip" in printed
        assert "video words changed" in printed

    def test_apply_writes_a_patch_that_binds_to_the_untouched_rom(self, tmp_path):
        from z64kit import aps, cli

        rom_path, patch_path = self.rom_and_patch(tmp_path)
        out_path = tmp_path / "merged.aps"

        code = cli.main(
            [
                "merge",
                str(rom_path),
                str(patch_path),
                "--no-aa",
                "--output",
                str(out_path),
                "--apply",
            ]
        )

        assert code == 0
        rom = rom_path.read_bytes()
        assert aps.parse(out_path.read_bytes()).crc1 == aps.target_checksums(rom)[0]

    def test_the_rom_file_is_not_rewritten(self, tmp_path):
        from z64kit import cli

        rom_path, patch_path = self.rom_and_patch(tmp_path)
        before = rom_path.read_bytes()

        cli.main(
            [
                "merge",
                str(rom_path),
                str(patch_path),
                "--no-aa",
                "--output",
                str(tmp_path / "m.aps"),
                "--apply",
            ]
        )

        assert rom_path.read_bytes() == before

    def test_says_nothing_was_needed_when_the_settings_already_match(self, tmp_path, capsys):
        from tests.test_merge import rom_with_table, save_patch_for

        from z64kit import cli

        rom = rom_with_table(ctrl=0x0000320E)
        rom_path = tmp_path / "already.z64"
        rom_path.write_bytes(rom)
        patch_path = tmp_path / "already.aps"
        patch_path.write_bytes(save_patch_for(rom))

        code = cli.main(["merge", str(rom_path), str(patch_path), "--no-aa"])

        assert code == 0
        assert "no video change was needed" in capsys.readouterr().out

    def test_requires_at_least_one_video_flag(self, tmp_path, capsys):
        from z64kit import cli

        rom_path, patch_path = self.rom_and_patch(tmp_path)

        assert cli.main(["merge", str(rom_path), str(patch_path)]) == 2
        assert "nothing requested" in capsys.readouterr().out
