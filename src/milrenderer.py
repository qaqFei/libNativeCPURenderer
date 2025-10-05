from __future__ import annotations

import sys
import argparse
import zipfile
import json
import io
import typing
import logging
import math

import pydub
import tqdm
from PIL import Image

import libNativeCPURendererPybind as CPURenderer

aparser = argparse.ArgumentParser()
aparser.add_argument("-r", "--res", type=str, required=True)
aparser.add_argument("-i", "--input", type=str, required=True)
aparser.add_argument("-o", "--output", type=str, required=True)
aparser.add_argument("-f", "--fps", type=int, default=60)
aparser.add_argument("-s-w", "--width", type=int, default=1920)
aparser.add_argument("-s-h", "--height", type=int, default=1080)
aparser.add_argument("-ns", "--note-scale", type=float, default=1.0)
aparser.add_argument("-d", "--debug", action="store_true")
aparser.add_argument("-sl", "--silent", action="store_true")

args = aparser.parse_args()

logging.basicConfig(
    level = logging.INFO if not args.debug else logging.DEBUG,
    format = "[%(asctime)s] %(levelname)s %(funcName)s: %(message)s",
    datefmt = "%H:%M:%S"
)

w, h = args.width, args.height
fps = args.fps
logging.info(f"output video size: {w}x{h}")
logging.info(f"output video fps: {fps}")
logging.info(f"output video file: {args.output}")

MIL_SCRW = 1920
MIL_SCRH = 1080
logging.debug(f"{MIL_SCRW=}, {MIL_SCRH=}")

LINE_CIRCLE_WIDTH = 0.003
LINE_HEAD_SIZE = 0.0223 * args.note_scale
LINE_HEAD_BORDER = LINE_HEAD_SIZE * (18 / 186)
NOTE_SIZE = LINE_HEAD_SIZE
NOTE_SCALE = 335 / 185
logging.debug(f"{LINE_CIRCLE_WIDTH=}, {LINE_HEAD_SIZE=}")
logging.debug(f"{LINE_HEAD_BORDER=}, {NOTE_SIZE=}, {NOTE_SCALE=}")

