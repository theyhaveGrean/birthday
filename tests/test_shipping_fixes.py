"""Behavioral regressions for requested review fixes (1024 x 600 target)."""
import json
import subprocess
from datetime import datetime, timezone
from types import SimpleNamespace as S

import pytest
from PySide6.QtGui import QFont, QFontMetrics

from video_archive import app, cloud, timestamps, ui


def config():
    return ui.ConfigWidget('', '', '', [], 30, True, True, True, 35, 15, 5, 1)


def signal_into(events):
    return S(emit=lambda *values: events.append(values))


@pytest.fixture
def cache(monkeypatch, tmp_path):
    for name in ('CLOUD_MEMOS_FILE', 'CLOUD_MESSAGE_FILE', 'CLOUD_MESSAGE_META_FILE', 'READ_MEMOS_FILE'):
        monkeypatch.setattr(cloud, name, tmp_path / name)
    return tmp_path


def row(id, day, message=None):
    return {'id': str(id), 'message': message or str(id),
            'created_at': f'2026-09-{day:02}T18:00:00+00:00'}


@pytest.mark.parametrize('handler', ['_physical_select', '_physical_select_held', '_physical_left', '_physical_right'])
def test_first_sleeping_button_wakes_without_action(qapp, handler):
    widget = config()
    widget.selected_index = 5
    widget.confirming_reboot = True
    events = []
    widget.reboot_requested.connect(lambda: events.append('reboot'))
    display = S(sleeping=True)
    def wake():
        display.sleeping = False
    display.wake = wake
    window = S(mode='config', config_page=widget, display=display,
               _resume_visible_effects=lambda: events.append('resume'),
               _restart_display_sleep_timer=lambda: events.append('timer'),
               audio=S(play=lambda x: events.append('sound')),
               go_home=lambda: events.append('home'),
               _start_admin_chord_if_ready=lambda: events.append('chord'))
    window._note_activity = lambda: app.VideoArchiveWindow._note_activity(window)
    getattr(app.VideoArchiveWindow, handler)(window)
    assert not display.sleeping
    assert events == ['resume', 'timer']
    if handler == '_physical_left':
        assert window.left_button_down
        window.admin_chord_timer=S(stop=lambda:None)
        app.VideoArchiveWindow._physical_left_released(window)
        assert not window.left_button_down
    if handler == '_physical_select':
        # A subsequent awake press retains the ordinary input semantics.
        app.VideoArchiveWindow._physical_select(window)
        assert 'reboot' in events


def test_sleep_cancels_confirmations_before_next_interaction(qapp):
    widget = config()
    widget.confirming_reboot = True
    widget.admin_confirm_action = 'RESET MEMOS'
    widget.admin_status = 'SELECT AGAIN TO CONFIRM'
    window = S(mode='config', config_page=widget, display=S(sleep=lambda:None),
               _pause_visible_effects=lambda:None, unread_memos=0,
               settings={'screensaver_mode':'clock'},
               ambient_sleep=S(set_unread_memo_count=lambda n:None,set_mode=lambda s:None,start=lambda:None),
               pages=S(setCurrentWidget=lambda w:None))
    app.VideoArchiveWindow._sleep_display(window)
    assert not widget.confirming_reboot
    assert widget.admin_confirm_action == widget.admin_status == ''


def test_empty_and_partial_remote_results_preserve_archive_and_read_state(cache):
    cloud._sync_supabase_notes([row('b', 18), row('a', 17)])
    cloud.mark_memo_read(cloud.load_memos()[1])
    cloud._sync_supabase_notes([])
    assert [m['id'] for m in cloud.load_memos()] == ['b', 'a']
    assert cloud.load_cached_message() == ''
    assert cloud.load_read_memo_keys() == {'a'}
    cloud._sync_supabase_notes([row('c', 19), row('b', 18, 'edited')])
    memos = cloud.load_memos()
    assert [m['id'] for m in memos] == ['c', 'b', 'a']
    assert memos[1]['message'] == 'edited'
    assert cloud.load_read_memo_keys() == {'a'}
    cloud._sync_supabase_notes([row('b', 18, 'edited')])
    assert len(cloud.load_memos()) == 3


def test_archive_retains_existing_100_entry_limit_without_cache_resurrection(cache, monkeypatch):
    monkeypatch.setattr(cloud, 'MAX_MEMOS', 2)
    cloud._sync_supabase_notes([row('new', 20), row('middle', 19)])
    cloud._sync_supabase_notes([row('old', 1)])
    assert [m['id'] for m in cloud.load_memos()] == ['new', 'middle']
    assert len(json.loads(cloud.CLOUD_MEMOS_FILE.read_text())) == 2


