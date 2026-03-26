"""Tests for subtagger.cleaner."""
import unittest

from subtagger.cleaner import clean_subtitle_text


class TestCleanSRTTimestamps(unittest.TestCase):
    """SRT timestamp lines should be removed."""

    def test_removes_srt_timestamp(self):
        raw = "1\n00:00:01,000 --> 00:00:02,500\nHello world.\n"
        result = clean_subtitle_text(raw, remove_sdh=False)
        self.assertNotIn("-->", result)
        self.assertIn("Hello world.", result)

    def test_removes_sequence_number(self):
        raw = "42\n00:00:05,000 --> 00:00:06,000\nSome dialogue.\n"
        result = clean_subtitle_text(raw, remove_sdh=False)
        lines = [ln.strip() for ln in result.splitlines() if ln.strip()]
        self.assertNotIn("42", lines)

    def test_multiple_blocks(self):
        raw = (
            "1\n00:00:01,000 --> 00:00:02,000\nFirst line.\n\n"
            "2\n00:00:03,000 --> 00:00:04,000\nSecond line.\n"
        )
        result = clean_subtitle_text(raw, remove_sdh=False)
        self.assertIn("First line.", result)
        self.assertIn("Second line.", result)
        self.assertNotIn("-->", result)


class TestCleanASSTags(unittest.TestCase):
    """ASS override tags and formatting directives should be stripped."""

    def test_removes_ass_override_block(self):
        raw = "{\\an8}This is dialogue.{\\i0}"
        result = clean_subtitle_text(raw, remove_sdh=False)
        self.assertNotIn("{", result)
        self.assertIn("This is dialogue.", result)

    def test_removes_ass_position_tag(self):
        raw = "{\\pos(320,240)}Positioned text."
        result = clean_subtitle_text(raw, remove_sdh=False)
        self.assertNotIn("\\pos", result)
        self.assertIn("Positioned text.", result)

    def test_extracts_ass_dialogue_lines(self):
        raw = (
            "[Script Info]\nTitle: Test\n\n"
            "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
            "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hello from ASS.\n"
        )
        result = clean_subtitle_text(raw, remove_sdh=False)
        self.assertIn("Hello from ASS.", result)
        self.assertNotIn("[Script Info]", result)


class TestRemoveSDH(unittest.TestCase):
    """SDH annotations inside brackets/parentheses should be removed."""

    def test_removes_square_bracket_sound(self):
        raw = "1\n00:00:01,000 --> 00:00:02,000\n[Music playing]\n"
        result = clean_subtitle_text(raw, remove_sdh=True)
        self.assertNotIn("[Music playing]", result)

    def test_removes_round_bracket_annotation(self):
        raw = "1\n00:00:01,000 --> 00:00:02,000\n(applause)\n"
        result = clean_subtitle_text(raw, remove_sdh=True)
        self.assertNotIn("(applause)", result)

    def test_preserves_dialogue_when_sdh_off(self):
        raw = "1\n00:00:01,000 --> 00:00:02,000\n[Music] Hello.\n"
        result = clean_subtitle_text(raw, remove_sdh=False)
        self.assertIn("[Music]", result)
        self.assertIn("Hello.", result)


class TestRemoveHTMLTags(unittest.TestCase):
    """HTML tags embedded in SRT should be stripped."""

    def test_removes_italic_tag(self):
        raw = "1\n00:00:01,000 --> 00:00:02,000\n<i>Italic text</i>\n"
        result = clean_subtitle_text(raw, remove_sdh=False)
        self.assertNotIn("<i>", result)
        self.assertNotIn("</i>", result)
        self.assertIn("Italic text", result)

    def test_removes_bold_tag(self):
        raw = "1\n00:00:01,000 --> 00:00:02,000\n<b>Bold</b>\n"
        result = clean_subtitle_text(raw, remove_sdh=False)
        self.assertNotIn("<b>", result)
        self.assertIn("Bold", result)

    def test_removes_font_color_tag(self):
        raw = '1\n00:00:01,000 --> 00:00:02,000\n<font color="#ffffff">White text</font>\n'
        result = clean_subtitle_text(raw, remove_sdh=False)
        self.assertNotIn("<font", result)
        self.assertIn("White text", result)


class TestEdgeCases(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(clean_subtitle_text(""), "")

    def test_whitespace_only(self):
        result = clean_subtitle_text("   \n\n\t  ")
        self.assertEqual(result.strip(), "")

    def test_plain_text_preserved(self):
        raw = "Just some plain text with no markup."
        result = clean_subtitle_text(raw, remove_sdh=False)
        self.assertIn("Just some plain text with no markup.", result)


if __name__ == "__main__":
    unittest.main()
