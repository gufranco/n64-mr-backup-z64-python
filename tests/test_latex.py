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


class TestATableMustFitThePage:
    """LaTeX only warns about an overfull box, so a table running off the right
    edge still produces a PDF and a zero exit code. A nine-column listing shipped
    15.9mm past the margin that way."""

    def test_it_refuses_columns_wider_than_the_page(self):
        with pytest.raises(latex.TooWideError):
            latex.longtable(["A", "B"], [["1", "2"]], widths=["120mm", "120mm"])

    def test_it_says_how_far_past_the_margin(self):
        with pytest.raises(latex.TooWideError, match="past the right margin"):
            latex.longtable(["A", "B"], [["1", "2"]], widths=["120mm", "120mm"])

    def test_it_names_the_widest_column_to_narrow(self):
        with pytest.raises(latex.TooWideError, match="150mm"):
            latex.longtable(["A", "B"], [["1", "2"]], widths=["150mm", "60mm"])

    def test_it_accepts_a_table_that_fits(self):
        out = latex.longtable(["A", "B"], [["1", "2"]], widths=["90mm", "90mm"])

        assert "longtable" in out

    def test_the_padding_between_columns_counts(self):
        """Columns summing to exactly the text width still overflow, because
        tabcolsep is added on both sides of every column."""
        exact = f"{latex.TEXT_WIDTH_MM / 2}mm"

        with pytest.raises(latex.TooWideError):
            latex.longtable(["A", "B"], [["1", "2"]], widths=[exact, exact])

    def test_a_single_column_has_no_padding_to_pay_for(self):
        out = latex.longtable(["A"], [["1"]], widths=[f"{latex.TEXT_WIDTH_MM}mm"])

        assert "longtable" in out

    def test_it_measures_centimetres_too(self):
        assert latex.table_width_mm(["2cm"]) == pytest.approx(20.0)

    def test_it_measures_points(self):
        assert latex.table_width_mm(["72.27pt"]) == pytest.approx(25.4, abs=0.01)

    def test_it_refuses_a_unit_it_cannot_measure(self):
        with pytest.raises(ValueError, match="unknown column width unit"):
            latex.table_width_mm(["3ex"])


class TestCellsAreNotJustified:
    """A bare p column justifies, and justifying a narrow one stretches the word
    spaces to fill the line. That produced 56 lines at badness 10000, the worst
    TeX reports, in a document made almost entirely of narrow columns."""

    def test_a_left_column_is_ragged_right(self):
        out = latex.longtable(["A"], [["x"]], widths=["40mm"])

        assert "RaggedRight" in out

    def test_a_right_column_is_ragged_left(self):
        out = latex.longtable(["A"], [["1"]], widths=["40mm"], align=["r"])

        assert "RaggedLeft" in out

    def test_no_column_is_left_to_justify(self):
        out = latex.longtable(["A", "B"], [["x", "1"]], widths=["40mm", "20mm"], align=["l", "r"])
        spec = out[out.index("begin{longtable}") : out.index("toprule")]

        assert spec.count("p{") == spec.count("Ragged")

    def test_the_cell_can_still_hold_a_paragraph(self):
        """arraybackslash restores the row separator that ragged2e overrides."""
        out = latex.longtable(["A"], [["x"]], widths=["40mm"])

        assert "arraybackslash" in out


class TestATableCarriesItsHeadingAcrossAPageBreak:
    """A disk heading sat above its table as a separate paragraph. When the break
    landed after the first row, page seven showed the heading with one game and
    page eight showed six games belonging to no disk the reader could name.
    """

    def test_the_heading_goes_inside_the_table(self):
        out = latex.longtable(
            ["A"], [["x"]], widths=["40mm"], heading="Zip Disk 35", aside="7 games"
        )

        assert out.index("Zip Disk 35") > out.index("begin{longtable}")

    def test_the_heading_shows_above_the_first_page_of_rows(self):
        out = latex.longtable(["A"], [["x"]], widths=["40mm"], heading="Zip Disk 35")
        first = out[: out.index("endfirsthead")]

        assert "Zip Disk 35" in first

    def test_a_continuation_says_which_table_it_belongs_to(self):
        out = latex.longtable(["A"], [["x"]], widths=["40mm"], heading="Zip Disk 35")
        repeated = out[out.index("endfirsthead") : out.index("endhead")]

        assert "Zip Disk 35" in repeated

    def test_a_continuation_is_marked_as_one(self):
        out = latex.longtable(["A"], [["x"]], widths=["40mm"], heading="Zip Disk 35")
        repeated = out[out.index("endfirsthead") : out.index("endhead")]

        assert "continued" in repeated

    def test_the_first_page_is_not_marked_as_a_continuation(self):
        out = latex.longtable(["A"], [["x"]], widths=["40mm"], heading="Zip Disk 35")
        first = out[: out.index("endfirsthead")]

        assert "continued" not in first

    def test_the_aside_rides_with_the_heading(self):
        out = latex.longtable(
            ["A"], [["x"]], widths=["40mm"], heading="Zip Disk 35", aside="7 games, 92 MiB"
        )

        assert "7 games, 92 MiB" in out

    def test_the_heading_spans_every_column(self):
        out = latex.longtable(
            ["A", "B", "C"], [["x", "y", "z"]], widths=["20mm"] * 3, heading="Zip Disk 35"
        )

        assert "multicolumn{3}" in out

    def test_a_table_without_a_heading_is_unchanged(self):
        out = latex.longtable(["A"], [["x"]], widths=["40mm"])

        assert "multicolumn" not in out
        assert "continued" not in out
