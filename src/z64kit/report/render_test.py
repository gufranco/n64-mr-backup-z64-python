import pytest

from z64kit.report import latex, render


@pytest.fixture
def minimal():
    return latex.document(
        title="Render Test",
        subtitle="A minimal document",
        body=latex.section("Table")
        + latex.longtable(
            ["Game", "MiB"],
            [["Command & Conquer", "32"], ["Wave Race 64", "8"]],
            widths=["80mm", "15mm"],
            align=["l", "r"],
        ),
    )


class TestEngineDetection:
    def test_names_the_engines_it_will_try_in_order(self):
        assert render.ENGINES[0] == "tectonic"
        assert "pdflatex" in render.ENGINES

    def test_reports_whichever_engine_is_present(self):
        found = render.find_engine()

        assert found is None or found in render.ENGINES

    def test_an_explicit_engine_that_does_not_exist_is_reported_as_missing(self):
        assert render.find_engine(prefer="definitely-not-installed") is None


class TestWriteSource:
    def test_always_writes_the_source(self, tmp_path, minimal):
        result = render.write(minimal, tmp_path / "doc", compile_pdf=False)

        assert result.tex_path.exists()
        assert result.tex_path.read_text(encoding="utf-8") == minimal

    def test_reports_that_no_pdf_was_produced(self, tmp_path, minimal):
        result = render.write(minimal, tmp_path / "doc", compile_pdf=False)

        assert result.pdf_path is None
        assert result.pages == 0

    def test_creates_the_output_folder_when_absent(self, tmp_path, minimal):
        target = tmp_path / "nested" / "deeper" / "doc"

        result = render.write(minimal, target, compile_pdf=False)

        assert result.tex_path.exists()

    def test_explains_how_to_compile_when_no_engine_is_available(self, tmp_path, minimal):
        result = render.write(minimal, tmp_path / "doc", compile_pdf=False)

        assert "tectonic" in result.message


class TestCompilation:
    def test_produces_a_pdf_when_an_engine_is_present(self, tmp_path, minimal):
        if render.find_engine() is None:
            pytest.skip("no TeX engine installed")

        result = render.write(minimal, tmp_path / "doc", compile_pdf=True)

        assert result.pdf_path is not None
        assert result.pdf_path.exists()

    def test_the_pdf_reports_its_page_count(self, tmp_path, minimal):
        if render.find_engine() is None:
            pytest.skip("no TeX engine installed")

        result = render.write(minimal, tmp_path / "doc", compile_pdf=True)

        assert result.pages >= 1

    def test_a_broken_document_reports_the_failure_without_raising(self, tmp_path):
        if render.find_engine() is None:
            pytest.skip("no TeX engine installed")

        result = render.write(r"\this is not valid", tmp_path / "bad", compile_pdf=True)

        assert result.pdf_path is None
        assert "failed" in result.message.lower()

    def test_the_source_survives_a_failed_compilation(self, tmp_path):
        if render.find_engine() is None:
            pytest.skip("no TeX engine installed")

        result = render.write(r"\broken", tmp_path / "bad", compile_pdf=True)

        assert result.tex_path.exists()


class TestPageCounting:
    def test_counts_pages_in_a_pdf(self, tmp_path, minimal):
        if render.find_engine() is None:
            pytest.skip("no TeX engine installed")

        result = render.write(minimal, tmp_path / "doc", compile_pdf=True)

        assert render.count_pages(result.pdf_path) == result.pages

    def test_reports_zero_for_something_that_is_not_a_pdf(self, tmp_path):
        path = tmp_path / "fake.pdf"
        path.write_bytes(b"not a pdf")

        assert render.count_pages(path) == 0


class TestPageCountingEdgeCases:
    def test_a_file_that_is_not_a_pdf_counts_zero(self, tmp_path):
        target = tmp_path / "not.pdf"
        target.write_bytes(b"just text")

        assert render.count_pages(target) == 0

    def test_a_missing_file_counts_zero(self, tmp_path):
        assert render.count_pages(tmp_path / "absent.pdf") == 0

    def test_none_counts_zero(self):
        assert render.count_pages(None) == 0

    def test_a_pdf_with_no_recoverable_metadata_counts_zero(self, tmp_path):
        target = tmp_path / "opaque.pdf"
        target.write_bytes(b"%PDF-1.7\nnothing useful here\n")

        assert render.count_pages(target) == 0

    def test_an_unreadable_compressed_stream_is_skipped(self, tmp_path):
        target = tmp_path / "broken.pdf"
        target.write_bytes(b"%PDF-1.7\nstream\n" + b"\x78\x9c not-zlib" + b"\nendstream\n")

        assert render.count_pages(target) == 0

    def test_reads_a_page_count_from_an_inflated_stream(self, tmp_path):
        import zlib

        body = zlib.compress(b"/Type /Pages /Count 7")
        target = tmp_path / "packed.pdf"
        target.write_bytes(b"%PDF-1.7\nstream\n" + body + b"\nendstream\n")

        assert render.count_pages(target) == 7


class TestEngineSelection:
    def test_reports_no_engine_when_none_is_installed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PATH", str(tmp_path))

        assert render.find_engine() is None

    def test_writes_the_tex_even_with_no_engine_available(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PATH", str(tmp_path))

        result = render.write(
            "\\documentclass{article}\\begin{document}x\\end{document}", tmp_path / "doc.tex"
        )

        assert result.tex_path.exists()
        assert result.pdf_path is None
        assert result.engine is None

    def test_names_the_missing_engines_in_the_message(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PATH", str(tmp_path))

        result = render.write("x", tmp_path / "doc.tex")

        assert "tectonic" in result.message

    def test_builds_a_tectonic_command_with_an_output_directory(self, tmp_path):
        argv = render._command("tectonic", tmp_path / "a.tex", tmp_path)

        assert "--outdir" in argv

    def test_builds_a_latex_command_that_halts_on_error(self, tmp_path):
        argv = render._command("pdflatex", tmp_path / "a.tex", tmp_path)

        assert "-halt-on-error" in argv
