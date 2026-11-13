import sqlite3

import pytest
from app import create_app
from test_app import app, auth


def transaction(client, headers, **changes):
    body = dict(kind='expense', amount='12.35', category='餐饮', entry_date='2026-11-13')
    body.update(changes)
    return client.post('/api/ledger', headers=headers, json=body)


@pytest.mark.parametrize('currency', ['CNY', 'HKD', 'TWD', 'GBP', 'USD'])
def test_currency_preference_persists_and_applies_to_new_records(app, currency):
    c = app.test_client(); h = auth(c)
    assert c.patch('/api/profile', headers=h, json={'currency': currency}).json['user']['currency'] == currency
    assert c.get('/api/session').json['user']['currency'] == currency
    assert transaction(c, h).status_code == 201
    report = c.get('/api/ledger?date=2026-11-13').json
    assert report['currency'] == currency
    assert report['items'][0]['currency'] == currency and report['expense_cents'] == 1235


def test_currency_changes_preserve_existing_amounts_and_isolate_users(app):
    a, b = app.test_client(), app.test_client(); ha, hb = auth(a), auth(b, 'bob')
    item = transaction(a, ha).json['id']
    a.patch('/api/profile', headers=ha, json={'currency': 'HKD'})
    transaction(a, ha, amount='7.10')
    assert a.get('/api/ledger?date=2026-11-13').json['expense_cents'] == 710
    old = a.get('/api/ledger?date=2026-11-13&currency=CNY').json
    assert old['items'][0]['currency'] == 'CNY' and old['expense_cents'] == 1235
    assert b.get('/api/session').json['user']['currency'] == 'CNY'
    assert b.get('/api/ledger?date=2026-11-13&currency=HKD').json['items'] == []
    # Older clients editing a record without currency must preserve that record's currency.
    body = dict(kind='expense', amount='13.00', category='交通', entry_date='2026-11-13')
    assert a.put(f'/api/ledger/{item}', headers=ha, json=body).status_code == 200
    assert a.get('/api/ledger?date=2026-11-13&currency=CNY').json['expense_cents'] == 1300
    assert b.put(f'/api/ledger/{item}', headers=hb, json=body).status_code == 404


def test_month_year_totals_boundaries_currency_and_privacy(app):
    a, b = app.test_client(), app.test_client(); ha, hb = auth(a), auth(b, 'bob')
    for changes in [dict(amount='10.00', entry_date='2026-11-01'),
                    dict(amount='20.00', entry_date='2026-11-30'),
                    dict(kind='income', amount='100.00'),
                    dict(amount='5.00', entry_date='2026-01-01'),
                    dict(amount='7.00', entry_date='2026-12-31'),
                    dict(amount='900.00', entry_date='2025-12-31'),
                    dict(amount='800.00', entry_date='2027-01-01'),
                    dict(amount='700.00', currency='HKD')]:
        assert transaction(a, ha, **changes).status_code == 201
    response = a.get('/api/ledger/summary?date=2026-11-13&currency=CNY')
    assert response.headers['Cache-Control'] == 'no-store'
    report = response.json
    assert report['month'] == dict(period='2026-11', count=3, income_cents=10000, expense_cents=3000, balance_cents=7000)
    assert report['year'] == dict(period='2026', count=5, income_cents=10000, expense_cents=4200, balance_cents=5800)
    assert a.get('/api/ledger/summary?date=2026-11-13&currency=HKD').json['year']['expense_cents'] == 70000
    assert b.get('/api/ledger/summary?date=2026-11-13').json['year']['count'] == 0
    assert app.test_client().get('/api/ledger/summary?date=2026-11-13').status_code == 401
    for invalid in ['2026-02-30', '', '2026-11', '2026-1-1']:
        assert a.get('/api/ledger/summary?date='+invalid).status_code == 400


@pytest.mark.parametrize('currency', ['EUR', 'RMB', 'NTD', '', None, []])
def test_unsupported_currency_is_rejected(app, currency):
    c = app.test_client(); h = auth(c)
    assert c.patch('/api/profile', headers=h, json={'currency': currency}).status_code == 400
    assert transaction(c, h, currency=currency).status_code == 400
    assert c.get('/api/ledger?currency=EUR').status_code == 400
    assert c.get('/api/ledger/summary?currency=EUR').status_code == 400
    assert c.get('/api/session').json['user']['currency'] == 'CNY'


def test_existing_database_migration_keeps_yuan_and_is_repeatable(app):
    c = app.test_client(); h = auth(c); transaction(c, h)
    path = app.config['DATABASE']
    with sqlite3.connect(path) as db:
        # Recreate the pre-currency ledger to exercise a real populated upgrade.
        db.executescript('''DROP INDEX ledger_user_currency_date;
            ALTER TABLE ledger RENAME TO old_ledger;
            CREATE TABLE ledger AS SELECT id,user_id,kind,amount_cents,category,note,entry_date,created_at FROM old_ledger;
            DROP TABLE old_ledger;''')
    for _ in range(2):
        create_app({'TESTING': True, 'DATABASE': path, 'SECRET_KEY': 'test-secret'})
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT currency,amount_cents FROM ledger').fetchone() == ('CNY', 1235)
