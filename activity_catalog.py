"""Local, curated relaxation activities shared by reviews and image generation."""
import json
from pathlib import Path

CATALOG = json.loads((Path(__file__).parent / 'data/relaxation-activities.json').read_text())
BY_ID = {item['id']: item for item in CATALOG}
DEFAULT_IDS = {category: category for category in ('yoga', 'music', 'meal', 'walk', 'rest', 'read')}
PROMPT_CHOICES = '\n'.join(f"{item['id']}：{item['name']}（{item['category']}）" for item in CATALOG)
