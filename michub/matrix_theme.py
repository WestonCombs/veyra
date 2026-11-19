"""Matrix-inspired native styling and scrollable preferences."""
import tkinter as tk
from tkinter import ttk
BG='#050b08';PANEL='#0b1c12';TEXT='#e1f8e8';MUTED='#8aaa96';GREEN='#68ff8c';EDGE='#214c32'

def apply(app):
 s=app.style
 app.root.option_add('*TCombobox*Listbox.background',PANEL)
 app.root.option_add('*TCombobox*Listbox.foreground',TEXT)
 app.root.option_add('*TCombobox*Listbox.selectBackground','#245b38')
 app.root.option_add('*TCombobox*Listbox.selectForeground','#ffffff')
 for name in ['TFrame','TLabel','TCheckbutton','TNotebook','TNotebook.Tab']:
  s.configure(name,background=BG,foreground=TEXT,font=('Segoe UI',11),borderwidth=0)
 s.configure('TNotebook',tabmargins=0,borderwidth=0,lightcolor=BG,darkcolor=BG,bordercolor=BG);s.layout('TNotebook',[('Notebook.client',{'sticky':'nswe'})])
 s.layout('TNotebook.Tab',[])
 s.configure('TEntry',fieldbackground=PANEL,foreground=TEXT,insertcolor=GREEN,bordercolor=EDGE,lightcolor=EDGE,darkcolor=EDGE,padding=12)
 s.map('TEntry',bordercolor=[('focus',GREEN)])
 s.configure('TCombobox',fieldbackground=PANEL,background=PANEL,foreground=TEXT,arrowcolor=GREEN,bordercolor=EDGE,lightcolor=EDGE,darkcolor=EDGE,padding=10)
 s.map('TCombobox',fieldbackground=[('readonly',PANEL),('active','#173724')],background=[('active','#173724'),('readonly',PANEL)],foreground=[('disabled',MUTED),('readonly',TEXT),('active',TEXT)],selectbackground=[('readonly',PANEL)],selectforeground=[('readonly',TEXT)],bordercolor=[('focus',GREEN),('active',GREEN)])
 from PIL import Image,ImageDraw,ImageTk
 images=[]
 for checked,hovered in [(False,False),(True,False),(False,True),(True,True)]:
  image=Image.new('RGBA',(136,96),(0,0,0,0));draw=ImageDraw.Draw(image)
  draw.rounded_rectangle((4,4,88,88),radius=9,fill=PANEL,outline=GREEN if hovered else '#66a57b',width=7)
  if checked:draw.rounded_rectangle((23,23,69,69),radius=3,fill='#7aff9b' if hovered else '#4dd477')
  images.append(ImageTk.PhotoImage(image.resize((34,24),Image.Resampling.LANCZOS)))
 app.checkbox_images=images
 if 'Veyra.Check.indicator' not in s.element_names():s.element_create('Veyra.Check.indicator','image',images[0],('selected','active',images[3]),('selected',images[1]),('active',images[2]),sticky='w')
 s.layout('TCheckbutton',[('Checkbutton.padding',{'sticky':'nswe','children':[('Veyra.Check.indicator',{'side':'left','sticky':'w'}),('Checkbutton.label',{'side':'left','sticky':'nswe'})]})])
 s.configure('TCheckbutton',padding=8,indicatorbackground=PANEL,indicatorforeground=GREEN,bordercolor=EDGE)
 s.map('TCheckbutton',background=[('active','#102d1c'),('selected',BG)],foreground=[('disabled',MUTED),('active','#ffffff'),('selected',TEXT)],indicatorbackground=[('selected','#297342'),('active','#1d4c2e')],indicatorforeground=[('selected','#c5ffcf')])
 s.configure('TProgressbar',background=GREEN,troughcolor=PANEL,bordercolor=PANEL,lightcolor=GREEN,darkcolor=GREEN,thickness=5)
 s.configure('Horizontal.TScale',background=BG,troughcolor=PANEL,bordercolor=EDGE,sliderlength=22)
 s.map('Horizontal.TScale',background=[('active','#32864a')])
 s.configure('Vertical.TScrollbar',background=EDGE,troughcolor=BG,arrowcolor=GREEN,borderwidth=0)
 s.map('Vertical.TScrollbar',background=[('active','#3b8453')])
 # Custom navigation avoids platform-specific tab hover and grey borders.
 nav=tk.Frame(app.tabs.master,bg=BG);nav.pack(fill='x',before=app.tabs,pady=(22,0))
 buttons=[]
 def select(index):
  app.tabs.select(index)
  for i,b in enumerate(buttons):b.configure(bg='#173c25' if i==index else BG,fg=GREEN if i==index else MUTED,highlightbackground=GREEN if i==index else BG)
 for i,name in enumerate(['DASHBOARD','SETTINGS']):
  b=tk.Button(nav,text=name,command=lambda n=i:select(n),bg=BG,fg=MUTED,font=('Consolas',11,'bold'),relief='flat',bd=0,padx=23,pady=13,highlightthickness=1,highlightbackground=BG,activebackground='#20482c',activeforeground='#ffffff',cursor='hand2')
  b.pack(side='left',padx=(0,10));buttons.append(b)
 app.nav_buttons=buttons
 app.tabs.pack_configure(pady=(12,0));select(0)
 app.big.configure(bd=0,activebackground='#9bffad',activeforeground=BG,highlightthickness=3,highlightbackground='#235535',font=('Consolas',21,'bold'))
 # Native dark caption on supported Windows versions.
 try:
  import ctypes
  app.root.update_idletasks();hwnd=ctypes.windll.user32.GetParent(app.root.winfo_id());value=ctypes.c_int(1)
  ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd,20,ctypes.byref(value),4)
 except Exception:pass

def animate_navigation(app,phase):
 selected=app.tabs.index(app.tabs.select())
 fill=f'#{int(15+phase*12):02x}{int(41+phase*40):02x}{int(24+phase*20):02x}'
 edge=f'#{int(30+phase*22):02x}{int(82+phase*70):02x}{int(45+phase*30):02x}'
 for i,button in enumerate(app.nav_buttons):
  active=i==selected
  button.configure(bg=fill if active else BG,activebackground=fill if active else '#142d1d',fg=GREEN if active else MUTED,activeforeground=GREEN if active else TEXT,highlightbackground=edge if active else BG,highlightcolor=edge if active else BG)

class ScrollPage(ttk.Frame):
 def __init__(self,parent):
  super().__init__(parent)
  canvas=tk.Canvas(self,bg=BG,highlightthickness=0,bd=0)
  bar=ttk.Scrollbar(self,orient='vertical',command=canvas.yview)
  bar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True);canvas.configure(yscrollcommand=bar.set)
  self.body=tk.Frame(canvas,bg=BG,padx=24,pady=24);window=canvas.create_window((0,0),window=self.body,anchor='nw')
  self.body.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
  canvas.bind('<Configure>',lambda e:canvas.itemconfigure(window,width=e.width))
  def wheel(e):
   if self.winfo_ismapped():canvas.yview_scroll(-int(e.delta/120),'units')
  self.bind_all('<MouseWheel>',wheel,add='+')
