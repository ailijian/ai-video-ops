from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_case_v1 import companion_assets, first_match  # noqa: E402


class CaseCompanionResolutionV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.video = self.root / "case.mp4"
        self.video.write_bytes(b"video")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def touch(self, name: str) -> Path:
        path = self.root / name
        path.write_bytes(name.encode("utf-8"))
        return path

    def test_single_companion_works(self) -> None:
        expected = self.touch("case_music.mp3")
        self.assertEqual(first_match(self.root, ["*_music.mp3", "*.mp3"]), expected)

    def test_explicit_companion_wins(self) -> None:
        first = self.touch("a_music.mp3")
        selected = self.touch("b_music.mp3")
        result = companion_assets(self.video, music=selected)
        self.assertEqual(result["music"], selected.resolve())
        self.assertNotEqual(result["music"], first.resolve())

    def test_multiple_ambiguous_companions_fail_closed(self) -> None:
        self.touch("a_music.mp3")
        self.touch("b_music.mp3")
        with self.assertRaisesRegex(RuntimeError, "Ambiguous Case companion"):
            first_match(self.root, ["*.mp3"])

    def test_filename_length_does_not_decide_authority(self) -> None:
        self.touch("x.mp3")
        self.touch("much_longer_music.mp3")
        with self.assertRaises(RuntimeError):
            first_match(self.root, ["*.mp3"])

    def test_filename_alphabetical_order_does_not_decide_authority(self) -> None:
        self.touch("alpha.jpg")
        self.touch("zebra.jpg")
        with self.assertRaises(RuntimeError):
            first_match(self.root, ["*.jpg"])


if __name__ == "__main__":
    unittest.main()
