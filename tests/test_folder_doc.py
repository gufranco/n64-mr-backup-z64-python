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

        expected = [e for e in manifest.entries() if e.kind in artifacts.FOLDER_KINDS]
        assert expected
        for entry in expected:
            assert entry.filename in text

    def test_carries_the_full_sha256_of_each_file(self):
        manifest = artifacts.load_default_manifest()

        text = artifacts.render_folder_readme(manifest)

        for entry in manifest.entries():
            if entry.kind in artifacts.FOLDER_KINDS:
                assert entry.sha256 in text

    def test_carries_the_exact_size_in_bytes(self):
        manifest = artifacts.load_default_manifest()

        text = artifacts.render_folder_readme(manifest).replace(",", "")

        for entry in manifest.entries():
            if entry.kind in artifacts.FOLDER_KINDS:
                assert str(entry.size) in text

    def test_names_the_game_each_patch_targets(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        assert "Command & Conquer (USA)" in text

    def test_states_the_target_checksums_for_patches(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        assert "95286EB4" in text

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

    def test_orders_rows_by_filename_so_the_output_is_stable(self):
        manifest = artifacts.load_default_manifest()

        text = artifacts.render_folder_readme(manifest)
        names = [e.filename for e in manifest.entries() if e.kind in artifacts.FOLDER_KINDS]
        positions = [text.index(n) for n in sorted(names)]

        assert positions == sorted(positions)

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
