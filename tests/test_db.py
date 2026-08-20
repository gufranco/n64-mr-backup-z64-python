import hashlib

import pytest

from z64kit import db

SAMPLE = """\
; comment line
; VALID TAGS

33c4d0041e03a2d14216a80c5cec31d8 ntsc|cic6102|eeprom512 # Super Mario 64
aabbccddeeff00112233445566778899 pal|cic6103|flash128k|rpak # Some PAL Game
ID:NSM___ eeprom512 # Super Mario 64
ID:NZL___ sram32k|rpak # Zelda family
ID:CP2___ flash128k|tpak # Pocket Monsters Stadium 2
"""


@pytest.fixture
def local(tmp_path):
    path = tmp_path / "n64.txt"
    path.write_text(SAMPLE, encoding="utf-8")
    return db.load(path)


class TestParse:
    def test_indexes_md5_entries(self, local):
        assert "33c4d0041e03a2d14216a80c5cec31d8" in local.by_md5

    def test_indexes_id_patterns(self, local):
        assert any(p.startswith("NSM") for p in local.id_patterns)

    def test_ignores_comment_lines(self, local):
        assert len(local.by_md5) == 2

    def test_reads_the_save_type(self, local):
        entry = local.by_md5["33c4d0041e03a2d14216a80c5cec31d8"]

        assert entry.save == "eeprom512"

    def test_reads_the_boot_chip(self, local):
        assert local.by_md5["33c4d0041e03a2d14216a80c5cec31d8"].cic == "6102"

    def test_reads_accessories(self, local):
        entry = local.by_md5["aabbccddeeff00112233445566778899"]

        assert "rpak" in entry.accessories

    def test_reads_the_game_name(self, local):
        assert local.by_md5["33c4d0041e03a2d14216a80c5cec31d8"].name == "Super Mario 64"

    def test_an_entry_with_no_save_type_reports_none(self, tmp_path):
        path = tmp_path / "x.txt"
        path.write_text("aa" * 16 + " ntsc|cic6102 # Nothing\n", encoding="utf-8")

        assert db.load(path).by_md5["aa" * 16].save == "none"


class TestLookup:
    def test_prefers_an_exact_md5_match(self, local):
        data = b"whatever"
        digest = hashlib.md5(data).hexdigest()
        local.by_md5[digest] = db.Entry(save="sram32k", cic="6102", name="X")

        assert local.lookup(data, "NSM_").save == "sram32k"

    def test_falls_back_to_the_game_code_pattern(self, local):
        assert local.lookup(b"unknown bytes", "NSME").save == "eeprom512"

    def test_a_wildcard_matches_any_character(self, local):
        assert local.lookup(b"x", "NZLJ").save == "sram32k"

    def test_prefers_the_more_specific_pattern(self, tmp_path):
        path = tmp_path / "y.txt"
        path.write_text(
            "ID:N_______ sram32k # generic\nID:NSME____ flash128k # specific\n",
            encoding="utf-8",
        )

        assert db.load(path).lookup(b"x", "NSME").save == "flash128k"

    def test_an_unknown_code_reports_nothing_known(self, local):
        assert local.lookup(b"x", "ZZZZ") is None

    def test_a_short_code_does_not_crash(self, local):
        assert local.lookup(b"x", "N") is None


class TestCache:
    def test_the_cache_path_is_under_the_user_cache_directory(self):
        assert "z64kit" in str(db.cache_path())

    def test_an_absent_cache_reports_not_available(self, tmp_path, monkeypatch):
        monkeypatch.setattr(db, "cache_path", lambda: tmp_path / "missing.txt")

        assert db.available() is False

    def test_a_present_cache_reports_available(self, tmp_path, monkeypatch):
        target = tmp_path / "present.txt"
        target.write_text(SAMPLE, encoding="utf-8")
        monkeypatch.setattr(db, "cache_path", lambda: target)

        assert db.available() is True

    def test_load_default_uses_the_cache(self, tmp_path, monkeypatch):
        target = tmp_path / "cached.txt"
        target.write_text(SAMPLE, encoding="utf-8")
        monkeypatch.setattr(db, "cache_path", lambda: target)

        assert len(db.load_default().by_md5) == 2

    def test_load_default_raises_a_clear_error_when_absent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(db, "cache_path", lambda: tmp_path / "nope.txt")

        with pytest.raises(db.DatabaseMissingError, match="db-update"):
            db.load_default()


class TestLicence:
    def test_the_source_url_and_licence_are_recorded(self):
        assert db.SOURCE_URL.startswith("https://")
        assert "GPL" in db.SOURCE_LICENCE

    def test_the_package_ships_no_copy_of_the_database(self):
        from z64kit import artifacts

        shipped = artifacts.DEFAULT_MANIFEST_PATH.parent
        assert not any(p.name.endswith("database.txt") for p in shipped.iterdir())


class TestUpdate:
    def test_writes_the_downloaded_catalogue_to_the_cache(self, tmp_path, monkeypatch):
        import io
        import urllib.request

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        payload = b"ID:NSME cic6102|eeprom512 # SUPER MARIO 64\n"

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Response(payload))

        written = db.update()

        assert written.read_bytes() == payload

    def test_the_cache_becomes_loadable_after_an_update(self, tmp_path, monkeypatch):
        import io
        import urllib.request

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            lambda *a, **k: Response(b"ID:NSME cic6102|eeprom512 # SUPER MARIO 64\n"),
        )
        db.update()

        assert db.available() is True
        assert db.load_default().id_patterns["NSME"].save == "eeprom512"


class TestLookupByCodeAlone:
    def catalogue(self):
        return db.parse(
            "ID:NSME cic6102|eeprom512 # SUPER MARIO 64\n"
            "ID:NZSE cic6105|flash128k # MAJORA'S MASK\n"
            "ID:N__E cic6102|sram32k # generic USA fallback\n"
        )

    def test_an_exact_code_resolves_without_the_rom(self):
        assert self.catalogue().lookup_by_code("NSME").save == "eeprom512"

    def test_a_wildcard_pattern_resolves_when_no_exact_match_exists(self):
        assert self.catalogue().lookup_by_code("NQQE").save == "sram32k"

    def test_the_most_specific_pattern_wins(self):
        assert self.catalogue().lookup_by_code("NZSE").save == "flash128k"

    def test_an_unknown_code_returns_nothing(self):
        assert self.catalogue().lookup_by_code("XXXX") is None

    def test_a_short_code_returns_nothing(self):
        assert self.catalogue().lookup_by_code("NS") is None

    def test_it_needs_no_rom_bytes_at_all(self):
        found = self.catalogue().lookup_by_code("NSME")

        assert found is not None
        assert found.cic == "6102"


class TestTheRealCatalogueCoversTheCollection:
    def test_it_knows_a_flashram_game(self):
        try:
            catalogue = db.load_default()
        except db.DatabaseMissingError:
            pytest.skip("catalogue not cached")

        assert catalogue.lookup_by_code("NZSE").save == "flash128k"

    def test_it_knows_an_eeprom_game(self):
        try:
            catalogue = db.load_default()
        except db.DatabaseMissingError:
            pytest.skip("catalogue not cached")

        assert catalogue.lookup_by_code("NSME").save == "eeprom512"
