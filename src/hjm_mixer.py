import argparse

import midi_parse
import pydub

import libNativeCPURendererPybind as CPURenderer

aparser = argparse.ArgumentParser()
aparser.add_argument("-i", "--input", help="input midi file", required=True)
aparser.add_argument("-o", "--output", help="output wav file", required=True)
args = aparser.parse_args()

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

max_time = msgs[-1]["sec_time"] + 1.0
bgm = CPURenderer.AudioClip.slient(FRAME_RATE, CHANNELS, int(FRAME_RATE * max_time))
nums_hjm = 15
hjm_source = CPURenderer.AudioClip.from_pydub_seg(pydub.AudioSegment.from_file("./../test_files/hjm_source.ogg"))
hjms = []

for i in range(nums_hjm):
    cuted = hjm_source.clone()
    cuted.cut(i, i + 1.0, time_unit="second")
    hjms.append(cuted)

curri = -1

std_hz = 440
for sec, et, n in notebin.result:
    hz = 440 * (2 ** ((n - 69) / 12))
    hz_gain = hz / std_hz
    curri = (curri + 1) % nums_hjm
    hjm = hjms[curri].clone()
    hjm.apply_speed(hz_gain)
    bgm.overlay(hjm, sec, time_unit="second")

with open(args.output, "wb") as f:
    f.write(bgm.save_as_wav())
