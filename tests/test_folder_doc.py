"""Tests for the supplied-artifact folder and the document that describes it.

The document is generated from the manifest rather than written by hand, so a test
can assert the committed copy still matches. That is what stops it drifting away
from the hashes the code actually checks.
"""

import subprocess
from pathlib import Path

import pytest

from z64kit import artifacts

FOLDER = Path(__file__).parent.parent / "patches"


def synthetic_manifest():
    """A manifest over payloads this test owns, so digests can be checked for real."""
    patch = artifacts.build_entry(
        name="demo",
        kind="patch",
        filename="demo.aps",
        data=b"APS10" + bytes(0x100),
        provenance="synthetic",
        game="Demo Game (USA)",
        companions=("demo.ram",),
    )
    save = artifacts.build_entry(
        name="demo-save",
        kind="save",
        filename="demo.ram",
        data=b"\xa5" * 64,
        provenance="synthetic",
    )
    firmware = artifacts.build_entry(
        name="fw",
        kind="bios",
        filename="fw.zip",
        data=b"PK\x03\x04",
        provenance="synthetic",
    )
    entries = (patch, save, firmware)
    return (
        artifacts.Manifest(
            by_sha256={e.sha256: e for e in entries},
            by_size={e.size: (e,) for e in entries},
        ),
        patch,
        save,
    )


