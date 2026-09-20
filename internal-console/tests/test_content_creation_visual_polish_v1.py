from pathlib import Path


def test_content_creation_visual_polish_v1():
    root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    views = (
        root
        / "static"
        / "assets"
        / "content-views.js"
    ).read_text(
        encoding="utf-8"
    )

    styles = (
        root
        / "static"
        / "assets"
        / "styles.css"
    ).read_text(
        encoding="utf-8"
    )

    # Creation page remains one continuous product surface.
    assert 'class="page create-entry-page"' in views
    assert 'class="create-workflow"' in views
    assert 'class="work-surface create-entry-card"' in views
    assert 'id="content-entry-form"' in views
    assert 'class="profile-choice-grid"' in views
    assert 'id="check-content-capacity"' in views
    assert 'data-creation-entry-locked' in views

    # UX copy preserves the capacity-first rule in operator language.
    assert (
        "系统会先检查当前还有多少值得做的新内容。"
        in views
    )
    assert "查看可创作内容" in views
    assert "素材混剪" in views
    assert "新闻体" in views
    assert "create-authority-card" not in views

    # Visual contract: page width, card, profile selector and authority note
    # all have dedicated styling hooks rather than relying on generic cards.
    assert ".create-entry-page" in styles
    assert ".create-workflow" in styles
    assert ".create-entry-card" in styles
    assert ".creation-entry-fields" in styles
    assert ".creation-entry-locked" in styles
    assert "#capacity-preview-result" in styles
    assert "#content-delivery-host" in styles
    assert ".profile-choice-grid" in styles
    assert ".profile-choice.selected" in styles
    assert ".creation-state" in styles


def test_console_branding_and_favicon_contract():
    root = Path(__file__).resolve().parents[1]
    index = (root / "static" / "index.html").read_text(encoding="utf-8")
    app = (root / "static" / "assets" / "app.js").read_text(encoding="utf-8")
    brand = root / "static" / "assets" / "brand"

    assert "<title>鲸汤AI视频代运营工作台</title>" in index
    assert 'name="description" content="鲸汤AI视频代运营工作台' in index
    assert 'href="/assets/brand/favicon.ico?v=transparent-1"' in index
    assert 'href="/assets/brand/favicon-32x32.png?v=transparent-1"' in index
    assert 'href="/assets/brand/favicon-16x16.png?v=transparent-1"' in index
    assert 'href="/assets/brand/apple-touch-icon.png?v=transparent-1"' in index
    assert 'styles.css?v=boundary-review-1' in index
    assert 'app.js?v=boundary-review-1' in index
    assert 'case-views.js?v=boundary-review-1' in app
    assert 'src="/assets/brand/logo.png?v=transparent-1"' in app
    assert "鲸汤AI视频代运营工作台" in app
    assert "视频创作" in app

    case_views = (root / "static" / "assets" / "case-views.js").read_text(encoding="utf-8")
    assert 'id="case-video-file"' in case_views
    assert 'id="case-file-rights"' not in case_views
    assert 'id="case-file-source-match"' not in case_views
    assert 'id="case-video-file" type="file"' in case_views
    assert 'aria-describedby="case-file-help case-file-selected" required' not in case_views
    assert 'url: file ? uploadedReceipt.canonical_url : input.value' in case_views

    for asset in (
        "logo.png",
        "favicon.ico",
        "favicon-32x32.png",
        "favicon-16x16.png",
        "apple-touch-icon.png",
        "source/鲸汤logo.png",
        "source/鲸汤logo带文字.png",
    ):
        assert (brand / asset).is_file()
