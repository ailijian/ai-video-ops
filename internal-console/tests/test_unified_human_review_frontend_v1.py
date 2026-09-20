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

    components = (
        root
        / "static"
        / "assets"
        / "creation-components.js"
    ).read_text(
        encoding="utf-8"
    )

    assert "ContentReviewItem" in delivery
    assert "data-content-decision" in delivery
    assert "data-revised-title" in components
    assert "data-revised-body" in components
    assert "<span>修改</span>" in components
    assert 'value="rejected"' in components
    assert "REVIEW_COMPLETE_NO_EXPORT" in delivery
    assert "当前 V1 前端还没有开放 Revision" not in delivery

    assert "已有内容" in content
    assert "暂时没有值得继续做的新内容" in content

    assert "Productized Creation System V1" in styles