def test_legacy_cache_still_migrates_once(cache):
    cloud.save_cached_message('legacy', '2026-09-18 10:00')
    first = cloud.load_memos()
    assert len(first) == 1
    assert cloud.load_memos() == first


@pytest.mark.parametrize('zone,expected', [('America/Los_Angeles', '2026-09-18 11:00'),
                                         ('America/New_York', '2026-09-18 14:00'),
                                         ('UTC', '2026-09-18 18:00')])
def test_clock_cache_and_memo_use_one_timezone(cache, monkeypatch, zone, expected):
    monkeypatch.setenv('VIDEO_ARCHIVE_TIMEZONE', zone)
    cloud._sync_supabase_notes([row('a', 18)])
    memo = cloud.load_memos()[0]
    assert memo['date'] == expected
    assert cloud.load_cached_message_date() == expected
    assert ui.memo_date_parts(memo['created_at']) == tuple(expected.split())
    assert str(ui.current_clock_time().tzinfo) == zone
    stored = json.loads(cloud.CLOUD_MEMOS_FILE.read_text())[0]
    assert stored['created_at'] == '2026-09-18T18:00:00+00:00'


def test_cached_memos_reformat_on_timezone_change_without_changing_read_identity(cache, monkeypatch):
    monkeypatch.setenv('VIDEO_ARCHIVE_TIMEZONE', 'UTC')
    cloud._sync_supabase_notes([row('a', 18)])
    cloud.mark_memo_read(cloud.load_memos()[0])
    monkeypatch.setenv('VIDEO_ARCHIVE_TIMEZONE', 'America/Los_Angeles')
    assert cloud.load_memos()[0]['date'] == '2026-09-18 11:00'
    assert cloud.load_cached_message_date() == '2026-09-18 11:00'
    assert cloud.unread_memo_count(cloud.load_memos()) == 0


def test_legacy_wall_dates_and_read_keys_are_not_reinterpreted(cache, monkeypatch):
    legacy = {'date':'2026-09-18 10:23', 'message':'legacy'}
    key = cloud._legacy_memo_key(legacy)
    cloud.CLOUD_MEMOS_FILE.write_text(json.dumps([legacy]))
    cloud.READ_MEMOS_FILE.write_text(json.dumps([key]))
    monkeypatch.setenv('VIDEO_ARCHIVE_TIMEZONE', 'America/New_York')
    memo = cloud.load_memos()[0]
    assert memo['date'] == legacy['date']
    assert memo['id'] == key
    assert cloud.unread_memo_count([memo]) == 0


def test_invalid_timezone_falls_back_consistently(cache, monkeypatch):
    monkeypatch.setenv('VIDEO_ARCHIVE_TIMEZONE', 'not/a/zone')
    cloud._sync_supabase_notes([row('a', 18)])
    assert str(ui.current_clock_time().tzinfo) == 'UTC'
    assert cloud.load_memos()[0]['date'] == '2026-09-18 18:00'


@pytest.mark.parametrize('saved', [False, True])
def test_connection_workers_allow_nmcli_full_wait_and_keep_password_off_argv(monkeypatch, saved):
    events, calls = [], []
    profiles = [{'ssid':' Home ', 'uuid':'uuid'}]
    monkeypatch.setattr(app, '_profiles_after_wifi_change', lambda: profiles)
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return S(returncode=0, stdout='', stderr='')
    monkeypatch.setattr(app.subprocess, 'run', run)
    w = S(wifi_connect_finished=signal_into(events))
    if saved:
        app.VideoArchiveWindow._connect_saved_wifi_worker(w, ['uuid'])
    else:
        app.VideoArchiveWindow._connect_wifi_worker(w, ' Home ', 'secret password')
        assert calls[0][1]['input'] == 'secret password\n'
        assert 'secret password' not in calls[0][0]
        assert calls[0][0][-1] == ' Home '
    command, kwargs = calls[0]
    wait = int(command[command.index('--wait')+1])
    assert wait == 90 and kwargs['timeout'] > wait
    assert events == [(True, 'connected', profiles)]


@pytest.mark.parametrize('saved', [False, True])
@pytest.mark.parametrize('late_success', [False, True])
def test_outer_timeout_reconciles_connection_before_reporting_failure(monkeypatch, saved, late_success):
    events, queries = [], []
    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs['timeout'])
    monkeypatch.setattr(app.subprocess, 'run', run)
    monkeypatch.setattr(app, '_profiles_after_wifi_change', lambda: [])
    monkeypatch.setattr(app, '_wifi_activation_succeeded', lambda **kw: queries.append(kw) or late_success)
    w = S(wifi_connect_finished=signal_into(events))
    if saved:
        app.VideoArchiveWindow._connect_saved_wifi_worker(w, ['uuid'])
        assert queries == [{'profile_uuid':'uuid'}]
    else:
        app.VideoArchiveWindow._connect_wifi_worker(w, 'Home', 'password')
        assert queries == [{'ssid':'Home'}]
    assert len(events) == 1 and events[0][0] is late_success
    if not late_success:
        assert 'timed out' in events[0][1]


