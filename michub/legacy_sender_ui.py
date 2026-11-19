"""Windows tray application. Closing the window hides it; Quit stops capture."""
import json
import os
from pathlib import Path
import queue
import socket
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sounddevice as sd
import pystray
from PIL import Image, ImageDraw
from michub.native_sender import NativeSender


def icon_image(color='#337e62'):
    im=Image.new('RGBA',(64,64),(0,0,0,0));d=ImageDraw.Draw(im)
    d.rounded_rectangle((3,3,61,61),radius=15,fill=color)
    for x,h in [(18,15),(27,30),(36,40),(45,24)]:
        d.rounded_rectangle((x,32-h//2,x+4,32+h//2),radius=2,fill='white')
    return im


class SenderApp:
    def __init__(self):
        self.root=tk.Tk();self.root.title('Cancel Group Mics · Windows Sender')
        self.root.geometry('560x730');self.root.minsize(540,710)
        self.events=queue.Queue();self.active=False;self.quitting=False
        self.worker=NativeSender(lambda k,v:self.events.put((k,v)))
        self.config_path=Path(os.environ.get('LOCALAPPDATA',str(Path.cwd())))/'CancelGroupMics'/'sender.json'
        try:self.config=json.loads(self.config_path.read_text())
        except (OSError,ValueError):self.config={}
        self.address=tk.StringVar(value=self.config.get('address','http://localhost:8787'))
        self.name=tk.StringVar(value=self.config.get('name',socket.gethostname()))
        self.code=tk.StringVar();self.ca=tk.StringVar(value=self.config.get('ca',''))
        self.mic=tk.StringVar();self.status=tk.StringVar(value='Disconnected · microphone off')
        self.level=tk.DoubleVar(value=0);self.level_text=tk.StringVar(value='No audio')
        style=ttk.Style();style.theme_use('clam')
        style.configure('TFrame',background='#f4f6f5');style.configure('TLabel',background='#f4f6f5',foreground='#214c3e',font=('Segoe UI',10))
        style.configure('Title.TLabel',font=('Segoe UI',21,'bold'));style.configure('TButton',padding=8)
        frame=ttk.Frame(self.root,padding=25);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Bring your voice.',style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame,text='Native microphone capture. Chrome can stay closed.').pack(anchor='w',pady=(4,17))
        self.fields=[]
        for label,var in [('Hub address',self.address),('Room code (from host dashboard)',self.code),('Microphone name',self.name)]:
            ttk.Label(frame,text=label).pack(anchor='w')
            entry=ttk.Entry(frame,textvariable=var);entry.pack(fill='x',pady=(3,9));self.fields.append(entry)
        ttk.Label(frame,text='Microphone').pack(anchor='w')
        row=ttk.Frame(frame);row.pack(fill='x',pady=(3,9))
        self.combo=ttk.Combobox(row,textvariable=self.mic,state='readonly');self.combo.pack(side='left',fill='x',expand=True)
        self.refresh_button=ttk.Button(row,text='Refresh',command=self.refresh);self.refresh_button.pack(side='right',padx=(6,0))
        ttk.Label(frame,text='Hub public CA file (other computers using HTTPS)').pack(anchor='w')
        row=ttk.Frame(frame);row.pack(fill='x',pady=(3,8))
        entry=ttk.Entry(row,textvariable=self.ca);entry.pack(side='left',fill='x',expand=True);self.fields.append(entry)
        self.browse=ttk.Button(row,text='Browse…',command=self.browse_ca);self.browse.pack(side='right',padx=(6,0))
        ttk.Label(frame,text='This PC: http://localhost:8787\nOther PC: https://HOST-IP:8788 and the hub’s ca.crt.',font=('Segoe UI',9)).pack(anchor='w')
        ttk.Separator(frame).pack(fill='x',pady=16)
        ttk.Label(frame,textvariable=self.status,wraplength=470).pack(anchor='w')
        ttk.Progressbar(frame,variable=self.level,maximum=100).pack(fill='x',pady=(9,2))
        ttk.Label(frame,textvariable=self.level_text,font=('Segoe UI',9)).pack(anchor='w')
        row=ttk.Frame(frame);row.pack(fill='x',pady=(12,0))
        self.connect_button=ttk.Button(row,text='Connect microphone',command=self.toggle_connect);self.connect_button.pack(side='left')
        self.mute_button=ttk.Button(row,text='Mute',command=self.toggle_mute,state='disabled');self.mute_button.pack(side='left',padx=7)
        ttk.Button(row,text='Hide to tray',command=self.hide).pack(side='right')
        ttk.Label(frame,text='Closing this window keeps audio running. Right-click the tray icon to Quit.',wraplength=470,font=('Segoe UI',9)).pack(anchor='w',pady=(12,0))
        self.tray=pystray.Icon('CancelGroupMicsSender',icon_image(),'Cancel Group Mics · Disconnected',pystray.Menu(
            pystray.MenuItem('Show microphone sender',lambda:self.events.put(('show',None)),default=True),
            pystray.MenuItem('Mute / unmute',lambda:self.events.put(('mute',None))),
            pystray.MenuItem('Disconnect',lambda:self.events.put(('disconnect',None))),
            pystray.MenuItem('Quit sender',lambda:self.events.put(('quit',None)))))
        self.tray.run_detached();self.root.protocol('WM_DELETE_WINDOW',self.hide)
        self.refresh();self.root.after(100,self.poll)

    def refresh(self):
        try:
            apis=sd.query_hostapis()
            devices=[(i,d) for i,d in enumerate(sd.query_devices()) if d['max_input_channels']>0]
            devices.sort(key=lambda item:(apis[item[1]['hostapi']]['name']!='Windows WASAPI',item[0]))
            self.devices={f"{d['name']} · {apis[d['hostapi']]['name']} [{i}]":i for i,d in devices}
            self.combo['values']=list(self.devices)
            preferred=self.config.get('mic','')
            if self.mic.get() not in self.devices:self.mic.set(preferred if preferred in self.devices else next(iter(self.devices),''))
        except Exception as exc:messagebox.showerror('Microphones',str(exc))

    def browse_ca(self):
        filename=filedialog.askopenfilename(filetypes=[('Public CA certificate','*.crt *.pem'),('All files','*.*')])
        if filename:self.ca.set(filename)

    def toggle_connect(self):
        if self.active:self.disconnect();return
        try:
            if self.mic.get() not in self.devices:raise ValueError('Choose a microphone first.')
            self.worker.start(self.address.get(),self.code.get().strip(),self.name.get().strip(),self.devices[self.mic.get()],self.ca.get().strip())
            self.active=True;self.controls(True)
            self.config={'address':self.address.get(),'name':self.name.get(),'ca':self.ca.get(),'mic':self.mic.get()}
            try:
                self.config_path.parent.mkdir(parents=True,exist_ok=True)
                self.config_path.write_text(json.dumps(self.config))
            except OSError:pass
        except Exception as exc:messagebox.showerror('Could not connect',str(exc))

    def controls(self,active):
        for entry in self.fields:entry.configure(state='disabled' if active else 'normal')
        self.combo.configure(state='disabled' if active else 'readonly')
        self.refresh_button.configure(state='disabled' if active else 'normal');self.browse.configure(state='disabled' if active else 'normal')
        self.connect_button.configure(text='Disconnect' if active else 'Connect microphone')
        self.mute_button.configure(state='normal' if active else 'disabled')

    def disconnect(self):
        if self.active:
            self.worker.stop();self.status.set('Disconnecting…');self.connect_button.configure(state='disabled')

    def toggle_mute(self):
        self.worker.muted=not self.worker.muted
        self.mute_button.configure(text='Unmute' if self.worker.muted else 'Mute')

    def hide(self):self.root.withdraw()

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='show':self.root.deiconify();self.root.lift()
                elif kind=='mute':self.toggle_mute()
                elif kind=='disconnect':self.disconnect()
                elif kind=='quit':
                    self.quitting=True;self.worker.stop();self.root.withdraw()
                elif kind=='status':self.status.set(value);self.tray.title=('Cancel Group Mics · '+value)[:120]
                elif kind=='ended':
                    self.active=False;self.controls(False);self.connect_button.configure(state='normal');self.level.set(0)
                    self.level_text.set('Microphone off')
                    if self.status.get()=='Disconnecting…':self.status.set('Disconnected · microphone off')
                elif kind=='meter':
                    level=value.get('level_db',-90);self.level.set(max(0,min(100,(level+65)/65*100)))
                    label='Muted' if self.worker.muted or value.get('muted') else 'Room muted' if value.get('master_muted') else 'On air' if value.get('active') and value.get('output_running') else 'Connected · output off' if not value.get('output_running') else 'Standing by'
                    self.status.set(label);self.level_text.set(f'{level:.0f} dB');self.tray.title='Cancel Group Mics · '+label
        except queue.Empty:pass
        if self.quitting and not (self.worker.thread and self.worker.thread.is_alive()):
            self.tray.stop();self.root.destroy();return
        self.root.after(100,self.poll)

    def run(self):self.root.mainloop()


if __name__=='__main__':SenderApp().run()