easings: list[list[typing.Callable[[float], float]]] = [
    [
        lambda t: t, # linear
        lambda t: 1 - math.cos((t * math.pi) / 2), # in sine
        lambda t: t ** 2, # in quad
        lambda t: t ** 3, # in cubic
        lambda t: t ** 4, # in quart
        lambda t: t ** 5, # in quint
        lambda t: 0 if t == 0 else 2 ** (10 * t - 10), # in expo
        lambda t: 1 - (1 - t ** 2) ** 0.5, # in circ
        lambda t: 2.70158 * (t ** 3) - 1.70158 * (t ** 2), # in back
        lambda t: 0 if t == 0 else (1 if t == 1 else - 2 ** (10 * t - 10) * math.sin((t * 10 - 10.75) * (2 * math.pi / 3))), # in elastic
        lambda t: 1 - (7.5625 * ((1 - t) ** 2) if ((1 - t) < 1 / 2.75) else (7.5625 * ((1 - t) - (1.5 / 2.75)) * ((1 - t) - (1.5 / 2.75)) + 0.75 if ((1 - t) < 2 / 2.75) else (7.5625 * ((1 - t) - (2.25 / 2.75)) * ((1 - t) - (2.25 / 2.75)) + 0.9375 if ((1 - t) < 2.5 / 2.75) else (7.5625 * ((1 - t) - (2.625 / 2.75)) * ((1 - t) - (2.625 / 2.75)) + 0.984375)))), # in bounce
    ],
    [
        lambda t: t, # linear
        lambda t: math.sin((t * math.pi) / 2), # out sine
        lambda t: 1 - (1 - t) * (1 - t), # out quad
        lambda t: 1 - (1 - t) ** 3, # out cubic
        lambda t: 1 - (1 - t) ** 4, # out quart
        lambda t: 1 - (1 - t) ** 5, # out quint
        lambda t: 1 if t == 1 else 1 - 2 ** (-10 * t), # out expo
        lambda t: (1 - (t - 1) ** 2) ** 0.5, # out circ
        lambda t: 1 + 2.70158 * ((t - 1) ** 3) + 1.70158 * ((t - 1) ** 2), # out back
        lambda t: 0 if t == 0 else (1 if t == 1 else 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1), # out elastic
        lambda t: 7.5625 * (t ** 2) if (t < 1 / 2.75) else (7.5625 * (t - (1.5 / 2.75)) * (t - (1.5 / 2.75)) + 0.75 if (t < 2 / 2.75) else (7.5625 * (t - (2.25 / 2.75)) * (t - (2.25 / 2.75)) + 0.9375 if (t < 2.5 / 2.75) else (7.5625 * (t - (2.625 / 2.75)) * (t - (2.625 / 2.75)) + 0.984375))), # out bounce
    ],
    [
        lambda t: t, # linear
        lambda t: -(math.cos(math.pi * t) - 1) / 2, # io sine
        lambda t: 2 * (t ** 2) if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2, # io quad
        lambda t: 4 * (t ** 3) if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2, # io cubic
        lambda t: 8 * (t ** 4) if t < 0.5 else 1 - (-2 * t + 2) ** 4 / 2, # io quart
        lambda t: 16 * (t ** 5) if t < 0.5 else 1 - ((-2 * t + 2) ** 5) / 2, # io quint
        lambda t: 0 if t == 0 else (1 if t == 1 else (2 ** (20 * t - 10) if t < 0.5 else (2 - 2 ** (-20 * t + 10))) / 2), # io expo
        lambda t: (1 - (1 - (2 * t) ** 2) ** 0.5) / 2 if t < 0.5 else (((1 - (-2 * t + 2) ** 2) ** 0.5) + 1) / 2, # io circ
        lambda t: ((2 * t) ** 2 * ((2.5949095 + 1) * 2 * t - 2.5949095)) / 2 if t < 0.5 else ((2 * t - 2) ** 2 * ((2.5949095 + 1) * (t * 2 - 2) + 2.5949095) + 2) / 2, # io back
        lambda t: 0 if t == 0 else (1 if t == 0 else (-2 ** (20 * t - 10) * math.sin((20 * t - 11.125) * ((2 * math.pi) / 4.5))) / 2 if t < 0.5 else (2 ** (-20 * t + 10) * math.sin((20 * t - 11.125) * ((2 * math.pi) / 4.5))) / 2 + 1), # io elastic
        lambda t: (1 - (7.5625 * ((1 - 2 * t) ** 2) if ((1 - 2 * t) < 1 / 2.75) else (7.5625 * ((1 - 2 * t) - (1.5 / 2.75)) * ((1 - 2 * t) - (1.5 / 2.75)) + 0.75 if ((1 - 2 * t) < 2 / 2.75) else (7.5625 * ((1 - 2 * t) - (2.25 / 2.75)) * ((1 - 2 * t) - (2.25 / 2.75)) + 0.9375 if ((1 - 2 * t) < 2.5 / 2.75) else (7.5625 * ((1 - 2 * t) - (2.625 / 2.75)) * ((1 - 2 * t) - (2.625 / 2.75)) + 0.984375))))) / 2 if t < 0.5 else (1 +(7.5625 * ((2 * t - 1) ** 2) if ((2 * t - 1) < 1 / 2.75) else (7.5625 * ((2 * t - 1) - (1.5 / 2.75)) * ((2 * t - 1) - (1.5 / 2.75)) + 0.75 if ((2 * t - 1) < 2 / 2.75) else (7.5625 * ((2 * t - 1) - (2.25 / 2.75)) * ((2 * t - 1) - (2.25 / 2.75)) + 0.9375 if ((2 * t - 1) < 2.5 / 2.75) else (7.5625 * ((2 * t - 1) - (2.625 / 2.75)) * ((2 * t - 1) - (2.625 / 2.75)) + 0.984375))))) / 2, # io bounce
    ]
]

logging.info("creating render context")
ctx = CPURenderer.RenderContext(w, h, enable_alpha=True)
cap = CPURenderer.VideoCap(w, h, fps)

def error(msg: str):
    print(f"Error: {msg}")
    sys.exit(1)

try:
    chart_zip = zipfile.ZipFile(args.input, "r")
except Exception as e:
    error(f"Failed to open chart file: {e}")

def normZipPath(path: str):
    path = path.replace("\\", "/")
    if path.startswith("/"):
        return path[1:]
    return path

def hasFile(path: str):
    path = normZipPath(path)
    for f in chart_zip.namelist():
        if f == path:
            return True
    return False

