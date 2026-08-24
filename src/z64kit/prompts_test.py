"""Tests for the interactive prompt layer.

The people this is for did not ask for a command line. Every case here is a way a
real person actually types: a path dragged from a file manager arrives quoted, a
Windows path arrives with backslashes, Enter means "the obvious thing", and a typo
must re-ask instead of crashing or silently doing the wrong thing.
"""

from pathlib import Path

import pytest

from z64kit import prompts


class Scripted:
    """A console that reads from a list instead of a keyboard."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.written = []

    def say(self, text=""):
        self.written.append(text)

    def ask(self, prompt):
        self.written.append(prompt)
        if not self.answers:
            raise AssertionError(f"ran out of scripted answers at {prompt!r}")
        return self.answers.pop(0)

    @property
    def output(self):
        return "\n".join(self.written)


class TestConfirm:
    def test_yes_is_true(self):
        assert prompts.confirm(Scripted(["y"]), "go?") is True

    def test_the_whole_word_yes_is_true(self):
        assert prompts.confirm(Scripted(["yes"]), "go?") is True

    def test_no_is_false(self):
        assert prompts.confirm(Scripted(["n"]), "go?") is False

    def test_case_and_padding_do_not_matter(self):
        assert prompts.confirm(Scripted(["  YES  "]), "go?") is True

    def test_enter_takes_the_default(self):
        assert prompts.confirm(Scripted([""]), "go?", default=True) is True
        assert prompts.confirm(Scripted([""]), "go?", default=False) is False

    def test_the_default_is_visible_in_the_prompt(self):
        console = Scripted(["y"])

        prompts.confirm(console, "go?", default=True)

        assert "[Y/n]" in console.output

    def test_a_typo_asks_again_rather_than_guessing(self):
        console = Scripted(["maybe", "y"])

        assert prompts.confirm(console, "go?") is True
        assert "yes or no" in console.output.lower()

    def test_quitting_raises_a_cancellation(self):
        with pytest.raises(prompts.Cancelled):
            prompts.confirm(Scripted(["q"]), "go?")


class TestChoose:
    def test_a_number_picks_that_option(self):
        assert prompts.choose(Scripted(["2"]), "pick", ["a", "b", "c"]) == 1

    def test_numbering_starts_at_one_for_humans(self):
        assert prompts.choose(Scripted(["1"]), "pick", ["a", "b"]) == 0

    def test_enter_takes_the_default(self):
        assert prompts.choose(Scripted([""]), "pick", ["a", "b"], default=1) == 1

    def test_zero_is_rejected_rather_than_wrapping_to_the_end(self):
        console = Scripted(["0", "1"])

        assert prompts.choose(console, "pick", ["a", "b"]) == 0
        assert "1 and 2" in console.output

    def test_a_number_past_the_end_asks_again(self):
        console = Scripted(["9", "1"])

        assert prompts.choose(console, "pick", ["a", "b"]) == 0

    def test_text_that_is_not_a_number_asks_again(self):
        console = Scripted(["banana", "2"])

        assert prompts.choose(console, "pick", ["a", "b"]) == 1

    def test_every_option_is_shown_with_its_number(self):
        console = Scripted(["1"])

        prompts.choose(console, "pick", ["alpha", "beta"])

        assert "1) alpha" in console.output
        assert "2) beta" in console.output

    def test_a_single_option_still_has_to_be_confirmed(self):
        console = Scripted(["1"])

        assert prompts.choose(console, "pick", ["only"]) == 0

    def test_quitting_raises_a_cancellation(self):
        with pytest.raises(prompts.Cancelled):
            prompts.choose(Scripted(["q"]), "pick", ["a"])

    def test_an_empty_option_list_is_a_programming_error(self):
        with pytest.raises(ValueError, match="no options"):
            prompts.choose(Scripted([]), "pick", [])


class TestCleanPath:
    def test_plain_text_is_unchanged(self):
        assert prompts.clean_path("/Users/me/roms") == "/Users/me/roms"

    def test_surrounding_whitespace_is_dropped(self):
        assert prompts.clean_path("  /Users/me/roms  ") == "/Users/me/roms"

    def test_single_quotes_from_a_dragged_folder_are_dropped(self):
        assert prompts.clean_path("'/Users/me/My Roms'") == "/Users/me/My Roms"

    def test_double_quotes_are_dropped(self):
        assert prompts.clean_path('"/Users/me/My Roms"') == "/Users/me/My Roms"

    def test_backslash_escaped_spaces_from_a_shell_paste_are_unescaped(self):
        assert prompts.clean_path("/Users/me/My\\ Roms") == "/Users/me/My Roms"

    def test_a_windows_path_survives_intact(self):
        assert prompts.clean_path(r"C:\Games\N64") == r"C:\Games\N64"

    def test_a_trailing_separator_is_dropped(self):
        assert prompts.clean_path("/Users/me/roms/") == "/Users/me/roms"

    def test_a_bare_separator_is_kept(self):
        assert prompts.clean_path("/") == "/"

    def test_a_home_shortcut_is_expanded(self):
        """Expansion is the platform's, so the expected value has to be too.

        Windows resolves ~ from USERPROFILE rather than HOME, so pinning one of
        them and predicting a POSIX separator asserts the test's idea of a home
        directory instead of the platform's.
        """
        expanded = prompts.clean_path("~/roms")

        assert expanded == str(Path.home() / "roms")
        assert "~" not in expanded

    def test_a_bare_home_shortcut_is_expanded(self):
        assert prompts.clean_path("~") == str(Path.home())

    def test_an_empty_string_stays_empty(self):
        assert prompts.clean_path("   ") == ""


class TestAskFolder:
    def test_accepts_a_folder_that_exists(self, tmp_path):
        assert prompts.ask_folder(Scripted([str(tmp_path)]), "where?") == tmp_path

    def test_re_asks_when_the_folder_does_not_exist(self, tmp_path):
        console = Scripted([str(tmp_path / "nope"), str(tmp_path)])

        assert prompts.ask_folder(console, "where?") == tmp_path
        assert "could not find" in console.output.lower()

    def test_says_so_when_the_path_is_a_file_not_a_folder(self, tmp_path):
        target = tmp_path / "a.txt"
        target.write_text("x")
        console = Scripted([str(target), str(tmp_path)])

        prompts.ask_folder(console, "where?")

        assert "a folder" in console.output.lower()

    def test_accepts_a_quoted_dragged_path(self, tmp_path):
        folder = tmp_path / "My Roms"
        folder.mkdir()

        assert prompts.ask_folder(Scripted([f"'{folder}'"]), "where?") == folder

    def test_enter_takes_the_default_when_it_exists(self, tmp_path):
        assert prompts.ask_folder(Scripted([""]), "where?", default=tmp_path) == tmp_path

    def test_enter_with_no_default_asks_again(self, tmp_path):
        console = Scripted(["", str(tmp_path)])

        assert prompts.ask_folder(console, "where?") == tmp_path

    def test_a_folder_that_may_be_created_is_accepted_when_absent(self, tmp_path):
        target = tmp_path / "new"

        assert prompts.ask_folder(Scripted([str(target)]), "where?", must_exist=False) == target

    def test_quitting_raises_a_cancellation(self):
        with pytest.raises(prompts.Cancelled):
            prompts.ask_folder(Scripted(["q"]), "where?")


class TestToggleList:
    def test_nothing_is_selected_by_default(self):
        assert prompts.toggle_list(Scripted([""]), "own?", ["a", "b"]) == set()

    def test_a_number_selects_that_item(self):
        assert prompts.toggle_list(Scripted(["1", ""]), "own?", ["a", "b"]) == {0}

    def test_the_same_number_twice_deselects(self):
        assert prompts.toggle_list(Scripted(["1", "1", ""]), "own?", ["a", "b"]) == set()

    def test_several_numbers_on_one_line_all_toggle(self):
        assert prompts.toggle_list(Scripted(["1 2", ""]), "own?", ["a", "b"]) == {0, 1}

    def test_commas_between_numbers_are_accepted(self):
        assert prompts.toggle_list(Scripted(["1,2", ""]), "own?", ["a", "b"]) == {0, 1}

    def test_all_selects_everything(self):
        assert prompts.toggle_list(Scripted(["a", ""]), "own?", ["x", "y", "z"]) == {0, 1, 2}

    def test_none_clears_everything(self):
        assert prompts.toggle_list(Scripted(["a", "n", ""]), "own?", ["x", "y"]) == set()

    def test_preselected_items_start_marked(self):
        assert prompts.toggle_list(Scripted([""]), "own?", ["a", "b"], selected={1}) == {1}

    def test_a_selected_item_is_drawn_marked(self):
        console = Scripted(["1", ""])

        prompts.toggle_list(console, "own?", ["alpha"])

        assert "[x] 1) alpha" in console.output

    def test_an_unselected_item_is_drawn_empty(self):
        console = Scripted([""])

        prompts.toggle_list(console, "own?", ["alpha"])

        assert "[ ] 1) alpha" in console.output

    def test_an_out_of_range_number_is_reported_and_ignored(self):
        console = Scripted(["9", ""])

        assert prompts.toggle_list(console, "own?", ["a"]) == set()
        assert "9" in console.output

    def test_quitting_raises_a_cancellation(self):
        with pytest.raises(prompts.Cancelled):
            prompts.toggle_list(Scripted(["q"]), "own?", ["a"])


class TestATokenThatIsNotANumber:
    """The list is ticked by typing numbers, and a person types other things.

    A stray word in an otherwise valid answer has to be named and skipped, not
    swallowed and not fatal, because the rest of the line is still a valid
    selection and retyping it is the annoyance this flow exists to avoid.
    """

    def test_it_is_named_and_the_rest_of_the_line_still_counts(self):
        console = Scripted(["1 banana 2", ""])

        picked = prompts.toggle_list(console, "Tick:", ["one", "two", "three"])

        assert picked == {0, 1}
        assert any("'banana' is not a number" in line for line in console.written)
