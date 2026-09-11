from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from privacy_projection_v1 import (  # noqa: E402
    PRIVACY_POLICY_VERSION,
    assert_safe_for_external_model,
    build_case_privacy_gate,
    build_egress_audit,
    detect_sensitive_spans,
    project_safe_semantic,
    project_safe_verbatim,
    validate_case_privacy_gate,
)


class PrivacyProjectionV1Tests(unittest.TestCase):
    PRESERVED = (
        "骑手配送问题",
        "配送的问题我们一直在改进",
        "所以小店对高温天气的出餐配送把控都非常严格",
        "以防配送过程中蛋糕磕碰",
        "闪送1V1配送",
        "工作人员手持一个蛋糕，准备进行配送",
        "骑手取餐之前就制作好",
        "订单很多",
        "今天配送了很多单",
        "骑手正在取餐",
    )

    REDACTED = {
        "收件人：张三": "收件人：[姓名]",
        "联系人：李四": "联系人：[姓名]",
        "手机号：13812345678": "手机号：[电话]",
        "联系电话：021-12345678": "联系电话：[电话]",
        "收件地址：盐城市某区某路88号3栋502": "收件地址：[地址]",
        "订单号：123456789012345": "订单号：[订单号]",
        "运单号：SF1234567890": "运单号：[运单号]",
    }

    def test_business_semantics_are_preserved(self) -> None:
        for source in self.PRESERVED:
            with self.subTest(source=source):
                self.assertEqual(project_safe_verbatim(source), source)
                self.assertEqual(detect_sensitive_spans(source), [])

    def test_required_span_redactions(self) -> None:
        for source, expected in self.REDACTED.items():
            with self.subTest(source=source):
                self.assertEqual(project_safe_verbatim(source), expected)

    def test_remaining_v1_taxonomy_and_public_address_context(self) -> None:
        cases = {
            "私人邮箱：alice@example.com": "私人邮箱：[邮箱]",
            "身份证号：11010519491231002X": "身份证号：[身份证号]",
            "银行卡号：6222021234567890123": "银行卡号：[银行卡号]",
            "用户ID：private_123": "用户ID：[账号]",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(project_safe_verbatim(source), expected)

        public_address = "门店地址：上海市浦东新区世纪大道100号"
        self.assertEqual(
            project_safe_verbatim(public_address),
            public_address,
        )

    def test_internal_numeric_identifiers_and_decimal_telemetry(self) -> None:
        for source in (
            "7650056203686530319",
            "pixel_difference_signal=0.024600694444444446",
        ):
            with self.subTest(source=source):
                self.assertNotIn(
                    "id_card",
                    {item["type"] for item in detect_sensitive_spans(source)},
                )

        actual_id_card = "身份证号：11010519491231002X"
        self.assertIn(
            "id_card",
            {item["type"] for item in detect_sensitive_spans(actual_id_card)},
        )

    def test_minimal_redaction_not_sentence_replacement(self) -> None:
        source = "请核对收件人：张三，然后安排骑手配送"
        self.assertEqual(
            project_safe_verbatim(source),
            "请核对收件人：[姓名]，然后安排骑手配送",
        )

    def test_idempotency_and_determinism(self) -> None:
        for source in (*self.PRESERVED, *self.REDACTED):
            with self.subTest(source=source):
                once = project_safe_verbatim(source)
                self.assertEqual(project_safe_verbatim(once), once)
                self.assertEqual(project_safe_verbatim(source), once)

    def test_safe_semantic_minimizes_private_order_label(self) -> None:
        source = "购物袋订单标签，收件人：张三"
        self.assertEqual(
            project_safe_semantic(source),
            "购物袋上有订单标签（个人信息已隐藏）",
        )

    def test_egress_gate_blocks_before_network(self) -> None:
        network_called = False
        with self.assertRaises(RuntimeError):
            build_egress_audit(
                safe_input={"text": "收件人：张三"},
                rendered_prompt="请分析收件人：张三",
                privacy_context=None,
            )
            network_called = True
        self.assertFalse(network_called)

    def test_egress_gate_accepts_projection(self) -> None:
        prompt = project_safe_verbatim("请分析收件人：张三")
        assert_safe_for_external_model(prompt)
        audit = build_egress_audit(
            safe_input={"text": prompt},
            rendered_prompt=prompt,
            privacy_context=None,
        )
        self.assertEqual(
            audit["privacy_policy_version"],
            PRIVACY_POLICY_VERSION,
        )

    def test_case_approval_privacy_gate(self) -> None:
        context = {
            "path": "privacy_projection_v1.json",
            "privacy_projection_sha256": "abc",
            "artifact": {
                "validation": {
                    "passed": True,
                    "unresolved_sensitive_items": 0,
                    "review_required_items": 0,
                }
            },
        }
        gate = build_case_privacy_gate(
            privacy_context=context,
            derived_artifact={"text_safe_semantic": "骑手正在取餐"},
        )
        case = {"privacy_gate": gate}
        validate_case_privacy_gate(case)
        self.assertTrue(gate["library_safe"])

        unsafe_gate = build_case_privacy_gate(
            privacy_context=context,
            derived_artifact={"text": "手机号：13812345678"},
        )
        with self.assertRaises(RuntimeError):
            validate_case_privacy_gate({"privacy_gate": unsafe_gate})


if __name__ == "__main__":
    unittest.main()
