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
    assert ".create-entry-card" in styles
    assert ".profile-choice-grid" in styles
    assert ".profile-choice.selected" in styles
    assert ".create-authority-card" in styles
