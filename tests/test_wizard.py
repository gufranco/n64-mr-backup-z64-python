"""Tests for the guided flow.

Every step takes a console, so the whole thing runs from scripted answers. Nothing
here writes a disk image: the step that would is injected, and the tests assert on
what it was asked to do rather than on gigabytes of output.
"""

from tests.test_prompts import Scripted

from z64kit import prompts, wizard


class Recorder:
    """Stands in for the step that actually writes, so tests stay fast."""

    def __init__(self, code=0):
        self.calls = []
        self.code = code

    def __call__(self, action, source, output, patches):
        self.calls.append((action, str(source), str(output), patches))
        return self.code


class TestCandidateFolders:
    def test_offers_a_folder_that_exists(self, tmp_path):
        (tmp_path / "roms").mkdir()

        assert tmp_path / "roms" in wizard.candidate_folders(tmp_path, tmp_path)

    def test_never_offers_a_folder_that_does_not_exist(self, tmp_path):
        assert wizard.candidate_folders(tmp_path, tmp_path) == []

    def test_offers_the_current_folder_when_it_holds_games(self, tmp_path):
        (tmp_path / "game.z64").write_bytes(b"\x00" * 16)

        assert tmp_path in wizard.candidate_folders(tmp_path / "elsewhere", tmp_path)

    def test_does_not_offer_the_current_folder_when_it_holds_no_games(self, tmp_path):
        (tmp_path / "notes.txt").write_text("x")

        assert tmp_path not in wizard.candidate_folders(tmp_path / "elsewhere", tmp_path)

    def test_lists_each_folder_only_once(self, tmp_path):
        (tmp_path / "roms").mkdir()
        (tmp_path / "roms" / "game.z64").write_bytes(b"\x00")

        found = wizard.candidate_folders(tmp_path, tmp_path / "roms")

        assert len(found) == len(set(found))

    def test_recognises_every_extension_the_unit_loads(self, tmp_path):
        for suffix in ("z64", "v64", "n64"):
            folder = tmp_path / suffix
            folder.mkdir()
            (folder / f"game.{suffix}").write_bytes(b"\x00")
            assert folder in wizard.candidate_folders(tmp_path, folder)


class TestPickSource:
    def test_choosing_a_candidate_returns_it(self, tmp_path):
        (tmp_path / "roms").mkdir()
        console = Scripted(["1"])

        picked = wizard.step_pick_source(console, [tmp_path / "roms"])

        assert picked == tmp_path / "roms"

    def test_the_last_option_asks_for_a_folder_instead(self, tmp_path):
        console = Scripted(["2", str(tmp_path)])

        assert wizard.step_pick_source(console, [tmp_path / "other"]) == tmp_path

    def test_with_no_candidates_it_asks_directly(self, tmp_path):
        console = Scripted([str(tmp_path)])

        assert wizard.step_pick_source(console, []) == tmp_path

    def test_a_wrong_path_is_re_asked_rather_than_fatal(self, tmp_path):
        console = Scripted([str(tmp_path / "nope"), str(tmp_path)])

        assert wizard.step_pick_source(console, []) == tmp_path

    def test_the_candidates_are_shown_with_numbers(self, tmp_path):
        (tmp_path / "roms").mkdir()
        console = Scripted(["1"])

        wizard.step_pick_source(console, [tmp_path / "roms"])

        assert "1) " in console.output


