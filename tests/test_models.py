"""歌曲模型测试"""

from musicclassifier.models.song import Song, Playlist


class TestSong:
    def test_artist_str(self):
        song = Song(name="测试歌曲", artists=["歌手A", "歌手B"])
        assert song.artist_str == "歌手A / 歌手B"

    def test_artist_str_empty(self):
        song = Song(name="测试歌曲", artists=[])
        assert song.artist_str == "未知"

    def test_duration_str(self):
        song = Song(name="测试歌曲", duration=195)
        assert song.duration_str == "3:15"

    def test_match_key(self):
        song1 = Song(name="晴天", artists=["周杰伦"])
        song2 = Song(name="晴天", artists=["周杰伦"], album="叶惠美")
        assert song1.match_key() == song2.match_key()

    def test_match_key_different(self):
        song1 = Song(name="晴天", artists=["周杰伦"])
        song2 = Song(name="雨天", artists=["周杰伦"])
        assert song1.match_key() != song2.match_key()

    def test_str(self):
        song = Song(name="晴天", artists=["周杰伦"])
        assert str(song) == "晴天 - 周杰伦"


class TestPlaylist:
    def test_str(self):
        pl = Playlist(id="1", name="我的歌单", song_count=10)
        assert str(pl) == "[我的歌单] (10 首)"
