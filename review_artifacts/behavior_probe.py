import os,sys,json,tempfile
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path[:0]=['/home/pi/app/src','/home/pi/app']
from video_archive import app,display,cloud
from tools import normalize_videos as norm
from PySide6.QtWidgets import QApplication
q=QApplication([])
class LED:
 value=0
 def close(self):pass
led=LED()
with patch.object(display.DisplayController,'apply_brightness',return_value=True):
 d=display.DisplayController(led=led,led_brightness=50,sleep_led_brightness=5)
 d.sleep();print('sleep_LED: requested=5%, actual=',led.value*100)
 for value in [0,5,100]:
  d.set_sleep_led_brightness(value);print('sleep_LED requested=',value,'actual=',led.value*100)
# Read-only settings migration reproduction.
with tempfile.TemporaryDirectory() as temp:
 f=Path(temp)/'settings.json';f.write_text('{"sleep_brightness":20}')
 with patch.object(app,'SETTINGS_FILE',f):print('legacy sleep brightness 20 migrated to',app.load_settings()['sleep_led_brightness'])
# A failed encoder leaves a file which a retry treats as success.
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp);src=root/'input';dest=root/'output';src.mkdir();dest.mkdir();(src/'test.mov').write_bytes(b'source')
 args=S(input_dir=src,output_dir=dest,width=1024,height=576,video_bitrate='2500k',audio_bitrate='160k',fps=30,force=False,dry_run=False)
 calls=[]
 def failed_encoder(command,**kw):
  calls.append(command);Path(command[-1]).write_bytes(b'incomplete mp4');return S(returncode=1)
 with patch.object(norm,'detect_padded_landscape_crop',return_value=None),patch.object(norm.subprocess,'run',failed_encoder):
  first=norm.normalize_videos(args);second=norm.normalize_videos(args)
 print('normalization first=',first,'retry=',second,'encoder calls=',len(calls),'leftover bytes=',(dest/'test.mp4').read_bytes())
# Renamed connection profile shown as network name.
captured=[]
results=[S(returncode=0,stdout='wlan0:wifi:connected:Saved home profile\n'),S(returncode=0,stdout='IP4.ADDRESS[1]:192.0.2.1/24\n')]
with patch.object(app.subprocess,'run',side_effect=results):
 app.VideoArchiveWindow._wifi_status_worker(S(wifi_status_finished=S(emit=captured.append)))
print('wifi current derived from profile name:',captured)
