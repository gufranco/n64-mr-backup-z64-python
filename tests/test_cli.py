import json
from pathlib import Path

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
    def test_no_arguments_starts_the_guided_flow_rather_than_printing_usage(self, monkeypatch):
        from z64kit import wizard

        monkeypatch.setattr(wizard, "run", lambda console, **kw: 0)

        assert cli.main([]) == 0


class TestPatchLibrary:
    def test_no_folder_yields_no_patches(self):
        assert cli._patch_library(None) == {}

    def test_a_missing_folder_is_an_error_not_an_empty_library(self, tmp_path):
        with pytest.raises(cli.PatchFolderMissingError, match="does not exist"):
            cli._patch_library(str(tmp_path / "nope"))

    def test_no_folder_at_all_yields_no_patches(self):
        assert cli._patch_library(None) == {}

    def test_an_empty_folder_yields_no_patches(self, tmp_path):
        assert cli._patch_library(str(tmp_path)) == {}

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


class TestArtifactsCommand:
    def test_the_command_is_registered(self):
        from z64kit import cli

        assert cli.build_parser().parse_args(["artifacts"]).func is not None

    def test_reports_missing_files_against_an_empty_folder(self, tmp_path, capsys):
        from z64kit import cli

        code = cli.main(["artifacts", "--folder", str(tmp_path)])
        printed = capsys.readouterr().out

        assert code == 1
        assert "missing" in printed.lower()
        assert "cc-usa.aps" in printed

    def test_names_the_folder_it_looked_in(self, tmp_path, capsys):
        from z64kit import cli

        cli.main(["artifacts", "--folder", str(tmp_path)])

        assert str(tmp_path) in capsys.readouterr().out

    def test_flags_a_file_that_does_not_match_its_digest(self, tmp_path, capsys):
        from z64kit import cli

        (tmp_path / "cc-usa.aps").write_bytes(b"\x00" * 92484)

        cli.main(["artifacts", "--folder", str(tmp_path)])

        assert "cc-usa.aps" in capsys.readouterr().out

    def test_regenerates_the_document_from_the_manifest(self, tmp_path, capsys):
        from z64kit import artifacts, cli

        target = tmp_path / "README.md"

        code = cli.main(["artifacts", "--folder", str(tmp_path), "--write-readme"])

        assert code == 0
        expected = artifacts.render_folder_readme(artifacts.load_default_manifest())
        assert target.read_text(encoding="utf-8") == expected
        assert str(target) in capsys.readouterr().out

    def test_emits_machine_readable_output_on_request(self, tmp_path, capsys):
        import json

        from z64kit import cli

        cli.main(["artifacts", "--folder", str(tmp_path), "--json"])

        payload = json.loads(capsys.readouterr().out)
        assert payload["complete"] is False
        assert "cc-usa.aps" in payload["missing"]


class TestPatchFolderIsNotSilentlySkipped:
    def test_an_explicit_folder_that_does_not_exist_is_an_error(self, tmp_path, capsys):
        from z64kit import cli

        source = tmp_path / "roms"
        source.mkdir()

        code = cli.main(
            [
                "organise",
                str(source),
                str(tmp_path / "out"),
                "--patches",
                str(tmp_path / "nope"),
            ]
        )

        assert code == 2
        assert "nope" in capsys.readouterr().out


