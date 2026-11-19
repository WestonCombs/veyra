"""Window-contained dialogs; no auxiliary OS windows or draggable chrome."""
import tkinter as tk
import math,time,os
from tkinter import filedialog
from pathlib import Path
from .matrix_theme import BG,PANEL,TEXT,MUTED,GREEN

class Dialog(tk.Frame):
 def __init__(self,root,title='',width=660,height=420):
  self.root=root;self.previous=root.grab_current();self.old_focus=root.focus_get();self.closer=None
  self.backdrop=tk.Frame(root,bg='#020604');self.backdrop.place(x=0,y=0,relwidth=1,relheight=1)
  self.shell=tk.Frame(self.backdrop,bg='#326f46',bd=0,highlightthickness=0)
  self.surface=tk.Frame(self.shell,bg=PANEL);self.surface.pack(fill='both',expand=True,padx=2,pady=2)
  self.hovered=False;self.hover_job=None
  header=tk.Frame(self.surface,bg=PANEL,padx=18,pady=12);header.pack(fill='x')
  self.caption=tk.Label(header,text=title,bg=PANEL,fg=GREEN,font=('Consolas',11,'bold'));self.caption.pack(side='left')
  self.close_button=tk.Button(header,text='×',command=self.close,bg=PANEL,fg=TEXT,activebackground='#244d31',activeforeground='white',relief='flat',font=('Segoe UI',15),cursor='hand2')
  self.close_button.own_glow=True
  self.close_button.configure(activebackground='#a52b3e',activeforeground='#ffffff',padx=5,pady=1)
  self.close_button.bind('<Enter>',lambda e:self.close_hover(True))
  self.close_button.bind('<Leave>',lambda e:self.close_hover(False))
  self.close_button.pack(side='right')
  super().__init__(self.surface,bg=BG);self.pack(fill='both',expand=True,padx=1,pady=(0,1))
  self.w,self.h=width,height
  self.binding=root.bind('<Configure>',self.resize,add='+');self.resize();self.backdrop.grab_set();self.focus_set()
  self.escape_binding=root.bind('<Escape>',self.escape,add='+')
 def close_hover(self,hovered):
  self.hovered=hovered
  if self.hover_job is not None:self.root.after_cancel(self.hover_job);self.hover_job=None
  if hovered:self.animate_close()
  else:
   self.close_button.configure(bg=PANEL,fg=TEXT,activebackground='#a52b3e');self.shell.configure(bg='#326f46')
 def animate_close(self):
  if not self.hovered or not self.winfo_exists():return
  preference=getattr(self.root,'veyra_animation',None)
  phase=(math.sin(time.monotonic()*.55)+1)/2 if preference is None or preference.get() else .65
  fill=f'#{int(65+phase*125):02x}{int(12+phase*23):02x}{int(23+phase*32):02x}'
  edge=f'#{int(165+phase*90):02x}{int(40+phase*60):02x}{int(60+phase*65):02x}'
  self.close_button.configure(bg=fill,activebackground=fill,fg='#ffffff');self.shell.configure(bg=edge)
  self.hover_job=self.root.after(40,self.animate_close)
 def escape(self,event=None):
  if self.root.grab_current()==self.backdrop:self.close();return 'break'
 def resize(self,event=None):
  if event is not None and event.widget is not self.root:return
  self.shell.place(relx=.5,rely=.5,anchor='center',width=min(self.w,max(100,self.root.winfo_width()-40)),height=min(self.h,max(100,self.root.winfo_height()-40)))
 def title(self,value):self.caption.configure(text=value)
 def geometry(self,value):
  self.w,self.h=map(int,value.split('x'));self.resize()
 def protocol(self,name,callback):self.closer=callback
 def close(self):
  if self.closer:self.closer()
  else:self.destroy()
 def destroy(self):
  if not self.winfo_exists():return
  self.hovered=False
  if self.hover_job is not None:self.root.after_cancel(self.hover_job);self.hover_job=None
  self.root.unbind('<Configure>',self.binding)
  self.root.unbind('<Escape>',self.escape_binding)
  try:self.backdrop.grab_release()
  except tk.TclError:pass
  tk.Frame.destroy(self)
  self.backdrop.destroy()
  try:
   if self.previous and self.previous.winfo_exists():self.previous.grab_set()
   if self.old_focus and self.old_focus.winfo_exists():self.old_focus.focus_set()
  except tk.TclError:pass

class Messages:
 def __init__(self,root):self.root=root
 def show(self,title,text,question=False,**kwargs):
  dialog=Dialog(self.root,title,640,kwargs.get('height',340));result=[False]
  tk.Label(dialog,text=text,bg=BG,fg=TEXT,font=('Segoe UI',12),wraplength=560,justify='left').pack(fill='both',expand=True,padx=26,pady=20)
  row=tk.Frame(dialog,bg=BG);row.pack(fill='x',padx=24,pady=20)
  def done(value):result[0]=value;dialog.destroy()
  for label,value in ([('Yes',True),('No',False)] if question else [('OK',True)]):
   tk.Button(row,text=label,command=lambda v=value:done(v),bg=PANEL,fg=GREEN,activebackground='#245534',activeforeground='white',relief='flat',padx=25,pady=10,font=('Segoe UI',11)).pack(side='right',padx=6)
  self.root.wait_window(dialog);return result[0]
 def showerror(self,title,text,**kwargs):return self.show(title,text)
 def showinfo(self,title,text,**kwargs):return self.show(title,text)
 def askyesno(self,title,text,**kwargs):return self.show(title,text,True,**kwargs)

def downloads_folder():
 try:
  import winreg
  with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
   folder=Path(os.path.expandvars(winreg.QueryValueEx(key,'{374DE290-123F-4565-9164-39C4925E467B}')[0]))
  if folder.is_dir():return str(folder)
 except (OSError,ImportError):pass
 folder=Path.home()/'Downloads'
 return str(folder if folder.is_dir() else Path.home())

class Files:
 """Use the operating system's standard certificate Open/Save dialogs."""
 def __init__(self,root):self.root=root
 def choose(self,save=False,**kwargs):
  kwargs.setdefault('parent',self.root)
  kwargs.setdefault('initialdir',downloads_folder())
  kwargs.setdefault('title','Save Certificate' if save else 'Choose Certificate')
  kwargs.setdefault('filetypes',[('Certificate','*.crt *.pem'),('All files','*.*')])
  previous=self.root.grab_current()
  if previous:previous.grab_release()
  try:
   return (filedialog.asksaveasfilename if save else filedialog.askopenfilename)(**kwargs)
  finally:
   if previous and previous.winfo_exists():previous.grab_set()
 def askopenfilename(self,**kwargs):return self.choose(**kwargs)
 def asksaveasfilename(self,**kwargs):return self.choose(save=True,**kwargs)
