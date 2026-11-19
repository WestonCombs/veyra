"""Shared, graded glow states without geometry changes or extra animation timers."""
import tkinter as tk
from tkinter import ttk
from .matrix_theme import PANEL,TEXT,GREEN,EDGE

def shade(low,high,phase):
 return '#'+''.join(f'{int(a+(b-a)*phase):02x}' for a,b in zip(low,high))

class GlowTheme:
 def __init__(self,app):
  self.app=app;self.hover=None;self.focus=None;self.buttons=set();self.styles={}
  app.root.bind('<Enter>',self.enter,add='+');app.root.bind('<Leave>',self.leave,add='+')
  app.root.bind('<FocusIn>',self.focus_in,add='+');app.root.bind('<FocusOut>',self.focus_out,add='+')
 def eligible(self,w):
  return isinstance(w,tk.Button) and not getattr(w,'own_glow',False) and w is not self.app.big and w not in self.app.nav_buttons
 def enter(self,e):
  if self.eligible(e.widget):self.hover=e.widget;self.buttons.add(e.widget)
 def leave(self,e):
  if self.hover is e.widget:self.hover=None
 def focus_in(self,e):
  w=e.widget
  if isinstance(w,(ttk.Entry,ttk.Combobox,ttk.Scale)):
   self.focus=w
   if w not in self.styles:
    base=w.cget('style') or w.winfo_class();name=f'Glow{id(w)}.{base}';self.styles[w]=name;w.configure(style=name)
 def focus_out(self,e):
  if self.focus is e.widget:self.focus=None
 def update(self,p):
  self.buttons.add(self.app.advanced_button)
  for b in list(self.buttons):
   if not b.winfo_exists():self.buttons.discard(b);continue
   if not self.eligible(b):continue
   # Persistent section toggles are intentionally darker than action hovers.
   always=b is self.app.advanced_button
   hover=b is self.hover and str(b.cget('state'))!='disabled'
   fill=shade((15,39,24),(25,67,37),p) if hover else shade((10,29,18),(16,43,26),p) if always else PANEL
   edge=shade((37,89,51),(62,143,78),p) if hover else shade((20,51,31),(30,77,43),p) if always else EDGE
   b.configure(bg=fill,activebackground=fill,fg=TEXT if hover else GREEN,activeforeground=TEXT,highlightbackground=edge,highlightcolor=edge)
  for w,name in list(self.styles.items()):
   if not w.winfo_exists():del self.styles[w];continue
   focused=w is self.focus
   # Fields keep a quiet fill; keyboard focus gets a crisp brighter rim.
   border=shade((39,110,59),(99,211,123),p) if focused else EDGE
   self.app.style.configure(name,bordercolor=border,lightcolor=border,darkcolor=border)
   self.app.style.map(name,bordercolor=[('focus',border)],lightcolor=[('focus',border)],darkcolor=[('focus',border)])
  self.app.style.map('TCheckbutton',background=[('active','#102d1c'),('selected',shade((8,24,15),(13,34,21),p))],foreground=[('disabled','#8aaa96'),('active','#ffffff'),('selected',TEXT)],indicatorbackground=[('selected',shade((26,76,40),(45,122,61),p)),('active','#1d4c2e')])
