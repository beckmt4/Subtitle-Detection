"""Tests for subtagger.scanner."""
import os
import tempfile
import unittest
from pathlib import Path

from subtagger.config import Config
from subtagger.scanner import scan_paths, split_media_and_subtitles


def _make_tree(base: Path, names: list[str]) -> list[Path]:
    """Create empty files under *base* and return their Paths."""
    created = []
    for name in names:
        p = base / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
        created.append(p)
    return created


class TestScanPaths(unittest.TestCase):
    """scan_paths() should respect extensions and exclude patterns."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.base = Path(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _default_config(self, **kwargs) -> Config:
        cfg = Config()
        for k, v in kwargs.items():
            setattr(cfg, k, v)
        return cfg

    # ------------------------------------------------------------------
    # Basic extension filtering
    # ------------------------------------------------------------------

    def test_finds_mkv_files(self):
        _make_tree(self.base, ["movie.mkv", "movie.txt", "cover.jpg"])
        cfg = self._default_config(include_extensions=[".mkv"])
        results = scan_paths([str(self.base)], cfg)
        names = [p.name for p in results]
        self.assertIn("movie.mkv", names)
        self.assertNotIn("movie.txt", names)
        self.assertNotIn("cover.jpg", names)

    def test_finds_srt_and_mp4(self):
        _make_tree(self.base, ["a.mp4", "b.srt", "c.mkv", "d.nfo"])
        cfg = self._default_config(include_extensions=[".mp4", ".srt"])
        results = scan_paths([str(self.base)], cfg)
        names = {p.name for p in results}
        self.assertIn("a.mp4", names)
        self.assertIn("b.srt", names)
        self.assertNotIn("c.mkv", names)
        self.assertNotIn("d.nfo", names)

    def test_case_insensitive_extension(self):
        _make_tree(self.base, ["MOVIE.MKV"])
        cfg = self._default_config(include_extensions=[".mkv"])
        results = scan_paths([str(self.base)], cfg)
        self.assertEqual(len(results), 1)

    # ------------------------------------------------------------------
    # Recursive scanning
    # ------------------------------------------------------------------

    def test_recursive_scan(self):
        _make_tree(
            self.base,
            [
                "tv/S01/ep1.mkv",
                "tv/S01/ep2.mkv",
                "movies/film.mkv",
            ],
        )
        cfg = self._default_config(include_extensions=[".mkv"])
        results = scan_paths([str(self.base)], cfg)
        self.assertEqual(len(results), 3)

    # ------------------------------------------------------------------
    # Exclude patterns
    # ------------------------------------------------------------------

    def test_excludes_by_pattern(self):
        _make_tree(
            self.base,
            [
                "movies/film.mkv",
                "sample/sample.mkv",
                "extras/extra.mkv",
            ],
        )
        cfg = self._default_config(
            include_extensions=[".mkv"],
            exclude_patterns=["*/sample/*", "*/extras/*"],
        )
        results = scan_paths([str(self.base)], cfg)
        names = [p.name for p in results]
        self.assertIn("film.mkv", names)
        self.assertNotIn("sample.mkv", names)
        self.assertNotIn("extra.mkv", names)

    def test_excludes_trailer_by_name(self):
        _make_tree(self.base, ["movie.mkv", "movie-trailer.mkv"])
        cfg = self._default_config(
            include_extensions=[".mkv"],
            exclude_patterns=["*trailer*"],
        )
        results = scan_paths([str(self.base)], cfg)
        names = [p.name for p in results]
        self.assertIn("movie.mkv", names)
        self.assertNotIn("movie-trailer.mkv", names)

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_nonexistent_path_is_skipped(self):
        cfg = self._default_config()
        results = scan_paths(["/does/not/exist"], cfg)
        self.assertEqual(results, [])

    def test_single_file_path(self):
        paths = _make_tree(self.base, ["single.mkv"])
        cfg = self._default_config(include_extensions=[".mkv"])
        results = scan_paths([str(paths[0])], cfg)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "single.mkv")

    def test_no_duplicates(self):
        _make_tree(self.base, ["movie.mkv"])
        cfg = self._default_config(include_extensions=[".mkv"])
        # Pass the same directory twice.
        results = scan_paths([str(self.base), str(self.base)], cfg)
        self.assertEqual(len(results), 1)


class TestSplitMediaAndSubtitles(unittest.TestCase):
    def test_split(self):
        paths = [
            Path("movie.mkv"),
            Path("movie.mp4"),
            Path("movie.en.srt"),
            Path("movie.fr.ass"),
            Path("movie.ssa"),
            Path("movie.vtt"),
        ]
        media, subs = split_media_and_subtitles(paths)
        self.assertEqual(len(media), 2)
        self.assertEqual(len(subs), 4)
        media_names = {p.name for p in media}
        self.assertIn("movie.mkv", media_names)
        self.assertIn("movie.mp4", media_names)

    def test_all_media(self):
        paths = [Path("a.mkv"), Path("b.mp4")]
        media, subs = split_media_and_subtitles(paths)
        self.assertEqual(len(media), 2)
        self.assertEqual(len(subs), 0)

    def test_all_subtitles(self):
        paths = [Path("a.srt"), Path("b.ass"), Path("c.ssa"), Path("d.vtt")]
        media, subs = split_media_and_subtitles(paths)
        self.assertEqual(len(media), 0)
        self.assertEqual(len(subs), 4)


if __name__ == "__main__":
    unittest.main()
