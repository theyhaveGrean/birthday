import io
import json
from http.client import IncompleteRead
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from video_archive import app, cloud, player
from video_archive.ui import ConfigWidget


def config_widget():
    return ConfigWidget('', '', '', [], 80, True, True, True, 80, 5)


def test_wifi_profiles_read_ssid_from_each_profile(monkeypatch):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if command[-2:] == ['connection', 'show']:
            assert command[3] == 'UUID,TYPE,NAME'
            output = 'u1:802-11-wireless:Renamed profile\nu2:802-3-ethernet:Ethernet\n'
        else:
            assert command == ['nmcli', '-t', '-f', '802-11-wireless.ssid',
                               'connection', 'show', 'uuid', 'u1']
            output = '802-11-wireless.ssid:My\\:Wifi\\\\Name\n'
        return SimpleNamespace(returncode=0, stdout=output)

    monkeypatch.setattr(app.subprocess, 'run', run)
    assert app._load_wifi_profiles() == [
        {'uuid': 'u1', 'name': 'Renamed profile', 'ssid': 'My:Wifi\\Name'}
    ]
    assert len(commands) == 2


def test_wifi_recovery_deletes_only_matching_ssid(monkeypatch):
    monkeypatch.setattr(app, '_load_wifi_profiles', lambda: [
        {'uuid': 'matching', 'ssid': 'Home'}, {'uuid': 'other', 'ssid': 'Elsewhere'}
    ])
    commands = []
    results = []

    def run(command, **kwargs):
        commands.append(command)
        failed = len(commands) == 1
        return SimpleNamespace(returncode=int(failed), stdout='',
                               stderr='key-mgmt: property is missing' if failed else '')

    monkeypatch.setattr(app.subprocess, 'run', run)
    window = SimpleNamespace(wifi_connect_finished=SimpleNamespace(emit=lambda *v: results.append(v)))
    app.VideoArchiveWindow._connect_wifi_worker(window, 'Home', 'password')
    assert ['nmcli', 'connection', 'delete', 'uuid', 'matching'] in commands
    assert all('other' not in command for command in commands)
    assert results == [(True, 'connected')]


@pytest.mark.parametrize('leave_session', [False, True])
def test_wifi_completion_only_updates_its_original_editor(qapp, leave_session):
    widget = config_widget()
    widget.showing_wifi = True
    widget.set_wifi_networks([
        {'ssid': 'A', 'security': 'WPA2'}, {'ssid': 'B', 'security': 'WPA2'}
    ])
    widget.select()
    session = widget.wifi_session
    if leave_session:
        widget.wifi_key_row = 6
        widget.wifi_key_col = 3  # CANCEL, then choose another network.
        widget.select()
        widget.wifi_selected_index = 1
        widget.select()
    widget.wifi_password = 'new password'
    window = SimpleNamespace(
        mode='config', config_page=widget, wifi_connect_context=session,
        wifi_connect_running=True, settings={}, _refresh_wifi_status=lambda: None,
        _maybe_start_pending_wifi_reset=lambda: None,
    )
    app.VideoArchiveWindow._wifi_connect_finished(window, True, 'connected')
    assert window.wifi_connect_running is False
    assert widget.wifi_password == ('new password' if leave_session else '')
    assert widget.wifi_stage == ('password' if leave_session else 'networks')


def test_large_unicode_cloud_response_is_complete_and_server_limited(monkeypatch, tmp_path):
    for name in ('CLOUD_MESSAGE_FILE', 'CLOUD_MESSAGE_META_FILE', 'CLOUD_MEMOS_FILE', 'READ_MEMOS_FILE'):
        monkeypatch.setattr(cloud, name, tmp_path / name)
    rows = [{'id': str(i), 'message': '😀' * 1200,
             'created_at': '2026-09-06T00:00:00Z'} for i in range(100)]
    payload = json.dumps(rows).encode()
    assert len(payload) > cloud.MAX_RESPONSE_BYTES

    def open_response(request, timeout):
        assert parse_qs(urlsplit(request.full_url).query)['limit'] == ['100']
        return io.BytesIO(payload)

    monkeypatch.setattr(cloud, 'urlopen', open_response)
    message, error = cloud.fetch_cloud_message()
    assert error == ''
    assert message == '😀' * 1200
    assert len(cloud.load_memos()) == 100


def test_interrupted_response_becomes_retryable_error(monkeypatch):
    class Response(io.BytesIO):
        def read(self, size=-1):
            raise IncompleteRead(b'[', 10)

    monkeypatch.setattr(cloud, 'urlopen', lambda *a, **k: Response())
    message, error = cloud.fetch_cloud_message()
    assert message is None
    assert 'IncompleteRead' in error


