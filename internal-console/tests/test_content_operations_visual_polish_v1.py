from pathlib import Path


def test_content_operations_visual_polish_v1():
    root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    views = (
        root
        / "static"
        / "assets"
        / "content-operations-views.js"
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

    assert "内容概览" in views
    assert "content-summary-grid" in views
    assert "content-management-empty" in views
    assert "进行中的创作" in views
    assert "数据来源说明" not in views
    assert "这是运营投影，不是新的业务真源" not in views

    assert (
        "Productized Content Management V1"
        in styles
    )
    assert "grid-template-columns:" in styles
    assert "content-delivery-list" in styles