def readFile(path: str):
    path = normZipPath(path)
    if not hasFile(path):
        error(f"File {path} not found in chart file")
    return chart_zip.read(path)

def readAsJson(path: str):
    return json.loads(readFile(path))

def getResPath(path: str):
    return f"{args.res}/{path}"

def milpos2scrpos(x: float, y: float):
    return (
        (x / MIL_SCRW + 0.5) * w,
        (1 - (y / MIL_SCRH + 0.5)) * h
    )

def milpos2scrpos_cen(x: float, y: float):
    return (
        (x / MIL_SCRW) * w,
        (y / MIL_SCRH) * h * -1
    )

def beatval(beat: list[int]):
    return beat[0] + beat[1] / beat[2]

def tosec(t: list[int], chart: MilChart):
    t = beatval(t)
    sec = chart.meta.offset

    if len(chart.bpms) == 1:
        sec += 60 / chart.bpms[0].bpm * t
    else:
        for i, e in enumerate(chart.bpms):
            if i != len(chart.bpms) - 1:
                et_beat = chart.bpms[i + 1].time - e.time
                
                if t >= et_beat:
                    sec += et_beat * (60 / e.bpm)
                    t -= et_beat
                else:
                    sec += t * (60 / e.bpm)
                    break
            else:
                sec += t * (60 / e.bpm)

    return sec

tosec: typing.Callable[[list[int]], float]

def num2rgba(v: int|float):
    v = int(v)
    return (
        (v >> 24) & 0xFF,
        (v >> 16) & 0xFF,
        (v >> 8) & 0xFF,
        v & 0xFF
    )

def rotate_point(x: float, y: float, deg: float, l: float):
    r = math.radians(deg)
    c = math.cos(r)
    s = math.sin(r)
    return (
        x + c * l,
        y + s * l
    )

class EnumAnimationKey:
    Unknown = -1
    
    PositionX = 0
    PositionY = 1
    Transparency = 2
    Size = 3
    Rotation = 4
    FlowSpeed = 5
    RelativeX = 6
    RelativeY = 7
    LineBodyTransparency = 8
    LineHeadTransparency = 9
    StoryBoardWidth = 10
    StoryBoardHeight = 11
    Speed = 12
    WholeTransparency = 13
    StoryBoardLeftBottomX = 14
    StoryBoardLeftBottomY = 15
    StoryBoardRightBottomX = 16
    StoryBoardRightBottomY = 17
    StoryBoardLeftTopX = 18
    StoryBoardLeftTopY = 19
    StoryBoardRightTopX = 20
    StoryBoardRightTopY = 21
    Color = 22
    VisibleArea = 23

class EnumAnimationBearerType:
    Unknown = -1
    
    Line = 0
    Note = 1
    StoryBoard = 2

class EnumNoteType:
    Hit = 0
    Drag = 1

MAX_ANIMKEY = EnumAnimationKey.VisibleArea

class ChartMeta:
    def __init__(self, data: dict):
        self.background_dim = data["background_dim"]
        self.name = data["name"]
        self.background_artist = data["background_artist"]
        self.music_artist = data["music_artist"]
        self.charter = data["charter"]
        self.difficulty_name = data["difficulty_name"]
        self.difficulty = data["difficulty"]
        self.offset = data["offset"]

class BPMEvent:
    def __init__(self, data: dict):
        self.time = beatval(data["time"])
        self.bpm = data["bpm"]

class MilNote:
    def __init__(self, data: dict, master_anims: list[MilAnimation]):
        self.time = tosec(data["time"])
        self.type = data["type"]
        self.isFake = data["isFake"]
        self.isAlwaysPerfect = data["isAlwaysPerfect"]
        self.endTime = tosec(data["endTime"])
        self.index = data["index"]

        self.acollection = MilAnimationCollectionGroup.from_filter_anims(master_anims, EnumAnimationBearerType.Note, self.index)
        self.ishit = self.type == EnumNoteType.Hit
        self.ishold = self.ishit and self.endTime > self.time
        self.master: typing.Optional[MilLine] = None
        self.floorPosition = 0.0
        self.endFloorPosition = 0.0
    
    def init(self):
        assert isinstance(self.master, MilLine), "master is not set"
        
        self.master.acollection.update(self.time, only=EnumAnimationKey.Speed)
        self.floorPosition = self.master.acollection.get_value(EnumAnimationKey.Speed)
        self.master.acollection.update(self.endTime, only=EnumAnimationKey.Speed)
        self.endFloorPosition = self.master.acollection.get_value(EnumAnimationKey.Speed)
    
    def update(self, t: float):
        self.acollection.update(t)

