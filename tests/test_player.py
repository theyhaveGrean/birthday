from video_archive.player import MpvController


class FakeProcess:
    def poll(self):
        return None


def test_mpv_uses_alsa_default_audio_device(monkeypatch, tmp_path):
    commands = []

    def fake_popen(args, stdout, stderr):
        commands.append(args)
        return FakeProcess()

    class FakeThread:
        def __init__(self, target, args, daemon):
            pass

        def start(self):
            pass

    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")

    monkeypatch.setattr("video_archive.player.subprocess.Popen", fake_popen)
    monkeypatch.setattr("video_archive.player.threading.Thread", FakeThread)

    controller = MpvController()
    controller.log_path = tmp_path / "mpv.log"
    controller.preload(video, wid=123, volume=80, event_generation=1)

    assert "--ao=alsa" in commands[0]
    assert "--audio-device=alsa/default" in commands[0]
