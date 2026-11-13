"""Original offline instrumental compositions. Requires numpy for asset preparation only."""
import json
import subprocess
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'instance/audio-library/music'
RATE, SECONDS = 24000, 120


def compose(key, tempo, chords, melody, seed):
    target = DIRECTORY / (key + '.m4a')
    if target.exists():
        return
    count = RATE * SECONDS
    left = np.zeros(count, dtype=np.float64)
    right = np.zeros(count, dtype=np.float64)
    random = np.random.default_rng(seed)

    def note(at, midi, strength, length=5.5, pan=0.0):
        offset = int(at * RATE)
        if offset >= count:
            return
        length = min(int(length * RATE), count-offset)
        time = np.arange(length) / RATE
        frequency = 440 * 2**((midi-69)/12)
        # Warm, rounded struck-string timbre, with a soft attack and long damped tail.
        envelope = (1-np.exp(-time*27)) * np.exp(-time/2.0) * np.minimum(1, (length/RATE-time)/0.1)
        sound = sum(weight * np.sin(2*np.pi*frequency*harmonic*time) * np.exp(-time*harmonic*0.055)
                    for harmonic,weight in ((1,1),(2,0.19),(3,0.055),(4,0.012)))
        sound *= envelope * strength
        left[offset:offset+length] += sound * (0.65-pan*0.2)
        right[offset:offset+length] += sound * (0.65+pan*0.2)
        for delay,volume in ((0.21,0.15),(0.43,0.09),(0.71,0.045)):
            start = offset+int(delay*RATE)
            size = min(length,count-start)
            if size>0:
                left[start:start+size] += sound[:size]*volume*(0.8 if pan>0 else 1)
                right[start:start+size] += sound[:size]*volume*(1 if pan>0 else 0.8)

    beat = 60/tempo
    for bar in range(int(SECONDS/(beat*4))+1):
        chord = chords[bar%len(chords)]
        start = bar*beat*4
        note(start,chord[0]-12,0.095,length=8,pan=-0.2)
        for position,index in enumerate((0,2,1,3)):
            note(start+position*beat+random.uniform(0,0.035),chord[index],0.055+random.uniform(0,0.012),pan=(-0.45 if position%2 else 0.45))
        if bar%2==0:
            note(start+beat*0.5,melody[(bar//2)%len(melody)],0.047,length=7,pan=0.1)
    time=np.arange(count)/RATE
    fade=np.minimum(1,time/4)*np.minimum(1,(SECONDS-time)/7)
    audio=np.column_stack((left,right))*fade[:,None]
    # Consistent quiet dynamics without clipping or abrupt endpoints.
    audio *= 0.65/max(1e-6,float(np.max(np.abs(audio))))
    pcm=(audio*32767).astype('<i2')
    wav=target.with_suffix('.wav')
    with wave.open(str(wav),'wb') as file:
        file.setnchannels(2);file.setsampwidth(2);file.setframerate(RATE);file.writeframes(pcm.tobytes())
    subprocess.run(['/usr/bin/afconvert',str(wav),str(target),'-f','m4af','-d','aac','-b','128000'],check=True,capture_output=True)
    wav.unlink()
    print(f'Original instrumental ready: {key} ({target.stat().st_size} bytes)',flush=True)


if __name__ == '__main__':
    DIRECTORY.mkdir(parents=True,exist_ok=True)
    compose('daylight',62,[(48,55,59,64),(45,52,55,60),(41,48,52,57),(43,50,57,62)],[76,74,71,69,72,71,67,64],11)
    compose('moonlight',48,[(45,52,57,60),(41,48,53,57),(48,55,59,64),(43,50,55,62)],[72,69,67,64,69,67,64,60],22)
    compose('breeze',58,[(50,57,61,66),(47,54,57,62),(43,50,54,59),(45,52,57,64)],[78,76,73,74,71,69,66,69],33)
    (DIRECTORY/'provenance.json').write_text(json.dumps({'provider':'local original synthesis','generator':'compose_local_music.py','duration_seconds':SECONDS,'sample_rate':RATE,'tracks':['daylight','moonlight','breeze'],'notes':'Original slow instrumental compositions, gentle struck-string timbre, no vocals or external samples. Music API was not used for these files.'},indent=2))
