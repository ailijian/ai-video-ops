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

    # Creation page structure remains the canonical entry surface.
    assert 'class="page create-entry-page"' in views
    assert 'class="create-workflow"' in views
    assert 'class="card create-entry-card"' in views
    assert 'id="content-entry-form"' in views
    assert 'class="profile-choice-grid"' in views
    assert 'id="check-content-capacity"' in views
    assert 'class="card notice-card create-authority-card"' in views

    # UX copy preserves the frozen "capacity first, generation later" rule.
    assert (
        "系统会先检查高质量内容容量，不会直接生成。"
        in views
    )
    assert (
        "先检查容量，再显式建立 Generation Request"
        in views
    )

    # Visual contract: page width, card, profile selector and authority note
    # all have dedicated styling hooks rather than relying on generic cards.
    assert ".create-entry-page" in styles
    assert ".create-workflow" in styles
    assert ".create-entry-card" in styles
    assert ".create-entry-card > form" in styles
    assert ".create-entry-card > form {\n  width: 100%;\n}" in styles
    assert "#capacity-preview-result" in styles
    assert "#content-delivery-host" in styles
    assert ".profile-choice-grid" in styles
    assert ".profile-choice.selected" in styles
    assert ".create-authority-card" in styles


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
    assert "production-acceptance-1" in index
    assert 'src="/assets/brand/logo.png?v=transparent-1"' in app
    assert "鲸汤AI视频代运营工作台" in app
    assert "视频创作" in app

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
