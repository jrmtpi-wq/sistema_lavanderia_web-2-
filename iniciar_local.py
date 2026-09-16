"""Inicia exclusivamente uma base SQLite local, independentemente do ambiente."""
import os
os.environ['DATABASE_URL'] = 'sqlite:///chrona_local.db'

from app import app, db, init_db

if __name__ == '__main__':
    with app.app_context():
        init_db()
    print('\nChrona Lavanderia local: http://127.0.0.1:5000\n')
    app.run(host='127.0.0.1', port=5000, debug=False)
