from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from generate_reverse_storyboard import (  # noqa: E402
    reconcile_proof_language,
    validate_effective_proof_language,
)


class StoryboardProofLanguageTests(unittest.TestCase):
    def test_reconciles_only_affirmative_effective_fields(self) -> None:
        raw = {
            "audio_visual_strategy": "形成‘口述+视觉佐证’的配合",
            "visual_scene_role": "画面佐证制作流程",
            "structure_sequence": [
                {"description": "这一段证明制作过程完整"},
                {"description": "无法证明商业成功"},
                {"description": "无验证性证据"},
                {"description": "不能证明商业成功"},
                {"description": "无法验证温度是否达标"},
            ],
            "claims": [
                {"claim": "旁白原文含佐证二字"},
                "普通 Claim 原文含证明二字",
            ],
            "verified_proofs": [],
        }
        raw_before = json.dumps(raw, ensure_ascii=False, sort_keys=True)

        effective, audit = reconcile_proof_language(raw)
        validate_effective_proof_language(effective)

        self.assertEqual(
            raw_before,
            json.dumps(raw, ensure_ascii=False, sort_keys=True),
        )
        self.assertEqual(
            effective["audio_visual_strategy"],
            "形成‘口述+视觉呼应’的配合",
        )
        self.assertEqual(
            effective["visual_scene_role"],
            "画面呼应制作流程",
        )
        self.assertEqual(
            effective["structure_sequence"][0]["description"],
            "这一段展示制作过程完整",
        )
        self.assertEqual(
            [x["description"] for x in effective["structure_sequence"][1:]],
            [
                "无法证明商业成功",
                "无验证性证据",
                "不能证明商业成功",
                "无法验证温度是否达标",
            ],
        )
        self.assertEqual(effective["claims"], raw["claims"])
        self.assertTrue(audit["applied"])
        self.assertEqual(audit["change_count"], 3)
        self.assertEqual(
            audit["changed_fields"],
            [
                "visual_scene_role",
                "audio_visual_strategy",
                "structure_sequence[0].description",
            ],
        )

    def test_validation_rejects_affirmative_language(self) -> None:
        value = {
            "audio_visual_strategy": "使用视觉佐证旁白",
            "verified_proofs": [],
        }
        with self.assertRaises(RuntimeError):
            validate_effective_proof_language(value)

    def test_verified_proofs_disable_reconciliation(self) -> None:
        value = {
            "audio_visual_strategy": "使用视觉佐证旁白",
            "verified_proofs": [{"evidence_shots": ["S001"]}],
        }
        effective, audit = reconcile_proof_language(copy.deepcopy(value))
        self.assertEqual(effective, value)
        self.assertFalse(audit["applied"])


if __name__ == "__main__":
    unittest.main()
