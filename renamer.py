import os

def f(dirname: str):
    for file in os.listdir(dirname):
        new_name = file.split("_")[0] + ".wav"
        os.rename(os.path.join(dirname, file), os.path.join(dirname, new_name))

f("./ha")
f("./ji")
f("./mi")