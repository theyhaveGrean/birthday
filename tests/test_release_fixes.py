"""Regressions for requested findings in the second ZIP review."""
import queue
import socket
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace as S

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QFontMetrics, QPainter
from video_archive import app, audio, cloud, player

@pytest.mark.parametrize('boundary', [1, 2, 3])
@pytest.mark.parametrize('target', ['gallery', 'home'])
def test_cancel_at_every_startup_event_boundary(qapp, monkeypatch, boundary, target):
    events = []
    page = app.PlaybackPage()
    window = S(videos=[Path('clip.mp4')], titles=['clip'], mode='gallery', playback_generation=0,
        gallery=S(cancel_navigation=lambda:None, flicker_timer=S(stop=lambda:None)),
        audio=S(play=lambda name:None, wait_until_idle=lambda:True),
        pages=S(setCurrentWidget=lambda p:None), playback_page=page,
        playback_watchdog=S(start=lambda:events.append('watchdog'), stop=lambda:None),
        settings={'volume':30}, player=S(stop=lambda **kw:None, preload=lambda *args:events.append('preload')))
    count = 0
    def process():
        nonlocal count
        count += 1
        if count == boundary:
            app.VideoArchiveWindow._begin_return(window, target)
    monkeypatch.setattr(app.QApplication, 'processEvents', process)
    returned = []
    page.transition.return_finished.connect(lambda:returned.append(True))
    app.VideoArchiveWindow.play_selected(window, 0)
    assert window.mode == 'returning'
    assert window.return_target == target
    assert page.transition.mode == 'return'
    for _ in range(20):page.transition._advance()
    assert returned
    assert events == []
    page.close()

@pytest.mark.parametrize('data', [b'\xff', b'{', b'[]', b'{"volume":1e999}', b'{"brightness":-1e999}', b'{"sleep_timeout_minutes":NaN}'])
def test_bad_settings_recover_without_rewriting_source(monkeypatch, tmp_path, data):
    path = tmp_path/'settings.json'
    path.write_bytes(data)
    monkeypatch.setattr(app, 'SETTINGS_FILE', path)
    result = app.load_settings()
    assert 0 <= result['volume'] <= 100
    assert 5 <= result['brightness'] <= 100
    assert 1 <= result['sleep_timeout_minutes'] <= 60
    assert path.read_bytes() == data

@pytest.fixture
def memo_files(monkeypatch, tmp_path):
    for name in ('CLOUD_MEMOS_FILE', 'CLOUD_MESSAGE_FILE', 'CLOUD_MESSAGE_META_FILE', 'READ_MEMOS_FILE'):
        monkeypatch.setattr(cloud, name, tmp_path/name)

@pytest.mark.parametrize('data', [b'{', b'\xff', b'{}', b'null'])
def test_invalid_index_recovers_cache(memo_files, data):
    cloud.CLOUD_MEMOS_FILE.write_bytes(data)
    cloud.CLOUD_MESSAGE_FILE.write_text('Offline memo')
    cloud.CLOUD_MESSAGE_META_FILE.write_bytes(b'\xff')
    cloud.READ_MEMOS_FILE.write_bytes(b'\xff')
    assert [m['message'] for m in cloud.load_memos()] == ['Offline memo']
    assert len(cloud.load_memos()) == 1

def test_empty_archive_does_not_resurrect_cache(memo_files):
    cloud.CLOUD_MEMOS_FILE.write_text('[]')
    cloud.CLOUD_MESSAGE_FILE.write_text('Expired memo')
    assert cloud.load_memos() == []

def test_invalid_cached_text_is_ignored(memo_files):
    cloud.CLOUD_MESSAGE_FILE.write_bytes(b'\xff')
    assert cloud.load_memos() == []

def blocked_socket():
    a, b = socket.socketpair()
    a.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)
    a.setblocking(False)
    try:
        while True:a.send(b'x'*1024)
    except BlockingIOError:pass
    a.setblocking(True)
    return a, b

def test_blocked_ipc_send_is_bounded(qapp):
    controller = player.MpvController()
    a, b = blocked_socket()
    controller._sock = a
    try:
        start = time.monotonic()
        assert controller.command(['quit']) is False
        assert time.monotonic() - start < 1
    finally:
        a.close(); b.close()

def test_stop_reaches_process_termination_with_blocked_ipc(qapp, tmp_path):
    controller = player.MpvController()
    controller.socket_path = str(tmp_path/'unused.sock')
    a, b = blocked_socket()
    controller._sock = a
    events = []
    def wait(timeout):
        if not events:raise subprocess.TimeoutExpired('mpv', timeout)
    controller.process = S(wait=wait, terminate=lambda:events.append('terminated'))
    try:
        controller.stop()
        assert events == ['terminated']
        assert controller.process is controller._sock is None
    finally:
        a.close(); b.close()

