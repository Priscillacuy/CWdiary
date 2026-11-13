"""Personal settings, private avatar storage and a simple per-user ledger."""
import base64
import io
import secrets
import sqlite3
import time
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import abort, jsonify, request, send_file, session
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash

ANIMALS = ('cat', 'dog', 'rabbit', 'fox', 'panda', 'bear')
CURRENCIES = ('CNY', 'HKD', 'TWD', 'GBP', 'USD')


def username_key(value):
    return unicodedata.normalize('NFKC', value).strip().casefold()


def migrate_accounts(connection):
    columns = {row[1] for row in connection.execute('PRAGMA table_info(users)')}
    for name, definition in {'gender': "TEXT NOT NULL DEFAULT ''", 'language': "TEXT NOT NULL DEFAULT 'zh'", 'avatar': "TEXT NOT NULL DEFAULT 'cat'", 'auth_version': 'INTEGER NOT NULL DEFAULT 0', 'username_key': 'TEXT', 'currency': "TEXT NOT NULL DEFAULT 'CNY'"}.items():
        if name not in columns:
            connection.execute(f'ALTER TABLE users ADD COLUMN {name} {definition}')
    for identity, name in connection.execute('SELECT id,username FROM users').fetchall():
        connection.execute('UPDATE users SET username_key=? WHERE id=?', (username_key(name), identity))
    connection.execute('CREATE UNIQUE INDEX IF NOT EXISTS users_username_key ON users(username_key)')
    connection.executescript('''CREATE TABLE IF NOT EXISTS password_history (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        password_hash TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id,password_hash));
        INSERT OR IGNORE INTO password_history(user_id,password_hash) SELECT id,password_hash FROM users;''')
    if 'profile_key' not in {row[1] for row in connection.execute('PRAGMA table_info(analyses)')}:
        connection.execute("ALTER TABLE analyses ADD COLUMN profile_key TEXT NOT NULL DEFAULT ''")
    connection.executescript('''CREATE TABLE IF NOT EXISTS ledger (
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
        kind TEXT NOT NULL CHECK(kind IN ('expense','income')), amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
        category TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', entry_date TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS ledger_user_date ON ledger(user_id,entry_date);''')
    if 'currency' not in {row[1] for row in connection.execute('PRAGMA table_info(ledger)')}:
        connection.execute("ALTER TABLE ledger ADD COLUMN currency TEXT NOT NULL DEFAULT 'CNY'")
    connection.execute('CREATE INDEX IF NOT EXISTS ledger_user_currency_date ON ledger(user_id,currency,entry_date)')
    connection.commit()


