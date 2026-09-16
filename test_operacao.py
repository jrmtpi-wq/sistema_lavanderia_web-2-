import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

import unittest
from datetime import timedelta
from app import app, db, init_db, Carga, Maquina, ProdutoQuimico, Manutencao
from operacao import agora_local


class OperacaoTest(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        db.create_all()
        init_db()
        self.client = app.test_client()
        self.maquina = Maquina.query.filter_by(tipo='lavar').first()
        self.carga = Carga(maquina_id=self.maquina.id, numero=1, op_manual='OP-1',
                           peso=80, data_inicio=agora_local()-timedelta(hours=3))
        db.session.add(self.carga)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def action(self, acao, **kwargs):
        revision=self.carga.apontamentos[-1].id if self.carga.apontamentos else 0
        if acao == 'concluir':
            kwargs = {'peso':80, 'pecas':100, **kwargs}
        return self.client.post(f'/api/operacao/cargas/{self.carga.id}/apontar',
                                json={'acao':acao,'operador':'Ana','revisao':revision,**kwargs})

    def test_cycle_preserves_plan_and_history(self):
        planned = self.carga.data_inicio
        self.assertEqual(self.action('iniciar').status_code, 200)
        self.assertEqual(self.action('pausar').status_code, 400)
        paused=self.action('pausar', motivo='Troca de insumo').get_json()['carga']
        self.assertEqual(paused['status'],'pausado')
        self.assertEqual(self.action('concluir').status_code,409)
        self.assertEqual(self.action('retomar').status_code,200)
        done=self.action('concluir').get_json()['carga']
        self.assertEqual(done['status'],'concluido')
        self.assertEqual(len(done['historico']),4)
        self.assertEqual(self.carga.data_inicio,planned)
        self.assertEqual(self.action('concluir').status_code,409)
        self.assertEqual(self.client.delete(f'/api/cargas/{self.carga.id}').status_code,409)
        self.assertEqual(self.client.put(f'/api/cargas/{self.carga.id}',json={'status':'aguardando'}).status_code,409)

    def test_completion_validates_measurements_and_preserves_actuals(self):
        for values in ({'peso': 0}, {'peso': 'NaN'}, {'peso': '1.0001'},
                       {'pecas': 0}, {'pecas': 1.5}, {'pecas': True}):
            with self.subTest(values=values):
                self.assertEqual(self.action('concluir', **values).status_code, 400)
                self.assertEqual(len(self.carga.apontamentos), 0)
        result = self.action('concluir', peso='75.125', pecas=93)
        self.assertEqual(result.status_code, 200)
        event = result.get_json()['carga']['historico'][-1]
        self.assertEqual((event['peso'], event['pecas']), (75.125, 93))
        self.assertEqual(self.action('concluir').status_code, 409)
        self.client.put(f'/api/cargas/{self.carga.id}', json={'peso': 90, 'qtde_pecas': 110})
        history = self.client.get(f'/api/operacao/maquinas/{self.maquina.id}').get_json()['cargas'][0]['historico']
        self.assertEqual(len(history), 1)
        self.assertEqual((history[0]['peso'], history[0]['pecas']), (75.125, 93))

    def test_stale_click_and_machine_already_running(self):
        self.assertEqual(self.action('iniciar',operador=' ').status_code,400)
        self.action('iniciar')
        self.assertEqual(self.action('pausar',motivo='Teste',revisao=0).status_code,409)
        other=Carga(maquina_id=self.maquina.id,numero=2,peso=10)
        db.session.add(other);db.session.commit()
        response=self.client.post(f'/api/operacao/cargas/{other.id}/apontar',json={'acao':'iniciar','operador':'Ana','revisao':0})
        self.assertEqual(response.status_code,409)

    def test_summary_separates_stages_and_only_counts_actual_events(self):
        now=agora_local()
        self.carga.data_inicio=now.replace(hour=0,minute=0,second=0,microsecond=0)
        dryer=Maquina.query.filter_by(tipo='secador').first()
        # Mesmo lote na secagem: não aumenta os kg da lavagem.
        db.session.add(Carga(maquina_id=dryer.id,numero=1,peso=80,status='concluido',data_inicio=self.carga.data_inicio))
        db.session.add(ProdutoQuimico(nome='Produto teste',quantidade_atual=1,estoque_minimo=10,ativo=True))
        db.session.add(Manutencao(equipamento='Teste',data_proxima=now.date()-timedelta(days=1),ativo=True))
        db.session.commit()
        self.action('iniciar');self.action('concluir')
        d=self.client.get('/api/operacao/resumo').get_json()
        self.assertEqual(d['etapas']['lavar']['previsto_kg'],80)
        self.assertEqual(d['etapas']['lavar']['realizado_kg'],80)
        self.assertEqual(d['etapas']['secador']['previsto_kg'],80)
        self.assertEqual(d['etapas']['secador']['realizado_kg'],0)
        self.assertEqual(d['estoque_baixo'],1)
        self.assertEqual(d['manutencoes_vencidas'],1)
        yesterday=(now.date()-timedelta(days=1)).isoformat()
        self.assertEqual(self.client.get('/api/operacao/resumo?data='+yesterday).get_json()['etapas']['lavar']['realizado_kg'],0)
        self.assertEqual(self.client.get('/api/operacao/resumo?data=errada').status_code,400)

    def test_all_machine_types_and_page_available(self):
        for tipo in ('lavar','centrifuga','secador'):
            machines=self.client.get('/api/maquinas?tipo='+tipo).get_json()
            self.assertTrue(machines)
            self.assertEqual(self.client.get(f"/api/operacao/maquinas/{machines[0]['id']}").status_code,200)
        self.assertIn(b'Modo operador',self.client.get('/').data)
        self.assertIn('id',self.client.get('/api/dashboard').get_json()['lavar'][0])


if __name__ == '__main__':
    unittest.main()