@pytest.mark.parametrize('saved', [False, True])
def test_nmcli_timeout_exit_also_reconciles(monkeypatch, saved):
    events = []
    monkeypatch.setattr(app.subprocess, 'run', lambda *a, **kw:S(returncode=3, stdout='', stderr='timeout'))
    monkeypatch.setattr(app, '_wifi_activation_succeeded', lambda **kw: True)
    monkeypatch.setattr(app, '_profiles_after_wifi_change', lambda: [])
    w = S(wifi_connect_finished=signal_into(events))
    if saved:
        app.VideoArchiveWindow._connect_saved_wifi_worker(w, ['uuid'])
    else:
        app.VideoArchiveWindow._connect_wifi_worker(w, 'Home', 'password')
    assert events == [(True, 'connected', [])]


@pytest.mark.parametrize('target,expected', [(' Home ', True), ('Home', False)])
def test_timeout_reconciliation_matches_exact_active_ssid(monkeypatch, target, expected):
    outputs = iter(['wlan0:wifi:connected\n', 'uuid\n', '802-11-wireless.ssid: Home \n'])
    monkeypatch.setattr(app.subprocess, 'run', lambda *a, **kw:S(returncode=0, stdout=next(outputs)))
    assert app._wifi_activation_succeeded(ssid=target) is expected


def test_scan_preserves_whitespace_and_escaped_ssids(monkeypatch):
    events=[]
    monkeypatch.setattr(app, '_load_wifi_profiles', lambda:[{'ssid':' Home ', 'uuid':'u'}])
    def run(command, **kwargs):
        return S(returncode=0, stdout=' Home :WPA2:80\nHome:WPA2:70\nA\\:B:WPA2:60\n:--:50\n', stderr='')
    monkeypatch.setattr(app.subprocess, 'run', run)
    app.VideoArchiveWindow._scan_wifi_worker(S(wifi_scan_finished=signal_into(events)))
    networks,error = events[0]
    assert not error
    assert [n['ssid'] for n in networks] == [' Home ', 'Home', 'A:B']
    assert networks[0]['profile_uuids'] == ['u']
    assert not networks[1]['saved']


def test_rejected_rescan_preserves_networks_selection_and_session(qapp):
    widget=config();widget.showing_wifi=True
    widget.set_wifi_networks([{'ssid':'A','security':'WPA2'}])
    widget.wifi_selected_index=1
    session=widget.wifi_session
    window=S(config_page=widget, wifi_scan_running=False, _wifi_busy=lambda **kw:True,
             _refresh_wifi_status=lambda:None)
    widget.wifi_scan_requested.connect(lambda:app.VideoArchiveWindow._scan_wifi(window))
    widget.select()
    assert widget.wifi_networks[0]['ssid']=='A'
    assert widget.wifi_selected_index==1 and widget.wifi_session==session
    assert 'busy' in widget.wifi_status


def test_accepted_scan_starts_one_session_and_clears_only_after_acceptance(qapp, monkeypatch):
    widget=config();widget.selected_index=1
    started=[]
    monkeypatch.setattr(app.threading,'Thread',lambda **kw:S(start=lambda:started.append(True)))
    window=S(config_page=widget,wifi_scan_running=False,_wifi_busy=lambda **kw:False,
             _refresh_wifi_status=lambda:None,_scan_wifi_worker=lambda:None)
    widget.wifi_scan_requested.connect(lambda:app.VideoArchiveWindow._scan_wifi(window))
    session=widget.wifi_session
    widget.select()
    assert widget.wifi_session==session+1
    assert window.wifi_scan_running and started==[True]


def connected_window(widget):
    return S(mode='config', config_page=widget, wifi_connect_running=True,
             wifi_connect_context=widget.wifi_session, settings={},
             _refresh_wifi_status=lambda:None, _maybe_start_pending_wifi_reset=lambda:None)


def test_connect_success_immediately_exposes_saved_profile_actions(qapp):
    widget=config();widget.showing_wifi=True
    widget.set_wifi_networks([{'ssid':'Home','security':'WPA2','saved':False}])
    widget.select();widget.wifi_password='secret'
    window=connected_window(widget)
    app.VideoArchiveWindow._wifi_connect_finished(window,True,'connected',[{'ssid':'Home','uuid':'u'}])
    assert widget.wifi_password=='' and widget.wifi_stage=='networks'
    widget.select()
    assert widget.wifi_stage=='saved'
    events=[];widget.wifi_connect_saved_requested.connect(events.append)
    widget.select()
    assert events==[['u']]