def test_unexpected_cloud_failure_releases_busy_flag(monkeypatch):
    def fail(url):
        raise RuntimeError('interrupted')

    monkeypatch.setattr(app, 'fetch_cloud_message', fail)
    config = SimpleNamespace(set_cloud_status=lambda *v: None, showing_admin=False, showing_about=False)
    window = SimpleNamespace(
        cloud_message_running=True, memo_reset_pending=False, cloud_last_logged_error='',
        cloud_last_error_log_monotonic=0, config_page=config,
        gallery=SimpleNamespace(set_cloud_status=lambda *v: None),
        cloud_message_timer=SimpleNamespace(setInterval=lambda v: None),
    )
    window.cloud_message_finished = SimpleNamespace(
        emit=lambda *v: app.VideoArchiveWindow._cloud_message_finished(window, *v)
    )
    app.VideoArchiveWindow._cloud_message_worker(window, 'https://example.test')
    assert window.cloud_message_running is False
    assert window.cloud_status == 'OFFLINE'
    assert window.cloud_error == 'interrupted'


@pytest.mark.parametrize('ready_first', [True, False])
def test_playback_waits_paused_then_reveals_unmutes_and_plays(qapp, ready_first):
    calls = []
    window = SimpleNamespace(
        mode='loading', playback_generation=3, mpv_ready=False, transition_minimum_elapsed=False,
        playback_watchdog=SimpleNamespace(stop=lambda: calls.append('watchdog stopped')),
        playback_page=SimpleNamespace(hide_transition=lambda: calls.append('reveal')),
        player=SimpleNamespace(unmute=lambda: calls.append('unmute'), play=lambda: calls.append('play')),
    )
    window._maybe_start_video = lambda: app.VideoArchiveWindow._maybe_start_video(window)
    window._maybe_reveal_video = lambda g: app.VideoArchiveWindow._maybe_reveal_video(window, g)
    ready = lambda: app.VideoArchiveWindow._mpv_ready(window, 3)
    minimum = lambda: app.VideoArchiveWindow._transition_minimum_elapsed(window)
    first, second = (ready, minimum) if ready_first else (minimum, ready)
    first()
    assert calls == []
    second()
    assert calls == ['watchdog stopped', 'reveal', 'unmute', 'play']
    assert window.mode == 'playing'
    ready()
    assert calls.count('play') == 1


def test_stale_reveal_cannot_start_a_new_video(qapp):
    window = SimpleNamespace(playback_generation=2, mode='loading')
    app.VideoArchiveWindow._maybe_reveal_video(window, 1)
    assert window.mode == 'loading'


@pytest.mark.parametrize('mode', ['loading', 'playing'])
def test_eof_returns_even_for_a_tiny_video(qapp, mode):
    returned = []
    window = SimpleNamespace(mode=mode, playback_generation=4, _begin_return=lambda: returned.append(True))
    app.VideoArchiveWindow._video_ended(window, 3)
    assert returned == []
    app.VideoArchiveWindow._video_ended(window, 4)
    assert returned == [True]


@pytest.mark.parametrize('termination', ['closed', 'socket_error', 'decoder_error', 'eof', 'cancel'])
def test_player_reports_terminal_events_once(monkeypatch, tmp_path, termination):
    controller = player.MpvController()
    controller.log_path = tmp_path / 'mpv.log'
    notifications = []
    controller.ready.connect(lambda g: notifications.append(('ready', g)))
    controller.failed.connect(lambda g, message: notifications.append(('failed', g)))
    controller.ended.connect(lambda g: notifications.append(('ended', g)))
    messages = [{'event': 'file-loaded'}, {'event': 'playback-restart'}]
    if termination == 'decoder_error':
        messages.append({'event': 'end-file', 'reason': 'error', 'file_error': 'broken frame'})
    elif termination == 'eof':
        messages.extend([{'event': 'property-change', 'name': 'eof-reached', 'data': True},
                         {'event': 'end-file', 'reason': 'eof'}])
    chunks = [b''.join((json.dumps(m) + '\n').encode() for m in messages)]
    commands = []

    class Socket:
        def __init__(self, *args): pass
        def connect(self, path): pass
        def sendall(self, payload): commands.append(json.loads(payload)['command'])
        def close(self): pass
        def recv(self, size):
            if chunks: return chunks.pop()
            if termination == 'socket_error': raise OSError('lost connection')
            if termination == 'cancel': controller._generation += 1
            return b''

    monkeypatch.setattr(player.socket, 'socket', Socket)
    monkeypatch.setattr(player.os.path, 'exists', lambda path: True)
    controller._ipc_reader(0, 5, SimpleNamespace(poll=lambda: None), '/tmp/fake.sock', tmp_path / 'clip.mp4')
    assert commands == [['observe_property', 1, 'eof-reached'],
                        ['loadfile', str(tmp_path / 'clip.mp4'), 'replace']]
    expected = [('ready', 5)]
    if termination != 'cancel': expected.append(('ended' if termination == 'eof' else 'failed', 5))
    assert notifications == expected


@pytest.mark.parametrize('setting,expected', [(0, 0), (70, 105), (80, 120), (100, 150)])
def test_video_volume_preserves_master_boost(setting, expected):
    controller = player.MpvController()
    commands = []
    controller.command = commands.append
    controller.set_volume(app.mpv_volume_from_setting(setting))
    assert commands == [['set_property', 'volume-max', 150], ['set_property', 'volume', expected]]