class TestArtifactsCommandReporting:
    def test_reports_a_recognised_file_under_the_wrong_name(self, tmp_path, capsys):
        from z64kit import artifacts, cli

        entry = artifacts.folder_entries(artifacts.load_default_manifest())[0]
        source = Path("patches") / entry.filename
        if not source.exists():
            pytest.skip("the real payload is not present on this machine")
        (tmp_path / "wrongname.aps").write_bytes(source.read_bytes())

        cli.main(["artifacts", "--folder", str(tmp_path)])
        printed = capsys.readouterr().out

        assert "wrong name" in printed
        assert entry.filename in printed

    def test_reports_a_file_the_manifest_does_not_know(self, tmp_path, capsys):
        from z64kit import cli

        (tmp_path / "stray.txt").write_bytes(b"hello")

        cli.main(["artifacts", "--folder", str(tmp_path)])

        assert "not in the manifest" in capsys.readouterr().out

    def test_reports_success_when_every_file_verifies(self, tmp_path, capsys):
        from z64kit import artifacts, cli

        manifest = artifacts.load_default_manifest()
        for entry in artifacts.folder_entries(manifest):
            source = Path("patches") / entry.filename
            if not source.exists():
                pytest.skip("the real payloads are not present on this machine")
            (tmp_path / entry.filename).write_bytes(source.read_bytes())

        code = cli.main(["artifacts", "--folder", str(tmp_path)])

        assert code == 0
        assert "present and verified" in capsys.readouterr().out

    def test_json_output_reports_completeness(self, tmp_path, capsys):
        import json as jsonlib

        from z64kit import artifacts, cli

        manifest = artifacts.load_default_manifest()
        for entry in artifacts.folder_entries(manifest):
            source = Path("patches") / entry.filename
            if not source.exists():
                pytest.skip("the real payloads are not present on this machine")
            (tmp_path / entry.filename).write_bytes(source.read_bytes())

        code = cli.main(["artifacts", "--folder", str(tmp_path), "--json"])

        assert code == 0
        assert jsonlib.loads(capsys.readouterr().out)["complete"] is True


class TestDoctorChecksTheArtifactFolder:
    def test_reports_how_many_of_the_required_files_verified(self, tmp_path, capsys):
        from z64kit import cli

        cli.main(["doctor", "--folder", str(tmp_path)])

        assert "0 of 15 verified" in capsys.readouterr().out

    def test_lists_every_missing_file_by_name(self, tmp_path, capsys):
        from z64kit import artifacts, cli

        cli.main(["doctor", "--folder", str(tmp_path)])
        printed = capsys.readouterr().out

        for entry in artifacts.folder_entries(artifacts.load_default_manifest()):
            assert entry.filename in printed

    def test_gives_the_digest_of_each_missing_file(self, tmp_path, capsys):
        from z64kit import artifacts, cli

        cli.main(["doctor", "--folder", str(tmp_path)])
        printed = capsys.readouterr().out

        for entry in artifacts.folder_entries(artifacts.load_default_manifest()):
            assert entry.sha256 in printed

    def test_gives_the_size_of_each_missing_file(self, tmp_path, capsys):
        from z64kit import artifacts, cli

        cli.main(["doctor", "--folder", str(tmp_path)])
        printed = capsys.readouterr().out.replace(",", "")

        for entry in artifacts.folder_entries(artifacts.load_default_manifest()):
            assert str(entry.size) in printed

    def test_names_the_folder_it_checked(self, tmp_path, capsys):
        from z64kit import cli

        cli.main(["doctor", "--folder", str(tmp_path)])

        assert str(tmp_path) in capsys.readouterr().out

    def test_points_at_the_command_that_gates_on_this(self, tmp_path, capsys):
        from z64kit import cli

        cli.main(["doctor", "--folder", str(tmp_path)])

        assert "z64kit artifacts" in capsys.readouterr().out

    def test_stays_a_diagnostic_and_exits_zero_even_when_files_are_missing(self, tmp_path, capsys):
        from z64kit import cli

        code = cli.main(["doctor", "--folder", str(tmp_path)])
        capsys.readouterr()

        assert code == 0

    def test_reports_a_file_present_under_the_wrong_name(self, tmp_path, capsys):
        from z64kit import artifacts, cli

        entry = artifacts.folder_entries(artifacts.load_default_manifest())[0]
        source = Path("patches") / entry.filename
        if not source.exists():
            pytest.skip("the real payload is not present on this machine")
        (tmp_path / "misnamed.aps").write_bytes(source.read_bytes())

        cli.main(["doctor", "--folder", str(tmp_path)])
        printed = capsys.readouterr().out

        assert "misnamed.aps" in printed
        assert "rename" in printed.lower()

    def test_reports_a_file_whose_contents_are_wrong(self, tmp_path, capsys):
        from z64kit import artifacts, cli

        entry = artifacts.folder_entries(artifacts.load_default_manifest())[0]
        (tmp_path / entry.filename).write_bytes(b"\x00" * entry.size)

        cli.main(["doctor", "--folder", str(tmp_path)])

        assert entry.filename in capsys.readouterr().out

    def test_says_so_when_everything_verifies(self, tmp_path, capsys):
        from z64kit import artifacts, cli

        manifest = artifacts.load_default_manifest()
        for entry in artifacts.folder_entries(manifest):
            source = Path("patches") / entry.filename
            if not source.exists():
                pytest.skip("the real payloads are not present on this machine")
            (tmp_path / entry.filename).write_bytes(source.read_bytes())

        cli.main(["doctor", "--folder", str(tmp_path)])
        printed = capsys.readouterr().out

        assert "15 of 15 verified" in printed
        assert "missing" not in printed.lower()

    def test_a_missing_folder_is_reported_rather_than_raised(self, tmp_path, capsys):
        from z64kit import cli

        code = cli.main(["doctor", "--folder", str(tmp_path / "absent")])

        assert code == 0
        assert "0 of 15 verified" in capsys.readouterr().out

    def test_both_commands_agree_on_what_is_missing(self, tmp_path, capsys):
        """One inspection function, so doctor and artifacts cannot disagree."""
        from z64kit import cli

        cli.main(["doctor", "--folder", str(tmp_path)])
        from_doctor = capsys.readouterr().out
        cli.main(["artifacts", "--folder", str(tmp_path)])
        from_artifacts = capsys.readouterr().out

        for name in ("cc-usa.aps", "zoot-usa.aps", "swep1rus.eep"):
            assert name in from_doctor
            assert name in from_artifacts