class TestArtifactStep:
    def test_a_complete_folder_reports_success_and_continues(self, tmp_path, monkeypatch):
        console = Scripted([])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 15, [], [], []))

        assert wizard.step_check_supplied(console, tmp_path) is True

    def test_a_complete_folder_says_how_many_verified(self, tmp_path, monkeypatch):
        console = Scripted([])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 15, [], [], []))

        wizard.step_check_supplied(console, tmp_path)

        assert "15 of 15" in console.output

    def test_missing_files_are_listed_by_name(self, tmp_path, monkeypatch):
        console = Scripted(["y"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 13, ["a.aps", "b.ram"], [], []))

        wizard.step_check_supplied(console, tmp_path)

        assert "a.aps" in console.output
        assert "b.ram" in console.output

    def test_missing_files_explain_the_consequence(self, tmp_path, monkeypatch):
        console = Scripted(["y"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 14, ["a.aps"], [], []))

        wizard.step_check_supplied(console, tmp_path)

        assert "will not" in console.output.lower() or "without" in console.output.lower()

    def test_answering_no_stops_the_flow(self, tmp_path, monkeypatch):
        console = Scripted(["n"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 0, ["a.aps"], [], []))

        assert wizard.step_check_supplied(console, tmp_path) is False

    def test_answering_yes_continues_without_the_files(self, tmp_path, monkeypatch):
        console = Scripted(["y"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 0, ["a.aps"], [], []))

        assert wizard.step_check_supplied(console, tmp_path) is True

    def test_a_file_under_the_wrong_name_is_reported_as_a_rename(self, tmp_path, monkeypatch):
        console = Scripted(["y"])
        monkeypatch.setattr(
            wizard, "_inspect", lambda folder: (15, 14, ["a.aps"], [], [("x.aps", "a.aps")])
        )

        wizard.step_check_supplied(console, tmp_path)

        assert "rename" in console.output.lower()

    def test_a_wrong_file_is_reported_with_its_reason(self, tmp_path, monkeypatch):
        console = Scripted(["y"])
        monkeypatch.setattr(
            wizard, "_inspect", lambda folder: (15, 14, [], [("a.aps", "size is 10")], [])
        )

        wizard.step_check_supplied(console, tmp_path)

        assert "size is 10" in console.output


class TestOutputMode:
    def test_folders_can_be_chosen(self, tmp_path):
        assert wizard.step_pick_action(Scripted(["1"])) == wizard.ACTION_FOLDERS

    def test_images_can_be_chosen(self, tmp_path):
        assert wizard.step_pick_action(Scripted(["2"])) == wizard.ACTION_IMAGES

    def test_both_options_are_explained_not_just_named(self):
        console = Scripted(["1"])

        wizard.step_pick_action(console)

        assert "copy" in console.output.lower() or "hand" in console.output.lower()


class TestConfirmation:
    def test_nothing_runs_until_confirmed(self, tmp_path, monkeypatch):
        runner = Recorder()
        console = Scripted(["1", str(tmp_path / "out"), "n"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 15, [], [], []))
        monkeypatch.setattr(wizard, "_describe_plan", lambda console, source: 3)

        code = wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path)

        assert runner.calls == []
        assert code == 1

    def test_confirming_runs_the_chosen_action(self, tmp_path, monkeypatch):
        runner = Recorder()
        console = Scripted(["1", str(tmp_path / "out"), "y", "n", "n"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 15, [], [], []))
        monkeypatch.setattr(wizard, "_describe_plan", lambda console, source: 3)

        code = wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path)

        assert code == 0
        assert runner.calls[0][0] == wizard.ACTION_FOLDERS

    def test_the_chosen_output_folder_is_passed_through(self, tmp_path, monkeypatch):
        runner = Recorder()
        target = tmp_path / "out"
        console = Scripted(["2", str(target), "y", "n", "n"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 15, [], [], []))
        monkeypatch.setattr(wizard, "_describe_plan", lambda console, source: 3)

        wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path)

        assert runner.calls[0][2] == str(target)

    def test_the_supplied_folder_is_passed_through(self, tmp_path, monkeypatch):
        runner = Recorder()
        console = Scripted(["1", str(tmp_path / "out"), "y", "n", "n"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 15, [], [], []))
        monkeypatch.setattr(wizard, "_describe_plan", lambda console, source: 3)

        wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path)

        assert runner.calls[0][3] == str(tmp_path)

    def test_a_runner_failure_is_reported_not_swallowed(self, tmp_path, monkeypatch):
        runner = Recorder(code=2)
        console = Scripted(["1", str(tmp_path / "out"), "y", "n", "n"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 15, [], [], []))
        monkeypatch.setattr(wizard, "_describe_plan", lambda console, source: 3)

        assert wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path) == 2


