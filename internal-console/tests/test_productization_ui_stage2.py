from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def read_asset(name: str) -> str:
    return (STATIC / "assets" / name).read_text(encoding="utf-8")


def test_customer_and_speaker_use_shared_profile_primitives():
    shared = read_asset("profile-components.js")
    customer = read_asset("customer-views.js")
    speaker = read_asset("speaker-views.js")

    expected = (
        "ProfileSection",
        "ProfileRow",
        "ReviewList",
        "ReviewRow",
        "EvidenceDisclosure",
        "DecisionControl",
        "ProfileTabs",
        "ProfileSummary",
        "NeedsInfoState",
    )
    for name in expected:
        assert f"export function {name}" in shared

    assert 'from "./profile-components.js?v=productized-stage2-3"' in customer
    assert 'from "./profile-components.js?v=productized-stage2-3"' in speaker
    # The approved E2-UX amendment replaces Customer's per-row confirmation
    # while retaining shared display/source primitives and Speaker's own gate.
    for name in ("ProfileSection({", "ProfileRow({", "EvidenceDisclosure("):
        assert name in customer
    assert "customerReviewGroups(needsReview)" in customer
    assert "bindCustomerReviewControls(detail)" in customer
    assert 'data-review-choice="reject"' in customer
    assert 'data-review-choice="edit"' in customer
    assert "待统一确认" in customer
    assert "ReviewList({" in speaker
    assert "bindDecisionControls" in speaker


def test_customer_list_and_detail_are_product_management_surfaces():
    customer_components = read_asset("customer-components.js")
    customer = read_asset("customer-views.js")

    # CUSTOMER-LIST-1 supersedes the directory row with a read-only operations card.
    assert 'class="customer-operation-card"' in customer_components
    for label in ("已批准出镜人", "创作记录", "待处理", "查看作品记录"):
        assert label in customer_components
    assert "/api/customers/operations" in customer
    assert 'class="card customer-card"' not in customer_components
    assert 'id: "overview", label: "概览"' in customer
    assert 'id: "profile", label: "客户资料"' in customer
    assert 'id: "speakers", label: "出镜人"' in customer
    assert 'id: "content", label: "内容"' in customer
    assert "customerProfileSections(facts)" in customer
    assert "return formatProfileValue(value" in customer_components
    assert 'class="fact-json"' not in customer_components
    assert "去创作" in customer
    assert "仍需检查内容机会与可行性" in customer
    assert "添加出镜人" in customer


def test_customer_needs_info_uses_capability_gap_language():
    customer_components = read_asset("customer-components.js")
    customer = read_asset("customer-views.js")

    assert 'customer_use_context: "还缺少顾客或使用场景信息"' in customer_components
    assert (
        'production_bearing_facts: "还缺少可用于内容创作的真实业务信息"'
        in customer_components
    )
    assert 'critical_constraints: "还有关键冲突或边界需要确认"' in customer_components
    assert "补充缺失信息" in customer
    assert "/gaps/supplement" in customer
    assert "/edit\" data-route>编辑完整资料" in customer
    assert "customer-name" not in customer[
        customer.index("async function renderCustomerSupplement") : customer.index(
            "function renderFailedCustomer"
        )
    ]
    assert "customer-materials" not in customer[
        customer.index("async function renderCustomerSupplement") : customer.index(
            "function renderFailedCustomer"
        )
    ]
    assert "legacy_readiness_recheck_available" in customer
    assert "/readiness/recheck" in customer


def test_speaker_raw_intake_can_be_saved_before_customer_profile_approval():
    speaker = read_asset("speaker-views.js")
    component = read_asset("speaker-components.js")
    assert "暂时不能添加出镜人" not in speaker
    assert "保存出镜人资料" in speaker
    assert "result.draft_saved" in speaker
    assert "pending_customer_profile" in speaker
    assert "继续确认出镜人" in speaker
    assert "待客户档案确认" in component


def test_customer_and_speaker_reviews_are_compact_and_complete_before_submit():
    shared = read_asset("profile-components.js")
    customer = read_asset("customer-views.js")
    speaker = read_asset("speaker-views.js")

    assert 'class="review-list-row"' in shared
    assert 'class="decision-control"' in shared
    assert "submitButton.disabled = completed !== rows.length" in shared
    assert "已确认 ${completed} / ${rows.length}" in shared
    assert 'class="card fact-card"' not in customer
    assert 'class="card fact-card"' not in speaker
    assert "确认客户档案？" in customer
    assert "确认出镜人档案？" in speaker
    assert "window.confirm" not in customer
    assert "window.confirm" not in speaker
    assert "window.prompt" not in customer
    assert "window.prompt" not in speaker


def test_stage2_default_surfaces_do_not_expose_architecture_vocabulary():
    content = "\n".join(
        read_asset(name)
        for name in (
            "customer-components.js",
            "customer-views.js",
            "speaker-components.js",
            "speaker-views.js",
            "profile-components.js",
        )
    )
    forbidden = (
        "Customer Truth",
        "Business Persona",
        "Speaker Persona",
        "Speaker Truth",
        "Business Fact",
        "Speaker Fact",
        "Authority",
        "Canonical",
        "Artifact",
        "Intake",
    )
    for term in forbidden:
        assert term not in content


def test_stage2_forms_and_rights_copy_are_single_continuous_surfaces():
    customer = read_asset("customer-views.js")
    speaker = read_asset("speaker-views.js")

    assert 'class="work-surface profile-form-surface"' in customer
    assert 'class="work-surface profile-form-surface"' in speaker
    assert "系统整理后，由你分别确认客户信息和出镜人信息。" in customer
    rights_copy = "确认出镜人档案，不会自动获得照片、视频或肖像素材使用权。"
    assert speaker.count(rights_copy) == 1
    assert 'id="customer-new-form"' in customer
    assert "data-speaker-new-surface" in speaker


def test_stage2_responsive_components_do_not_hide_horizontal_overflow():
    css = read_asset("styles.css")

    for selector in (
        ".customer-row",
        ".speaker-row",
        ".profile-tabs",
        ".profile-row",
        ".review-list-row",
        ".decision-control",
        ".needs-info-state",
    ):
        assert selector in css
    assert "grid-template-columns: 1fr 1fr;" in css
    assert ".decision-confirm { grid-column: 1 / -1; grid-row: 1; }" in css
    assert "overflow-x: hidden" not in css


def test_shared_profile_spacing_and_palette_variables_are_defined():
    """Undefined design tokens silently discard padding and colour in browsers."""
    css = read_asset("styles.css")
    definitions = set(re.findall(r"(--[\w-]+)\s*:", css))
    # These common design tokens are static. References with a fallback are
    # deliberately excluded; media geometry can have separate runtime owners.
    references = set(re.findall(
        r"var\((--(?:space-\d+|brand|forest[\w-]*|ink[\w-]*|line[\w-]*))\s*\)", css
    ))
    assert references <= definitions, sorted(references - definitions)
