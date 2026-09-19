import os,sys,json,random
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_FONT_DPI']='96'
sys.path.insert(0,'/home/pi/app/src')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter
from PySide6.QtCore import QRect,Qt
from video_archive import ui
app=QApplication([])
out='/tmp/ship-review'
w=ui.ConfigWidget('Long note '*300,'','',[],80,True,True,True,80,50,5,5)
w.resize(1024,600)
w.flicker_timer.stop()
shots=[]
class Recorder:
 def __init__(self,p): self.p=p;self.overflows=[]
 def __getattr__(self,k):return getattr(self.p,k)
 def drawText(self,*args):
  if len(args)>=3 and isinstance(args[0],QRect):
   rect,flags,text=args[:3]
   bounds=self.p.fontMetrics().boundingRect(rect,flags,text)
   if bounds.width()>rect.width()+2 or bounds.height()>rect.height()+2:
    self.overflows.append({'text':text,'rect':rect.getRect(),'bounds':bounds.getRect(),'font':self.p.font().pointSize()})
  return self.p.drawText(*args)
def snap(name, renderer=None):
 img=QImage(1024,600,QImage.Format_ARGB32); img.fill(Qt.black)
 p=QPainter(img);w._draw_shell(p);r=Recorder(p)
 (renderer or w.settings_renderer).draw(r,w)
 p.end();img.save(f'{out}/{name}.png');shots.append(name)
 if r.overflows:print(name,json.dumps(r.overflows))
for section,n in [(None,7),('sounds',4),('display',7)]:
 for index in range(n):
  w.show_settings_home();w.settings_section=section;w.selected_index=index
  w.set_wifi_current({'ssid':'ABCDEFGHIJKLMNOPQRSTUVWXYZ123456','device':'wlan0','ip':'192.168.1.100'})
  snap(f'{section or "settings"}-{index}')
w.showing_admin=True;w.admin_index=1;w.admin_status='SELECT AGAIN TO CONFIRM';w.admin_confirm_action='RESET WIFI';snap('admin-reset',w.admin_renderer)
w.admin_status='Error: Connection deletion failed: Not authorized to perform this operation.';snap('admin-error',w.admin_renderer)
w.showing_wifi=True
w.set_wifi_networks([{'ssid':'ABCDEFGHIJKLMNOPQRSTUVWXYZ123456','security':'WPA2','saved':True,'signal':'100','profile_uuids':['test']}])
for stage in ['networks','saved','password']:
 w.wifi_stage=stage;w.wifi_password='test PASSWORD'*5;snap('wifi-'+stage,w.wifi_renderer)
w.show_memos_home();w.set_memos([{'id':'1','date':'2026-09-19 10:00','message':'This is a long memo. '*80,'name':'Test author'}]);w.memo_reading=True
snap('memo-reader',w.memo_renderer)
w.memo_scroll=w.memo_max_scroll;snap('memo-end',w.memo_renderer)
# Use the actual QWidget paint path too.
for name,widget in [('home',ui.HomeWidget(100)),('gallery',ui.GalleryWidget(['A','B','very long name '*10],2)),('sleep',ui.AmbientSleepWidget('clock'))]:
 widget.resize(1024,600);widget.grab().save(f'{out}/{name}.png')
# Long navigation sequences exercise all renderer/controller paths, without external actions.
errors=[];sys.excepthook=lambda *args: errors.append(str(args[1]))
random.seed(55)
for start in ['settings','memos','wifi']:
 w.show_settings_home()
 if start=='memos': w.show_memos_home()
 if start=='wifi': w.showing_wifi=True;w.wifi_stage='networks'
 for i in range(2000):
  random.choice([w.move_left,w.move_right,w.select])()
  w.grab()
print('navigation_paint_exceptions',errors)