def register_account_routes(app, db, login_required, user):
    avatar_dir = Path(app.config['DATABASE']).parent / 'avatars'
    avatar_dir.mkdir(exist_ok=True)

    @app.post('/api/avatar')
    @login_required
    def upload_avatar():
        body = request.get_json(silent=True)
        if not isinstance(body,dict):
            abort(400, description='请提交有效内容')
        data = body.get('image')
        if not isinstance(data, str) or len(data) > 2800000 or ',' not in data:
            abort(400, description='请上传2MB以内的PNG、JPG或WebP图片')
        prefix, encoded = data.split(',', 1)
        if prefix not in ('data:image/png;base64', 'data:image/jpeg;base64', 'data:image/webp;base64'):
            abort(400, description='请上传PNG、JPG或WebP图片')
        try:
            content = base64.b64decode(encoded, validate=True)
            if len(content) > 2 * 1024 * 1024:
                raise ValueError
            with Image.open(io.BytesIO(content)) as picture:
                if picture.format not in ('PNG', 'JPEG', 'WEBP') or picture.width * picture.height > 16000000:
                    raise ValueError
                picture = ImageOps.fit(ImageOps.exif_transpose(picture).convert('RGBA'), (256, 256))
                filename = secrets.token_hex(16) + '.png'
                picture.save(avatar_dir / filename, 'PNG')
        except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
            abort(400, description='头像图片无效或过大，请换一张图片')
        previous = user()['avatar']
        db().execute('UPDATE users SET avatar=? WHERE id=?', ('upload:' + filename, session['uid']))
        db().commit()
        if previous.startswith('upload:'):
            (avatar_dir / previous.split(':', 1)[1]).unlink(missing_ok=True)
        return jsonify(user=user())

    @app.get('/api/avatar')
    @login_required
    def avatar():
        selected = user()['avatar']
        if not selected.startswith('upload:'):
            abort(404, description='尚未上传头像')
        path = avatar_dir / selected.split(':', 1)[1]
        if not path.is_file():
            abort(404, description='头像不存在')
        return send_file(path, mimetype='image/png')

    @app.post('/api/password')
    @login_required
    def password():
        body = request.get_json(silent=True)
        if not isinstance(body,dict):
            abort(400, description='请提交有效内容')
        old, new, confirm = (body.get(key) for key in ('old_password', 'new_password', 'confirm_password'))
        if not all(isinstance(value, str) for value in (old, new, confirm)) or not 8 <= len(new) <= 128:
            abort(400, description='新密码须为8至128位')
        if new != confirm:
            abort(400, description='两次输入的新密码不一致')
        if old == new:
            abort(400, description='新密码不能与旧密码相同')
        identity = f'password:{session["uid"]}'
        attempt = db().execute('SELECT * FROM login_attempts WHERE identity=?', (identity,)).fetchone()
        if attempt and attempt['attempts'] >= 8 and attempt['until_at'] > time.time():
            abort(429, description='尝试次数较多，请15分钟后再试')
        account = db().execute('SELECT * FROM users WHERE id=?', (session['uid'],)).fetchone()
        if not check_password_hash(account['password_hash'], old):
            count = attempt['attempts'] + 1 if attempt and attempt['until_at'] > time.time() else 1
            db().execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)', (identity, count, time.time()+900))
            db().commit()
            abort(400, description='旧密码不正确')
        history = db().execute('SELECT password_hash FROM password_history WHERE user_id=?', (session['uid'],)).fetchall()
        if any(check_password_hash(row['password_hash'], new) for row in history):
            abort(400, description='新密码不能重复使用以前的密码')
        new_hash = generate_password_hash(new, method='pbkdf2:sha256:1000000')
        changed = db().execute('UPDATE users SET password_hash=?,auth_version=auth_version+1 WHERE id=? AND auth_version=?',
                     (new_hash, session['uid'], account['auth_version']))
        if not changed.rowcount:
            db().rollback()
            abort(409, description='密码已在其他设备更改，请重新登录')
        db().execute('INSERT INTO password_history(user_id,password_hash) VALUES(?,?)', (session['uid'], new_hash))
        db().execute('DELETE FROM login_attempts WHERE identity=?', (identity,))
        db().commit()
        uid = session['uid']
        session.clear()
        session.update(uid=uid, auth_version=account['auth_version']+1, csrf=secrets.token_hex(24))
        session.permanent = True
        return jsonify(ok=True, csrf=session['csrf'])

    def ledger_values(body, previous_currency=None):
        if not isinstance(body, dict):
            abort(400, description='请提交有效内容')
        currency = body.get('currency', previous_currency or user()['currency'])
        if currency not in CURRENCIES:
            abort(400, description='交易货币选项不正确')
        kind, category, note, entry_date = (body.get(key, '') for key in ('kind', 'category', 'note', 'entry_date'))
        if kind not in ('income', 'expense') or not isinstance(category, str) or not 1 <= len(category.strip()) <= 24 or not isinstance(note, str) or len(note) > 200:
            abort(400, description='请填写有效的记账类型、分类和备注')
        try:
            amount = Decimal(str(body.get('amount')))
            if not amount.is_finite() or amount <= 0 or amount > Decimal('99999999.99') or amount != amount.quantize(Decimal('.01')):
                raise ValueError
            if date.fromisoformat(entry_date).isoformat() != entry_date:
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            abort(400, description='请填写有效日期与金额，金额最多两位小数')
        return kind, int(amount*100), category.strip(), note.strip(), entry_date, currency

    def ledger_currency():
        currency = request.args.get('currency', user()['currency'])
        if currency not in CURRENCIES:
            abort(400, description='交易货币选项不正确')
        return currency

    def ledger_date(value):
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError
        except (ValueError, TypeError):
            abort(400, description='日期格式不正确')
        return value

    @app.get('/api/ledger/summary')
    @login_required
    def ledger_summary():
        selected = ledger_date(request.args.get('date', date.today().isoformat()))
        currency = ledger_currency()
        def totals(length):
            period = selected[:length]
            row = db().execute('''SELECT
                COALESCE(SUM(CASE WHEN kind='income' THEN amount_cents ELSE 0 END),0) AS income_cents,
                COALESCE(SUM(CASE WHEN kind='expense' THEN amount_cents ELSE 0 END),0) AS expense_cents,
                COUNT(*) AS count FROM ledger WHERE user_id=? AND currency=? AND substr(entry_date,1,?)=?''',
                (session['uid'], currency, length, period)).fetchone()
            result = dict(row)
            result.update(period=period, balance_cents=result['income_cents']-result['expense_cents'])
            return result
        response = jsonify(currency=currency, month=totals(7), year=totals(4))
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/ledger')
    @login_required
    def ledger():
        currency = ledger_currency()
        if 'date' in request.args:
            selected = request.args['date']
            try:
                if date.fromisoformat(selected).isoformat() != selected:
                    raise ValueError
            except (ValueError, TypeError):
                abort(400, description='日期格式不正确')
            condition = 'entry_date=?'
        else:
            # Preserve month queries for existing clients; the UI now selects a day.
            selected = request.args.get('month', date.today().strftime('%Y-%m'))
            try:
                if date.fromisoformat(selected+'-01').strftime('%Y-%m') != selected:
                    raise ValueError
            except (ValueError, TypeError):
                abort(400, description='月份格式不正确')
            condition = 'substr(entry_date,1,7)=?'
        rows = db().execute('SELECT id,kind,amount_cents,category,note,entry_date,currency FROM ledger WHERE user_id=? AND currency=? AND '+condition+' ORDER BY entry_date DESC,id DESC', (session['uid'], currency, selected)).fetchall()
        items = [dict(row) for row in rows]
        return jsonify(items=items, currency=currency, income_cents=sum(row['amount_cents'] for row in rows if row['kind']=='income'), expense_cents=sum(row['amount_cents'] for row in rows if row['kind']=='expense'))

    @app.post('/api/ledger')
    @login_required
    def create_ledger():
        values = ledger_values(request.get_json(silent=True))
        cursor = db().execute('INSERT INTO ledger(user_id,kind,amount_cents,category,note,entry_date,currency) VALUES(?,?,?,?,?,?,?)', (session['uid'],)+values)
        db().commit()
        return jsonify(id=cursor.lastrowid), 201

    @app.put('/api/ledger/<int:item_id>')
    @login_required
    def update_ledger(item_id):
        current = db().execute('SELECT id,currency FROM ledger WHERE id=? AND user_id=?', (item_id,session['uid'])).fetchone()
        if not current:
            abort(404, description='账目不存在')
        values = ledger_values(request.get_json(silent=True), current['currency'])
        db().execute('UPDATE ledger SET kind=?,amount_cents=?,category=?,note=?,entry_date=?,currency=? WHERE id=? AND user_id=?', values+(item_id,session['uid']))
        db().commit()
        return jsonify(ok=True)

    @app.delete('/api/ledger/<int:item_id>')
    @login_required
    def delete_ledger(item_id):
        cursor = db().execute('DELETE FROM ledger WHERE id=? AND user_id=?', (item_id,session['uid']))
        if not cursor.rowcount:
            abort(404, description='账目不存在')
        db().commit()
        return jsonify(ok=True)
