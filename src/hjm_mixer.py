import argparse
import os
import typing

import midi_parse
import pydub
import tqdm
import random

import libNativeCPURendererPybind as CPURenderer

class ProgInput(typing.Protocol):
    res: str
    input: str
    output: str
    min_note: int
    max_note: int
    dnote: int
    base: typing.Optional[CPURenderer.AudioClip]
    offset: int

def main(args: ProgInput):
    with open(args.input, "rb") as f:
        mid = midi_parse.MidiFile(f.read())

    DEFAULT_NOTELENGTH = 0.1

    class MidiNoteBin:
        def __init__(self):
            self.bin: dict[int, tuple[float, int]] = {}
            self.result: list[tuple[float, float, int]] = []
        
        def add(self, msg: dict, t: float):
            msghash = hash((msg["channel"], msg["note"]))
            if msghash in self.bin:
                ont, note = self.bin.pop(msghash)
                self.result.append((ont, ont + DEFAULT_NOTELENGTH, note))

            self.bin[msghash] = (t, msg["note"])
        
        def off(self, msg: dict, t: float):
            msghash = hash((msg["channel"], msg["note"]))
            if msghash not in self.bin: return
            
            ont, note = self.bin.pop(msghash)
            self.result.append((ont, t, note))
        
        def flush(self):
            for ont, note in self.bin.values():
                self.result.append((ont, ont + DEFAULT_NOTELENGTH, note))
            self.bin.clear()

    notebin = MidiNoteBin()

    for track in mid.tracks:
        for msg in track:
            if msg["type"] == "note_on": notebin.add(msg, msg["sec_time"])
            elif msg["type"] == "note_off": notebin.off(msg, msg["sec_time"])

    notebin.flush()
    notebin.result.sort(key=lambda x: x[0])

    FRAME_RATE = 44100
    CHANNELS = 2

    max_time = notebin.result[-1][0] + 1.0
    bgm = CPURenderer.AudioClip.slient(FRAME_RATE, CHANNELS, int(FRAME_RATE * max_time)) if args.base is None else args.base
    hjms = []

    for name in ("ha", "ji", "mi"):
        hjms.append([])

        for i in range(12, 144):
            hjms[-1].append(CPURenderer.AudioClip.from_pydub_seg(pydub.AudioSegment.from_file(os.path.join(args.res, name, f"{i}.wav"))))
        
        for i in hjms[-1]:
            i.resample_like(bgm)

    curri = -1
    lastsec = -1e9

    for sec, et, n in tqdm.tqdm(notebin.result):
        n += args.dnote
        sec += args.offset / 1000
        if sec != lastsec:
            curri += 1
            lastsec = sec
        
        if n < args.min_note or n > args.max_note:
            continue

        curri = curri % len(hjms)
        hjm = hjms[curri][n]
        bgm.overlay(hjm, sec, time_unit="second")

    with open(args.output, "wb") as f:
        f.write(bgm.save_as_wav())

if __name__ == "__main__":
    aparser = argparse.ArgumentParser()
    aparser.add_argument("-r", "--res", type=str, help="res file", required=True)
    aparser.add_argument("-i", "--input", help="input midi file", required=True)
    aparser.add_argument("-o", "--output", help="output wav file", required=True)
    aparser.add_argument("-min", "--min-note", help="min note", type=int, default=60)
    aparser.add_argument("-max", "--max-note", help="max note", type=int, default=127)
    aparser.add_argument("-d", "--dnote", help="dnote", type=int, default=0)
    aparser.add_argument("-o", "--offset", help="offset", type=int, default=0)
    args = aparser.parse_args()

    args.base = None
    main(args)
