import os,sys,time,subprocess
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,'/home/pi/app/src')
from PySide6.QtWidgets import QApplication
from video_archive import player
app=QApplication([])
c=player.MpvController();c.log_path=Path('/tmp/ship-review/mpv-headless.log');c.socket_path='/tmp/ship-review/mpv.sock'
real_popen=subprocess.Popen
seen=[]
def spawn(args,**kw):
 args=[arg for arg in args if not arg.startswith(('--wid=','--ao=','--audio-device='))]+['--vo=null','--ao=null']
 return real_popen(args,**kw)
def ready(g):
 seen.append(('ready',g));c.unmute();c.play();c.command(['seek',16,'absolute'])
c.ready.connect(ready);c.ended.connect(lambda g:seen.append(('ended',g)));c.failed.connect(lambda g,s:seen.append(('failed',g,s)))
with patch.object(player.subprocess,'Popen',spawn):
 c.preload('/home/pi/app/normalized_videos/REAGAN.mp4',0,50,101)
 deadline=time.monotonic()+12
 while time.monotonic()<deadline and not any(e[0] in ('ended','failed') for e in seen):
  app.processEvents();time.sleep(.01)
 c.stop(silent=True)
print('real_mpv_headless_signals',seen)
print('cleaned_up',c.process is None and not Path(c.socket_path).exists())
