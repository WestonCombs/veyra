"""Audio-driven card colors, independent of decorative breathing phase."""
from .matrix_theme import PANEL,EDGE

def microphone_colors(level_db,selected=False,muted=False,stale=False):
 if muted or stale:return EDGE,PANEL
 value=max(0,min(1,(level_db+60)/48))
 # Preset 04 low -> Preset 04 peak -> Preset 06 peak.
 low,high,t=((39,110,59),(99,211,123),value*2) if value<.5 else ((99,211,123),(115,255,145),(value-.5)*2)
 border='#'+''.join(f'{round(a+(b-a)*t):02x}' for a,b in zip(low,high))
 return border,'#153524' if selected else PANEL
