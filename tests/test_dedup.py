"""去重处理器测试"""

from musicclassifier.models.song import Song
from musicclassifier.processors.dedup import deduplicate, merge_playlists


class TestDeduplicate:
    def test_no_duplicates(self):
        songs = [
            Song(name="晴天", artists=["周杰伦"]),
            Song(name="稻香", artists=["周杰伦"]),
        ]
        unique, dups = deduplicate(songs)
        assert len(unique) == 2
        assert len(dups) == 0

    def test_with_duplicates(self):
        songs = [
            Song(name="晴天", artists=["周杰伦"]),
            Song(name="稻香", artists=["周杰伦"]),
            Song(name="晴天", artists=["周杰伦"], album="叶惠美"),  # 重复
        ]
        unique, dups = deduplicate(songs)
        assert len(unique) == 2
        assert len(dups) == 1

    def test_case_insensitive(self):
        songs = [
            Song(name="Hello", artists=["Adele"]),
            Song(name="hello", artists=["adele"]),
        ]
        unique, dups = deduplicate(songs)
        assert len(unique) == 1

    def test_empty(self):
        unique, dups = deduplicate([])
        assert len(unique) == 0
        assert len(dups) == 0


class TestMergePlaylists:
    def test_merge(self):
        list1 = [Song(name="晴天", artists=["周杰伦"])]
        list2 = [Song(name="稻香", artists=["周杰伦"])]
        merged = merge_playlists(list1, list2)
        assert len(merged) == 2

    def test_merge_with_overlap(self):
        list1 = [Song(name="晴天", artists=["周杰伦"])]
        list2 = [Song(name="晴天", artists=["周杰伦"]), Song(name="稻香", artists=["周杰伦"])]
        merged = merge_playlists(list1, list2)
        assert len(merged) == 2