class TestRunEndToEnd:
    def test_stopping_at_the_supplied_check_writes_nothing(self, tmp_path, monkeypatch):
        runner = Recorder()
        console = Scripted(["n"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 0, ["a.aps"], [], []))

        code = wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path)

        assert runner.calls == []
        assert code == 1

    def test_leaving_early_is_not_an_error(self, tmp_path, monkeypatch):
        runner = Recorder()
        console = Scripted(["q"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 0, ["a.aps"], [], []))

        code = wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path)

        assert code == 1
        assert "cancel" in console.output.lower() or "stopped" in console.output.lower()

    def test_an_empty_collection_stops_before_asking_anything_else(self, tmp_path, monkeypatch):
        runner = Recorder()
        console = Scripted([])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 15, [], [], []))
        monkeypatch.setattr(wizard, "_describe_plan", lambda console, source: 0)

        code = wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path)

        assert runner.calls == []
        assert code == 1

    def test_it_opens_by_saying_what_it_is_going_to_do(self, tmp_path, monkeypatch):
        console = Scripted(["1", str(tmp_path / "out"), "y", "n", "n"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 15, [], [], []))
        monkeypatch.setattr(wizard, "_describe_plan", lambda console, source: 2)

        wizard.run(console, source=tmp_path, runner=Recorder(), supplied=tmp_path)

        assert "disk" in console.output.lower()

    def test_it_closes_by_saying_what_to_do_next(self, tmp_path, monkeypatch):
        console = Scripted(["1", str(tmp_path / "out"), "y", "n", "n"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 15, [], [], []))
        monkeypatch.setattr(wizard, "_describe_plan", lambda console, source: 2)

        wizard.run(console, source=tmp_path, runner=Recorder(), supplied=tmp_path)

        assert "next" in console.output.lower()

    def test_a_missing_source_folder_is_asked_for(self, tmp_path, monkeypatch):
        runner = Recorder()
        console = Scripted([str(tmp_path), "1", str(tmp_path / "out"), "y", "n", "n"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 15, [], [], []))
        monkeypatch.setattr(wizard, "_describe_plan", lambda console, source: 1)
        monkeypatch.setattr(wizard, "candidate_folders", lambda home, cwd: [])

        code = wizard.run(console, runner=runner, supplied=tmp_path)

        assert code == 0


class TestStepNumbering:
    def test_every_step_says_where_you_are(self, tmp_path, monkeypatch):
        console = Scripted(["1", str(tmp_path / "out"), "y", "n", "n"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 15, [], [], []))
        monkeypatch.setattr(wizard, "_describe_plan", lambda console, source: 2)

        wizard.run(console, source=tmp_path, runner=Recorder(), supplied=tmp_path)

        assert "Step 1 of" in console.output
        assert "Step 2 of" in console.output


class TestCancellationIsGraceful:
    def test_cancelling_inside_a_prompt_does_not_escape_as_an_exception(
        self, tmp_path, monkeypatch
    ):
        console = Scripted(["1", "q"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 15, [], [], []))
        monkeypatch.setattr(wizard, "_describe_plan", lambda console, source: 2)

        code = wizard.run(console, source=tmp_path, runner=Recorder(), supplied=tmp_path)

        assert code == 1

    def test_the_cancellation_type_is_the_prompt_layers_own(self):
        assert issubclass(prompts.Cancelled, KeyboardInterrupt)


class TestInspectAgainstARealFolder:
    def test_an_empty_folder_reports_everything_missing(self, tmp_path):
        expected, verified, missing, wrong, misnamed = wizard._inspect(tmp_path)

        assert verified == 0
        assert len(missing) == expected
        assert wrong == []
        assert misnamed == []

    def test_a_stray_file_does_not_count_as_verified(self, tmp_path):
        (tmp_path / "stray.txt").write_bytes(b"x")

        _, verified, _, _, _ = wizard._inspect(tmp_path)

        assert verified == 0

    def test_a_wrong_sized_file_is_reported_as_wrong(self, tmp_path):
        from z64kit import artifacts

        entry = artifacts.folder_entries(artifacts.load_default_manifest())[0]
        (tmp_path / entry.filename).write_bytes(b"\x00" * 5)

        _, _, _, wrong, _ = wizard._inspect(tmp_path)

        assert wrong and wrong[0][0] == entry.filename

    def test_a_missing_folder_does_not_raise(self, tmp_path):
        expected, verified, missing, _, _ = wizard._inspect(tmp_path / "absent")

        assert verified == 0
        assert len(missing) == expected


