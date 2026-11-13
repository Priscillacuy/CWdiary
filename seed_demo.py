"""可选演示账号与示例日记，重复运行不会覆盖已有数据。"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import sqlite3
from werkzeug.security import generate_password_hash
from app import create_app

app = create_app()
with sqlite3.connect(app.config['DATABASE']) as db:
    if db.execute('SELECT 1 FROM users WHERE username_key=?', ('demo',)).fetchone():
        print('演示账号已存在，未修改任何日记。')
    else:
        hashed = generate_password_hash('diary2026', method='pbkdf2:sha256:1000000')
        uid = db.execute('INSERT INTO users(username,username_key,nickname,password_hash) VALUES(?,?,?,?)', ('demo', 'demo', '小隅', hashed)).lastrowid
        db.execute('INSERT INTO password_history(user_id,password_hash) VALUES(?,?)', (uid,hashed))
        examples = [
            ('立冬后的第一场晴天', '今天阳光特别好，风也不那么冷了。午休的时候去楼下走了一圈，看到银杏叶铺了一地，金灿灿的，很治愈。晚上做了喜欢的番茄意面，简单但很满足。这样平凡又舒服的一天，真好。', '开心', ['日常', '小确幸']),
            ('慢下来，也挺好', '今天没有太多特别的事，事情按部就班地推进，效率还不错。傍晚泡了一杯热奶茶，读了几页一直想看的书，心情很平静。有时候不用很充实，能安安静静地做点喜欢的事，就已经很幸福了。', '平静', ['生活']),
            ('有点累的一天', '今天事情比预想的要忙，开了好几个会，脑袋有点转不动。回到家只想躺着，连晚饭都简单对付了。虽然有点疲惫，但也还好，提醒自己早点休息，明天会轻松一些的。', '疲惫', ['日常'])]
        now = datetime.now(ZoneInfo('Asia/Shanghai')).date()
        for i, (title, content, mood, tags) in enumerate(examples):
            db.execute('INSERT INTO entries(user_id,title,content,mood,tags,entry_date) VALUES(?,?,?,?,?,?)', (uid,title,content,mood,json.dumps(tags,ensure_ascii=False),(now-timedelta(days=i)).isoformat()))
        print('已创建演示账号 demo，密码 diary2026（含三篇示例日记）。')
