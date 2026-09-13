from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from operational_controls_v1 import (  # noqa: E402
    load_controls,
    release_hold,
    set_hold,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OperationalControlsV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.operations_root = Path(self.temp.name) / "operations"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_set_hold_writes_only_business_operations_metadata(self) -> None:
        sentinel = Path(self.temp.name) / "persona.json"
        sentinel.write_text('{"authority":"unchanged"}\n', encoding="utf-8")
        before = sha256(sentinel)

        value, path = set_hold(
            self.operations_root,
            "business_a",
            "Human Operator",
            "customer outreach intentionally deferred",
            at="2026-09-13T00:00:00+00:00",
        )

        self.assertEqual(path.parent, self.operations_root / "business_a")
        self.assertTrue(value["operational_hold"]["active"])
        self.assertEqual(value["last_action"], "set_hold")
        self.assertEqual(value["last_actor"], "Human Operator")
        self.assertEqual(before, sha256(sentinel))
        self.assertEqual(
            sorted(p for p in Path(self.temp.name).rglob("*.json") if p != sentinel),
            [path],
        )

    def test_release_requires_explicit_actor_and_action(self) -> None:
        set_hold(
            self.operations_root,
            "business_a",
            "Operator A",
            "manual pause",
            at="2026-09-13T00:00:00+00:00",
        )
        with self.assertRaises(ValueError):
            release_hold(self.operations_root, "business_a", "")

        value, _path = release_hold(
            self.operations_root,
            "business_a",
            "Operator B",
            at="2026-09-13T00:01:00+00:00",
        )

        self.assertFalse(value["operational_hold"]["active"])
        self.assertEqual(value["last_action"], "release_hold")
        self.assertEqual(value["last_actor"], "Operator B")
        self.assertEqual([item["action"] for item in value["history"]], ["set_hold", "release_hold"])

    def test_read_path_cannot_auto_release_hold(self) -> None:
        _value, path = set_hold(
            self.operations_root,
            "business_a",
            "Human Operator",
            "manual pause",
            at="2026-09-13T00:00:00+00:00",
        )
        before = sha256(path)

        loaded, loaded_path = load_controls(self.operations_root, "business_a")

        self.assertEqual(path, loaded_path)
        self.assertTrue(loaded["operational_hold"]["active"])
        self.assertEqual(before, sha256(path))

    def test_business_ids_are_isolated(self) -> None:
        first, first_path = set_hold(
            self.operations_root,
            "business_a",
            "Operator A",
            "pause A",
            at="2026-09-13T00:00:00+00:00",
        )
        second, second_path = set_hold(
            self.operations_root,
            "business_b",
            "Operator B",
            "pause B",
            at="2026-09-13T00:00:01+00:00",
        )

        self.assertNotEqual(first_path, second_path)
        self.assertEqual(first["business_id"], "business_a")
        self.assertEqual(second["business_id"], "business_b")
        self.assertEqual(
            json.loads(first_path.read_text(encoding="utf-8"))["operational_hold"]["reason"],
            "pause A",
        )


if __name__ == "__main__":
    unittest.main()
