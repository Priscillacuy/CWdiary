"""Pre-generate the 50 activity images, export a readable local library, and resume safely."""
import html
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from activity_catalog import CATALOG
from image_service import ImageService

load_dotenv(ROOT / '.env')
service = ImageService(ROOT / 'instance/activity-images', max_workers=4)
library = ROOT / 'instance/relaxation-library'
(library / 'images').mkdir(parents=True, exist_ok=True)


def export():
    records, cards = [], []
    for i, item in enumerate(CATALOG, 1):
        record = {k: v for k, v in item.items() if k != 'image_prompt'}
        record['number'] = i
        source = service.path(item['id'], 'image')
        record['status'] = 'ready' if source.exists() else 'pending'
        if source.exists():
            signature = source.read_bytes()[:12]
            suffix = 'png' if signature.startswith(b'\x89PNG') else 'jpg' if signature.startswith(b'\xff\xd8') else 'webp'
            filename = f"images/{i:02d}-{item['id']}.{suffix}"
            destination = library / filename
            if not destination.exists():
                # A hard link keeps the standard-named export and app cache in sync without duplicating image data.
                try:
                    os.link(source, destination)
                except OSError:
                    import shutil
                    shutil.copyfile(source, destination)
            record['image'] = filename
        records.append(record)
        picture = f'<img src="{record["image"]}" alt="{html.escape(item["name"])}" loading="lazy">' if record.get('image') else '<div class="pending">配图准备中</div>'
        cards.append(f'<article>{picture}<div class="copy"><small>{i:02d} · {item["duration_minutes"]} 分钟</small><h2>{html.escape(item["name"])}</h2><p>{html.escape(item["suitable_for"])}</p><p>{html.escape(item["instructions"])}</p></div></article>')
    (library / 'catalog.json').write_text(json.dumps(CATALOG, ensure_ascii=False, indent=2)+'\n')
    (library / 'manifest.json').write_text(json.dumps(records, ensure_ascii=False, indent=2)+'\n')
    done = sum(r['status'] == 'ready' for r in records)
    (library / 'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>50种舒缓心情的小事</title><style>body{margin:0;background:#faf7ef;color:#67523f;font-family:system-ui,sans-serif}header{max-width:1200px;margin:50px auto 30px;padding:0 24px}h1{font-family:serif;font-size:36px}main{max-width:1200px;margin:auto;padding:0 24px 50px;display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:22px}article{background:#fffdf7;border:1px solid #e8dfcf;border-radius:18px;overflow:hidden}img,.pending{display:block;width:100%;aspect-ratio:1;object-fit:cover;background:#ede8d8}.copy{padding:20px}small{color:#99866d}h2{font-size:19px}p{line-height:1.8;font-size:13px}</style><header><h1>50种舒缓心情的小事</h1><p>放松无需完成清单。按当下精力、需要与喜好选择，也可以跳过。</p><p>本地参考图库 · '+str(done)+'/50 张 · gpt-image-2.6 · 图片为活动示意</p></header><main>'+''.join(cards)+'</main></html>')
    (library / '活动清单.md').write_text('# 50种舒缓心情的小事\n\n按精力、喜好与需要选择，非治疗方案。参考图与个人日记无关。\n\n'+ '\n'.join(f"{i}. **{r['name']}**（{r['duration_minutes']}分钟） — {r['suitable_for']}。{r['instructions']}" for i,r in enumerate(CATALOG,1))+'\n')
    return done


if __name__ == '__main__':
    import fcntl
    run_lock = (library / '.prepare.lock').open('a')
    try:
        fcntl.flock(run_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('A library preparation process is already running')
    ids = [item['id'] for item in CATALOG]
    if not service.key:
        raise SystemExit('IMAGE_API_KEY is not configured')
    service.start(ids, retry=True)
    previous = -1
    while True:
        done = export()
        statuses = service.statuses(ids)
        if done != previous:
            print(f'Local activity library: {done}/50 ready', flush=True)
            previous = done
        pending = any(value['status'] in ('queued', 'running') for value in statuses.values())
        if not pending:
            failed = {key: value.get('error') for key,value in statuses.items() if value['status'] != 'succeeded'}
            print(json.dumps({'ready': done, 'failed': failed}, ensure_ascii=False), flush=True)
            break
        time.sleep(5)
    service.pool.shutdown(wait=True)
    raise SystemExit(0 if done == 50 else 1)
