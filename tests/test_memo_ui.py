from pathlib import Path

UI_SOURCE = Path("src/video_archive/ui.py").read_text()


def test_memo_list_uses_wrapped_fitted_titles():
    memo_block = UI_SOURCE.split("class MemoRenderer:", 1)[1]

    assert "def draw_fitted_wrapped_text(" in UI_SOURCE
    assert "draw_fitted_wrapped_text(" in memo_block
    assert "Qt.TextWordWrap" in UI_SOURCE