class TestRenderedDocument:
    def test_names_every_file_the_folder_expects(self):
        manifest = artifacts.load_default_manifest()

        text = artifacts.render_folder_readme(manifest)

        expected = artifacts.folder_entries(manifest)
        assert expected
        for entry in expected:
            assert entry.filename in text

    def test_carries_the_full_sha256_of_each_file(self):
        manifest = artifacts.load_default_manifest()

        text = artifacts.render_folder_readme(manifest)

        for entry in artifacts.folder_entries(manifest):
            assert entry.sha256 in text

    def test_carries_the_exact_size_in_bytes(self):
        manifest = artifacts.load_default_manifest()

        text = artifacts.render_folder_readme(manifest).replace(",", "")

        for entry in artifacts.folder_entries(manifest):
            assert str(entry.size) in text

    def test_names_the_game_each_patch_targets(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        assert "Command & Conquer (USA)" in text

    def test_states_the_target_checksums_for_patches(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        assert "C2E9AA9A" in text

    def test_lists_a_companion_save_alongside_its_patch(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        assert "dk64-usa.ram" in text

    def test_keeps_the_firmware_out_of_the_expected_file_list(self):
        manifest, _, _ = synthetic_manifest()

        text = artifacts.render_folder_readme(manifest)
        before_footnotes = text.split("## What does not belong here")[0]

        assert "fw.zip" not in before_footnotes

    def test_explains_where_the_firmware_does_belong(self):
        manifest, _, _ = synthetic_manifest()

        text = artifacts.render_folder_readme(manifest)

        assert "fw.zip" in text

    def test_never_names_a_place_to_obtain_the_files(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest()).lower()

        for word in ("download", "http://", "https://", "torrent", "archive.org", "romset"):
            assert word not in text

    def test_is_deterministic(self):
        manifest = artifacts.load_default_manifest()

        assert artifacts.render_folder_readme(manifest) == artifacts.render_folder_readme(manifest)

    def test_rows_within_a_section_are_ordered_by_filename(self):
        manifest = artifacts.load_default_manifest()

        text = artifacts.render_folder_readme(manifest)
        section = text.split("## Save and boot fixes")[1].split("## ")[0]
        rows = [line.split("`")[1] for line in section.splitlines() if line.startswith("| `")]

        assert rows == sorted(rows)

    def test_the_digest_block_is_ordered_by_filename(self):
        manifest = artifacts.load_default_manifest()

        text = artifacts.render_folder_readme(manifest)
        block = text.split("## Digests")[1].split("```")[1]
        names = [line.split()[1] for line in block.strip().splitlines()]

        assert names == sorted(names)

    def test_gives_a_digest_command_for_each_platform(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        assert "shasum" in text
        assert "sha256sum" in text
        assert "Get-FileHash" in text

    def test_says_that_sha256_alone_decides(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        assert "SHA-256" in text


class TestCommittedDocumentIsCurrent:
    def test_the_folder_exists(self):
        assert FOLDER.is_dir()

    def test_the_committed_readme_matches_the_manifest(self):
        expected = artifacts.render_folder_readme(artifacts.load_default_manifest())

        assert (FOLDER / "README.md").read_text(encoding="utf-8") == expected

    def test_the_folder_ignores_payloads_but_keeps_its_own_documentation(self):
        rules = (FOLDER / ".gitignore").read_text(encoding="utf-8")

        assert "*" in rules
        assert "!README.md" in rules
        assert "!.gitignore" in rules

    def test_git_tracks_nothing_in_the_folder_but_its_own_documentation(self):
        """Payloads on disk are expected. Payloads in history would be the defect."""
        result = subprocess.run(
            ["git", "ls-files", "patches/"],
            cwd=FOLDER.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip("not a git checkout")

        tracked = {Path(line).name for line in result.stdout.split() if line}

        assert tracked <= {"README.md", ".gitignore"}

    def test_the_ignore_rule_actually_covers_a_real_payload_name(self):
        first = artifacts.folder_entries(artifacts.load_default_manifest())[0]
        result = subprocess.run(
            ["git", "check-ignore", f"patches/{first.filename}"],
            cwd=FOLDER.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode not in (0, 1):
            pytest.skip("not a git checkout")

        assert result.returncode == 0, f"{first.filename} would be committable"


class TestFolderInspection:
    def test_reports_everything_missing_for_an_empty_folder(self, tmp_path):
        manifest, patch, save = synthetic_manifest()

        report = artifacts.inspect_folder(tmp_path, manifest)

        assert set(report.missing) == {patch.filename, save.filename}
        assert not report.present

    def test_recognises_a_file_that_matches_its_digest(self, tmp_path):
        manifest, patch, _ = synthetic_manifest()
        (tmp_path / patch.filename).write_bytes(b"APS10" + bytes(0x100))

        report = artifacts.inspect_folder(tmp_path, manifest)

        assert patch.filename in report.present

    def test_flags_a_file_whose_contents_do_not_match(self, tmp_path):
        manifest, patch, _ = synthetic_manifest()
        (tmp_path / patch.filename).write_bytes(b"\x00" * patch.size)

        report = artifacts.inspect_folder(tmp_path, manifest)

        assert patch.filename in report.wrong

    def test_separates_a_size_mismatch_from_a_content_mismatch(self, tmp_path):
        manifest, patch, _ = synthetic_manifest()
        (tmp_path / patch.filename).write_bytes(b"\x00" * 7)

        report = artifacts.inspect_folder(tmp_path, manifest)

        assert "size" in report.wrong[patch.filename].lower()

    def test_a_content_mismatch_at_the_right_size_says_so(self, tmp_path):
        manifest, patch, _ = synthetic_manifest()
        (tmp_path / patch.filename).write_bytes(b"\xff" * patch.size)

        report = artifacts.inspect_folder(tmp_path, manifest)

        assert "size" not in report.wrong[patch.filename].lower()

    def test_ignores_files_the_manifest_does_not_know(self, tmp_path):
        manifest, _, _ = synthetic_manifest()
        (tmp_path / "notes.txt").write_bytes(b"hello")

        report = artifacts.inspect_folder(tmp_path, manifest)

        assert "notes.txt" in report.unknown

    def test_does_not_treat_its_own_documentation_as_unknown(self, tmp_path):
        manifest, _, _ = synthetic_manifest()
        (tmp_path / "README.md").write_bytes(b"x")
        (tmp_path / ".gitignore").write_bytes(b"x")

        report = artifacts.inspect_folder(tmp_path, manifest)

        assert not report.unknown

    def test_recognises_a_file_that_arrived_under_the_wrong_name(self, tmp_path):
        manifest, patch, _ = synthetic_manifest()
        (tmp_path / "renamed.aps").write_bytes(b"APS10" + bytes(0x100))

        report = artifacts.inspect_folder(tmp_path, manifest)

        assert "renamed.aps" in report.misnamed
        assert report.misnamed["renamed.aps"] == patch.filename

    def test_a_misnamed_file_is_not_reported_as_unknown(self, tmp_path):
        manifest, _, _ = synthetic_manifest()
        (tmp_path / "renamed.aps").write_bytes(b"APS10" + bytes(0x100))

        report = artifacts.inspect_folder(tmp_path, manifest)

        assert "renamed.aps" not in report.unknown

    def test_a_missing_folder_reports_everything_missing_rather_than_raising(self, tmp_path):
        manifest, _, _ = synthetic_manifest()

        report = artifacts.inspect_folder(tmp_path / "absent", manifest)

        assert len(report.missing) == 2

    def test_a_folder_holding_everything_is_reported_complete(self, tmp_path):
        manifest, patch, save = synthetic_manifest()
        (tmp_path / patch.filename).write_bytes(b"APS10" + bytes(0x100))
        (tmp_path / save.filename).write_bytes(b"\xa5" * 64)

        report = artifacts.inspect_folder(tmp_path, manifest)

        assert report.complete is True

    def test_a_folder_missing_one_file_is_not_complete(self, tmp_path):
        manifest, patch, _ = synthetic_manifest()
        (tmp_path / patch.filename).write_bytes(b"APS10" + bytes(0x100))

        report = artifacts.inspect_folder(tmp_path, manifest)

        assert report.complete is False


class TestCompanionRowsAreNotBlank:
    def test_a_save_file_names_the_game_it_belongs_to(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        row = next(line for line in text.splitlines() if "`swep1rus.eep`" in line)

        assert "Star Wars Episode I - Racer (USA)" in row

    def test_a_save_file_appears_in_its_own_section(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        section = text.split("## Save data")[1].split("## ")[0]

        assert "swep1rus.eep" in section

    def test_no_expected_file_row_has_a_blank_game_column(self):
        manifest = artifacts.load_default_manifest()
        text = artifacts.render_folder_readme(manifest)
        names = {e.filename for e in artifacts.folder_entries(manifest)}

        for line in text.splitlines():
            if not line.startswith("| `") or not line.endswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 5 or cells[0].strip("`") not in names:
                continue
            assert cells[1], f"blank game column: {line}"

    def test_no_expected_file_row_has_a_blank_game_column_in_a_patch_section(self):
        manifest = artifacts.load_default_manifest()
        text = artifacts.render_folder_readme(manifest)
        names = {e.filename for e in artifacts.folder_entries(manifest)}

        for line in text.splitlines():
            if not line.startswith("| `") or not line.endswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 5 or cells[0].strip("`") not in names:
                continue
            assert cells[2], f"blank purpose column: {line}"

    def test_a_patch_row_names_the_game_and_its_binding(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        row = next(line for line in text.splitlines() if "`dx-btusc.aps`" in line)

        assert "Banjo-Tooie" in row
        assert "C2E9AA9A" in row

    def test_a_save_row_says_it_is_matched_by_its_own_digest(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        section = text.split("## Save data")[1].split("## ")[0]

        assert "matched by its own digest" in section

    def test_the_checksum_column_is_explained_before_it_is_used(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        assert text.index("What the checksum column means") < text.index("Checksum after")

    def test_a_no_boot_chip_result_is_called_a_measurement_not_a_verdict(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        assert "measurement, not a verdict" in text


class TestOwningPatch:
    def test_finds_the_patch_that_lists_a_companion(self):
        manifest = artifacts.load_default_manifest()

        owner = artifacts.owning_patch(manifest, "swep1rus.eep")

        assert owner is not None
        assert owner.filename == "swep1rus.aps"

    def test_returns_nothing_for_a_file_no_patch_claims(self):
        manifest = artifacts.load_default_manifest()

        assert artifacts.owning_patch(manifest, "cc-usa.aps") is None

    def test_returns_nothing_for_a_name_the_manifest_does_not_know(self):
        manifest = artifacts.load_default_manifest()

        assert artifacts.owning_patch(manifest, "nothing.ram") is None


class TestOnlyWhatTheCollectionNeeds:
    def test_without_a_filter_every_entry_is_required(self, tmp_path):
        manifest = artifacts.load_default_manifest()

        report = artifacts.inspect_folder(tmp_path, manifest)

        assert len(report.missing) == len(artifacts.folder_entries(manifest))

    def test_a_filter_narrows_what_counts_as_missing(self, tmp_path):
        manifest = artifacts.load_default_manifest()

        report = artifacts.inspect_folder(tmp_path, manifest, required={"dx-btusc.aps"})

        assert set(report.missing) == {"dx-btusc.aps"}

    def test_an_empty_filter_means_nothing_is_missing(self, tmp_path):
        manifest = artifacts.load_default_manifest()

        report = artifacts.inspect_folder(tmp_path, manifest, required=set())

        assert report.missing == ()
        assert report.complete is True

    def test_a_file_outside_the_filter_is_still_verified_when_present(self, tmp_path):
        from pathlib import Path

        manifest = artifacts.load_default_manifest()
        for name in ("dx-btusc.aps", "kgsgood.aps"):
            source = Path("patches") / name
            if not source.exists():
                pytest.skip("the real payloads are not present on this machine")
            (tmp_path / name).write_bytes(source.read_bytes())

        report = artifacts.inspect_folder(tmp_path, manifest, required={"kgsgood.aps"})

        assert "dx-btusc.aps" in report.present

    def test_a_patch_the_database_carries_is_verified_not_called_unknown(self, tmp_path):
        from pathlib import Path

        manifest = artifacts.load_default_manifest()
        source = Path("patches") / "cc-usa.aps"
        if not source.exists():
            pytest.skip("the real payload is not present on this machine")
        (tmp_path / "cc-usa.aps").write_bytes(source.read_bytes())

        report = artifacts.inspect_folder(tmp_path, manifest)

        assert "cc-usa.aps" in report.present
        assert "cc-usa.aps" not in report.unknown

    def test_a_wrong_file_outside_the_filter_is_still_reported(self, tmp_path):
        manifest = artifacts.load_default_manifest()
        (tmp_path / "dx-btusc.aps").write_bytes(b"\x00" * 10)

        report = artifacts.inspect_folder(tmp_path, manifest, required={"kgsgood.aps"})

        assert "dx-btusc.aps" in report.wrong


class TestRequiredForCollection:
    def test_a_game_in_the_collection_requires_its_patch(self):
        manifest = artifacts.load_default_manifest()
        entry = next(e for e in artifacts.folder_entries(manifest) if e.filename == "dx-btusc.aps")

        required = artifacts.required_for(manifest, {(entry.target_crc1, entry.target_crc2)})

        assert "dx-btusc.aps" in required

    def test_a_game_not_in_the_collection_requires_nothing(self):
        manifest = artifacts.load_default_manifest()

        assert artifacts.required_for(manifest, {("DEADBEEF", "CAFEBABE")}) == {
            artifacts.PATCH_DATABASE
        }

    def test_a_non_aps_patch_requires_its_header_sidecar(self):
        manifest = artifacts.load_default_manifest()
        entry = next(e for e in artifacts.folder_entries(manifest) if e.filename == "banjo.zps")

        required = artifacts.required_for(manifest, {(entry.target_crc1, entry.target_crc2)})

        assert "banjo.hdr" in required

    def test_an_aps_patch_needs_no_header_because_it_carries_its_own_binding(self):
        manifest = artifacts.load_default_manifest()
        entry = next(e for e in artifacts.folder_entries(manifest) if e.filename == "kgsgood.aps")

        required = artifacts.required_for(manifest, {(entry.target_crc1, entry.target_crc2)})

        assert not any(name.endswith(".hdr") for name in required)

    def test_a_companion_save_is_required_with_its_patch(self):
        manifest = artifacts.load_default_manifest()
        entry = next(e for e in manifest.entries() if e.filename == "dk64-usa.aps")

        required = artifacts.required_for(manifest, {(entry.target_crc1, entry.target_crc2)})

        assert "dk64-usa.ram" in required
        assert "dk64-usa.aps" not in required

    def test_matching_is_case_insensitive_on_the_checksum(self):
        manifest = artifacts.load_default_manifest()
        entry = next(e for e in artifacts.folder_entries(manifest) if e.filename == "dx-btusc.aps")
        lowered = (entry.target_crc1.lower(), entry.target_crc2.lower())

        assert "dx-btusc.aps" in artifacts.required_for(manifest, {lowered})


class TestVerifiedCountRespectsTheFilter:
    def test_a_file_outside_the_filter_is_not_counted_as_needed(self, tmp_path):
        from pathlib import Path

        manifest = artifacts.load_default_manifest()
        for name in ("dx-btusc.aps", "kgsgood.aps"):
            source = Path("patches") / name
            if not source.exists():
                pytest.skip("the real payloads are not present on this machine")
            (tmp_path / name).write_bytes(source.read_bytes())

        report = artifacts.inspect_folder(tmp_path, manifest, required={"dx-btusc.aps"})

        assert "dx-btusc.aps" in report.needed
        assert set(report.present) == {"dx-btusc.aps", "kgsgood.aps"}

    def test_needed_present_counts_only_what_was_asked_for(self, tmp_path):
        from pathlib import Path

        manifest = artifacts.load_default_manifest()
        for name in ("dx-btusc.aps", "kgsgood.aps"):
            source = Path("patches") / name
            if not source.exists():
                pytest.skip("the real payloads are not present on this machine")
            (tmp_path / name).write_bytes(source.read_bytes())

        report = artifacts.inspect_folder(tmp_path, manifest, required={"dx-btusc.aps"})

        assert report.needed_present == ("dx-btusc.aps",)

    def test_with_no_filter_needed_is_every_folder_entry(self, tmp_path):
        manifest = artifacts.load_default_manifest()

        report = artifacts.inspect_folder(tmp_path, manifest)

        assert len(report.needed) == len(artifacts.folder_entries(manifest))


class TestProvenanceNamesNoContainerToHunt:
    """Provenance says how much to trust a file, never where to go and get it.

    Naming an archive sends the reader looking for the archive instead of the file,
    which is both worse advice and closer to a distribution pointer than this
    project should print.
    """

    def test_no_archive_is_named_among_the_files_to_obtain(self):
        """The firmware's own name is fine. An archive to go hunting for is not."""
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())
        asked_for = text.split("## What does not belong here")[0].lower()

        for suffix in (".zip", ".rar", ".7z"):
            assert suffix not in asked_for

    def test_no_bare_domain_appears_anywhere(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest()).lower()

        for domain in (".com", ".net", ".org/", ".to/", ".io/"):
            assert domain not in text

    def test_the_patch_database_is_still_named_because_it_is_a_needed_file(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        assert artifacts.PATCH_DATABASE in text

    def test_every_crack_asks_for_the_file_itself(self):
        manifest = artifacts.load_default_manifest()
        names = {e.filename for e in artifacts.folder_entries(manifest)}

        for name in ("1080_j.zps", "banjo.zps", "nba_cs.zps", "yoshi_e.zps"):
            assert name in names

    def test_no_provenance_names_an_archive(self):
        manifest = artifacts.load_default_manifest()

        for entry in manifest.entries():
            lowered = entry.provenance.lower()
            assert ".zip" not in lowered, entry.filename
            assert ".com" not in lowered, entry.filename

    def test_the_provenance_section_says_what_it_is_for(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        assert "how much to trust" in text.lower()
