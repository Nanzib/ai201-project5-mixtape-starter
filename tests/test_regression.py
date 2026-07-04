import pytest
from datetime import datetime, timezone
from app import create_app, db

@pytest.fixture
def app():
    """Provides an isolated app instance for regression testing."""
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"
    })
    return app


def test_playlist_returns_all_songs_including_the_last_one(app):
    """
    Regression Test: Ensures get_playlist_songs returns every single song 
    added to a playlist, specifically verifying that the final track is not truncated.
    """
    with app.app_context():
        from services.playlist_service import create_playlist, get_playlist_songs
        from models import User, Song, playlist_entries
        
        user = User(username="reg_playlist_user", email="reg_playlist@test.com")
        db.session.add(user)
        db.session.commit()
        
        songs = []
        for i in range(1, 4):
            song = Song(title=f"Regression Track {i}", artist=f"Artist {i}", shared_by=user.id)
            db.session.add(song)
            songs.append(song)
        db.session.commit()
        
        playlist = create_playlist(name="Regression Test Choice", created_by_user_id=user.id)
        
        for idx, song in enumerate(songs):
            db.session.execute(
                playlist_entries.insert().values(
                    playlist_id=playlist.id,
                    song_id=song.id,
                    position=idx,
                    added_by=user.id
                )
            )
        db.session.commit()
            
        retrieved_songs = get_playlist_songs(playlist.id)
        
        assert len(retrieved_songs) == 3
        assert retrieved_songs[-1]["id"] == songs[-1].id


def test_streak_increments_saturday_to_sunday(app):
    """
    Regression Test: Ensures that when a user listens on Saturday and 
    subsequently listens on Sunday, the listening streak increments to 2 
    instead of resetting to 1.
    """
    with app.app_context():
        from services.streak_service import update_listening_streak
        from models import User
        
        user = User(username="reg_streak_user", email="reg_streak@test.com", listening_streak=1)
        db.session.add(user)
        db.session.commit()
        
        saturday = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)
        sunday = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
        
        user.last_listened_at = saturday
        
        update_listening_streak(user, sunday)
        
        assert user.listening_streak == 2