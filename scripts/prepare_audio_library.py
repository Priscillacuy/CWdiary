"""Management-only: generate reusable music and sample voices into instance/."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
from audio_service import AudioService, MUSIC, closing, guidance


if __name__ == '__main__':
    service = AudioService(ROOT / 'instance/audio-library')
    try:
        for key in MUSIC:
            path = service.music(key)
            print(f'Music ready: {key} ({path.stat().st_size} bytes)', flush=True)
        samples = []
        for language in ('zh', 'en'):
            for voice in ('female', 'male'):
                text = guidance({'activity_id': 'rest', 'category': 'rest', 'duration_seconds': 300}, language)
                key = service.speech(text, voice, language)
                samples.append({'voice': voice, 'language': language, 'text': text, 'file': 'speech/' + key + '.mp3'})
                for mode in ('day', 'sleep'):
                    service.speech(closing(language, mode), voice, language)
                print(f'Voice ready: {voice}/{language}', flush=True)
        (service.directory / 'manifest.json').write_text(json.dumps({'music': [{**value, 'id': key, 'file': 'music/' + service.music(key).name, 'duration_seconds': 120 if service.music(key).suffix == '.m4a' else 90, 'provider': 'local original synthesis' if service.music(key).suffix == '.m4a' else 'ElevenLabs', 'model': 'procedural-piano-v1' if service.music(key).suffix == '.m4a' else 'music_v1'} for key, value in MUSIC.items()], 'speech_model': service.model, 'samples': samples}, ensure_ascii=False, indent=2))
    finally:
        service.pool.shutdown(wait=True)
