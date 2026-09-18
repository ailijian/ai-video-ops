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
    assert "operations-overview-grid" in views
    assert "operations-empty-strip" in views
    assert "数据来源说明" in views
    assert "这是运营投影，不是新的业务真源" in views

    assert (
        "Content Operations View V1.1 — Visual Polish"
        in styles
    )
    assert "grid-template-columns:" in styles
    assert "operations-delivery-list" in styles