@pytest.mark.parametrize('success', [True,False])
def test_forget_completion_preserves_another_network_editor(qapp, success):
    widget=config();widget.showing_wifi=True
    widget.set_wifi_networks([{'ssid':'A','security':'WPA2','saved':True,'profile_uuids':['a']},
                              {'ssid':'B','security':'WPA2','saved':False}])
    widget.select();old_session=widget.wifi_session
    widget.wifi_saved_action_index=2;widget.select()
    widget.wifi_selected_index=1;widget.select();widget.wifi_password='in progress'
    widget.wifi_key_row=2;widget.wifi_key_col=4
    status=widget.wifi_status
    window=S(mode='config',config_page=widget,wifi_forget_running=True,wifi_forget_context=old_session,
             _refresh_wifi_status=lambda:None,_maybe_start_pending_wifi_reset=lambda:None)
    profiles=[] if success else [{'ssid':'A','uuid':'a'}]
    app.VideoArchiveWindow._wifi_forget_finished(window,success,'done' if success else 'forget failed',profiles)
    assert widget.wifi_stage=='password' and widget.wifi_selected_index==1
    assert widget.wifi_password=='in progress'
    assert (widget.wifi_key_row,widget.wifi_key_col)==(2,4)
    assert widget.wifi_status==status


def test_forget_failure_remains_visible_in_original_editor(qapp):
    widget=config();widget.showing_wifi=True
    widget.set_wifi_networks([{'ssid':'A','security':'WPA2','saved':True,'profile_uuids':['a']}])
    widget.select()
    window=S(mode='config',config_page=widget,wifi_forget_running=True,wifi_forget_context=widget.wifi_session,
             _refresh_wifi_status=lambda:None,_maybe_start_pending_wifi_reset=lambda:None)
    app.VideoArchiveWindow._wifi_forget_finished(window,False,'forget failed // permission denied',[{'ssid':'A','uuid':'a'}])
    assert widget.wifi_stage=='saved'
    assert widget.wifi_status=='forget failed // permission denied'


def test_forget_success_clears_only_removed_profile_metadata(qapp):
    widget=config();widget.showing_wifi=True
    widget.set_wifi_networks([{'ssid':'A','security':'WPA2','saved':True,'profile_uuids':['a']}])
    widget.select()
    window=S(mode='config',config_page=widget,wifi_forget_running=True,wifi_forget_context=widget.wifi_session,
             _refresh_wifi_status=lambda:None,_maybe_start_pending_wifi_reset=lambda:None)
    app.VideoArchiveWindow._wifi_forget_finished(window,True,'profile forgotten',[])
    assert widget.wifi_stage=='networks'
    assert not widget.wifi_networks[0]['saved']
    assert widget.wifi_status=='profile forgotten'


def test_profile_refresh_failure_does_not_fabricate_unsaved_metadata(monkeypatch):
    monkeypatch.setattr(app.subprocess,'run',lambda *a, **kw:S(returncode=1,stdout='',stderr='permission denied'))
    assert app._profiles_after_wifi_change() is None


@pytest.mark.parametrize('title', ['GRADUATION.mp4', 'A_VERY_LONG_BIRTHDAY_VIDEO_FILENAME.mp4', 'X'*200+'.mp4'])
def test_gallery_detail_title_is_bounded_at_1024x600(qapp,title):
    metrics=QFontMetrics(QFont(ui.FONT_FAMILY,18,QFont.Bold))
    lines=ui.gallery_title_lines(title,metrics,509)
    assert 1<=len(lines)<=2
    assert all(metrics.horizontalAdvance(line)<=509 for line in lines)
    assert len(lines)*metrics.lineSpacing()<=68


def test_unsynced_timestamp_does_not_become_a_misleading_date():
    assert timestamps.format_stored_timestamp('1970-01-01T00:00:00+00:00') == 'TIME UNSYNCED'


def test_forget_partial_failure_reports_error_and_refreshes_metadata(monkeypatch):
    events=[]
    responses=iter([S(returncode=0,stdout='',stderr=''),S(returncode=1,stdout='',stderr='')])
    monkeypatch.setattr(app.subprocess,'run',lambda *a,**kw:next(responses))
    monkeypatch.setattr(app,'_profiles_after_wifi_change',lambda:[{'ssid':'A','uuid':'a2'}])
    app.VideoArchiveWindow._forget_wifi_worker(S(wifi_forget_finished=signal_into(events)),['a1','a2'])
    assert len(events)==1 and events[0][0] is False
    assert 'incomplete' in events[0][1]
    assert events[0][2]==[{'ssid':'A','uuid':'a2'}]
