from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_shot_boundaries_v1 import (  # noqa: E402
    compact_frame,
    invoke_boundary_transport,
    prepare_boundary_egress,
)


class BoundaryPrivacyGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.privacy_context = {
            "privacy_projection_sha256": "projection-sha",
        }

    def invoke(self, prompt: str) -> tuple[int, object | None]:
        calls = 0

        def transport() -> str:
            nonlocal calls
            calls += 1
            return "response"

        audit = {
            "privacy_state": "safe_for_external_model",
            "privacy_policy_version": "privacy-policy-v1.0",
            "privacy_projection_sha256": "projection-sha",
            "safe_input_sha256": "unused-on-blocked-input",
            "rendered_prompt_sha256": "unused-on-blocked-input",
        }
        response = None
        try:
            response, _ = invoke_boundary_transport(
                safe_input={"text": prompt},
                rendered_prompt=prompt,
                privacy_context=self.privacy_context,
                pre_call_audit=audit,
                transport=transport,
            )
        except RuntimeError:
            if calls:
                raise
        return calls, response

    def test_high_confidence_pii_blocks_before_transport(self) -> None:
        unsafe_values = (
            "身份证号：11010519491231002X",
            "手机号：13812345678",
            "私人邮箱：alice@example.com",
            "收件地址：盐城市某区某路88号3栋502",
        )
        for prompt in unsafe_values:
            with self.subTest(prompt=prompt):
                calls, response = self.invoke(prompt)
                self.assertEqual(calls, 0)
                self.assertIsNone(response)

    def test_privacy_safe_prompt_calls_transport_and_post_audits(self) -> None:
        safe_input = {"text": "骑手正在取餐"}
        prompt = "请分析骑手正在取餐"
        from privacy_projection_v1 import build_egress_audit

        pre_call_audit = build_egress_audit(
            safe_input=safe_input,
            rendered_prompt=prompt,
            privacy_context=self.privacy_context,
        )
        calls = 0

        def transport() -> str:
            nonlocal calls
            calls += 1
            return "response"

        response, post_call_audit = invoke_boundary_transport(
            safe_input=safe_input,
            rendered_prompt=prompt,
            privacy_context=self.privacy_context,
            pre_call_audit=pre_call_audit,
            transport=transport,
        )
        self.assertEqual(calls, 1)
        self.assertEqual(response, "response")
        self.assertEqual(post_call_audit, pre_call_audit)

    def test_prompt_rendering_projects_raw_evidence(self) -> None:
        raw = {
            "frame_id": "frame_000001000ms.jpg",
            "timestamp_seconds": 1.0,
            "ocr_raw": "收件人：张三，手机号：13812345678",
            "scene_summary": "骑手正在取餐",
            "visual_change_from_previous": "",
            "information_change": "YES",
            "pyscenedetect_reasons": [],
            "pixel_difference_signal": 0.1,
        }
        safe_input, prompt, audit = prepare_boundary_egress(
            case_id="7650056203686530319",
            context_frame=None,
            primary_frames=[raw],
            privacy_context=self.privacy_context,
        )
        self.assertNotIn("张三", prompt)
        self.assertNotIn("13812345678", prompt)
        self.assertEqual(
            safe_input["primary_frames"][0]["ocr_raw"],
            "收件人：[姓名]，手机号：[电话]",
        )
        self.assertEqual(audit["privacy_state"], "safe_for_external_model")

    def test_internal_ids_and_telemetry_are_safe_and_minimized(self) -> None:
        frame = {
            "frame_id": "frame_000019000ms.jpg",
            "timestamp_seconds": 19.0,
            "ocr_raw": "",
            "scene_summary": "植物细节",
            "visual_change_from_previous": "",
            "information_change": "NO",
        }
        manifest = {
            "frame_000019000ms.jpg": {
                "difference_ratio_from_previous_kept": 0.024600694444444446,
            }
        }
        compact = compact_frame(frame, manifest)
        self.assertEqual(compact["pixel_difference_signal"], 0.024601)
        _, prompt, _ = prepare_boundary_egress(
            case_id="7650056203686530319",
            context_frame=None,
            primary_frames=[compact],
            privacy_context=self.privacy_context,
        )
        self.assertIn("7650056203686530319", prompt)
        self.assertNotIn("0.024600694444444446", prompt)


if __name__ == "__main__":
    unittest.main()