class TestDescribePlan:
    def rom(self, folder, name, size=8 * 1024 * 1024):
        from tests.conftest import make_rom

        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(make_rom(size=size))

    def test_an_empty_folder_reports_zero_disks(self, tmp_path):
        console = Scripted([])

        assert wizard._describe_plan(console, tmp_path) == 0

    def test_an_empty_folder_says_what_it_expected_to_find(self, tmp_path):
        console = Scripted([])

        wizard._describe_plan(console, tmp_path)

        assert ".z64" in console.output

    def test_one_game_needs_one_disk(self, tmp_path):
        self.rom(tmp_path, "game.z64")
        console = Scripted([])

        assert wizard._describe_plan(console, tmp_path) == 1

    def test_it_reports_the_game_count_and_total_size(self, tmp_path):
        self.rom(tmp_path, "game.z64")
        console = Scripted([])

        wizard._describe_plan(console, tmp_path)

        assert "1 games" in console.output
        assert "MiB" in console.output

    def test_a_curated_layout_uses_the_folder_names_as_disks(self, tmp_path):
        self.rom(tmp_path / "Zip Disk 01", "a.z64")
        self.rom(tmp_path / "Zip Disk 02", "b.z64")
        console = Scripted([])

        assert wizard._describe_plan(console, tmp_path) == 2

    def test_many_games_need_more_than_one_disk(self, tmp_path):
        for index in range(14):
            self.rom(tmp_path, f"g{index:02d}.z64", size=8 * 1024 * 1024)
        console = Scripted([])

        assert wizard._describe_plan(console, tmp_path) >= 2


class TestFollowUpOffers:
    def setup_flow(self, tmp_path, monkeypatch, extra_answers):
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 15, [], [], []))
        monkeypatch.setattr(wizard, "_describe_plan", lambda console, source: 2)
        answers = ["1", str(tmp_path / "out"), "y", *extra_answers]
        return Scripted(answers)

    def test_it_offers_to_write_a_catalogue(self, tmp_path, monkeypatch):
        runner = Recorder()
        console = self.setup_flow(tmp_path, monkeypatch, ["y", "n"])

        wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path)

        assert any(call[0] == wizard.ACTION_REPORT for call in runner.calls)

    def test_declining_the_catalogue_does_not_write_one(self, tmp_path, monkeypatch):
        runner = Recorder()
        console = self.setup_flow(tmp_path, monkeypatch, ["n", "n"])

        wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path)

        assert not any(call[0] == wizard.ACTION_REPORT for call in runner.calls)

    def test_it_offers_to_record_the_cartridges_owned(self, tmp_path, monkeypatch):
        runner = Recorder()
        console = self.setup_flow(tmp_path, monkeypatch, ["n", "y"])

        wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path)

        assert any(call[0] == wizard.ACTION_INVENTORY for call in runner.calls)

    def test_declining_both_still_reports_success(self, tmp_path, monkeypatch):
        runner = Recorder()
        console = self.setup_flow(tmp_path, monkeypatch, ["n", "n"])

        assert wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path) == 0

    def test_the_catalogue_gets_the_same_source_folder(self, tmp_path, monkeypatch):
        runner = Recorder()
        console = self.setup_flow(tmp_path, monkeypatch, ["y", "n"])

        wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path)

        call = next(c for c in runner.calls if c[0] == wizard.ACTION_REPORT)
        assert call[1] == str(tmp_path)

    def test_a_failing_catalogue_does_not_undo_the_disks(self, tmp_path, monkeypatch):
        calls = []

        def runner(action, source, output, patches):
            calls.append(action)
            return 0 if action != wizard.ACTION_REPORT else 3

        console = self.setup_flow(tmp_path, monkeypatch, ["y", "n"])

        code = wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path)

        assert code == 0
        assert wizard.ACTION_REPORT in calls

    def test_a_failing_catalogue_says_so(self, tmp_path, monkeypatch):
        def runner(action, source, output, patches):
            return 0 if action != wizard.ACTION_REPORT else 3

        console = self.setup_flow(tmp_path, monkeypatch, ["y", "n"])

        wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path)

        assert "catalogue" in console.output.lower()

    def test_cancelling_at_a_follow_up_still_reports_the_disks_were_written(
        self, tmp_path, monkeypatch
    ):
        runner = Recorder()
        console = self.setup_flow(tmp_path, monkeypatch, ["q"])

        code = wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path)

        assert code == 0


