import sqlite3
import json
import os
from flask import Flask, render_template, request, redirect, url_for, Response

app = Flask(__name__)

DATABASE = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'combis.db'))
os.makedirs(os.path.dirname(os.path.abspath(DATABASE)), exist_ok=True)


def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS combis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS combi_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            combi_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (combi_id) REFERENCES combis(id)
        )
    ''')
    db.commit()
    db.close()


init_db()


@app.route('/')
def index():
    db = get_db()
    combis = db.execute('SELECT * FROM combis ORDER BY position, name').fetchall()
    db.close()
    return render_template('index.html', combis=combis)


@app.route('/add', methods=['POST'])
def add():
    name = request.form.get('name', '').strip()
    if not name:
        return redirect(url_for('index'))
    db = get_db()
    max_pos = db.execute('SELECT MAX(position) FROM combis').fetchone()[0]
    position = (max_pos or 0) + 1
    cursor = db.execute('INSERT INTO combis (name, position) VALUES (?, ?)', (name, position))
    combi_id = cursor.lastrowid
    for i in range(24):
        db.execute(
            'INSERT INTO combi_items (combi_id, position, label) VALUES (?, ?, ?)',
            (combi_id, i, '')
        )
    db.commit()
    db.close()
    return redirect(url_for('edit', combi_id=combi_id))


@app.route('/edit/<int:combi_id>', methods=['GET', 'POST'])
def edit(combi_id):
    db = get_db()
    combi = db.execute('SELECT * FROM combis WHERE id = ?', (combi_id,)).fetchone()
    if not combi:
        db.close()
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if name:
            db.execute('UPDATE combis SET name = ? WHERE id = ?', (name, combi_id))
        for i in range(24):
            label = request.form.get(f'item_{i}', '').strip()
            db.execute(
                'UPDATE combi_items SET label = ? WHERE combi_id = ? AND position = ?',
                (label, combi_id, i)
            )
        db.commit()
        db.close()
        return redirect(url_for('index'))

    items = db.execute(
        'SELECT * FROM combi_items WHERE combi_id = ? ORDER BY position',
        (combi_id,)
    ).fetchall()
    result = render_template('edit.html', combi=combi, items=items)
    db.close()
    return result


@app.route('/delete/<int:combi_id>', methods=['POST'])
def delete(combi_id):
    db = get_db()
    db.execute('DELETE FROM combi_items WHERE combi_id = ?', (combi_id,))
    db.execute('DELETE FROM combis WHERE id = ?', (combi_id,))
    db.commit()
    db.close()
    return redirect(url_for('index'))


@app.route('/purge', methods=['POST'])
def purge():
    db = get_db()
    db.execute('DELETE FROM combi_items')
    db.execute('DELETE FROM combis')
    db.commit()
    db.close()
    return redirect(url_for('index'))


@app.route('/import', methods=['POST'])
def import_json():
    f = request.files.get('file')
    if not f:
        return redirect(url_for('index'))
    try:
        data = json.load(f)
    except (json.JSONDecodeError, ValueError):
        return redirect(url_for('index'))

    db = get_db()
    max_pos = db.execute('SELECT MAX(position) FROM combis').fetchone()[0]
    position = (max_pos or 0) + 1

    for combi in data:
        name = combi.get('name', '').strip()
        if not name:
            continue
        items = combi.get('items', [])
        cursor = db.execute('INSERT INTO combis (name, position) VALUES (?, ?)', (name, position))
        combi_id = cursor.lastrowid
        for i in range(24):
            label = items[i] if i < len(items) else ''
            db.execute(
                'INSERT INTO combi_items (combi_id, position, label) VALUES (?, ?, ?)',
                (combi_id, i, label)
            )
        position += 1

    db.commit()
    db.close()
    return redirect(url_for('index'))


@app.route('/export')
def export():
    db = get_db()
    combis = db.execute('SELECT * FROM combis ORDER BY position, name').fetchall()
    data = []
    for combi in combis:
        items = db.execute(
            'SELECT label, position FROM combi_items WHERE combi_id = ? ORDER BY position',
            (combi['id'],)
        ).fetchall()
        data.append({
            'name': combi['name'],
            'items': [row['label'] if row['label'] else str(row['position'] + 1) for row in items],
        })
    db.close()

    json_str = json.dumps(data, indent=2)
    lua_content = f'local data = json.toTable([[\n{json_str}\n]])\n'

    return Response(
        lua_content,
        mimetype='text/plain',
        headers={'Content-Disposition': 'attachment; filename=combis.lua'},
    )


if __name__ == '__main__':
    app.run(debug=True)
