"""Confere a importação WSGI em banco existente sem tabelas dos novos módulos."""
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class InicializacaoTest(unittest.TestCase):
    def test_wsgi_creates_missing_tables_and_preserves_existing_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'upgrade.db'
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute('CREATE TABLE ordem_producao (id INTEGER PRIMARY KEY, '
                                   'op VARCHAR(20), referencia VARCHAR(50), lavacao VARCHAR(80), '
                                   'cap_pecas INTEGER, qtd TEXT, peso_unit TEXT, created_at DATETIME)')
                connection.execute("INSERT INTO ordem_producao (id, op, qtd, peso_unit, created_at) "
                                   "VALUES (1, 'PRESERVAR', '{}', '{}', '2026-09-16 10:00:00')")
            environment = dict(os.environ, DATABASE_URL='sqlite:///' + database.as_posix())
            script = '''
from app import app, inicializar_tabelas
inicializar_tabelas()
client = app.test_client()
for path in ('/api/ops', '/api/maquinas', '/api/operacao/resumo', '/relatorios'):
    response = client.get(path)
    assert response.status_code == 200, (path, response.status_code)
'''
            result = subprocess.run([sys.executable, '-c', script], env=environment,
                                    cwd=Path(__file__).parent, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute('SELECT op FROM ordem_producao').fetchall(),
                                 [('PRESERVAR',)])
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertTrue({'cadastro_arquivo', 'apontamento_carga',
                                 'medicao_conclusao', 'ficha_op', 'custo_op', 'fluxo_op',
                                 'passagem_op', 'vinculo_passagem', 'movimento_fluxo'} <= tables)