class TestInventoryAsk:
    def test_the_ask_flag_is_registered(self):
        from z64kit import cli

        args = cli.build_parser().parse_args(["inventory", "src", "--ask"])

        assert args.ask is True

    def test_it_defaults_to_off_so_scripts_keep_working(self):
        from z64kit import cli

        args = cli.build_parser().parse_args(["inventory", "src"])

        assert args.ask is False

    def test_ticking_a_cartridge_records_it(self, tmp_path, monkeypatch):
        from z64kit import cli, compat, inventory

        answers = iter(["1", ""])
        monkeypatch.setattr(cli.ConsoleIO, "ask", lambda self, prompt: next(answers))
        monkeypatch.setattr(cli.ConsoleIO, "say", lambda self, text="": None)

        rules = compat.load_rules()
        games = [
            compat.Candidate(key="dk64.z64", title="Donkey Kong 64 (USA)", save="eeprom2k"),
            compat.Candidate(key="cc.z64", title="Command & Conquer (USA)", save="flash128k"),
        ]
        questions = inventory.questions(games, rules)
        target = tmp_path / "inv.json"

        result = cli._ask_inventory(questions, inventory.Inventory(), target)

        assert result.is_recorded is True
        assert len(result.owned) == 1
        assert target.exists()

    def test_ticking_nothing_still_records_an_answer(self, tmp_path, monkeypatch):
        from z64kit import cli, compat, inventory

        monkeypatch.setattr(cli.ConsoleIO, "ask", lambda self, prompt: "")
        monkeypatch.setattr(cli.ConsoleIO, "say", lambda self, text="": None)

        rules = compat.load_rules()
        games = [compat.Candidate(key="dk64.z64", title="Donkey Kong 64", save="eeprom2k")]
        questions = inventory.questions(games, rules)

        result = cli._ask_inventory(questions, inventory.Inventory(), tmp_path / "inv.json")

        assert result.is_recorded is True
        assert result.owned == frozenset()

    def test_a_collection_needing_nothing_says_so(self, tmp_path, monkeypatch, capsys):
        from z64kit import cli, inventory

        said = []
        monkeypatch.setattr(cli.ConsoleIO, "say", lambda self, text="": said.append(text))

        result = cli._ask_inventory((), inventory.Inventory(), tmp_path / "inv.json")

        assert result.is_recorded is False
        assert any("Nothing" in line for line in said)

    def test_previously_owned_cartridges_start_ticked(self, tmp_path, monkeypatch):
        from z64kit import cli, compat, inventory

        monkeypatch.setattr(cli.ConsoleIO, "ask", lambda self, prompt: "")
        monkeypatch.setattr(cli.ConsoleIO, "say", lambda self, text="": None)

        rules = compat.load_rules()
        games = [compat.Candidate(key="dk64.z64", title="Donkey Kong 64", save="eeprom2k")]
        questions = inventory.questions(games, rules)
        already = inventory.Inventory(owned=frozenset({questions[0].key}), recorded=True)

        result = cli._ask_inventory(questions, already, tmp_path / "inv.json")

        assert result.owned == already.owned