class MilEase:
    def __init__(self, data: dict):
        self.type = data["type"]
        self.press = data["press"]
        self.isValueExp = data["isValueExp"]
        self.cusValueExp = data["cusValueExp"]
        self.clipLeft = data["clipLeft"]
        self.clipRight = data["clipRight"]

        if not self.isValueExp:
            try:
                self.doease = easings[self.type][self.press]
            except IndexError:
                self.doease = easings[0][0]
        else:
            self.doease = lambda p: p
    
    def interplate(self, p: float, start: float, end: float, etype: int):
        is_color = etype == EnumAnimationKey.Color
        p = self.doease(p)

        if not is_color:
            return start + (end - start) * p
        else:
            s_color = num2rgba(start)
            e_color = num2rgba(end)
            r = s_color[0] + (e_color[0] - s_color[0]) * p
            g = s_color[1] + (e_color[1] - s_color[1]) * p
            b = s_color[2] + (e_color[2] - s_color[2]) * p
            a = s_color[3] + (e_color[3] - s_color[3]) * p
            return (r, g, b, a)

class MilAnimation:
    def __init__(self, data: dict):
        self.startTime = tosec(data["startTime"])
        self.endTime = tosec(data["endTime"])
        self.type = data["type"]
        self.start = data["start"]
        self.end = data["end"]
        self.index = data["index"]
        self.bearer_type = data["bearer_type"]
        self.bearer = data["bearer"]
        self.ease = MilEase(data["ease"])
        self.index = data["index"]

        self.floorPosition = 0
    
    def interplate(self, t: float):
        p = 1 if self.startTime == self.endTime else (t - self.startTime) / (self.endTime - self.startTime)
        p = max(0, min(1, p))
        res = self.ease.interplate(p, self.start, self.end, self.type)
        return res

ss = []
class MilAnimationCollectionGroup:
    def __init__(self, anims: list[MilAnimation], defaults: list[float]):
        self.values = defaults.copy()
        self.defaults = defaults.copy()
        self.indexs = [0 for _ in range(MAX_ANIMKEY + 1)]
        self.anim_groups = [[] for _ in range(MAX_ANIMKEY + 1)]
        self._t = 0

        for e in anims:
            self.anim_groups[e.type].append(e)
            ss.append(e.startTime)
        
        for es in self.anim_groups:
            es.sort(key=lambda e: e.startTime)
        
        speed_es = self.anim_groups[EnumAnimationKey.Speed]
        fp = 0.0

        for e in speed_es:
            e.floorPosition = fp
            fp += (e.endTime - e.startTime) * (e.start + e.end) / 2
        
        self.is_effect_opt = any(map(lambda k: self.anim_groups(k), (
            EnumAnimationKey.PositionX,
            EnumAnimationKey.PositionY,
            EnumAnimationKey.Size,
            EnumAnimationKey.Rotation,
            EnumAnimationKey.FlowSpeed,
            EnumAnimationKey.RelativeX,
            EnumAnimationKey.RelativeY,
            EnumAnimationKey.Speed
        )))
    
    def update(self, t: float, *, only: typing.Optional[int] = None):
        if t < self._t:
            self.indexs = [0 for _ in range(MAX_ANIMKEY + 1)]
        
        self._t = t

        for i, es in enumerate(self.anim_groups):
            if len(es) == 0 or (only is not None and i != only):
                if i == EnumAnimationKey.Speed and (only == -1 or only == EnumAnimationKey.Speed):
                    self.values[i] = t * self.defaults[i]
                continue
            
            while self.indexs[i] < len(es) - 1 and es[self.indexs[i] + 1].startTime <= t:
                self.indexs[i] += 1
            
            e = es[self.indexs[i]]
            self.values[i] = e.interplate(t)

            # if i == EnumAnimationKey.Speed:
            #     if t < e.startTime: self.values[i] = t * e.start
            #     elif e.startTime < t <  e.endTime: self.values[i] = e.floorPosition + (t - e.startTime) * (self.values[i] + e.start) / 2
            #     else: self.values[i] = e.floorPosition + (e.endTime - e.startTime) * (e.start + e.end) / 2 + (t - e.endTime) * e.end
    
    def get_value(self, key: int):
        return self.values[key]

    @staticmethod
    def from_filter_anims(anims: list[MilAnimation], bearer_type: int, bearer: typing.Optional[int] = None):
        anims = list(filter(lambda e: e.bearer_type == bearer_type and (bearer is None or e.bearer == bearer), anims))

        return MilAnimationCollectionGroup(anims, {
            0: [
                0.0,
                -350.0,
                1.0,
                1.0,
                90.0,
                1.0,
                0.0,
                0.0,
                1.0,
                1.0,
                0.0,
                0.0,
                1.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                (255, 255, 255, 255),
                float("inf"),
            ],
            1: [
                0.0,
                0.0,
                1.0,
                1.0,
                0.0,
                1.0,
                0.0,
                0.0,
                1.0,
                1.0,
                0.0,
                0.0,
                1.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                (255, 255, 255, 255),
                0.0,
            ],
            2: [
                0.0,
                0.0,
                0.0,
                1.0,
                0.0,
                1.0,
                0.0,
                0.0,
                1.0,
                1.0,
                1.0,
                1.0,
                1.0,
                1.0,
                -0.5,
                0.5,
                0.5,
                0.5,
                -0.5,
                -0.5,
                0.5,
                -0.5,
                (255, 255, 255, 255),
                float("inf"),
            ]
        }[bearer_type])


