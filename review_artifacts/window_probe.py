import os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace as S
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,'/home/pi/app/src')
from PySide6.QtCore import QObject,Signal
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from video_archive import app as a
q=QApplication([])
class Input(QObject):
 left_pressed=Signal();left_released=Signal();right_pressed=Signal();right_released=Signal();select_pressed=Signal();select_held=Signal()
 def close(self):pass
class Player(QObject):
 ready=Signal(int);ended=Signal(int);failed=Signal(int,str)
 def __getattr__(self,n):return lambda *x,**kw:None
class Audio:
 def __init__(self,**kw):pass
 def __getattr__(self,n):return lambda *x,**kw:None
class Display:
 def __init__(self,*args,**kw):self.sleeping=False
 def sleep(self):self.sleeping=True
 def wake(self):self.sleeping=False
 def close(self):pass
 def __getattr__(self,n):return lambda *x,**kw:None
errors=[];sys.excepthook=lambda *args:errors.append(str(args[1]))
with patch.multiple(a,InputController=Input,MpvController=Player,AudioController=Audio,DisplayController=Display,load_settings=lambda:dict(a.DEFAULT_SETTINGS),load_note=lambda:'test note',load_memos=lambda:[],load_cached_message=lambda:'',load_cached_message_date=lambda:'',unread_memo_count=lambda m:0,load_read_memo_keys=lambda:set()),patch.object(a.threading,'Thread',lambda *args,**kw:S(start=lambda:None)):
 w=a.VideoArchiveWindow();w.resize(1024,600);w.show();w.start_screen._finish_boot();w._physical_select()
 assert w.mode=='home'
 w._physical_select();assert w.mode=='gallery'
 w._physical_select();assert w.mode=='loading'
 w.player.ready.emit(w.playback_generation);w._transition_minimum_elapsed();assert w.mode=='playing'
 w._physical_select();assert w.mode=='returning';QTest.qWait(400);assert w.mode=='gallery'
 w._physical_select();assert w.mode=='loading';w._physical_select_held();QTest.qWait(400);assert w.mode=='home'
 w.home.selected_index=2;w._physical_select();assert w.mode=='config'
 w._sleep_display();assert w.display.sleeping
 prev=w.config_page.selected_index;w._physical_right();assert not w.display.sleeping and w.config_page.selected_index==prev
 w._physical_right();assert w.config_page.selected_index==prev+1
 w._physical_select_held();assert w.mode=='home'
 w.close()
print('window_flow_checks PASS: boot, home, gallery, preload, reveal, return, loading cancel to Home, settings, sleep/wake input consumption, global Home')
print('window Qt exceptions',errors)
