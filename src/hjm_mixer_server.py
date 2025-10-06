import os
import base64
import random

import flask
import pydub

import hjm_mixer
import libNativeCPURendererPybind as CPURenderer

app = flask.Flask(__name__)

@app.route("/")
def index():
    return open("./hjm_mixer_index.html", "r", encoding="utf-8").read()

@app.route("/🐱/<min>/<max>/<dnote>/<offset>", methods=["POST"])
def req(min: int, max: int, dnote: int, offset: int):
    input_bytes = flask.request.get_data()
    input_fp = f"{random.randint(0, 1000000000)}.mid"
    output_fp = f"{random.randint(0, 1000000000)}.mp3"

    with open(input_fp, "wb") as f:
        f.write(input_bytes)
    
    try:
        os.system(f"timidity {input_fp} -Ow -o - | ffmpeg -i - -acodec libmp3lame -ab 180k {output_fp}")
        hjm_mixer.main(type("", (object, ), {
            "res": "../test_files/",
            "input": input_fp,
            "output": output_fp,
            "min_note": int(min),
            "max_note": int(max),
            "dnote": int(dnote),
            "base": CPURenderer.AudioClip.from_pydub_seg(pydub.AudioSegment.from_file(output_fp)),
            "offset": int(offset)
        })())
    except Exception as e:
        # os.remove(input_fp)
        os.remove(output_fp)
        return flask.Response(f"{e}", status=500)
    
    os.remove(input_fp)
    seg = pydub.AudioSegment.from_file(output_fp).set_frame_rate(18000)
    seg.export(output_fp, format="mp3")

    with open(output_fp, "rb") as f:
        output_bytes = f.read()
        
    os.remove(output_fp)
    return flask.Response(output_bytes, status=200)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
