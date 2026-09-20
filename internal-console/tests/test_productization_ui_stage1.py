from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def read_asset(name: str) -> str:
    return (STATIC / "assets" / name).read_text(encoding="utf-8")


def test_shell_navigation_is_calm_equal_weight_and_in_frozen_order():
    app = read_asset("app.js")

    expected = [
        '{ path: "/workbench", label: "工作台"',
        '{ path: "/cases", label: "案例"',
        '{ path: "/customers", label: "客户"',
        '{ path: "/create", label: "创作"',
        '{ path: "/tasks", label: "任务"',
    ]
    assert [app.index(value) for value in expected] == sorted(
        app.index(value) for value in expected
    )
    assert "create-link" not in app
    assert "create-bottom" not in app
    assert "create-orb" not in app
    assert "内部生产工作台 · V1" not in app


def test_workbench_and_case_library_use_compact_product_surfaces():
    app = read_asset("app.js")
    case_components = read_asset("case-components.js")
    case_views = read_asset("case-views.js")

    assert 'class="action-list"' in app
    assert 'class="action-row"' in app
    assert 'class="quick-actions"' in app
    assert 'class="workbench-overview"' in app
    assert 'class="workbench-recent"' in app
    assert 'api("/api/workbench?projection=productized-stage3-3")' in app
    assert 'api("/api/customers")' in app
    assert 'api("/api/cases")' in app
    assert "const hasCustomers = customers.length > 0" in app
    assert "const customerCount = customers.length" in app
    assert "const caseCount = cases.length" in app
    assert 'cache: method === "GET" || method === "HEAD" ? "no-store"' in read_asset("api-client.js")
    assert "attention-card" not in app
    assert "customer-snapshot" not in app
    assert 'class="case-row"' in case_components
    assert "case-card" not in case_components
    assert "caseItem.profile" not in case_components
    assert "caseItem.summary" not in case_components
    assert 'pageHeading("", "案例"' in case_views


def test_add_case_is_one_continuous_surface_and_progress_moves_to_durable_task_route():
    case_views = read_asset("case-views.js")
    case_components = read_asset("case-components.js")

    assert 'class="work-surface add-case-surface"' in case_views
    assert 'data-case-input-panel' in case_views
    assert 'data-live-progress data-embedded="true"' not in case_views
    assert 'navigate(`/tasks/${encodeURIComponent(result.task.task_id)}`, true)' in case_views
    assert 'navigate(`/tasks/${encodeURIComponent(result.existing_task.task_id)}`, true)' in case_views
    assert "查看当前进度" in case_views
    assert "批准后的案例只用于内部参考，不会获得原视频素材使用权。" in case_views
    assert "案例使用边界" not in case_views
    assert "embedded = false" in case_components


def test_case_review_is_evidence_first_and_uses_accessible_modal():
    app = read_asset("app.js")
    case_views = read_asset("case-views.js")
    case_components = read_asset("case-components.js")

    assert 'role="dialog"' in app
    assert 'aria-modal="true"' in app
    assert 'event.key === "Escape"' in app
    assert 'event.key !== "Tab"' in app
    assert "window.confirm" not in case_views
    assert "window.prompt" not in case_views
    assert "批准这个案例？" in case_views
    assert "确认不收录" in case_views
    assert 'class="case-analysis"' in case_components
    assert 'class="panel review-decision"' in case_components
    assert "预览暂时不可用" in case_components
    assert "批准不会改变原视频素材使用权。" in case_components
    assert "rights-banner" not in case_components
    assert "transient-media-notice" not in case_components
    for internal_term in ("Authority", "Canonical", "Artifact", "Attempt", "Companion"):
        assert internal_term not in case_components


def test_foundation_tokens_and_create_overflow_fix_are_explicit():
    css = read_asset("styles.css")

    assert "--paper: #f6f7f4;" in css
    assert "--surface: #ffffff;" in css
    assert "--forest: #214c3d;" in css
    assert "--radius-lg: 16px;" in css
    assert "--radius-md: 12px;" in css
    assert ".card, .panel, .work-surface" in css
    assert ".card, .panel, .work-surface { border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface); }" in css
    assert ".profile-choice input {" in css
    assert "width: 1px;" in css
    assert "height: 1px;" in css
    assert "overflow-x: hidden" not in css


def test_loading_empty_and_error_share_state_foundation_without_raw_error_copy():
    app = read_asset("app.js")

    assert "state-panel state-loading" in app
    assert "state-panel state-error" in app
    assert "暂时无法完成操作" in app
    assert 'pageHeading("Error"' not in app
    assert "title, error.message" not in app
