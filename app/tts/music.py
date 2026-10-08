"""Fondos ambientales originales, sintetizados localmente sin grabaciones externas."""
import math
import numpy as np
import soundfile as sf

MUSIC = {"calma": "Calma", "aire": "Aire", "sereno": "Sereno"}

def music_choices():
    return [{"key": "none", "label": "Sin música"}] + [
        {"key": k, "label": v} for k, v in MUSIC.items()]

def write_music(path, key, sample_rate=24000):
    if key not in MUSIC:
        raise ValueError("Música no reconocida")
    progressions = {
        "calma": [[48,55,60,64],[45,52,57,60],[41,48,53,57],[43,50,55,62]],
        "aire": [[50,57,62,66],[47,54,59,62],[43,50,55,59],[45,52,57,64]],
        "sereno": [[45,52,57,60],[41,48,53,57],[48,55,60,64],[43,50,55,59]],
    }
    # 64 segundos, con silencio en la unión para evitar chasquidos al repetir.
    n = sample_rate * 64
    audio = np.zeros((n, 2), dtype=np.float32)
    for k, chord in enumerate(progressions[key]):
        start = k * 16
        t = np.arange(16 * sample_rate) / sample_rate
        envelope = np.minimum(t/3, 1) * np.minimum((16-t)/4, 1)
        for j, note in enumerate(chord):
            freq = 440 * 2**((note-69)/12)
            wave = (np.sin(2*np.pi*freq*t) + .15*np.sin(4*np.pi*freq*t)) * envelope
            pan = .2 + .2*j
            audio[start*sample_rate:(start+16)*sample_rate, 0] += wave * math.sqrt(1-pan)
            audio[start*sample_rate:(start+16)*sample_rate, 1] += wave * math.sqrt(pan)
    audio *= 10**(-45/20) / max(float(np.sqrt(np.mean(audio**2))), 1e-9)
    sf.write(path, audio, sample_rate, subtype="PCM_16")
