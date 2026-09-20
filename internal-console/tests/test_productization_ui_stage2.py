from pathlib import Path


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
    assert "ReviewList({" in customer
    assert "ReviewList({" in speaker
    assert "bindDecisionControls" in customer
    assert "bindDecisionControls" in speaker


def test_customer_list_and_detail_are_product_management_surfaces():
    customer_components = read_asset("customer-components.js")
    customer = read_asset("customer-views.js")

    assert 'class="customer-row"' in customer_components
    assert 'class="card customer-card"' not in customer_components
    assert 'id: "overview", label: "概览"' in customer
    assert 'id: "profile", label: "客户资料"' in customer
    assert 'id: "speakers", label: "出镜人"' in customer
    assert 'id: "content", label: "内容"' in customer
    assert "customerProfileSections(facts)" in customer
    assert "return formatProfileValue(value" in customer_components
    assert 'class="fact-json"' not in customer_components
    assert "开始创作" in customer
    assert "添加出镜人" in customer


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
    assert "系统会先整理资料，之后仍需要你确认。" in customer
    rights_copy = "确认出镜人档案，不会自动获得照片、视频或肖像素材使用权。"
    assert speaker.count(rights_copy) == 1
    assert "data-customer-new-surface" in customer
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
