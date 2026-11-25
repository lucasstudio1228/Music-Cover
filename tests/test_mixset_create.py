import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session, SQLModel, create_engine, select

from backend import batch_service
from backend.models import BatchRun, Project, SourceSong
from backend.routers.projects import _read_mixset_lines


class MixSetFileTests(unittest.TestCase):
    def test_txt_one_song_per_line(self):
        payload = "Tìm Em - Hngle, Bảo Anh\nNguyễn Vĩ - Không Môn Đăng Hộ Đối\n".encode()
        self.assertEqual(2, len(_read_mixset_lines("songs.txt", payload)))

    def test_docx_one_paragraph_per_song(self):
        xml = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body><w:p><w:r><w:t>Tim Em - Hngle</w:t></w:r></w:p>
          <w:p><w:r><w:t>Nguyen Vi - Khong Mon Dang Ho Doi</w:t></w:r></w:p></w:body>
        </w:document>'''
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("word/document.xml", xml)
        self.assertEqual(2, len(_read_mixset_lines("songs.docx", stream.getvalue())))


class MixSetCreateTests(unittest.TestCase):
    def test_creates_one_project_and_sources(self):
        self._create_and_check(None, "")

    def test_creative_instrument_off_disables_every_song(self):
        from backend.cover.style_prompt import NO_CREATIVE_INSTRUMENT
        self._create_and_check(False, NO_CREATIVE_INSTRUMENT)

    def test_mixset_keeps_shared_video_and_instrument_tools(self):
        with tempfile.TemporaryDirectory() as root:
            engine = create_engine(f"sqlite:///{Path(root) / 'shared.sqlite'}")
            SQLModel.metadata.create_all(engine)

            class NoStartThread:
                def __init__(self, *args, **kwargs): pass
                def start(self): pass
                def is_alive(self): return False

            with patch.object(batch_service, "engine", engine), \
                 patch.object(batch_service.threading, "Thread", NoStartThread):
                result = batch_service.create_cover_mixset(
                    name="Mix", song_lines=["Bai Mot - Ca Si"],
                    music_style="Ballad", video_style="real",
                    footage_scene_mode="character_screen",
                    creative_instrument=False)
                with Session(engine) as session:
                    project = session.exec(select(Project)).one()
                    self.assertEqual("character_screen", project.footage_scene_mode)
                    self.assertFalse(project.creative_instrument)
                    self.assertTrue(project.auto_video)
                    self.assertTrue(project.auto_upload)
                batch_service._threads.pop(result["batch_key"], None)
                batch_service._cancel_flags.pop(result["batch_key"], None)
            engine.dispose()

    def test_skip_missing_lyrics_keeps_only_songs_with_lyrics(self):
        with tempfile.TemporaryDirectory() as root:
            engine = create_engine(f"sqlite:///{Path(root) / 'skip.sqlite'}")
            SQLModel.metadata.create_all(engine)

            class NoStartThread:
                def __init__(self, *args, **kwargs): pass
                def start(self): pass
                def is_alive(self): return False

            with patch.object(batch_service, "engine", engine), \
                 patch.object(batch_service.threading, "Thread", NoStartThread):
                result = batch_service.create_cover_mixset(
                    name="Mix", song_lines=["Bai Mot - Ca Si", "Bai Hai - Ca Si"],
                    music_style="Ballad", video_style="real")
                with Session(engine) as session:
                    songs = session.exec(select(SourceSong).order_by(SourceSong.id)).all()
                    songs[0].lyrics_text = "[Verse]\nCo loi"
                    session.add(songs[0])
                    run = session.exec(select(BatchRun)).one()
                    run.status = "blocked"
                    session.add(run)
                    session.commit()
                resumed = batch_service.skip_missing_lyrics(result["batch_key"])
                self.assertEqual([], resumed["missing_lyrics"])
                with Session(engine) as session:
                    songs = session.exec(select(SourceSong).order_by(SourceSong.id)).all()
                    self.assertEqual("skipped_no_lyrics", songs[1].status)
                    self.assertNotEqual("skipped_no_lyrics", songs[0].status)
                batch_service._threads.pop(result["batch_key"], None)
                batch_service._cancel_flags.pop(result["batch_key"], None)
            engine.dispose()

    def _create_and_check(self, creative, expected_instrument):
        extra = {} if creative is None else {"creative_instrument": creative}
        with tempfile.TemporaryDirectory() as root:
            engine = create_engine(f"sqlite:///{Path(root) / 'mixset.sqlite'}")
            SQLModel.metadata.create_all(engine)

            class NoStartThread:
                def __init__(self, *args, **kwargs):
                    pass

                def start(self):
                    pass

                def is_alive(self):
                    return False

            with patch.object(batch_service, "engine", engine), \
                 patch.object(batch_service.threading, "Thread", NoStartThread):
                result = batch_service.create_cover_mixset(
                    name="Ballad mua thu",
                    song_lines=["Tim Em - Hngle", "Nguyen Vi - Khong Mon Dang Ho Doi"],
                    music_style="Ballad", music_line="Nhac Viet",
                    video_style="real", **extra)
                self.assertEqual("interrupted", result["status"])
                self.assertEqual(2, len(result["missing_lyrics"]))
                with self.assertRaisesRegex(ValueError, "chưa có lyrics"):
                    batch_service.resume_batch(result["batch_key"])
                with Session(engine) as session:
                    self.assertEqual(1, len(session.exec(select(Project)).all()))
                    songs = session.exec(select(SourceSong)).all()
                    self.assertEqual(2, len(songs))
                    self.assertEqual({expected_instrument},
                                     {x.featured_instrument for x in songs})
                    for song in songs:
                        song.lyrics_text = "[Verse]\nCau mot\nCau hai"
                        session.add(song)
                    session.commit()
                    run = session.exec(select(BatchRun)).one()
                    self.assertEqual(1, run.total)
                resumed = batch_service.resume_batch(result["batch_key"])
                self.assertEqual([], resumed["missing_lyrics"])
                batch_service._threads.pop(result["batch_key"], None)
                batch_service._cancel_flags.pop(result["batch_key"], None)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
