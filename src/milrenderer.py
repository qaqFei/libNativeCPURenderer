from __future__ import annotations

import sys
import argparse
import zipfile
import json
import io
import typing

import pydub
import tqdm
from PIL import Image

import libNativeCPURendererPybind as CPURenderer

aparser = argparse.ArgumentParser()
aparser.add_argument("--input", type=str, required=True)
aparser.add_argument("--output", type=str, required=True)
aparser.add_argument("--fps", type=int, default=60)
aparser.add_argument("--width", type=int, default=1920)
aparser.add_argument("--height", type=int, default=1080)

args = aparser.parse_args()

w, h = args.width, args.height
fps = args.fps
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

def beatval(beat: list[int]):
    return beat[0] + beat[1] / beat[2]

def tosec(beat: list[int], chart: MilChart):
    beat = beatval(beat)
    sec = chart.meta.offset

    if len(chart.bpms) == 1:
        sec += 60 / chart.bpms[0].bpm * beat
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
    
    def doease(self, p: float):
        return p
    
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

class MilAnimationCollectionGroup:
    def __init__(self, anims: list[MilAnimation], defaults: list[float]):
        self.values = defaults.copy()
        self.defaults = defaults.copy()
        self.indexs = [0 for _ in range(MAX_ANIMKEY + 1)]
        self.anim_groups = [[] for _ in range(MAX_ANIMKEY + 1)]
        self._t = -1e9

        for e in anims:
            self.anim_groups[e.type].append(e)
        
        for es in self.anim_groups:
            es.sort(key=lambda e: e.startTime)
        
        speed_es = self.anim_groups[EnumAnimationKey.Speed]
        fp = 0.0

        for e in speed_es:
            e.floorPosition = fp
            fp += (e.endTime - e.startTime) * (e.start + e.end) / 2
    
    def update(self, t: float, only: typing.Optional[int] = None):
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

            if i == EnumAnimationKey.Speed:
                if t < e.startTime: self.values[i] = t * e.start
                elif e.startTime < t <  e.endTime: self.values[i] = e.floorPosition + (t - e.startTime) * (self.values[i] + e.start) / 2
                else: self.values[i] = e.floorPosition + (e.endTime - e.startTime) * (e.start + e.end) / 2 + (t - e.endTime) * e.end
        
    def value_from_key(self, key: int):
        return self.values[key]

    @staticmethod
    def from_filter_anims(anims: list[MilAnimation], bearer_type: int, bearer: typing.Optional[int] = None):
        anims = list(filter(lambda e: e.bearer_type == bearer_type and (bearer is None or e.bearer == bearer), anims))

        return MilAnimationCollectionGroup(anims, {
            0: [
                0.0
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

class MilLine:
    def __init__(self, data: dict):
        self.animations = list(map(MilAnimation, data["animations"]))
        self.notes = list(map(MilNote, data["notes"], (self.animations, ) * len(data["notes"])))
        self.index = data["index"]

        self.notes.sort(key=lambda e: e.time)
        self.acollection = MilAnimationCollectionGroup.from_filter_anims(self.animations, EnumAnimationBearerType.Line)
    
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
    hit = CPURenderer.AudioClip.from_pydub_seg(pydub.AudioSegment.from_file("./../test_files/hit.ogg"))
    drag = CPURenderer.AudioClip.from_pydub_seg(pydub.AudioSegment.from_file("./../test_files/drag.ogg"))

    hit.resample_like(bgm)
    drag.resample_like(bgm)
    
    for line in chart.lines:
        for note in line.notes:
            if note.isFake:
                continue

            bgm.overlay(hit if note.ishit else drag, note.time, time_unit="second")

bgm = CPURenderer.AudioClip.from_pydub_seg(pydub.AudioSegment.from_file(io.BytesIO(readFile(meta["audio_file"]))))
chart = MilChart(readAsJson(meta["chart_file"]))

mixbgm(bgm)
cap.initialize(args.output, hasAudio=True, a_clip=bgm)
num_frames = int(bgm.duration * cap.frame_rate) + 1

bg_tex = CPURenderer.Texture.from_pilimg(Image.open(io.BytesIO(readFile(meta["image_file"]))))
ratio_bg = bg_tex.width / bg_tex.height
ratio_scr = cap.width / cap.height

if ratio_bg > ratio_scr:
    bg_tex = bg_tex.resample(int(cap.height / bg_tex.height * bg_tex.width), cap.height)
else:
    bg_tex = bg_tex.resample(cap.width, int(cap.width / bg_tex.width * bg_tex.height))

for frame_i in tqdm.trange(300, desc="Rendering"):
    ctx.set_color(0, 0, 0, 0)
    t = frame_i / cap.frame_rate
    chart.update(t)

    ctx.draw_texture(bg_tex, w / 2 - bg_tex.width / 2, h / 2 - bg_tex.height / 2, bg_tex.width, bg_tex.height)

    for line in chart.lines:
        ...

        for note in line.notes:
            ...

    cap.put_renderer_context_frame(ctx)

cap.release()
