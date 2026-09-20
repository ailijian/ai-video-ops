from pathlib import Path


def test_news_delivery_frontend_contract():
    root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    news = (
        root
        / "static"
        / "assets"
        / "news-delivery-views.js"
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

    assert (
        "createNewsDeliveryViews"
        in news
    )
    assert (
        "/api/create/news/"
        in news
    )
    assert (
        "本次需要保留 4–8 个标题"
        in news
    )
    assert (
        "data-content-decision"
        in news
    )


    assert (
        "News V1 暂不能创建新任务"
        not in news
    )
    assert (
        "当前只开放已经完成 Production Validation"
        not in news
    )
    assert (
        "同一历史内容已经用相同 News Pattern 导出后"
        not in news
    )
    assert (
        "新闻体只重新组织已经确认的内容"
        in news
    )
    assert (
        "暂无适合生成新闻体的已有内容"
        in news
    )
    assert (
        "createNewsDeliveryViews"
        in content
    )
    assert (
        "/api/create/news/preview"
        in content
    )
    assert (
        "restoreActiveNewsRequest"
        in content
    )
    assert (
        "create-quantity-field"
        in content
    )

    assert 'name="create-profile"' in content
    assert '.profile-choice input' in content

    assert (
        "News Delivery Console V1"
        in styles
    )