class TestCandidateSubfolders:
    def test_offers_a_subfolder_of_the_current_folder_that_holds_games(self, tmp_path):
        games = tmp_path / "games"
        games.mkdir()
        (games / "a.z64").write_bytes(b"\x00")

        assert games in wizard.candidate_folders(tmp_path / "home", tmp_path)

    def test_does_not_offer_a_subfolder_with_no_games(self, tmp_path):
        (tmp_path / "notes").mkdir()

        assert (tmp_path / "notes") not in wizard.candidate_folders(tmp_path / "home", tmp_path)

    def test_offers_a_curated_parent_rather_than_each_disk_folder(self, tmp_path):
        for disk in ("Zip Disk 01", "Zip Disk 02"):
            folder = tmp_path / "collection" / disk
            folder.mkdir(parents=True)
            (folder / "a.z64").write_bytes(b"\x00")

        found = wizard.candidate_folders(tmp_path / "home", tmp_path)

        assert tmp_path / "collection" in found

    def test_does_not_look_more_than_two_levels_down(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "game.z64").write_bytes(b"\x00")

        assert deep not in wizard.candidate_folders(tmp_path / "home", tmp_path)

    def test_a_home_folder_that_does_not_exist_is_harmless(self, tmp_path):
        assert wizard.candidate_folders(tmp_path / "nope", tmp_path) == []

    def test_the_list_stays_short_enough_to_read(self, tmp_path):
        for index in range(40):
            folder = tmp_path / f"set{index}"
            folder.mkdir()
            (folder / "g.z64").write_bytes(b"\x00")

        assert len(wizard.candidate_folders(tmp_path / "home", tmp_path)) <= wizard.MAX_CANDIDATES


class TestMissingSuppliedFolderDoesNotCrash:
    def test_carrying_on_without_the_folder_passes_no_patch_folder(self, tmp_path, monkeypatch):
        runner = Recorder()
        console = Scripted(["y", "1", str(tmp_path / "out"), "y", "n", "n"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 0, ["a.aps"], [], []))
        monkeypatch.setattr(wizard, "_describe_plan", lambda console, source: 1)

        wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path / "absent-patches")

        assert runner.calls[0][3] is None

    def test_an_existing_folder_is_still_passed_through(self, tmp_path, monkeypatch):
        runner = Recorder()
        console = Scripted(["1", str(tmp_path / "out"), "y", "n", "n"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 15, [], [], []))
        monkeypatch.setattr(wizard, "_describe_plan", lambda console, source: 1)

        wizard.run(console, source=tmp_path, runner=runner, supplied=tmp_path)

        assert runner.calls[0][3] == str(tmp_path)

    def test_an_unexpected_failure_is_reported_without_a_traceback(self, tmp_path, monkeypatch):
        def explode(action, source, output, patches):
            raise OSError("disk went away")

        console = Scripted(["1", str(tmp_path / "out"), "y"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 15, [], [], []))
        monkeypatch.setattr(wizard, "_describe_plan", lambda console, source: 1)

        code = wizard.run(console, source=tmp_path, runner=explode, supplied=tmp_path)

        assert code == 1
        assert "disk went away" in console.output

    def test_the_failure_message_says_nothing_was_completed(self, tmp_path, monkeypatch):
        def explode(action, source, output, patches):
            raise OSError("nope")

        console = Scripted(["1", str(tmp_path / "out"), "y"])
        monkeypatch.setattr(wizard, "_inspect", lambda folder: (15, 15, [], [], []))
        monkeypatch.setattr(wizard, "_describe_plan", lambda console, source: 1)

        wizard.run(console, source=tmp_path, runner=explode, supplied=tmp_path)

        assert "did not finish" in console.output.lower()
