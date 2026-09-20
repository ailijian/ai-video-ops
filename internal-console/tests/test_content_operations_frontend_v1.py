from pathlib import Path


def test_content_operations_frontend_contract():
    root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    routes = (
        root
        / "static"
        / "assets"
        / "routes.js"
    ).read_text(
        encoding="utf-8"
    )

    app = (
        root
        / "static"
        / "assets"
        / "app.js"
    ).read_text(
        encoding="utf-8"
    )

    customer = (
        root
        / "static"
        / "assets"
        / "customer-views.js"
    ).read_text(
        encoding="utf-8"
    )

    operations = (
        root
        / "static"
        / "assets"
        / "content-operations-views.js"
    ).read_text(
        encoding="utf-8"
    )

    assert "customer-content-operations" in routes
    assert "createContentOperationsViews" in app
    assert "renderContentOperations" in app
    assert "ContentOperationsPanel" in customer
    assert "data-customer-content-operations" in customer
    assert "content-entry-list" not in customer
    assert "content-entry-row" not in customer
    assert "已交付内容" in operations
    assert "还能继续做什么" in operations
    assert "进行中的创作" in operations
    assert "最近交付" in operations
    assert "export function ContentOperationsPanel" in operations
    assert "这是运营投影，不是新的业务真源" not in operations
    assert "只读运营总览" not in operations