class TestNoArgumentsStartsTheGuidedFlow:
    def test_an_empty_argument_list_runs_the_wizard(self, monkeypatch):
        from z64kit import cli, wizard

        seen = []
        monkeypatch.setattr(wizard, "run", lambda console, **kw: seen.append(console) or 0)

        assert cli.main([]) == 0
        assert seen

    def test_the_wizard_gets_the_real_console(self, monkeypatch):
        from z64kit import cli, wizard

        seen = []
        monkeypatch.setattr(wizard, "run", lambda console, **kw: seen.append(console) or 0)

        cli.main([])

        assert isinstance(seen[0], cli.ConsoleIO)

    def test_the_wizard_exit_code_is_passed_through(self, monkeypatch):
        from z64kit import cli, wizard

        monkeypatch.setattr(wizard, "run", lambda console, **kw: 1)

        assert cli.main([]) == 1

    def test_an_unknown_command_still_shows_usage(self, capsys):
        from z64kit import cli

        with pytest.raises(SystemExit):
            cli.main(["not-a-command"])
        capsys.readouterr()


class TestPlanJson:
    def test_emits_a_disk_list(self, tmp_path, capsys):
        from tests.conftest import make_rom

        from z64kit import cli

        (tmp_path / "game.z64").write_bytes(make_rom(size=8 * 1024 * 1024))

        assert cli.main(["plan", str(tmp_path), "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["disks"]

    def test_each_disk_lists_its_games_with_the_short_name(self, tmp_path, capsys):
        from tests.conftest import make_rom

        from z64kit import cli

        (tmp_path / "game.z64").write_bytes(make_rom(size=8 * 1024 * 1024))

        cli.main(["plan", str(tmp_path), "--json"])
        payload = json.loads(capsys.readouterr().out)

        entry = payload["disks"][0]["games"][0]
        assert entry["file"] == "game.z64"
        assert entry["name83"]


class TestDoctorUnknownFiles:
    def test_a_stray_file_in_the_folder_is_listed_as_ignored(self, tmp_path, capsys):
        from z64kit import cli

        (tmp_path / "readme-of-my-own.txt").write_bytes(b"x")

        cli.main(["doctor", "--folder", str(tmp_path)])
        printed = capsys.readouterr().out

        assert "not in the manifest" in printed
        assert "readme-of-my-own.txt" in printed


class TestWizardDispatchWithNoArgv:
    def test_passing_none_reads_the_real_argv_and_starts_the_flow(self, monkeypatch):
        import sys

        from z64kit import cli, wizard

        monkeypatch.setattr(sys, "argv", ["z64kit"])
        monkeypatch.setattr(wizard, "run", lambda console, **kw: 7)

        assert cli.main(None) == 7
