from pathlib import Path


def test_unified_news_review_contract():
    root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    main = (
        root
        / "app"
        / "main.py"
    ).read_text(
        encoding="utf-8"
    )

    gateway = (
        root
        / "app"
        / "news_delivery_gateway.py"
    ).read_text(
        encoding="utf-8"
    )

    views = (
        root
        / "static"
        / "assets"
        / "news-delivery-views.js"
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

    assert '"revised",' in main
    assert "NEWS_REVIEW_SCHEMA_V1_1" in gateway
    assert "ContentReviewItem" in views
    assert "data-content-decision" in views
    assert "data-revised-title" in components
    assert "这条内容暂时不能移除" in views
    assert "不使用" not in views