def test_ipc_lock_contention_is_bounded(qapp):
    controller = player.MpvController()
    controller._send_lock.acquire()
    try:
        start = time.monotonic()
        assert not controller.command(['quit'])
        assert time.monotonic() - start < 1
    finally:controller._send_lock.release()

@pytest.mark.parametrize('failed_step', [0, 1])
def test_scan_failure_never_reports_cached_success(monkeypatch, failed_step):
    calls, results = [], []
    def run(command, **kwargs):
        calls.append(command)
        return S(returncode=1 if len(calls)-1 == failed_step else 0, stdout='', stderr='not authorized')
    monkeypatch.setattr(app.subprocess, 'run', run)
    window = S(wifi_scan_finished=S(emit=lambda *args:results.append(args)))
    app.VideoArchiveWindow._scan_wifi_worker(window)
    assert len(calls) == failed_step+1
    assert len(results) == 1 and results[0][0] == [] and results[0][1]

def test_playback_footer_fits_at_target_resolution(qapp, monkeypatch):
    original = QPainter.drawText
    captured = []
    def draw(painter, *args):
        if args and isinstance(args[0], QRect) and isinstance(args[-1], str) and 'SELECT // RETURN' in args[-1]:
            captured.append((args[0], QFontMetrics(painter.font()), args[-1]))
        return original(painter, *args)
    monkeypatch.setattr(QPainter, 'drawText', draw)
    page = app.PlaybackPage()
    page.resize(1024, 600)
    page.grab()
    assert captured
    rect, metrics, label = captured[0]
    assert metrics.horizontalAdvance(label) <= rect.width()
    assert rect.right() < 1024 and rect.bottom() < 600
    page.close()

def test_audio_worker_continues_after_timeout(monkeypatch):
    controller = audio.AudioController.__new__(audio.AudioController)
    controller.player = 'aplay'
    controller.volume = 100
    controller._play_queue = queue.Queue()
    controller._playing = threading.Event()
    played = []
    def run(command, **kwargs):
        assert kwargs['timeout'] == audio.PLAYBACK_TIMEOUT_SECONDS
        played.append(command[-1])
        if len(played) == 1:raise subprocess.TimeoutExpired(command, kwargs['timeout'])
        return S(returncode=0)
    monkeypatch.setattr(audio.subprocess, 'run', run)
    controller._play_queue.put(('click', 'click.wav'))
    controller._play_queue.put(('notify', 'notify.wav'))
    original_get = controller._play_queue.get
    def get():
        if len(played) == 2:raise StopIteration
        return original_get()
    controller._play_queue.get = get
    with pytest.raises(StopIteration):controller._audio_worker()
    assert played == ['click.wav', 'notify.wav']
    assert controller._play_queue.unfinished_tasks == 0
    assert not controller._playing.is_set()

def test_reader_survives_idle_socket_timeout(qapp, monkeypatch, tmp_path):
    controller = player.MpvController()
    controller.log_path = tmp_path/'mpv.log'
    results = []
    controller.ready.connect(lambda g:results.append(('ready', g)))
    controller.failed.connect(lambda *args:results.append(('failed', args)))
    responses = iter([socket.timeout(), b'{"event":"playback-restart"}\n', b''])
    class Socket:
        def settimeout(self, timeout):pass
        def connect(self, path):pass
        def sendall(self, data):pass
        def close(self):pass
        def recv(self, size):
            response = next(responses)
            if isinstance(response, Exception):raise response
            if not response:controller._generation += 1
            return response
    monkeypatch.setattr(player.socket, 'socket', lambda *args:Socket())
    monkeypatch.setattr(player.os.path, 'exists', lambda p:True)
    controller._ipc_reader(0, 9, S(poll=lambda:None), '/tmp/fake', tmp_path/'clip')
    assert results == [('ready', 9)]


def test_return_overlay_uses_destination_neutral_label(qapp, monkeypatch):
    from video_archive import ui
    original = ui.draw_text_glow
    labels = []
    def draw(*args, **kwargs):
        labels.append(args[3])
        return original(*args, **kwargs)
    monkeypatch.setattr(ui, 'draw_text_glow', draw)
    widget = ui.TransitionWidget()
    widget.resize(1024, 600)
    widget.start_return('clip')
    widget.grab()
    assert 'RETURNING' in labels
    assert not any('GALLERY' in label for label in labels)
    widget.close()


def test_recovered_memo_available_if_index_cannot_be_written(memo_files, monkeypatch):
    cloud.CLOUD_MEMOS_FILE.write_text('{')
    cloud.CLOUD_MESSAGE_FILE.write_text('Offline memo')
    def fail(*args):raise PermissionError('read only')
    monkeypatch.setattr(cloud, 'save_memos', fail)
    assert cloud.load_memos()[0]['message'] == 'Offline memo'
