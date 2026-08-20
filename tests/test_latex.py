import pytest

from z64kit.report import latex


class TestEscaping:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Command & Conquer", r"Command \& Conquer"),
            ("100%", r"100\%"),
            ("a_b", r"a\_b"),
            ("#1", r"\#1"),
            ("$5", r"\$5"),
            ("{x}", r"\{x\}"),
            ("~", r"\textasciitilde{}"),
            ("^", r"\textasciicircum{}"),
            (r"a\b", r"a\textbackslash{}b"),
        ],
    )
    def test_escapes_every_special_character(self, raw, expected):
        assert latex.escape(raw) == expected

    def test_leaves_ordinary_text_alone(self):
        assert latex.escape("Super Mario 64") == "Super Mario 64"

    def test_accepts_a_non_string(self):
        assert latex.escape(64) == "64"

    def test_escapes_a_backslash_without_double_escaping_it(self):
        assert latex.escape("\\") == r"\textbackslash{}"


class TestLongTable:
    def test_repeats_the_header_across_pages(self):
        out = latex.longtable(["A", "B"], [["1", "2"]], widths=["2cm", "2cm"])

        assert r"\endhead" in out
        assert out.count("A") >= 2

    def test_declares_one_column_per_header(self):
        out = latex.longtable(["A", "B", "C"], [["1", "2", "3"]], widths=["1cm"] * 3)

        assert out.count("p{1cm}") == 3

    def test_escapes_cell_content(self):
        out = latex.longtable(["Game"], [["Command & Conquer"]], widths=["4cm"])

        assert r"Command \& Conquer" in out

    def test_renders_every_row(self):
        rows = [[str(n)] for n in range(5)]

        out = latex.longtable(["N"], rows, widths=["1cm"])

        assert all(str(n) in out for n in range(5))

    def test_an_empty_body_still_produces_a_valid_table(self):
        out = latex.longtable(["A"], [], widths=["1cm"])

        assert r"\begin{longtable}" in out
        assert r"\end{longtable}" in out

    def test_refuses_a_row_whose_width_does_not_match_the_header(self):
        with pytest.raises(ValueError, match="columns"):
            latex.longtable(["A", "B"], [["only one"]], widths=["1cm", "1cm"])

    def test_right_aligns_a_numeric_column_when_asked(self):
        out = latex.longtable(["N"], [["1"]], widths=["1cm"], align=["r"])

        assert r"\RaggedLeft" in out

    def test_left_aligns_by_default(self):
        out = latex.longtable(["N"], [["1"]], widths=["1cm"])

        assert r"\RaggedLeft" not in out


class TestDocument:
    def test_produces_a_compilable_skeleton(self):
        out = latex.document(title="Test", subtitle="Sub", body="Hello")

        assert out.startswith(r"\documentclass")
        assert r"\begin{document}" in out
        assert r"\end{document}" in out

    def test_includes_the_title_and_subtitle(self):
        out = latex.document(title="My Catalogue", subtitle="Some context", body="")

        assert "My Catalogue" in out
        assert "Some context" in out

    def test_escapes_the_title(self):
        out = latex.document(title="A & B", subtitle="", body="")

        assert r"A \& B" in out

    def test_sets_a4_paper_and_tight_margins(self):
        out = latex.document(title="T", subtitle="", body="")

        assert "a4paper" in out
        assert "geometry" in out

    def test_loads_the_packages_the_tables_need(self):
        out = latex.document(title="T", subtitle="", body="")

        for package in ("longtable", "booktabs", "array"):
            assert package in out

    def test_body_content_is_placed_verbatim(self):
        out = latex.document(title="T", subtitle="", body=r"\section{Raw}")

        assert r"\section{Raw}" in out

    def test_stays_monochrome_so_it_prints_cleanly(self):
        out = latex.document(title="T", subtitle="", body="")

        assert "xcolor" not in out

    def test_omits_the_subtitle_line_when_there_is_none(self):
        with_sub = latex.document(title="T", subtitle="Context", body="")
        without = latex.document(title="T", subtitle="", body="")

        assert "Context" in with_sub
        assert len(without) < len(with_sub)

    def test_the_footer_carries_the_document_title(self):
        out = latex.document(title="My Report", subtitle="", body="")

        assert out.count("My Report") >= 2

    def test_refuses_a_width_list_that_does_not_match_the_header(self):
        with pytest.raises(ValueError, match="width"):
            latex.longtable(["A", "B"], [], widths=["1cm"])

    def test_a_caption_is_rendered_when_given(self):
        out = latex.longtable(["A"], [["1"]], widths=["1cm"], caption="Table one")

        assert "Table one" in out

    def test_no_caption_command_appears_without_one(self):
        out = latex.longtable(["A"], [["1"]], widths=["1cm"])

        assert r"\caption" not in out


class TestNote:
    def test_wraps_text_in_a_quote_block(self):
        out = latex.note("Read this first")

        assert r"\begin{quote}" in out
        assert "Read this first" in out

    def test_escapes_the_text(self):
        assert r"A \& B" in latex.note("A & B")


class TestSection:
    def test_renders_a_heading(self):
        assert r"\section*{Games}" in latex.section("Games")

    def test_escapes_the_heading(self):
        assert r"A \& B" in latex.section("A & B")


class TestKeyValue:
    def test_renders_each_pair(self):
        out = latex.key_values([("Disks", "48"), ("Games", "292")])

        assert "Disks" in out
        assert "292" in out

    def test_escapes_both_sides(self):
        out = latex.key_values([("A & B", "100%")])

        assert r"A \& B" in out
        assert r"100\%" in out
