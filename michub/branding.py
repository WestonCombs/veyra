"""Resolution-independent Veyra mark rendered for native app surfaces."""
from PIL import Image, ImageDraw


def icon_image(size=64):
    image = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 248, 248), radius=62, fill='#0b1c12', outline='#245d37', width=5)
    # Two incoming signals converge into one voice: a V-shaped waveform.
    draw.line([(51, 83), (87, 83), (128, 179), (174, 68), (205, 68)],
              fill='#68ff8c', width=16, joint='curve')
    draw.ellipse((43, 75, 59, 91), fill='#baffc9')
    draw.ellipse((197, 60, 213, 76), fill='#baffc9')
    draw.line([(83, 126), (99, 126)], fill='#328c4d', width=7)
    draw.line([(163, 126), (185, 126)], fill='#328c4d', width=7)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def mic_icon(muted=False,size=24):
    im=Image.new('RGBA',(96,96),(0,0,0,0));d=ImageDraw.Draw(im);c='#ff8c98' if muted else '#68ff8c'
    d.rounded_rectangle((34,10,62,55),radius=14,outline=c,width=6)
    d.arc((23,26,73,73),0,180,fill=c,width=6);d.line((48,70,48,85),fill=c,width=6);d.line((34,85,62,85),fill=c,width=6)
    if muted:d.line((16,15,81,83),fill=c,width=8)
    return im.resize((size,size),Image.Resampling.LANCZOS)


def copy_icon(size=22):
    im=Image.new('RGBA',(80,80),(0,0,0,0));d=ImageDraw.Draw(im)
    d.rounded_rectangle((26,10,66,55),radius=5,outline='#68ff8c',width=5)
    d.rounded_rectangle((13,24,53,69),radius=5,fill='#0b1c12',outline='#68ff8c',width=5)
    return im.resize((size,size),Image.Resampling.LANCZOS)


def exit_icon(size=28):
    im=Image.new('RGBA',(96,96),(0,0,0,0));d=ImageDraw.Draw(im);c='#a9e9b9'
    d.line([(48,12),(17,12),(17,84),(48,84)],fill=c,width=6)
    d.line([(37,48),(83,48)],fill=c,width=6);d.line([(65,30),(83,48),(65,66)],fill=c,width=6)
    return im.resize((size,size),Image.Resampling.LANCZOS)


def plus_icon(size=28):
    im=Image.new('RGBA',(112,112),(0,0,0,0));d=ImageDraw.Draw(im)
    d.rounded_rectangle((49,19,62,92),radius=2,fill='#b4ffca')
    d.rounded_rectangle((19,49,92,62),radius=2,fill='#b4ffca')
    return im.resize((size,size),Image.Resampling.LANCZOS)


def refresh_icon(size=24):
    import math
    im=Image.new('RGBA',(112,112),(0,0,0,0));d=ImageDraw.Draw(im);color='#87f5a4'
    for start,end in [(25,155),(205,335)]:
        d.arc((22,22,90,90),start,end,fill=color,width=8)
        a=math.radians(end);x,y=56+34*math.cos(a),56+34*math.sin(a);tx,ty=-math.sin(a),math.cos(a)
        d.polygon([(x+tx*4,y+ty*4),(x-tx*13+math.cos(a)*10,y-ty*13+math.sin(a)*10),(x-tx*13-math.cos(a)*10,y-ty*13-math.sin(a)*10)],fill=color)
    return im.resize((size,size),Image.Resampling.LANCZOS)
