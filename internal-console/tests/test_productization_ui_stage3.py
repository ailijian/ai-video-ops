from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "static" / "assets"


def read_asset(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def test_create_mix_and_news_share_creation_primitives():
    shared = read_asset("creation-components.js")
    create = read_asset("content-views.js")
    mix = read_asset("content-delivery-views.js")
    news = read_asset("news-delivery-views.js")

    for name in (
        "CreationHeader",
        "CreationStepper",
        "CreationSummary",
        "CreationState",
        "CreationMetricRow",
        "TopicList",
        "TopicRow",
        "ContentReviewList",
        "ContentReviewItem",
        "ContentDecisionControl",
        "CreationEvidenceDisclosure",
        "ExportSummary",
        "CreationCompletedState",
    ):
        assert f"export function {name}" in shared

    import_contract = (
        'from "./creation-components.js?v=productized-stage3-3"'
    )
    assert import_contract in create
    assert import_contract in mix
    assert import_contract in news


def test_create_entry_is_business_language_and_progressively_collapses():
    create = read_asset("content-views.js")

    assert "选择客户、出镜人和内容类型" in create
    assert "素材混剪" in create
    assert "新闻体" in create
    assert "计划生成" in create
    assert "查看可创作内容" in create
    assert "data-creation-entry-locked" in create
    assert 'form.classList.add("completed")' in create
    assert "create-authority-card" not in create
    assert "检查内容容量" not in create


def test_capacity_ready_limited_and_zero_states_are_productized():
    create = read_asset("content-views.js")

    assert "本次建议做 ${recommended} 条" in create
    assert "本次最多建议做 ${recommended} 条" in create
    assert "按 ${recommended} 条继续" in create
    assert "调整数量" in create
    assert "暂时没有值得继续做的新内容" in create
    assert "系统不会为了凑够数量重复已经做过的内容" in create
    assert "不代表已获得相关素材使用权" in create


def test_creation_recovery_and_preparation_states_are_humanized():
    create = read_asset("content-views.js")

    for label in (
        "本次创作已创建",
        "继续上次创作",
        "创作准备",
        "还需要准备创作内容",
        "准备完成",
        "正在准备…",
        "现有参考不足，暂时无法继续生成",
        "这次创作暂时无法继续",
    ):
        assert label in create

    assert "sourcePlan?.coverageStatus === \"supported\"" in create
    assert "safeCreationMessage(sourcePlan.coverageReason" in create


def test_mix_lifecycle_and_review_contract_are_complete():
    mix = read_asset("content-delivery-views.js")

    for state in (
        "RESOLVE_GENERATION_SOURCES",
        "CREATE_CONTENT_PLAN",
        "GENERATE_SCRIPTS",
        "HUMAN_REVIEW",
        "REVIEW_COMPLETE_NO_EXPORT",
        "EXPORT_EXCEL",
        "EXCEL_EXPORTED",
    ):
        assert state in mix

    for label in (
        "生成选题",
        "选题已经准备好",
        "生成文案",
        "审核文案",
        "已处理 0 /",
        "提交审核",
        "本次没有通过审核的内容",
        "导出 Excel",
        "下载 Excel",
    ):
        assert label in mix

    assert "data-submit-review disabled" in mix
    assert "ContentReviewItem" in mix


def test_mix_review_revision_bulk_no_export_and_export_recovery_are_present():
    shared = read_asset("creation-components.js")
    mix = read_asset("content-delivery-views.js")

    for contract in (
        "data-content-decision",
        "data-revised-title",
        "data-revised-body",
        "data-content-review-note",
    ):
        assert contract in shared

    for contract in (
        "data-approve-all",
        "completed !== items.length",
        "REVIEW_COMPLETE_NO_EXPORT",
        "本次没有通过审核的内容",
        "state.export?.completed === true",
        "正在完成导出",
        "完成导出",
    ):
        assert contract in mix


def test_news_lifecycle_selection_review_and_constraints_are_complete():
    news = read_asset("news-delivery-views.js")

    for state in (
        "RESOLVE_NEWS_PLAN",
        "HUMAN_REVIEW",
        "EXPORT_NEWS_EXCEL",
        "NEWS_EXCEL_EXPORTED",
    ):
        assert state in news

    for label in (
        "暂无适合生成新闻体的已有内容",
        "选择已有内容",
        "用所选内容生成标题",
        "新闻体创作已开始",
        "生成标题",
        "审核标题",
        "提交审核",
        "本次需要保留 4–8 个标题",
        "导出 Excel",
        "下载 Excel",
    ):
        assert label in news

    assert "这条内容暂时不能移除" in news
    assert "不新增来源事实" in news
    assert "ContentReviewItem" in news


def test_news_empty_selection_edit_export_completion_and_recovery_are_present():
    shared = read_asset("creation-components.js")
    news = read_asset("news-delivery-views.js")

    for label in (
        "暂无适合生成新闻体的已有内容",
        "当前可使用 ${sources.length} 条已有内容",
        "用所选内容生成标题",
        "生成标题",
        "正在生成标题…",
        "审核标题",
        "审核完成",
        "标题已经导出",
        "这次创作暂时无法继续",
    ):
        assert label in news

    assert 'editorMode: "news"' in news
    assert "data-revised-title" in shared
    assert "data-news-export" in news
    assert "NEWS_EXCEL_EXPORTED" in news


def test_stage3_default_templates_do_not_expose_internal_vocabulary():
    content = "\n".join(
        read_asset(name)
        for name in (
            "content-views.js",
            "content-delivery-views.js",
            "news-delivery-views.js",
        )
    )
    literals = []
    pattern = re.compile(
        r'"((?:\\.|[^"\\])*)"'
        r"|'((?:\\.|[^'\\])*)'"
        r"|`((?:\\.|[^`\\])*)`",
        re.DOTALL,
    )
    for match in pattern.finditer(content):
        literal = next(
            group for group in match.groups()
            if group is not None
        )
        literals.append(
            re.sub(
                r"\$\{.*?\}",
                "",
                literal,
                flags=re.DOTALL,
            )
        )
    user_visible_literals = "\n".join(literals)

    forbidden = (
        "Authority",
        "Canonical",
        "Artifact",
        "Generation Request",
        "Request ID",
        "Source Planning Handoff",
        "Generation Source Plan",
        "Content Plan",
        "Script Generation",
        "Generation Batch",
        "Content Ledger",
        "Semantic Ledger",
        "Approved Projection",
        "Historical Exposure",
        "Presentation History",
        "Approved Pattern",
        "Eligible Cases",
        "Coverage Code",
        "Central Claim",
        "Human Review",
        "Human Revision",
        "Known Fact",
        "Authority Field",
        "Cross-profile Repurpose",
        "Remote Model",
        "Local Model",
    )
    for term in forbidden:
        assert term not in user_visible_literals


def test_stage3_responsive_contract_keeps_actions_touchable_without_masking_overflow():
    styles = read_asset("styles.css")

    for selector in (
        ".creation-stepper",
        ".creation-summary",
        ".creation-metric-row",
        ".content-review-item",
        ".content-decision-control",
        ".creation-action-bar",
        ".news-source-row",
    ):
        assert selector in styles

    assert "min-height: 44px;" in styles
    assert "bottom: calc(70px + env(safe-area-inset-bottom));" in styles
    assert "overflow-x: hidden" not in styles


def test_customer_content_tab_embeds_productized_content_management():
    customer = read_asset("customer-views.js")
    operations = read_asset("content-operations-views.js")
    styles = read_asset("styles.css")

    assert "ContentOperationsPanel" in customer
    assert "data-customer-content-operations" in customer
    assert "content-entry-list" not in customer
    assert "content-entry-row" not in customer
    assert "Productized Content Management V1" in styles
    assert "内容概览" in operations
    assert "进行中的创作" in operations
    assert "最近交付" in operations
    assert "只读运营总览" not in operations
    assert "这是运营投影，不是新的业务真源" not in operations