T = typing.TypeVar("")
class IterRemovableList(typing.Generic[T]):
    def __init__(self, lst: list[T], *, can_break: bool = True):
        self.head: typing.Optional[Node[T]] = None
        self.tail: typing.Optional[Node[T]] = None
        self._build_linked_list(lst)
        self.current: typing.Optional[Node[T]] = None
        self.can_break = can_break

    def _build_linked_list(self, lst: list[T]) -> None:
        prev_node = None
        for item in lst:
            new_node = Node(item)
            if not self.head:
                self.head = new_node
            if prev_node:
                prev_node.next = new_node
                new_node.prev = prev_node
            prev_node = new_node
        self.tail = prev_node

    def __iter__(self) -> typing.Iterator[tuple[T, typing.Callable[[], None]]]:
        self.current = self.head
        return self

    def __next__(self) -> tuple[T, typing.Callable[[], None]]:
        if self.current is None:
            raise StopIteration
        
        current_node = self.current
        self.current = current_node.next
        
        def remove_callback() -> None:
            prev_node = current_node.prev
            next_node = current_node.next
            
            if prev_node:
                prev_node.next = next_node
            else:
                self.head = next_node
            
            if next_node:
                next_node.prev = prev_node
            else:
                self.tail = prev_node
        
        return current_node.value, remove_callback
    
    def append(self, i: T):
        new = Node(i)
        new.prev = self.tail
        new.next = None
        
        if self.tail is None:
            self.head = new
            self.tail = new
        else:
            self.tail.next = new
            self.tail = new

class MilLine:
    def __init__(self, data: dict):
        self.animations = list(map(MilAnimation, data["animations"]))
        self.notes = list(map(MilNote, data["notes"], (self.animations, ) * len(data["notes"])))
        self.index = data["index"]

        self.notes.sort(key=lambda e: e.time)
        self.acollection = MilAnimationCollectionGroup.from_filter_anims(self.animations, EnumAnimationBearerType.Line)
        self.note_groups = [IterRemovableList(can_break=False), IterRemovableList(can_break=True)]

        for note in self.notes:
            if note.acollection.is_effect_opt:
                self.note_groups[0].append(note)
            else:
                self.note_groups[1].append(note)
    
    def init(self):
        for n in self.notes:
            n.master = self
            n.init()
    
    def update(self, t: float):
        self.acollection.update(t)

        for n in self.notes:
            n.update(t)

