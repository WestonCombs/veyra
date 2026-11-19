"""Native guest and host dashboard."""
import asyncio,json,math,os,queue,socket,sys,threading,tkinter as tk
from tkinter import ttk
from michub.dialogs import Dialog,Messages,Files
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import sounddevice as sd
import pystray
from michub.branding import icon_image,mic_icon,copy_icon,exit_icon,plus_icon,refresh_icon
from PIL import ImageTk
from michub.native_sender import NativeSender
from michub.desktop_host import DesktopHost
from michub.local_sender import LocalSender
from michub.glow_theme import GlowTheme
from michub.mic_visuals import microphone_colors
from michub.certificate_info import certificate_info

from michub.matrix_theme import BG,PANEL,TEXT,MUTED,GREEN,ScrollPage,apply as apply_theme,animate_navigation
class App:
 def __init__(self):
  self.root=tk.Tk();self.messages=Messages(self.root);self.files=Files(self.root);self.root.title('Veyra');self.root.geometry('1080x920');self.root.minsize(940,860);self.root.configure(bg=BG)
  self.path=Path(os.environ.get('LOCALAPPDATA','.'))/'CancelGroupMics'/'desktop.json'
  try:self.cfg=json.loads(self.path.read_text())
  except Exception:self.cfg={}
  self.events=queue.Queue();self.worker=NativeSender(lambda k,v:self.events.put((k,v)));self.host=DesktopHost();self.running=False;self.quitting=False;self.local_workers=[];self.local_enabled=False;self.join_generation=0;self.room_devices=[];self.pending_join=None;self.connected_target=None;self.switch_target=None;self.join_prompted=False;self.session_connected=False;self.reported_muted=True
  self.role=tk.StringVar(value='Host' if self.cfg.get('host_default') else 'Guest');self.status=tk.StringVar(value='Ready when you are.');self.invite=tk.StringVar();self.name=tk.StringVar(value=self.cfg.get('name',socket.gethostname()));self.mic=tk.StringVar(value=self.cfg.get('mic',''));self.ca=tk.StringVar(value=self.cfg.get('ca',''));self.output=tk.StringVar(value=self.cfg.get('output',''));self.animation=tk.BooleanVar(value=self.cfg.get('animation',True));self.startup=tk.BooleanVar(value=self.cfg.get('startup',False));self.host_default=tk.BooleanVar(value=self.cfg.get('host_default',False));self.close_tray=tk.BooleanVar(value=self.cfg.get('close_tray',True));self.muted=tk.BooleanVar(value=False)
  self.root.veyra_animation=self.animation
  self.style=ttk.Style();self.style.theme_use('clam')
  for item in ['TFrame','TLabel','TCheckbutton','TNotebook','TNotebook.Tab']:
   self.style.configure(item,background=BG,foreground=TEXT,font=('Segoe UI',11))
  self.style.configure('TEntry',fieldbackground=PANEL,foreground=TEXT,padding=10)
  self.style.configure('TCombobox',fieldbackground=PANEL,background=PANEL,foreground=TEXT,padding=8)
  self.style.map('TCombobox',fieldbackground=[('readonly',PANEL)],foreground=[('readonly',TEXT)])
  self.style.configure('TProgressbar',background=GREEN,troughcolor=PANEL,borderwidth=0)
  self.style.configure('TButton',background=PANEL,foreground=TEXT,padding=10)
  outer=tk.Frame(self.root,bg=BG);outer.pack(fill='both',expand=True,padx=32,pady=25)
  top=tk.Frame(outer,bg=BG);top.pack(fill='x')
  self.brand_icon=ImageTk.PhotoImage(icon_image(44));self.window_icon=ImageTk.PhotoImage(icon_image(64));self.root.iconphoto(True,self.window_icon)
  tk.Label(top,image=self.brand_icon,bg=BG).pack(side='left',padx=(0,13))
  self.label(top,'VEYRA',24,GREEN).pack(side='left')
  self.label(top,'  /  ONE ROOM. ONE VOICE.',10,MUTED).pack(side='left',padx=14)
  self.rolebox=ttk.Combobox(top,textvariable=self.role,values=['Guest','Host'],state='readonly',width=9);self.profile_selection=tk.BooleanVar(value=self.cfg.get('profile_selection',False));
  if self.profile_selection.get():self.rolebox.pack(side='right')
  self.rolebox.bind('<<ComboboxSelected>>',lambda e:self.change_role())
  self.tabs=ttk.Notebook(outer);self.tabs.pack(fill='both',expand=True,pady=22)
  self.dash=ttk.Frame(self.tabs,padding=24);self.settings_page=ScrollPage(self.tabs);self.settings=self.settings_page.body;self.tabs.add(self.dash,text='  Dashboard  ');self.tabs.add(self.settings_page,text='  Settings  ')
  self.heading=self.label(self.dash,'Your voice. Connected.',30);self.heading.pack(anchor='w')
  self.label(self.dash,'A quiet background. A clear conversation.',11,MUTED).pack(anchor='w',pady=(5,20))
  self.guest=tk.Frame(self.dash,bg=BG);self.guest.pack(fill='x')
  self.label(self.guest,'ROOM CODE OR INVITE LINK',11,GREEN).pack(anchor='w')
  self.invite_entry=ttk.Entry(self.guest,textvariable=self.invite);self.invite_entry.pack(fill='x',pady=8)
  self.placeholder=tk.Label(self.invite_entry,text='e.g. 123456 or https://host.example:8788/setup#code=123456',bg=PANEL,fg='#52675a',font=('Segoe UI',11),cursor='xterm')
  self.placeholder.place(x=12,rely=.5,anchor='w');self.placeholder.bind('<Button-1>',lambda e:self.invite_entry.focus_set())
  self.invite.trace_add('write',lambda *a:self.update_placeholder());self.invite_entry.bind('<FocusIn>',lambda e:self.placeholder.place_forget());self.invite_entry.bind('<FocusOut>',lambda e:self.update_placeholder())
  self.label(self.guest,'Room code finds hosts on the same Wi-Fi network. Links connect to a reachable host on the same or a different network.',10,MUTED).pack(anchor='w')
  self.host_panel=tk.Frame(self.dash,bg=BG)
  self.mic_images=[ImageTk.PhotoImage(mic_icon(False,32)),ImageTk.PhotoImage(mic_icon(True,32))];self.copy_image=ImageTk.PhotoImage(copy_icon());self.plus_image=ImageTk.PhotoImage(plus_icon())
  self.cards=tk.Frame(self.host_panel,bg=BG);self.cards.pack(fill='x',pady=12);self.card_widgets=[]
  for i in range(4):
   f=tk.Frame(self.cards,bg=PANEL,padx=12,pady=12,width=400,height=132,highlightthickness=2,highlightbackground=PANEL,highlightcolor=PANEL);f.grid(row=i//2,column=i%2,sticky='nsew',padx=4,pady=4);f.pack_propagate(False);self.cards.columnconfigure(i%2,weight=1,uniform='mic_columns');self.cards.rowconfigure(i//2,weight=1,uniform='mic_rows')
   l=self.label(f,f'Microphone {i+1} · Idle',11);l.configure(bg=PANEL);l.place(x=0,y=0,relwidth=.78);bar=ttk.Progressbar(f,maximum=100);bar.place(x=0,y=44,relwidth=.78,height=5)
   b=self.button(f,'+',lambda index=i:self.slot_action(index));b.configure(padx=0,pady=0,width=2,height=1);b.hovered=False;b.own_glow=True;b.bind('<Enter>',lambda e,b=b:setattr(b,'hovered',True));b.bind('<Leave>',lambda e,b=b:self.leave_slot_hover(b));b.place(relx=1,x=-3,rely=.5,anchor='e',width=60,height=60);self.card_widgets.append((l,bar,b))
  self.mic_panel=tk.Frame(self.dash,bg=BG);self.mic_panel.pack(fill='x');self.label(self.mic_panel,'YOUR MICROPHONE',10,MUTED).pack(anchor='w',pady=(18,4));self.combo=ttk.Combobox(self.mic_panel,textvariable=self.mic,state='readonly');self.combo.pack(fill='x');self.combo.bind('<<ComboboxSelected>>',lambda e:self.change_microphone())
  self.big=tk.Button(self.dash,text='START',command=self.toggle,bg=GREEN,fg=BG,font=('Segoe UI',20,'bold'),relief='flat',height=2,cursor='hand2');self.big.pack(fill='x',pady=(22,12))
  ttk.Label(self.dash,textvariable=self.status,wraplength=820,width=90).pack(anchor='w',fill='x')
  self.meter=ttk.Progressbar(self.dash,maximum=100);self.meter.pack(fill='x',pady=12)
  self.room_actions=tk.Frame(self.dash,bg=BG,height=54);self.room_actions.pack(fill='x',pady=4);self.room_actions.pack_propagate(False)
  self.mute_button=self.button(self.room_actions,'',self.toggle_mute);self.mute_button.own_glow=True;self.mute_button.configure(image=self.mic_images[0],padx=7,pady=5);self.mute_button.pack(anchor='w')
  self.mute_button.pack_forget();self.exit_image=ImageTk.PhotoImage(exit_icon());self.leave_button=self.button(self.room_actions,'  Leave room',self.leave_room);self.leave_button.configure(image=self.exit_image,compound='left')
  self.build_settings();self.refresh_devices();self.change_role();apply_theme(self);self.glows=GlowTheme(self)
  self.tray=pystray.Icon('CancelGroupMics',icon_image(), 'Veyra',pystray.Menu(pystray.MenuItem('Open dashboard',lambda:self.events.put(('show',None)),default=True),pystray.MenuItem('Mute / unmute',lambda:self.events.put(('mute',None))),pystray.MenuItem('Quit',lambda:self.events.put(('quit',None)))))
  self.tray.run_detached();self.root.protocol('WM_DELETE_WINDOW',self.close);self.root.after(100,self.tick)
 def label(self,parent,text,size=11,color=TEXT):return tk.Label(parent,text=text,bg=BG,fg=color,font=('Consolas' if size<=10 else 'Segoe UI',size),anchor='w')
 def button(self,parent,text,command):
  button=tk.Button(parent,text=text,command=command,bg=PANEL,fg=GREEN,activebackground='#245534',activeforeground='#ffffff',relief='flat',bd=0,highlightthickness=1,highlightbackground='#214c32',padx=17,pady=11,cursor='hand2',font=('Segoe UI',10,'bold'))
  button.bind('<Enter>',lambda e:button.configure(bg='#193c25',fg='#ffffff',highlightbackground=GREEN))
  button.bind('<Leave>',lambda e:button.configure(bg=PANEL,fg=GREEN,highlightbackground='#214c32'))
  return button
 def build_settings(self):
  self.label(self.settings,'SYSTEM PREFERENCES',10,GREEN).pack(anchor='w');self.label(self.settings,'Your setup. Your rules.',28).pack(anchor='w',pady=(8,5));self.label(self.settings,'Set it once. Stay in the conversation.',11,MUTED).pack(anchor='w',pady=(0,20))
  for title,var in [('Neon breathing animations',self.animation),('Keep running in the tray when I close the window',self.close_tray),('Open when I sign in to Windows',self.startup),('Present Profile Selection (Host / Guest)',self.profile_selection),('Open the host dashboard by default',self.host_default)]:ttk.Checkbutton(self.settings,text=title,variable=var,command=self.save).pack(fill='x',anchor='w',pady=6)
  self.label(self.settings,'Your microphone name').pack(anchor='w',pady=(16,5));ttk.Entry(self.settings,textvariable=self.name).pack(fill='x')
  self.name.trace_add('write',lambda *args:self.settings_changed())
  self.advanced_button=self.button(self.settings,'+  Advanced audio & connection',self.advanced_toggle);self.advanced_button.pack(fill='x',pady=(18,8))
  self.advanced=tk.Frame(self.settings,bg=BG)
  self.label(self.advanced,'Call output device (host)').pack(anchor='w')
  output_row=tk.Frame(self.advanced,bg=BG);output_row.pack(fill='x',pady=(5,14))
  self.output_combo=ttk.Combobox(output_row,textvariable=self.output,state='readonly',values=[]);self.output_combo.pack(side='left',fill='x',expand=True);self.output_combo.bind('<<ComboboxSelected>>',self.output_changed)
  self.refresh_image=ImageTk.PhotoImage(refresh_icon());self.refresh_button=self.button(output_row,'',self.refresh_devices);self.refresh_button.configure(image=self.refresh_image,padx=8,pady=6);self.refresh_button.pack(side='right',padx=(8,0))
  self.attach_tooltip(self.refresh_button,'Refresh audio devices')
  self.label(self.advanced,'Trusted Hub Certificate (Required, if connecting to a host)').pack(anchor='w')
  certificate_row=tk.Frame(self.advanced,bg=BG);certificate_row.pack(fill='x',pady=7)
  self.certificate_button=self.button(certificate_row,'Choose a certificate to use',self.certificate_action);self.certificate_button.pack(side='left')
  self.export_button=self.button(certificate_row,'Export certificate',self.export_ca);self.export_button.pack(side='left',padx=(10,0))
  self.label(self.advanced,'Guests select the host’s public certificate once. Windows installation is not needed.',10,MUTED).pack(anchor='w',pady=5)
  self.label(self.advanced,'Wi-Fi buffer · increase if audio breaks up').pack(anchor='w');self.delay=tk.DoubleVar(value=self.cfg.get('delay_ms',180));ttk.Scale(self.advanced,from_=80,to=1000,variable=self.delay,command=lambda v:self.set_delay()).pack(fill='x')
  self.label(self.advanced,'Discord microphone: CABLE Output. Use headphones for playback.',10,MUTED).pack(anchor='w',pady=8)
 def attach_tooltip(self,widget,text):
  state={'job':None,'label':None}
  def hide(event=None):
   if state['job']:self.root.after_cancel(state['job']);state['job']=None
   if state['label'] is not None:state['label'].destroy();state['label']=None
  def show():
   state['job']=None
   if not widget.winfo_exists() or not widget.winfo_ismapped():return
   tip=tk.Label(self.root,text=text,bg='#173c25',fg=TEXT,font=('Segoe UI',10),padx=10,pady=6,highlightthickness=1,highlightbackground='#3b8051')
   tip.update_idletasks();x=widget.winfo_rootx()-self.root.winfo_rootx();y=widget.winfo_rooty()-self.root.winfo_rooty()+widget.winfo_height()+6
   tip.place(x=max(8,min(x,self.root.winfo_width()-tip.winfo_reqwidth()-8)),y=min(y,self.root.winfo_height()-tip.winfo_reqheight()-8));tip.lift();state['label']=tip
  def enter(event):hide();state['job']=self.root.after(450,show)
  widget.bind('<Enter>',enter,add='+');widget.bind('<Leave>',hide,add='+');widget.bind('<ButtonPress>',hide,add='+');widget.bind('<Destroy>',hide,add='+')
 def advanced_toggle(self):
  if self.advanced.winfo_manager():self.advanced.pack_forget();self.advanced_button.configure(text='+  Advanced audio & connection')
  else:self.advanced.pack(fill='x',pady=14);self.advanced_button.configure(text='−  Hide advanced settings')
 def settings_changed(self):
  job=getattr(self,'settings_job',None)
  if job:self.root.after_cancel(job)
  self.worker.name=self.name.get()
  if self.host.hub:
   with self.host.hub.mixer.lock:
    for w in self.local_workers:
     if w.id in self.host.hub.mixer.devices:self.host.hub.mixer.devices[w.id].name=self.name.get()
  self.settings_job=self.root.after(350,self.save)
 def output_changed(self,event=None):
  try:
   if self.host.hub and self.running:self.host.hub.output.start(self.outputs[self.output.get()])
   self.save()
  except Exception as e:self.messages.showerror('Audio output',str(e))
 def set_delay(self):
  if self.host.hub:self.host.hub.mixer.delay_ms=int(self.delay.get())
  self.settings_changed()
 def current_certificate(self):
  if self.role.get()=='Host':return Path(os.environ.get('LOCALAPPDATA','.'))/'CancelGroupMics'/'hub'/'ca.crt'
  return Path(self.ca.get()) if self.ca.get() else Path(sys.executable if getattr(sys,'frozen',False) else __file__).parent/'ca.crt'
 def refresh_certificate(self):
  try:certificate_info(self.current_certificate());valid=True
  except Exception:valid=False
  if hasattr(self,'certificate_button'):self.certificate_button.configure(text='View certificate' if valid else 'Choose a certificate to use')
  return valid
 def certificate_action(self):
  if not self.refresh_certificate():self.choose_ca();return
  info=certificate_info(self.current_certificate());page=Dialog(self.root,'Certificate',700,420)
  frame=tk.Frame(page,bg=BG,padx=24,pady=24);frame.pack(fill='both',expand=True)
  self.label(frame,'Host connection certificate',22).pack(anchor='w',pady=(0,12))
  text=f"Issued to: {info['subject']}\nIssuer: {info['issuer']}\nExpires: {info['expires']}\n\nSHA-256 fingerprint\n{info['fingerprint']}"
  tk.Label(frame,text=text,bg=BG,fg=TEXT,font=('Segoe UI',11),wraplength=620,justify='left').pack(anchor='w')
  if self.role.get()=='Guest':self.button(frame,'Use a different certificate',lambda:(page.destroy(),self.choose_ca())).pack(anchor='w',pady=15)
 def export_ca(self):
  source=Path(os.environ.get('LOCALAPPDATA','.'))/'CancelGroupMics'/'hub'/'ca.crt'
  if not source.exists():self.messages.showinfo('Certificate','Start the host once to create its certificate.');return
  target=self.files.asksaveasfilename(defaultextension='.crt',initialfile='ca.crt')
  if target:
   import shutil
   shutil.copyfile(source,target)
 def choose_ca(self):
  p=self.files.askopenfilename(filetypes=[('Certificate','*.crt *.pem')])
  if p:
   try:
    certificate_info(p);self.ca.set(p);self.save();self.refresh_certificate()
   except Exception as e:self.messages.showerror('Invalid certificate',str(e))
 def save(self):
  if getattr(self,'settings_job',None):self.root.after_cancel(self.settings_job);self.settings_job=None
  try:
   import winreg
   with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
    if self.startup.get():
     command=f'"{sys.executable}"' if getattr(sys,'frozen',False) else f'"{sys.executable}" "{Path(__file__).resolve()}"'
     winreg.SetValueEx(key,'CancelGroupMics',0,winreg.REG_SZ,command)
    else:
     try:winreg.DeleteValue(key,'CancelGroupMics')
     except FileNotFoundError:pass
   self.cfg=dict(output=self.output.get(),delay_ms=int(self.delay.get()),profile_selection=self.profile_selection.get(),startup=self.startup.get(),host_default=self.host_default.get(),close_tray=self.close_tray.get(),animation=self.animation.get(),name=self.name.get(),ca=self.ca.get(),mic=self.mic.get())
   self.path.parent.mkdir(parents=True,exist_ok=True);self.path.write_text(json.dumps(self.cfg));self.rolebox.pack_forget()
   if self.profile_selection.get():self.rolebox.pack(side='right')
   self.status.set('Settings applied automatically.')
  except Exception as e:self.messages.showerror('Settings',str(e))
 def refresh_devices(self):
  try:
   apis=sd.query_hostapis();ds=list(enumerate(sd.query_devices()));ds.sort(key=lambda p:apis[p[1]['hostapi']]['name']!='Windows WASAPI')
   self.inputs={f"{d['name']} · {apis[d['hostapi']]['name']}":i for i,d in ds if d['max_input_channels']}
   self.outputs={f"{d['name']} · {apis[d['hostapi']]['name']}":i for i,d in ds if d['max_output_channels']}
   self.combo['values']=list(self.inputs);self.output_combo['values']=list(self.outputs)
   if self.mic.get() not in self.inputs:self.mic.set(next(iter(self.inputs),''))
   if self.output.get() not in self.outputs:self.output.set(next((k for k in self.outputs if 'CABLE Input' in k and 'WASAPI' in k),''))
  except Exception as e:self.status.set(str(e))
 def change_role(self):
  if self.running:self.role.set('Host' if self.host.hub else 'Guest');self.status.set('Stop before switching roles.');return
  self.refresh_certificate()
  ishost=self.role.get()=='Host';
  self.mic_panel.pack_forget()
  if self.running and not ishost or ishost and self.local_enabled:self.mic_panel.pack(fill='x',before=self.big)
  self.mute_button.pack_forget()
  if not ishost and self.session_connected:self.mute_button.pack(anchor='w')
  self.heading.configure(text='Your room. In harmony.' if ishost else 'Your voice. Connected.')
  self.guest.pack_forget();self.host_panel.pack_forget()
  (self.host_panel if ishost else self.guest).pack(fill='x',after=self.dash.winfo_children()[1]);self.render_cards()
 def toggle(self):
  if self.role.get()=='Guest' and not self.running and not self.invite.get().strip():return
  if self.running:
   if self.role.get()=='Host' and not self.confirm_host_stop():return
   self.join_generation+=1;self.worker.stop()
   for worker in self.local_workers:worker.stop()
   self.host.stop();self.running=False;self.status.set('Stopping…');return
  try:
   if self.role.get()=='Host':
    self.slot_action(0)
   else:
    self.running=True;self.join_generation+=1
    generation=self.join_generation;value=self.invite.get().strip();mode=0 if value.isdigit() and len(value)==6 else 1;self.status.set('Finding host…')
    def resolve():
     try:
      if mode<.5:
       from michub.discovery import discover
       address=discover(value);code=value
      else:
       u=urlsplit(value);q=parse_qs(u.fragment);code=q.get('code',[''])[0]
       if not u.hostname or len(code)!=6 or not code.isdigit():raise ValueError('Paste a complete invite link with a six-digit code.')
       address=f"https://{u.hostname}:{int(q.get('tls',['8788'])[0])}"
      self.events.put(('resolved',(generation,address,code)))
     except Exception as e:self.events.put(('join_error',(generation,str(e))))
    threading.Thread(target=resolve,daemon=True).start()
  except Exception as e:self.messages.showerror('Could not start',str(e))
 def confirm_host_stop(self):
  h=self.host.hub
  devices=h.mixer.snapshot()['devices'] if h else []
  if not devices:return True
  names='\n'.join('• '+d['name'] for d in devices)
  return self.messages.askyesno('Stop this room?',f'Are you sure you want to stop?\n\nThis will disconnect all microphones in the room:\n{names}\n\nThey will need to reconnect after the room starts again.',parent=self.root,height=480)
 def finish_host(self):
  h=self.host.hub
  if not self.running:return
  if self.host.error:self.running=False;self.status.set('Could not host: '+self.host.error);return
  if not h or not h.engine.thread.is_alive():self.root.after(400,self.finish_host);return
  try:
   h.mixer.delay_ms=int(self.delay.get());h.output.start(self.outputs[self.output.get()]);self.refresh_certificate();self.status.set('Room live. Add a microphone or invite another machine.')
   callback=getattr(self,'after_host',None);self.after_host=None
   if callback:callback()
  except Exception as e:self.host.stop();self.running=False;self.status.set(str(e))
 def copy_invite(self):
  h=self.host.hub
  if not h or not h.addresses:self.status.set('Start the host to create an invite.');return
  link=f'http://{h.addresses[0]}:8787/setup#code={h.code}&tls=8788'
  self.root.clipboard_clear();self.root.clipboard_append(link);self.status.set('Invite copied. Guests can paste it into their app.')
 def toggle_mute(self):
  if not self.session_connected:return
  self.worker.muted=not self.worker.muted;self.mute_button.configure(image=self.mic_images[int(self.worker.muted)])
 def mute_device(self,index):
  h=self.host.hub
  if h:
   with h.mixer.lock:
    ds=list(h.mixer.devices.values())
    if index<len(ds):ds[index].muted=not ds[index].muted
 def update_placeholder(self):
  if not self.invite.get() and self.root.focus_get()!=self.invite_entry:self.placeholder.place(x=12,rely=.5,anchor='w')
  else:self.placeholder.place_forget()
  if hasattr(self,'big'):self.update_connect_availability()
 def update_connect_availability(self):
  disabled=self.role.get()=='Guest' and not self.running and not self.invite.get().strip()
  self.big.configure(state='disabled' if disabled else 'normal')
  if disabled:self.big.configure(bg='#14271b',disabledforeground='#6d8876',highlightbackground='#213e2a')
 def leave_room(self):
  self.join_generation+=1;self.switch_target=None;self.worker.stop();self.running=False;self.session_connected=False;self.join_prompted=False;self.room_devices=[];self.mute_button.pack_forget();self.leave_button.pack_forget();self.mic_panel.pack_forget();self.host_panel.pack_forget();self.status.set('You left the room.')
 def welcome_room(self):
  if not self.session_connected or self.join_prompted:return
  self.join_prompted=True
  code=self.connected_target[1] if self.connected_target else ''
  count=len(self.room_devices)
  unmute=self.messages.askyesno('Connected to room',f'You successfully connected to room {code}.\n\nMicrophones connected: {count} (including yours).\n\nYour mic is muted. Would you like to unmute it now?',parent=self.root)
  if self.session_connected:
   self.worker.muted=not unmute;self.mute_button.configure(image=self.mic_images[int(self.worker.muted)])
 def confirm_microphone(self,address,code):
  self.status.set('Host found. Choose your microphone to finish connecting.')
  page=Dialog(self.root);page.title('Choose your microphone');page.configure(bg=BG);page.geometry('650x280')
  frame=tk.Frame(page,bg=BG,padx=24,pady=24);frame.pack(fill='both',expand=True)
  self.label(frame,'Choose your microphone',24).pack(anchor='w',pady=12)
  selection=tk.StringVar(value=self.mic.get());ttk.Combobox(frame,textvariable=selection,values=list(self.inputs),state='readonly').pack(fill='x',pady=12)
  def cancel():self.running=False;self.status.set('Connection cancelled.');page.destroy()
  def confirm():
   self.mic.set(selection.get());self.remember_mic();page.destroy();self.start_guest(address,code)
  self.button(frame,'Confirm & connect',confirm).pack(side='left',pady=12);self.button(frame,'Cancel',cancel).pack(side='right');page.protocol('WM_DELETE_WINDOW',cancel)
 def start_guest(self,address,code):
  try:
   self.connected_target=(address,code);self.worker.muted=True;self.join_prompted=False;self.session_connected=False;self.reported_muted=True;self.mute_button.pack_forget();self.leave_button.pack_forget();self.status.set('Connecting to host…');self.worker.start(address,code,self.name.get(),self.inputs[self.mic.get()],self.ca.get() or str(Path(sys.executable if getattr(sys,'frozen',False) else __file__).parent/'ca.crt'));self.running=True
  except Exception as e:self.running=False;self.status.set(str(e))
 def change_microphone(self):
  self.remember_mic()
  if self.role.get()=='Guest' and self.running and self.connected_target:
   self.switch_target=self.connected_target;self.worker.stop();self.status.set('Changing microphone…')
 def remember_mic(self):
  self.cfg['mic']=self.mic.get();self.path.parent.mkdir(parents=True,exist_ok=True);self.path.write_text(json.dumps(self.cfg))
 def ensure_host(self,callback):
  if self.host.hub and self.host.hub.engine.thread.is_alive():callback();return
  if self.running:self.status.set('Room is starting. Please wait.');return
  if self.output.get() not in self.outputs:self.messages.showerror('Call output','Install VB-CABLE, then select CABLE Input in advanced settings.');return
  self.after_host=callback;self.host.start();self.running=True;self.status.set('Starting your room…');self.root.after(250,self.finish_host)
 def slot_action(self,index):
  h=self.host.hub
  if h and h.engine.thread.is_alive() and index<len(h.mixer.snapshot()['devices']):self.mute_device(index);return
  page=Dialog(self.root);page.title('Add microphone');page.configure(bg=BG);page.geometry('640x370')
  frame=tk.Frame(page,bg=BG,padx=25,pady=25);frame.pack(fill='both',expand=True)
  self.label(frame,'Add a microphone',24).pack(anchor='w',pady=12)
  def local():
   for widget in frame.winfo_children():widget.destroy()
   self.label(frame,'Microphone from this machine',22).pack(anchor='w',pady=12)
   selection=tk.StringVar(value=self.mic.get());ttk.Combobox(frame,textvariable=selection,values=list(self.inputs),state='readonly').pack(fill='x',pady=14)
   def connect_local():
    h=self.host.hub
    if not page.winfo_exists():return
    try:
     if selection.get() not in self.inputs:raise ValueError('Select an available microphone.')
     if len(h.mixer.devices)>=4:raise ValueError('All four microphone slots are occupied.')
     w=LocalSender(h,lambda k,v:self.events.put(('local_'+k,v)))
     w.start('http://localhost:8787',h.code,self.name.get(),self.inputs[selection.get()]);self.local_workers.append(w)
     self.mic.set(selection.get());self.remember_mic();self.local_enabled=True;self.mic_panel.pack(fill='x',before=self.big);page.destroy()
    except Exception as e:self.messages.showerror('Microphone',str(e),parent=page)
   self.button(frame,'START',lambda:self.ensure_host(connect_local)).pack(fill='x',pady=15)
  def display_remote():
   h=self.host.hub
   if not page.winfo_exists():return
   for widget in frame.winfo_children():widget.destroy()
   self.label(frame,'Invite another machine',22).pack(anchor='w',pady=12)
   def copy(value):self.root.clipboard_clear();self.root.clipboard_append(value)
   row=tk.Frame(frame,bg=BG);row.pack(fill='x');self.label(row,h.code,30,GREEN).pack(side='left');copy_code=self.button(row,'',lambda:copy(h.code));copy_code.configure(image=self.copy_image,padx=7,pady=5);copy_code.pack(side='right')
   link=f"http://{h.addresses[0] if h.addresses else '127.0.0.1'}:8787/setup#code={h.code}&tls=8788"
   link_row=tk.Frame(frame,bg=BG);link_row.pack(fill='x',pady=15)
   copy_link=self.button(link_row,'',lambda:copy(link));copy_link.configure(image=self.copy_image,padx=7,pady=5);copy_link.pack(side='right')
   link_text=self.label(link_row,link,14,GREEN);link_text.configure(wraplength=480,justify='left');link_text.pack(side='left',fill='x',expand=True)
   self.attach_tooltip(copy_link,'Copy invite link');self.attach_tooltip(copy_code,'Copy room code')
   self.label(frame,'First connection: select this host’s certificate in guest settings.',10,MUTED).pack(anchor='w',pady=12)
  self.button(frame,'Microphone from this machine',local).pack(fill='x',pady=9)
  self.button(frame,'Microphone from another machine',lambda:self.ensure_host(display_remote)).pack(fill='x',pady=9)
 def close(self):
  if self.close_tray.get():self.root.withdraw()
  else:self.quit()
 def quit(self):
  if getattr(self,'settings_job',None):self.save()
  self.quitting=True;self.worker.stop()
  for worker in self.local_workers:worker.stop()
  self.host.stop();self.root.withdraw()
 def leave_slot_hover(self,button):
  button.hovered=False;button.configure(bg=getattr(button,'slot_background',PANEL),activebackground='#245534',highlightbackground='#214c32')
 def render_cards(self):
  h=self.host.hub
  ishost=self.role.get()=='Host'
  ds=h.mixer.snapshot()['devices'] if h else ([] if ishost else self.room_devices)
  for i,(label,bar,button) in enumerate(self.card_widgets):
   if i<len(ds):
    d=ds[i]
    border,fill=microphone_colors(d['level_db'],d['active'],d['muted'],d.get('stale',False));label.master.configure(bg=fill,highlightbackground=border,highlightcolor=border);label.configure(bg=fill);button.slot_background=fill
    if not button.hovered:button.configure(bg=fill,activebackground=fill)
    label.configure(text=d['name']+(' · ON AIR' if d['active'] else ' · muted' if d['muted'] else ' · standby'),fg=GREEN if d['active'] else TEXT)
    bar['value']=max(0,(d['level_db']+65)/65*100)
    button.configure(text='',image=self.mic_images[int(d['muted'])],width=42,height=38,padx=7,pady=5)
    if ishost:button.place(relx=1,x=-3,rely=.5,anchor='e',width=60,height=60)
    else:button.place_forget()
   else:
    button.slot_background=PANEL;label.master.configure(bg=PANEL);label.configure(bg=PANEL)
    if not button.hovered:button.configure(bg=PANEL)
    label.configure(text=f'Microphone {i+1} · Idle',fg=MUTED);bar['value']=0
    button.configure(text='',image=self.plus_image,width=28,height=28,padx=0,pady=0,anchor='center',compound='none')
    if ishost and i==len(ds):button.place(relx=1,x=-3,rely=.5,anchor='e',width=60,height=60)
    else:button.place_forget()
 def tick(self):
  try:
   while True:
    k,v=self.events.get_nowait()
    if k=='show':self.root.deiconify();self.root.lift()
    elif k=='quit':self.quit()
    elif k=='mute':self.toggle_mute()
    elif k=='resolved':
     generation,address,code=v
     if generation==self.join_generation and self.running:
      try:
       self.confirm_microphone(address,code)
      except Exception as e:self.running=False;self.status.set(str(e))
    elif k=='join_error':
     if v[0]==self.join_generation:self.running=False;self.status.set(v[1])
    elif k=='local_status':self.status.set(v)
    elif k=='status':
     self.status.set(v)
     if self.role.get()=='Guest' and ('interrupted' in v or 'Retrying' in v):self.session_connected=False;self.worker.muted=True;self.join_prompted=False;self.mute_button.pack_forget();self.leave_button.pack_forget()
    elif k=='ended':
     if self.role.get()=='Guest':
      if self.switch_target:
       address,code=self.switch_target;self.switch_target=None;self.start_guest(address,code)
      else:self.running=False;self.session_connected=False;self.mute_button.pack_forget();self.leave_button.pack_forget();self.mic_panel.pack_forget();self.host_panel.pack_forget()
    elif k=='meter':
     self.session_connected=True;self.reported_muted=bool(v.get('muted'));self.mute_button.pack(anchor='w');self.leave_button.pack(anchor='e');self.room_devices=v.get('devices',[]);
     if not self.join_prompted:self.root.after(1,self.welcome_room)
     self.host_panel.pack(fill='x',after=self.guest);self.mic_panel.pack(fill='x',before=self.big)
     self.mute_button.configure(image=self.mic_images[int(bool(v.get('muted') or self.worker.muted))]);self.meter['value']=max(0,(v['level_db']+65)/65*100)
     self.status.set('Muted' if v.get('muted') else 'On air' if v.get('active') and v.get('output_running') else 'Connected · standing by')
  except queue.Empty:pass
  self.render_cards()
  phase=(math.sin(__import__('time').monotonic()*.55)+1)/2 if self.animation.get() else .5
  animate_navigation(self,phase)
  self.glows.update(phase)
  color=f'#{int(45+phase*70):02x}{int(150+phase*105):02x}{int(65+phase*80):02x}' if not self.running else f'#{int(100+phase*85):02x}{int(20+phase*18):02x}{int(32+phase*18):02x}'
  self.big.configure(text=('DISCONNECT' if self.role.get()=='Guest' else '■   STOP') if self.running else ('CONNECT TO HOST' if self.role.get()=='Guest' else '▶   START'),bg=color,fg=TEXT if self.running else BG,highlightbackground=f'#{int(15+phase*25):02x}{int(65+phase*90):02x}{int(27+phase*35):02x}')
  for _,_,button in self.card_widgets:
   if getattr(button,'hovered',False) and button.winfo_ismapped():
    hover=f'#{int(12+phase*12):02x}{int(37+phase*35):02x}{int(21+phase*17):02x}'
    button.configure(bg=hover,activebackground=hover,highlightbackground=f'#{int(28+phase*20):02x}{int(70+phase*55):02x}{int(41+phase*23):02x}')
  h=self.host.hub
  occupied=len(h.mixer.snapshot()['devices']) if h else len(self.room_devices) if self.role.get()=='Guest' else 0
  for i,(label,_,button) in enumerate(self.card_widgets):
   if i<occupied:
    ds=h.mixer.snapshot()['devices'] if h else self.room_devices
    if i<len(ds) and ds[i]['muted']:
     red=f'#{int(100+phase*85):02x}{int(20+phase*18):02x}{int(32+phase*18):02x}'
     label.master.configure(highlightbackground=red,highlightcolor=red);button.configure(bg=red,activebackground=red,highlightbackground=red,highlightcolor=red)
    continue
   elif getattr(button,'hovered',False) and button.winfo_ismapped():
    border=f'#{int(12+phase*12):02x}{int(37+phase*35):02x}{int(21+phase*17):02x}'
   else:border=PANEL
   label.master.configure(highlightbackground=border,highlightcolor=border)
  if self.session_connected and (self.worker.muted or getattr(self,'reported_muted',False)):
   red=f'#{int(100+phase*85):02x}{int(20+phase*18):02x}{int(32+phase*18):02x}'
   self.mute_button.configure(bg=red,activebackground=red,highlightbackground=red,highlightcolor=red)
  else:self.mute_button.configure(bg=PANEL,activebackground='#245534',highlightbackground='#214c32',highlightcolor='#214c32')
  self.update_connect_availability()
  if self.quitting and not any(w.thread and w.thread.is_alive() for w in self.local_workers) and not (self.worker.thread and self.worker.thread.is_alive()) and not (self.host.thread and self.host.thread.is_alive()):self.tray.stop();self.root.destroy();return
  self.root.after(100,self.tick)
 def run(self):self.root.mainloop()
if __name__=='__main__':
 if '--verify-native-host' in sys.argv:
  import time
  host=DesktopHost();host.start();deadline=time.time()+10
  while time.time()<deadline and not host.error and not (host.hub and host.hub.engine.thread.is_alive()):time.sleep(.05)
  result={'ready':bool(host.hub and host.hub.engine.thread.is_alive()),'error':host.error}
  host.stop()
  if host.thread:host.thread.join(5)
  Path(sys.argv[sys.argv.index('--verify-native-host')+1]).write_text(json.dumps(result))
 else:App().run()
