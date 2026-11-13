"""Only publish the frontend assets; never copy instance/, .env or QA captures."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
target = root / 'public' / 'static'
shutil.copytree(root / 'static', target, dirs_exist_ok=True)