class MilChart:
    def __init__(self, data: dict):
        if data["fmt"] != 2:
            raise ValueError(f"Unsupported chart format: {data['fmt']}")

        self.meta = ChartMeta(data["meta"])
        self.bpms = list(map(BPMEvent, data["bpms"]))
        self.bpms.sort(key=lambda e: e.time)

        global tosec
        rtosec = tosec
        tosec = lambda beat: rtosec(beat, self)

        self.lines = list(map(MilLine, data["lines"]))
        self.lines.sort(key=lambda e: e.index)

        self.init()
    
    def init(self):
        for l in self.lines:
            l.init()
    
    def update(self, t: float):
        for l in self.lines:
            l.update(t)

if not hasFile("/meta.json"):
    error(f"{args.input} is not a valid chart file, /meta.json not found")

meta = readAsJson("/meta.json")

if not isinstance(meta, dict):
    error(f"{args.input} is not a valid chart file, /meta.json is not a valid dict object")

for n in ("chart_file", "audio_file", "image_file"):
    if n not in meta:
        error(f"{args.input} is not a valid chart file, /meta.json is missing required field {n}")
    
    if not hasFile(meta[n]):
        error(f"{args.input} is not a valid chart file, {meta[n]} not found in chart file")

def mixbgm(bgm: CPURenderer.AudioClip):
    hit = CPURenderer.AudioClip.from_pydub_seg(pydub.AudioSegment.from_file(getResPath("hit.ogg")))
    drag = CPURenderer.AudioClip.from_pydub_seg(pydub.AudioSegment.from_file(getResPath("drag.ogg")))

    hit.resample_like(bgm)
    drag.resample_like(bgm)
    
    for line in chart.lines:
        for note in line.notes:
            if note.isFake:
                continue

            bgm.overlay(hit if note.ishit else drag, note.time, time_unit="second")

logging.info("loading audio file")
bgm = CPURenderer.AudioClip.from_pydub_seg(pydub.AudioSegment.from_file(io.BytesIO(readFile(meta["audio_file"]))))

logging.info("loading chart file")
chart = MilChart(readAsJson(meta["chart_file"]))

logging.info("mixing bgm")
mixbgm(bgm)

logging.info("initializing video cap")
cap.initialize(args.output, hasAudio=not args.silent, a_clip=bgm)
num_frames = int(bgm.duration * cap.frame_rate) + 1

logging.info("resizing bg image")
bg_tex = CPURenderer.Texture.from_pilimg(Image.open(io.BytesIO(readFile(meta["image_file"]))))
ratio_bg = bg_tex.width / bg_tex.height
ratio_scr = cap.width / cap.height

if ratio_bg > ratio_scr:
    bg_tex = bg_tex.resample(int(cap.height / bg_tex.height * bg_tex.width), cap.height)
else:
    bg_tex = bg_tex.resample(cap.width, int(cap.width / bg_tex.width * bg_tex.height))

logging.debug(f"bg_tex: {bg_tex.width}x{bg_tex.height}")

logging.info("loading game textures")
game_res = {
    "tap": CPURenderer.Texture.from_pilimg(Image.open(getResPath("tap.png"))),
    "tap_double": CPURenderer.Texture.from_pilimg(Image.open(getResPath("tap_double.png"))),
    "extap": CPURenderer.Texture.from_pilimg(Image.open(getResPath("extap.png"))),
    "extap_double": CPURenderer.Texture.from_pilimg(Image.open(getResPath("extap_double.png"))),
    "hold": CPURenderer.Texture.from_pilimg(Image.open(getResPath("hold.png"))),
    "hold_double": CPURenderer.Texture.from_pilimg(Image.open(getResPath("hold_double.png"))),
    "exhold": CPURenderer.Texture.from_pilimg(Image.open(getResPath("exhold.png"))),
    "exhold_double": CPURenderer.Texture.from_pilimg(Image.open(getResPath("exhold_double.png"))),
    "drag": CPURenderer.Texture.from_pilimg(Image.open(getResPath("drag.png"))),
    "drag_double": CPURenderer.Texture.from_pilimg(Image.open(getResPath("drag_double.png"))),
    "line_head": CPURenderer.Texture.from_pilimg(Image.open(getResPath("line_head.png"))),
}

logging.info("rendering")

