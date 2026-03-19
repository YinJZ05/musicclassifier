"""工具函数测试"""

from musicclassifier.utils.helpers import extract_playlist_ids


class TestExtractPlaylistIds:
    def test_extract_single_numeric_id(self):
        ids = extract_playlist_ids("8032497163")
        assert ids == [8032497163]

    def test_extract_from_url(self):
        ids = extract_playlist_ids("https://y.qq.com/n/ryqq/playlist/8032497163")
        assert ids == [8032497163]

    def test_extract_multiple_keep_order_and_dedup(self):
        text = """
        8032497163
        https://y.qq.com/n/ryqq/playlist/1145141919
        再来一遍 8032497163
        """
        ids = extract_playlist_ids(text)
        assert ids == [8032497163, 1145141919]

    def test_extract_empty(self):
        ids = extract_playlist_ids("没有任何数字")
        assert ids == []
