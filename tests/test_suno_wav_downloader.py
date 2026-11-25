from pathlib import Path
from unittest.mock import patch
import base64
import hashlib

import pytest

from backend.cover.suno_wav_downloader import (
    PublicSong,
    SunoWavDownloadError,
    _safe_page_url,
    _decrypt_ctr_file,
    _unwrap_rights,
    download_song_as_wav,
    parse_public_song,
    save_authorized_audio_bytes,
    save_pcm_f32_chunks,
)

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


SONG_ID = "20f569e1-fb1b-4b4e-af8e-8518ffb5837a"


def _wrapped_rights(seed: str, key: bytes, iv: bytes) -> dict:
    wrapping = hashlib.sha256(seed.encode()).digest()

    def wrap(raw: bytes, nonce: bytes) -> str:
        encrypted = nonce + AESGCM(wrapping).encrypt(nonce, raw, SONG_ID.encode())
        return base64.b64encode(encrypted).decode()

    return {"key": wrap(key, b"K" * 12), "iv": wrap(iv, b"I" * 12), "glt": seed}


def test_rights_unwrap_and_ctr_stream_keep_continuity_across_odd_chunks(tmp_path: Path):
    seed = "guest-or-user-token"
    key, iv = bytes(range(16)), bytes(range(16, 32))
    rights = _wrapped_rights(seed, key, iv)
    assert _unwrap_rights(rights, SONG_ID) == (key, iv)

    plain = bytes((n * 37) % 256 for n in range(3 * 1024 * 1024 + 31))
    enc = Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor()
    source, output = tmp_path / "asset.enc", tmp_path / "asset.m4a"
    source.write_bytes(enc.update(plain) + enc.finalize())
    _decrypt_ctr_file(source, output, key, iv)
    assert output.read_bytes() == plain


def test_rejects_non_suno_and_non_song_urls():
    with pytest.raises(SunoWavDownloadError):
        _safe_page_url("https://example.com/song/" + SONG_ID)
    with pytest.raises(SunoWavDownloadError):
        _safe_page_url("https://suno.com/@someone")


def test_parser_keeps_only_media_for_requested_song():
    body = f'''<meta property="og:title" content="Hello &amp; Test">
      <audio src="https://cdn-o.suno.com/sil-100.mp3"></audio>
      https:\\/\\/cdn1.suno.ai/{SONG_ID}.mp4
      https:\\/\\/cdn1.suno.ai/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.mp4
      https:\\/\\/d2lwuy8qc234o3.cloudfront.net/1/clip/{SONG_ID}.m4a
    '''
    song = parse_public_song(f"https://suno.com/song/{SONG_ID}", body)
    assert song.title == "Hello & Test"
    assert len(song.media_urls) == 2
    assert all(SONG_ID in url for url in song.media_urls)
    assert not any("sil-100" in url for url in song.media_urls)


def test_exact_mode_never_converts_compressed_source(tmp_path: Path):
    song = PublicSong(SONG_ID, "Test", f"https://suno.com/song/{SONG_ID}",
                      (f"https://cdn1.suno.ai/{SONG_ID}.mp4",))
    with pytest.raises(SunoWavDownloadError, match="không có WAV gốc"):
        download_song_as_wav(song, tmp_path, allow_compatible=False)
    assert list(tmp_path.glob("*.wav")) == []


def test_compatible_mode_outputs_verified_pcm(tmp_path: Path):
    song = PublicSong(SONG_ID, "Test", f"https://suno.com/song/{SONG_ID}",
                      (f"https://cdn1.suno.ai/{SONG_ID}.mp4",))

    def fake_download(_url, path, _timeout=180):
        path.write_bytes(b"public-media")

    def fake_decode(_source, output):
        output.write_bytes(b"RIFF" + b"\0" * 4 + b"WAVE" + b"\0" * 64)

    meta = {"has_audio": True, "codec_name": "pcm_f32le", "sample_rate": 48000,
            "channels": 2, "duration": 60.0}
    with patch("backend.cover.suno_wav_downloader._download_file", fake_download), \
         patch("backend.cover.suno_wav_downloader._decode_pcm_float", fake_decode), \
         patch("backend.cover.suno_wav_downloader.probe_audio", return_value=meta):
        result = download_song_as_wav(song, tmp_path, allow_compatible=True)
    assert result["mode"] == "compatible_pcm_from_public_source"
    assert result["codec"] == "pcm_f32le"
    assert Path(result["path"]).read_bytes().startswith(b"RIFF")


def test_authorized_stream_is_verified_before_replacing_destination(tmp_path: Path):
    destination = tmp_path / "song.wav"
    destination.write_bytes(b"old")

    def fake_decode(_source, output):
        output.write_bytes(b"RIFF" + b"\0" * 4 + b"WAVE" + b"\0" * 64)

    meta = {"has_audio": True, "codec_name": "pcm_f32le", "sample_rate": 48000,
            "channels": 2, "duration": 120.0}
    with patch("backend.cover.suno_wav_downloader._decode_pcm_float", fake_decode), \
         patch("backend.cover.suno_wav_downloader.probe_audio", return_value=meta):
        result = save_authorized_audio_bytes(b"encoded" * 200, destination)
    assert result["mode"] == "compatible_pcm_from_authorized_stream"
    assert destination.read_bytes().startswith(b"RIFF")


def test_player_pcm_chunks_are_written_as_float_wav(tmp_path: Path):
    destination = tmp_path / "player.wav"
    frames, rate, channels = 48000, 48000, 2
    chunks = [b"\0" * (frames * channels * 4)]
    meta = {"has_audio": True, "codec_name": "pcm_f32le", "sample_rate": rate,
            "channels": channels, "duration": 1.0}
    with patch("backend.cover.suno_wav_downloader.probe_audio", return_value=meta):
        result = save_pcm_f32_chunks(chunks, rate, channels, frames, destination)
    assert result["mode"] == "captured_pcm_from_authorized_player"
    assert destination.read_bytes()[:12] == b"RIFF" + (48 + frames * channels * 4).to_bytes(4, "little") + b"WAVE"