for frame_i in tqdm.trange(300, desc="Rendering"):
    ctx.set_color(0, 0, 0, 0)
    t = frame_i / cap.frame_rate
    chart.update(t)

    ctx.draw_texture(bg_tex, w / 2 - bg_tex.width / 2, h / 2 - bg_tex.height / 2, bg_tex.width, bg_tex.height)
    ctx.fill_color(0, 0, 0, chart.meta.background_dim)
    ctx.draw_vertical_mut_grd(0, h * 0.6, w, h * 0.4, [
        (0.0, (0, 0, 0, 0.0)),
        (0.25, (0, 0, 0, 0.3)),
        (0.5, (0, 0, 0, 0.6)),
        (0.75, (0, 0, 0, 0.9)),
        (1.0, (0, 0, 0, 1.0)),
    ])

    for line in chart.lines:
        linePos = milpos2scrpos(line.acollection.get_value(EnumAnimationKey.PositionX), line.acollection.get_value(EnumAnimationKey.PositionY))
        lineTransp = line.acollection.get_value(EnumAnimationKey.Transparency)
        lineSize = line.acollection.get_value(EnumAnimationKey.Size)
        lineRot = line.acollection.get_value(EnumAnimationKey.Rotation)
        lineFsp = line.acollection.get_value(EnumAnimationKey.FlowSpeed)
        lineRelPos = milpos2scrpos_cen(line.acollection.get_value(EnumAnimationKey.RelativeX), line.acollection.get_value(EnumAnimationKey.RelativeY))
        lineHeadTransp = line.acollection.get_value(EnumAnimationKey.LineHeadTransparency)
        lineBodyTransp = line.acollection.get_value(EnumAnimationKey.LineBodyTransparency)
        noteWholeTransp = line.acollection.get_value(EnumAnimationKey.WholeTransparency)
        lineColor = line.acollection.get_value(EnumAnimationKey.Color)
        lineVisa = line.acollection.get_value(EnumAnimationKey.VisibleArea)
        lineFp = line.acollection.get_value(EnumAnimationKey.Speed)
        lineCen = (linePos[0] + lineRelPos[0], linePos[1] + lineRelPos[1])
        lineColor = tuple(map(lambda x: x / 255, lineColor))

        lineHeadPxSize = (w + h) * LINE_HEAD_SIZE * lineSize
        lineHeadPxBorder = (w + h) * LINE_HEAD_BORDER * lineSize

        if lineSize > 0.0:
            ctx.save_state()
            ctx.apply_color_transform(*lineColor)
            ctx.apply_color_transform(1, 1, 1, lineTransp * lineHeadTransp)
            ctx.draw_texture(
                game_res["line_head"],
                lineCen[0] - lineHeadPxSize / 2,
                lineCen[1] - lineHeadPxSize / 2,
                lineHeadPxSize, lineHeadPxSize,
            )
            ctx.restore_state()

            ctx.save_state()
            ctx.apply_color_transform(*lineColor)
            ctx.apply_color_transform(1, 1, 1, lineTransp * lineBodyTransp)
            lineBodyP1 = rotate_point(*lineCen, lineRot + 180, max(lineHeadPxSize / 2 - 1.0, 0.0))
            lineBodyP2 = rotate_point(*lineBodyP1, lineRot + 180, h * 2.5)
            ctx.draw_line(*lineBodyP1, *lineBodyP2, lineHeadPxBorder * 0.75, 1, 1, 1, 0.8)
            ctx.restore_state()
        
        ctx.save_state()
        ctx.translate(*lineCen)
        ctx.rotate(lineRot)
        for ngroup in line.note_groups:
            for rm, note in ngroup:
                noteClicked = note.time <= t
                noteCurrFp = note.floorPosition - lineFp
                noteRelPos = milpos2scrpos_cen(note.acollection.get_value(EnumAnimationKey.RelativeX), note.acollection.get_value(EnumAnimationKey.RelativeY))
                notePos = (0, -noteCurrFp)

                if note.ishold and noteClicked:
                    notePos = (0, 0)
                
                if note.acollection.anim_groups[EnumAnimationKey.PositionX]:
                    notePos = (note.acollection.get_value(EnumAnimationKey.PositionX) / MIL_SCRW * w, notePos[1])
                
                if note.acollection.anim_groups[EnumAnimationKey.PositionY]:
                    notePos = (notePos[0], note.acollection.get_value(EnumAnimationKey.PositionY) / MIL_SCRH * h)
                
                notePos = (notePos[0] + noteRelPos[0], notePos[1] + noteRelPos[1])

        ctx.restore_state()

    cap.put_renderer_context_frame(ctx)

cap.release()
