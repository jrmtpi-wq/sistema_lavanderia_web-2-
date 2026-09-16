"""Regras de estoque seco, passagens repetidas e liberação para faturar."""
import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
import json
import unittest
from app import (app, db, init_db, OrdemProducao, Maquina, Carga, Receita,
                 ReceitaEtapa, LaserEquipamento, LaserFila, PassadoriaItem,
                 Faturamento, TabelaPreco, fluxo)


class FluxoTest(unittest.TestCase):
    def setUp(self):
        self.ctx = app.app_context(); self.ctx.push(); init_db()
        self.client = app.test_client()
        self.op = OrdemProducao(op='FLUXO-1', referencia='JEANS', qtd='{"M":101,"G":11}',
                                peso_unit='{"M":0.8,"G":1.2}')
        self.recipe = Receita(nome='Preparação', versao=1)
        db.session.add_all([self.op, self.recipe]); db.session.flush()
        db.session.add(ReceitaEtapa(receita_id=self.recipe.id, titulo='Preparar', tempo_min=20))
        db.session.commit()
        self.base = f'/api/fluxo/ops/{self.op.id}'

    def tearDown(self):
        db.session.remove(); db.drop_all(); self.ctx.pop()

    def detail(self):
        return self.client.get(self.base).get_json()

    def configure(self, *phases, **extra):
        return self.client.post(self.base+'/roteiro', json={'operador':'Ana','revisao':self.detail()['revisao'],
            'nome':'Roteiro teste','receita_id':self.recipe.id,
            'passos':[{'fase':p} for p in ('estoque_seco', *phases)], **extra})

    def move(self, **extra):
        current=self.detail(); step=next(s for s in current['etapas'] if s['status']!='concluido')
        if step['setor'] in ('lavar','centrifuga','secador'):
            machine=Maquina.query.filter_by(tipo=step['setor']).first().id
        elif step['setor']=='laser': machine=LaserEquipamento.query.first().id
        else: machine=None
        return self.client.post(self.base+'/movimentar',json={'operador':'Ana','revisao':current['revisao'],
            'etapa_id':step['id'],'maquina_id':machine,**extra})

    def finish(self):
        current=self.detail(); step=next(s for s in current['etapas'] if s['status']!='concluido')
        if step['setor']=='manual':
            response=self.client.post(self.base+'/concluir-manual',json={'operador':'Ana',
                'revisao':current['revisao'],'etapa_id':step['id'],'pecas':112})
            self.assertEqual(response.status_code,200,response.get_data(as_text=True))
        for link in step['vinculos']:
            if link['carga_id']:
                c=db.session.get(Carga,link['carga_id'])
                r=self.client.post(f'/api/operacao/cargas/{c.id}/apontar',json={
                    'operador':'Ana','acao':'concluir','revisao':0,'pecas':c.qtde_pecas,'peso':c.peso})
            elif link['laser_id']:
                r=self.client.put(f"/api/laser/fila/{link['laser_id']}",json={'status':'concluido','operador':'Ana'})
            else:
                r=self.client.put(f"/api/passadoria/fila/{link['passadoria_id']}",json={'status':'concluido','operador':'Ana'})
            self.assertEqual(r.status_code,200,r.get_data(as_text=True))

    def test_requires_recipe_weights_machine_and_valid_terminal(self):
        self.assertEqual(self.configure('lavar_preparacao').status_code,400)
        self.assertEqual(self.configure('passadoria_final',receita_id=None).status_code,400)
        self.assertEqual(self.configure('lavar_preparacao','passadoria_final').status_code,200)
        self.op.peso_unit='{"M":0.8}';db.session.commit()
        self.assertEqual(self.move().status_code,400)
        self.assertEqual(Carga.query.count(),0)
        self.op.peso_unit='{"M":0.8,"G":1.2}';db.session.commit()
        self.assertEqual(self.move(maquina_id=None).status_code,400)
        dryer=Maquina.query.filter_by(tipo='secador').first()
        self.assertEqual(self.move(maquina_id=dryer.id).status_code,400)
        self.assertEqual(self.move().status_code,200)

    def test_distribution_stock_and_repeat_submission(self):
        self.configure('lavar_preparacao','passadoria_final')
        before=self.detail()
        first=self.move();self.assertEqual(first.status_code,200,first.get_data(as_text=True))
        loads=Carga.query.order_by(Carga.id).all()
        self.assertEqual(sum(c.qtde_pecas for c in loads),112)
        self.assertAlmostEqual(sum(c.peso for c in loads),94)
        self.assertTrue(all(c.peso<=c.maquina.capacidade for c in loads))
        self.assertEqual(self.client.get('/api/fluxo/ops').get_json()[0]['saldo_seco'],0)
        self.assertEqual(self.move().status_code,409)
        self.assertEqual(self.move(revisao=before['revisao']).status_code,409)
        self.assertEqual(Carga.query.count(),len(loads))
        response=self.client.post(f'/api/operacao/cargas/{loads[0].id}/apontar',json={
            'operador':'Ana','acao':'concluir','revisao':0,'peso':loads[0].peso,'pecas':loads[0].qtde_pecas})
        self.assertEqual(response.status_code,200)
        self.assertIsNone(self.detail()['etapas'][1]['inicio_real'])
        self.assertEqual(self.move().status_code,409)  # Ainda falta a segunda carga.
        for method,path,data in [('DELETE',f'/api/cargas/{loads[0].id}',None),
            ('PUT',f'/api/cargas/{loads[0].id}',{'qtde_pecas':1}),
            ('PUT',f'/api/ops/{self.op.id}',{'qtd':{'M':1}})]:
            self.assertEqual(self.client.open(path,method=method,json=data).status_code,409)

    def test_repeated_wash_is_separate_and_only_last_final_releases_invoice(self):
        self.assertEqual(self.configure('lavar_preparacao','diferenciado','lavar_meio','passadoria_final','laser_final').status_code,200)
        price=TabelaPreco(op=self.op.op,referencia=self.op.referencia,preco_peca=2)
        db.session.add(price);db.session.commit()
        for index in range(5):
            self.assertFalse(self.detail()['pronta'])
            self.assertEqual(self.client.get('/api/ops_prontas').get_json(),[])
            response=self.client.post('/api/faturamento',json={'op_id':self.op.id})
            self.assertEqual(response.status_code,409)
            self.assertEqual(self.move().status_code,200)
            self.finish()
            self.assertEqual(self.detail()['pronta'],index==4)
        wash_steps=[s for s in self.detail()['etapas'] if s['setor']=='lavar']
        self.assertNotEqual(wash_steps[0]['vinculos'],wash_steps[1]['vinculos'])
        self.assertTrue(self.client.get(f'/api/gestao/ops/{self.op.id}').get_json()['concluida'])
        self.assertEqual(len(self.client.get('/api/ops_prontas').get_json()),1)
        response=self.client.post('/api/faturamento',json={'op_id':self.op.id,'op_numero':self.op.op,
            'referencia':self.op.referencia,'qtd_pecas':112,'valor_total':224})
        self.assertEqual(response.status_code,200,response.get_data(as_text=True))
        self.assertEqual(Faturamento.query.first().op_id,self.op.id)

    def test_laser_before_final_ironing_and_no_auto_invoice(self):
        self.configure('laser_final','passadoria_final')
        self.assertEqual(self.move().status_code,200);self.finish()
        self.assertFalse(self.detail()['pronta'])
        self.assertEqual(self.move().status_code,200);self.finish()
        self.assertTrue(self.detail()['pronta']);self.assertEqual(Faturamento.query.count(),0)

    def test_recipe_snapshot_and_sequence_freeze(self):
        self.configure('lavar_preparacao','passadoria_final')
        self.recipe.nome='Alterada';self.recipe.etapas[0].titulo='Alterada';db.session.commit()
        self.assertEqual(self.detail()['etapas'][1]['receita']['nome'],'Preparação')
        self.move()
        self.assertEqual(self.configure('laser_final').status_code,409)
        last=self.detail()['etapas'][-1]
        self.assertEqual(self.move(etapa_id=last['id']).status_code,409)
        c=Carga.query.first()
        self.assertEqual(self.client.post(f'/api/operacao/cargas/{c.id}/apontar',json={
            'operador':'Ana','acao':'concluir','revisao':0,'peso':c.peso,'pecas':1}).status_code,400)

    def test_catalog_templates_and_repeated_custom_phase(self):
        r=self.client.post('/api/fluxo/fases',json={'nome':'Used especial','setor':'manual'})
        self.assertEqual(r.status_code,200)
        phase=r.get_json()['id']
        self.assertEqual(self.configure(phase,phase,'passadoria_final').status_code,200)
        self.assertEqual(len(self.detail()['etapas']),4)
        response=self.client.post('/api/fluxo/modelos',json={'nome':'Modelo próprio','passos':[
            {'fase':'estoque_seco'},{'fase':phase},{'fase':'laser_final'}]})
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(self.client.get('/api/fluxo/catalogo').get_json()['modelos']),1)

    def test_old_endpoints_cannot_bypass_and_old_production_not_stock(self):
        machine=Maquina.query.filter_by(tipo='lavar').first()
        for path in (f'/api/maquinas/{machine.id}/cargas',f'/api/maquinas/{machine.id}/gerar_cargas',
                     '/api/passadoria/fila','/api/laser/equipamentos/1/fila'):
            self.assertEqual(self.client.post(path,json={'op_id':self.op.id,'op':self.op.op,
                'referencia':self.op.referencia}).status_code,409)
        db.session.add(Carga(maquina_id=machine.id,op_id=self.op.id,numero=1,status='concluido'))
        db.session.commit()
        self.assertEqual(self.client.get('/api/fluxo/ops').get_json()[0]['saldo_seco'],0)
        self.assertEqual(self.configure('passadoria_final').status_code,409)

    def test_invalid_grade_rejected_without_mutation(self):
        for values in ({'M':-1},{'M':'NaN'},{'M':1.5},{'M':True},{'INVALIDO':1}):
            response=self.client.put(f'/api/ops/{self.op.id}',json={'qtd':values})
            self.assertEqual(response.status_code,400)
        self.assertEqual(self.op.total_pecas,112)

    def test_legacy_reconciliation_is_explicit_audited_and_does_not_invent_dates(self):
        machine=Maquina.query.filter_by(tipo='lavar').first()
        load=Carga(maquina_id=machine.id,op_id=self.op.id,numero=1,status='aguardando')
        db.session.add(load);db.session.commit()
        fields={'conferir_legado':True,'motivo_conferencia':'Conferência física do lote','fases_concluidas':2}
        self.assertEqual(self.configure('lavar_preparacao','passadoria_final',**fields).status_code,409)
        load.status='concluido';db.session.commit()
        self.assertEqual(self.configure('lavar_preparacao','passadoria_final',**fields).status_code,200)
        detail=self.detail()
        self.assertTrue(detail['conferencia']);self.assertFalse(detail['pronta'])
        self.assertIsNone(detail['etapas'][1]['fim_real'])
        self.assertEqual(self.client.get('/api/fluxo/ops').get_json()[0]['saldo_seco'],0)
        self.assertEqual(self.configure('laser_final').status_code,409)
        self.assertEqual(self.move().status_code,200);self.finish()
        self.assertTrue(self.detail()['pronta'])


if __name__ == '__main__':
    unittest.main()
