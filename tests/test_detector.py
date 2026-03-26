"""Tests for subtagger.detector and related inspector helpers."""
import unittest
from dataclasses import asdict
from unittest.mock import MagicMock, patch

from subtagger.inspector import is_unknown_language
from subtagger.detector import DetectionResult, _unknown_result, _resolve_codes


class TestIsUnknownLanguage(unittest.TestCase):
    """is_unknown_language() should recognise all absent/placeholder tags."""

    def test_none_is_unknown(self):
        self.assertTrue(is_unknown_language(None))

    def test_empty_string_is_unknown(self):
        self.assertTrue(is_unknown_language(""))

    def test_und_is_unknown(self):
        self.assertTrue(is_unknown_language("und"))

    def test_unknown_string_is_unknown(self):
        self.assertTrue(is_unknown_language("unknown"))

    def test_unk_is_unknown(self):
        self.assertTrue(is_unknown_language("unk"))

    def test_whitespace_und_is_unknown(self):
        self.assertTrue(is_unknown_language("  und  "))

    def test_english_is_not_unknown(self):
        self.assertFalse(is_unknown_language("eng"))

    def test_fra_is_not_unknown(self):
        self.assertFalse(is_unknown_language("fra"))

    def test_en_is_not_unknown(self):
        self.assertFalse(is_unknown_language("en"))


class TestDetectionResultDataclass(unittest.TestCase):
    """DetectionResult should be a proper dataclass with expected fields."""

    def test_fields_present(self):
        dr = DetectionResult(
            language_name="english",
            iso_639_1="en",
            iso_639_2="eng",
            confidence=0.97,
            method="lingua",
        )
        self.assertEqual(dr.language_name, "english")
        self.assertEqual(dr.iso_639_1, "en")
        self.assertEqual(dr.iso_639_2, "eng")
        self.assertAlmostEqual(dr.confidence, 0.97)
        self.assertEqual(dr.method, "lingua")

    def test_dataclass_asdict(self):
        dr = DetectionResult("french", "fr", "fra", 0.91, "langdetect")
        d = asdict(dr)
        self.assertIn("language_name", d)
        self.assertIn("iso_639_1", d)
        self.assertIn("iso_639_2", d)
        self.assertIn("confidence", d)
        self.assertIn("method", d)


class TestUnknownResult(unittest.TestCase):
    def test_unknown_result_defaults(self):
        r = _unknown_result()
        self.assertEqual(r.language_name, "unknown")
        self.assertEqual(r.iso_639_1, "und")
        self.assertEqual(r.iso_639_2, "und")
        self.assertEqual(r.confidence, 0.0)

    def test_unknown_result_method(self):
        r = _unknown_result("lingua")
        self.assertEqual(r.method, "lingua")


class TestResolveCodes(unittest.TestCase):
    def test_english(self):
        iso1, iso2 = _resolve_codes("english")
        self.assertEqual(iso1, "en")
        self.assertEqual(iso2, "eng")

    def test_french(self):
        iso1, iso2 = _resolve_codes("french")
        self.assertEqual(iso1, "fr")
        self.assertEqual(iso2, "fra")

    def test_unknown_language(self):
        iso1, iso2 = _resolve_codes("klingon")
        self.assertEqual(iso1, "und")
        self.assertEqual(iso2, "und")

    def test_case_insensitive(self):
        iso1, iso2 = _resolve_codes("ENGLISH")
        self.assertEqual(iso1, "en")
        self.assertEqual(iso2, "eng")


class TestDetectLanguageWithMockedLingua(unittest.TestCase):
    """Test detect_language() with lingua mocked out."""

    def test_returns_detection_result_on_success(self):
        """Mock lingua to return a high-confidence English result."""
        mock_language = MagicMock()
        mock_language.name = "ENGLISH"

        mock_cv = MagicMock()
        mock_cv.language = mock_language
        mock_cv.value = 0.99

        mock_detector = MagicMock()
        mock_detector.detect_language_of.return_value = mock_language
        mock_detector.compute_language_confidence_values.return_value = [mock_cv]

        mock_builder = MagicMock()
        mock_builder.from_all_languages.return_value = mock_builder
        mock_builder.build.return_value = mock_detector

        with patch.dict("sys.modules", {"lingua": MagicMock(LanguageDetectorBuilder=mock_builder)}):
            from subtagger.detector import detect_language
            result = detect_language("This is a test sentence in English.", min_confidence=0.80)

        self.assertIsInstance(result, DetectionResult)
        self.assertEqual(result.confidence, 0.99)
        self.assertEqual(result.method, "lingua")

    def test_returns_unknown_when_below_threshold(self):
        """If no library is available detect_language should return unknown."""
        with patch.dict("sys.modules", {"lingua": None, "langdetect": None}):
            # Re-import to pick up the mocked modules.
            import importlib
            import subtagger.detector as det_mod
            importlib.reload(det_mod)
            result = det_mod.detect_language("hello", min_confidence=0.85)
            self.assertEqual(result.language_name, "unknown")


if __name__ == "__main__":
    unittest.main()
