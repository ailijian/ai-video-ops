from pathlib import Path


def test_unified_human_review_frontend_contract():
    root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    delivery = (
        root
        / "static"
        / "assets"
        / "content-delivery-views.js"
    ).read_text(
        encoding="utf-8"
    )

    content = (
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

    assert "修改后通过" in delivery
    assert "淘汰" in delivery
    assert "data-revised-title" in delivery
    assert "data-revised-narration" in delivery
    assert "REVIEW_COMPLETE_NO_EXPORT" in delivery
    assert "当前 V1 前端还没有开放 Revision" not in delivery

    assert "已有历史内容" in content
    assert "剩余高质量新内容" in content

    assert "Unified Human Review V1" in styles
