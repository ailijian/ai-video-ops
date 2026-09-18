from pathlib import Path


def test_content_delivery_frontend_contract():
    root = Path(__file__).resolve().parents[1]

    module = (
        root
        / "static"
        / "assets"
        / "content-delivery-views.js"
    ).read_text(encoding="utf-8")

    content_views = (
        root
        / "static"
        / "assets"
        / "content-views.js"
    ).read_text(encoding="utf-8")

    styles = (
        root
        / "static"
        / "assets"
        / "styles.css"
    ).read_text(encoding="utf-8")

    assert "createContentDeliveryViews" in module
    assert "/resolve-content-plan" in module
    assert "/generate-scripts" in module
    assert "/review" in module
    assert "/export-mix" in module
    assert "/exported-excel" in module

    assert "content-delivery-host" in content_views
    assert "deliveryViews.restore" in content_views
    assert "Content Delivery Console V1" in styles
