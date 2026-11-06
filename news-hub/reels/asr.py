import subprocess
from pathlib import Path
from . import config as C

def transcribe(video:Path,out_dir:Path):
    from faster_whisper import WhisperModel
    audio=out_dir/"audio.wav"
    subprocess.run(["ffmpeg","-y","-i",str(video),"-t",str(C.MAX_VIDEO_MIN*60),
        "-vn","-ac","1","-ar","16000",str(audio)],check=True,capture_output=True,timeout=900)
    model=WhisperModel(C.WHISPER_MODEL,device="cpu",compute_type="int8")
    segments,_=model.transcribe(str(audio),language="ur",word_timestamps=True,vad_filter=True,
        beam_size=3,initial_prompt=C.WHISPER_PROMPT)
    output=[]
    for s in segments:
        words=[{"w":w.word.strip(),"start":w.start,"end":w.end} for w in (s.words or []) if w.word.strip()]
        if s.text.strip(): output.append({"start":float(s.start),"end":float(s.end),"text":s.text.strip(),"words":words})
    return output
