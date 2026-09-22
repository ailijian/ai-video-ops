from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "static" / "assets"


def test_news_dual_mode_ui_and_novel_review_contract() -> None:
    content = (ROOT / "content-views.js").read_text(encoding="utf-8")
    novel = (ROOT / "novel-news-views.js").read_text(encoding="utf-8")
    styles = (ROOT / "styles.css").read_text(encoding="utf-8")
    assert 'name="create-news-mode" value="novel_content" checked' in content
    assert 'data.novel_news?.available === true' in content
    assert 'data.novel_news.verification_badge' in content
    assert 'value="cross_profile_repurpose" ${data.novel_news?.available === true ? "" : "checked"}' in content
    assert 'name="create-news-mode" value="cross_profile_repurpose"' in content
    assert "restoreActiveNovelNewsRequest" in content
    assert "restoreActiveNewsRequest" in content
    assert "当前结构暂不支持" in novel
    assert "data-confirm-novel" in novel
    assert "审核新闻体" in novel and "查看来源事实" in novel
    assert "data-novel-revised" in novel and "data-submit-novel-review" in novel
    assert "导出新闻体 Excel" in novel
    assert "repeat(5, minmax(0, 1fr))" in styles
