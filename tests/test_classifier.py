"""分类器测试"""

from musicclassifier.models.song import Song
from musicclassifier.processors.classifier import SongClassifier


class TestClassifier:
    def setup_method(self):
        self.classifier = SongClassifier()

    def test_classify_by_genre_pop(self):
        songs = [Song(name="测试", artists=["A"], genre="流行")]
        results = self.classifier.classify_by_genre(songs)
        assert any(r.category == "流行" for r in results)

    def test_classify_by_genre_rock(self):
        songs = [Song(name="Rock Song", artists=["B"], genre="Rock")]
        results = self.classifier.classify_by_genre(songs)
        assert any(r.category == "摇滚" for r in results)

    def test_classify_by_genre_unknown(self):
        songs = [Song(name="神秘", artists=["C"], genre="")]
        results = self.classifier.classify_by_genre(songs)
        assert any(r.category == "其他" for r in results)

    def test_classify_by_language(self):
        songs = [Song(name="测试", artists=["A"], language="国语")]
        results = self.classifier.classify_by_language(songs)
        assert any(r.category == "华语" for r in results)

    def test_classify_songs_default_genre(self):
        songs = [Song(name="Pop", artists=["A"], genre="Pop")]
        results = self.classifier.classify_songs(songs)
        assert len(results) > 0

    def test_classify_songs_language(self):
        songs = [Song(name="Test", artists=["A"], language="English")]
        results = self.classifier.classify_songs(songs, by="language")
        assert any(r.category == "英语" for r in results)
