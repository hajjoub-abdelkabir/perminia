"""Local MP3 structure/metadata checks; this does not transcribe speech."""
from pathlib import Path
from mutagen.mp3 import MP3

def probe_audio(path):
    info=MP3(Path(path)).info
    if info.length<=0 or info.sample_rate<=0 or info.channels not in (1,2):
        raise ValueError('Invalid MP3 audio metadata')
    return {'duration_seconds':round(info.length,6),'audio_sample_rate':info.sample_rate,'audio_channels':info.channels}
