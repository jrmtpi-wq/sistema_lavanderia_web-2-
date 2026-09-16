"""Relatórios: limites de datas, dados reais, pendências e exportação segura."""
import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
import unittest
from datetime import date, datetime
from app import app, db, init_db, Carga, Maquina, OrdemProducao, gestao


class RelatoriosTest(unittest.TestCase):
    def setUp(self):
        self.ctx = app.app_context()
        self.ctx.push()
        init_db()
        self.client = app.test_client()
        self.m = Maquina.query.filter_by(tipo='lavar').first()
        self.base = '/relatorios?inicio=2026-09-01&fim=2026-09-11'

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_real_weight_and_inclusive_dates(self):
        c = Carga(maquina_id=self.m.id, numero=1, op_manual='REAL', peso=80,
                  data_inicio=datetime(2026, 8, 30), status='aguardando')
        db.session.add(c)
        db.session.commit()
        for action in ('iniciar', 'concluir'):
            revision = c.apontamentos[-1].id if c.apontamentos else 0
            self.assertEqual(self.client.post(f'/api/operacao/cargas/{c.id}/apontar', json={
                'acao': action, 'operador': 'Ana', 'revisao': revision, 'peso':80, 'pecas':100}).status_code, 200)
        c.apontamentos[-1].data = datetime(2026, 9, 11, 23, 59)
        c.peso = 99  # O relatório deve conservar os 80 kg registrados na conclusão.
        db.session.add(Carga(maquina_id=self.m.id, numero=2, op_manual='ANTIGA', peso=50,
                            status='concluido', data_inicio=datetime(2026, 9, 1)))
        db.session.commit()
        response = self.client.get(self.base + '&formato=csv')
        text = response.get_data(as_text=True)
        self.assertIn('Realizado: 80,00 kg', text)
        self.assertIn('Previsto: 50,00 kg', text)
        self.assertIn('Sem apontamento', text)
        self.assertNotIn('REAL', self.client.get(self.base.replace('09-11', '09-10') + '&formato=csv').get_data(as_text=True))

    def test_ops_costs_archives_and_export_safety(self):
        op = OrdemProducao(op='=FORMULA()', referencia='<script>alert(1)</script>')
        db.session.add(op)
        db.session.flush()
        db.session.add(gestao.models.FichaOP(op_id=op.id, prazo=date(2026, 9, 11), cliente='Cliente A'))
        db.session.add(gestao.models.CustoOP(op_id=op.id, categoria='energia', descricao='Energia',
            unidade='kWh', quantidade_prevista=10, unitario_previsto=2))
        db.session.commit()
        html = self.client.get(self.base + '&tipo=custos').get_data(as_text=True)
        self.assertIn('R$ 20,00', html)
        self.assertIn('Pendente', html)
        self.assertNotIn('<script>alert(1)</script>', html)
        csv = self.client.get(self.base + '&tipo=custos&formato=csv').get_data(as_text=True)
        self.assertIn("'=FORMULA()", csv)
        self.assertTrue(csv.startswith('\ufeff'))
        self.assertNotIn('Cliente A', self.client.get(self.base + '&tipo=ops&busca=inexistente').get_data(as_text=True))
        self.assertEqual(self.client.post(f'/api/gestao/cadastros/ops/{op.id}/arquivar',
            json={'operador': 'Ana', 'motivo': 'Teste'}).status_code, 200)
        self.assertNotIn('Cliente A', self.client.get(self.base + '&tipo=custos').get_data(as_text=True))

    def test_invalid_filters_and_empty_results(self):
        for query in ('inicio=errado', 'inicio=2026-10-01&fim=2026-09-01', 'tipo=errado', 'maquina=999999'):
            self.assertEqual(self.client.get('/relatorios?' + query).status_code, 400)
        r = self.client.get(self.base)
        self.assertEqual(r.status_code, 200)
        self.assertIn('Nenhum registro encontrado', r.get_data(as_text=True))
        self.assertEqual(r.headers['Cache-Control'], 'no-store')

    def test_legacy_completed_weights_pieces_and_dates(self):
        for n, status, when, weight, pieces in [
            (1, 'concluido', datetime(2026, 9, 9, 10), 80, 200),
            (2, 'aguardando', datetime(2026, 9, 9, 10), 90, 300),
            (3, 'concluido', datetime(2026, 11, 10, 10), 40, 100),
            (4, 'concluido', None, 20, 50),
        ]:
            db.session.add(Carga(maquina_id=self.m.id, numero=n, op_manual=f'OP-{n}',
                status=status, data_inicio=when, peso=weight, qtde_pecas=pieces))
        other = Maquina.query.filter_by(tipo='secador').first()
        db.session.add(Carga(maquina_id=other.id, numero=1, op_manual='SECAGEM',
            status='concluido', data_inicio=datetime(2026, 9, 9, 10), peso=80, qtde_pecas=200))
        db.session.commit()
        text = self.client.get(self.base + '&formato=csv').get_data(as_text=True)
        self.assertIn('Total de quilos lavados — seleção;80,00 kg', text)
        self.assertIn('Total de peças lavadas — seleção;200', text)
        self.assertIn('Programação (sem data real)', text)
        self.assertNotIn('OP-3;', text)
        text = self.client.get(self.base + '&sem_data=1&formato=csv').get_data(as_text=True)
        self.assertIn('Total de quilos lavados — sem data real;140,00 kg', text)
        self.assertIn('Total de peças lavadas — sem data real;350', text)
        self.assertIn('OP-3;', text)
        self.assertIn('OP-4;', text)
        self.assertNotIn('OP-2;', text)
        self.assertIn('Todos — sem data real', text)


if __name__ == '__main__':
    unittest.main()
