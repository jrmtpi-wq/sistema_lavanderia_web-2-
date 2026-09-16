"""Cenários de negócio em banco isolado, sem acessar dados locais ou hospedados."""
import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
import unittest
from datetime import date
from app import (app, db, init_db, OrdemProducao, Carga, Maquina, Faturamento,
                 ProdutoQuimico, Receita, ReceitaEtapa, Funcionario, TabelaPreco,
                 PecaAmostra, Manutencao, OrdemServico)


class GestaoTest(unittest.TestCase):
    def setUp(self):
        self.ctx = app.app_context(); self.ctx.push()
        init_db(); self.client = app.test_client()
        self.op = OrdemProducao(op='OP-TESTE', referencia='JEANS', qtd='{"M":100}', peso_unit='{"M":0.8}')
        db.session.add(self.op); db.session.commit()
        self.base = f'/api/gestao/ops/{self.op.id}'

    def tearDown(self):
        db.session.remove(); db.drop_all(); self.ctx.pop()

    def detail(self):
        response = self.client.get(self.base)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    def mutate(self, path='', method='POST', **data):
        payload = {'operador':'Ana', 'revisao':self.detail()['revisao'], **data}
        return self.client.open(self.base+path, method=method, json=payload)

    def cost(self, **fields):
        return self.mutate('/custos', categoria='energia', descricao='Energia da OP', unidade='kWh',
                           quantidade_prevista='10', unitario_previsto='2.35', **fields)

    def test_route_sequence_revision_and_audit(self):
        result = self.mutate('/roteiro', etapas=[{'tipo':'qualidade'}, {'tipo':'expedicao'}])
        self.assertEqual(result.status_code, 200)
        quality, dispatch = result.get_json()['etapas']
        self.assertEqual(self.mutate(f"/etapas/{dispatch['id']}/apontar", acao='iniciar').status_code, 409)
        self.assertEqual(self.mutate(f"/etapas/{quality['id']}/apontar", acao='iniciar').status_code, 200)
        self.assertEqual(self.mutate('/roteiro', etapas=[{'tipo':'expedicao'},{'tipo':'qualidade'}]).status_code, 409)
        self.assertEqual(self.mutate(f"/etapas/{quality['id']}/apontar", acao='concluir').status_code, 200)
        self.assertEqual(self.mutate(f"/etapas/{dispatch['id']}/apontar", acao='iniciar').status_code, 200)
        self.assertEqual(self.mutate(f"/etapas/{dispatch['id']}/apontar", acao='concluir').status_code, 200)
        self.assertTrue(self.detail()['concluida'])
        stale = self.client.put(self.base, json={'operador':'Ana','revisao':0,'cliente':'Desatualizado'})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(len(self.detail()['historico']), 5)

    def test_automatic_route_uses_real_production(self):
        machine=Maquina.query.filter_by(tipo='lavar').first()
        load=Carga(maquina_id=machine.id,op_id=self.op.id,numero=1,peso=80,status='aguardando')
        db.session.add(load);db.session.commit()
        self.mutate('/roteiro',etapas=[{'tipo':'lavar'}])
        step=self.detail()['etapas'][0]
        self.assertTrue(step['automatico'])
        self.assertEqual(self.mutate(f"/etapas/{step['id']}/apontar",acao='iniciar').status_code,409)
        for action in ('iniciar','concluir'):
            revision=load.apontamentos[-1].id if load.apontamentos else 0
            r=self.client.post(f'/api/operacao/cargas/{load.id}/apontar',json={'operador':'Ana','acao':action,'revisao':revision,'peso':80,'pecas':100})
            self.assertEqual(r.status_code,200)
        step=self.detail()['etapas'][0]
        self.assertEqual(step['status'],'concluido');self.assertIsNotNone(step['fim_real'])

    def test_margin_waits_for_actual_cost_and_invoice(self):
        self.mutate(method='PUT',receita_prevista='100')
        self.assertEqual(self.cost().status_code,200)
        costs=self.detail()['custos'];cid=costs['linhas'][0]['id']
        self.assertEqual(costs['total_previsto'],23.5)
        self.assertEqual(costs['margem_prevista'],76.5)
        self.assertIsNone(costs['margem_real'])
        self.mutate(f'/custos/{cid}',method='PUT',quantidade_real='12',unitario_real='2.50')
        self.assertIsNone(self.detail()['custos']['margem_real'])
        invoice=Faturamento(op_id=self.op.id,op_numero=self.op.op,referencia=self.op.referencia,valor_total=90,qtd_pecas=100,data_faturamento=date.today())
        db.session.add(invoice);db.session.commit()
        costs=self.detail()['custos']
        self.assertEqual(costs['margem_real'],60);self.assertEqual(costs['margem_pct'],66.67)
        r=self.client.delete(f'/api/faturamento/{invoice.id}',json={'operador':'Ana','motivo':'Lançamento incorreto'})
        self.assertEqual(r.status_code,200)
        self.assertIsNotNone(db.session.get(Faturamento,invoice.id))
        self.assertIsNone(self.detail()['custos']['margem_real'])
        self.assertEqual(self.client.get('/api/dre').get_json()['total_faturado'],0)

    def test_recipe_import_snapshots_prices_without_stock_movement(self):
        product=ProdutoQuimico(nome='Sabão',unidade='kg',quantidade_atual=100,custo_unitario=12,ativo=True)
        recipe=Receita(nome='Jeans',versao=1)
        db.session.add_all([product,recipe]);db.session.flush()
        db.session.add(ReceitaEtapa(receita_id=recipe.id,titulo='Lavagem',produto_quimico_id=product.id,quantidade=2,unidade='kg'))
        db.session.commit()
        r=self.mutate('/custos/receita',receita_id=recipe.id,repeticoes=3)
        self.assertEqual(r.status_code,200,r.get_data(as_text=True))
        self.assertEqual(r.get_json()['custos']['total_previsto'],72)
        self.assertEqual(product.quantidade_atual,100)
        product.custo_unitario=20;db.session.commit()
        self.assertEqual(self.detail()['custos']['total_previsto'],72)
        self.assertEqual(self.mutate('/custos/receita',receita_id=recipe.id,repeticoes=3).status_code,409)

    def test_archive_restore_keeps_records_and_blocks_use(self):
        p=ProdutoQuimico(nome='Produto',unidade='kg',ativo=True,quantidade_atual=10)
        db.session.add(p);db.session.commit()
        url=f'/api/quimicos/{p.id}'
        self.assertEqual(self.client.delete(url).status_code,400)
        self.assertEqual(self.client.delete(url,json={'operador':'Ana','motivo':'Descontinuado'}).status_code,200)
        self.assertEqual(self.client.get('/api/quimicos').get_json(),[])
        self.assertEqual(self.client.put(url,json={'ativo':True}).status_code,409)
        self.assertEqual(self.client.post(url+'/movimentar',json={'tipo':'saida','quantidade':1}).status_code,409)
        self.assertEqual(db.session.get(ProdutoQuimico,p.id).quantidade_atual,10)
        self.assertEqual(self.client.post(f'/api/gestao/arquivados/quimicos/{p.id}/restaurar',json={'operador':'Ana'}).status_code,200)
        self.assertTrue(p.ativo)
        self.assertEqual(len(self.client.get('/api/quimicos').get_json()),1)
        hist=self.client.get(f'/api/gestao/arquivados/quimicos/{p.id}/historico').get_json()
        self.assertEqual(len(hist['historico']),2)

    def test_all_supported_archives_are_hidden_and_restorable(self):
        records=[('ops',self.op),('funcionarios',Funcionario(nome='Ana',ativo=True)),
                 ('receitas',Receita(nome='Receita')),('amostras',PecaAmostra(referencia='A')),
                 ('manutencoes',Manutencao(equipamento='Máquina',ativo=True)),
                 ('os',OrdemServico(equipamento='Máquina',descricao_problema='Teste',status='CONCLUIDA')),
                 ('precos',TabelaPreco(op='OP-TESTE',referencia='JEANS',preco_peca=5))]
        db.session.add_all([r for _,r in records]);db.session.commit()
        for tipo,row in records:
            with self.subTest(tipo=tipo):
                r=self.client.delete(f'/api/{tipo}/{row.id}',json={'operador':'Ana','motivo':'Fim de uso'})
                self.assertEqual(r.status_code,200,r.get_data(as_text=True))
                listing=self.client.get(f'/api/{tipo}').get_json()
                self.assertFalse(any(item['id']==row.id for item in listing))
                self.assertEqual(self.client.post(f'/api/gestao/arquivados/{tipo}/{row.id}/restaurar',json={'operador':'Ana'}).status_code,200)

    def test_invalid_costs_and_route_rollback(self):
        for n in ('NaN','Infinity','-1','1000000001'):
            self.assertEqual(self.mutate('/custos',categoria='agua',descricao='Água',unidade='m3',quantidade_prevista=n,unitario_previsto=1).status_code,400)
        self.assertEqual(self.mutate('/roteiro',etapas=[{'tipo':[]}]).status_code,400)
        self.assertEqual(self.detail()['revisao'],0)
        self.assertEqual(self.detail()['custos']['linhas'],[])
        self.assertEqual(self.client.post(self.base+'/custos',json=['inválido']).status_code,400)

    def test_ambiguous_legacy_reference_is_not_double_counted(self):
        other=OrdemProducao(op=self.op.op,referencia=self.op.referencia)
        invoice=Faturamento(op_numero=self.op.op,referencia=self.op.referencia,valor_total=100,data_faturamento=date.today())
        db.session.add_all([other,invoice]);db.session.commit()
        d=self.detail();self.assertTrue(d['vinculo_ambiguo']);self.assertEqual(d['custos']['receita_faturada'],0)

    def test_cannot_archive_op_with_pending_production(self):
        machine=Maquina.query.first()
        db.session.add(Carga(maquina_id=machine.id,op_id=self.op.id,numero=1,status='aguardando'));db.session.commit()
        self.assertEqual(self.client.delete(f'/api/ops/{self.op.id}',json={'operador':'Ana','motivo':'Teste'}).status_code,409)

    def test_generation_preserves_started_loads_and_events(self):
        machine=Maquina.query.filter_by(tipo='lavar').first()
        c=Carga(maquina_id=machine.id,op_id=self.op.id,op_manual=self.op.op,referencia=self.op.referencia,numero=1,status='aguardando')
        db.session.add(c);db.session.commit()
        self.client.post(f'/api/operacao/cargas/{c.id}/apontar',json={'operador':'Ana','acao':'iniciar','revisao':0})
        response=self.client.post(f'/api/maquinas/{machine.id}/gerar_cargas',json={'op':self.op.op,'referencia':self.op.referencia,'quantidade':2,'data_inicio':'2026-09-14T08:00'})
        self.assertEqual(response.status_code,409)
        self.assertEqual(Carga.query.count(),1);self.assertEqual(len(c.apontamentos),1)

    def test_archived_op_cannot_be_reused_by_legacy_forms(self):
        self.client.delete(f'/api/ops/{self.op.id}',json={'operador':'Ana','motivo':'Fim'})
        machine=Maquina.query.first()
        r=self.client.post(f'/api/maquinas/{machine.id}/cargas',json={'op':self.op.op,'referencia':self.op.referencia})
        self.assertEqual(r.status_code,409)
        r=self.client.post('/api/faturamento',json={'op_numero':self.op.op,'referencia':self.op.referencia,'valor_total':100})
        self.assertEqual(r.status_code,409);self.assertEqual(Faturamento.query.count(),0)
        r=self.client.post('/api/passadoria/fila',json={'op':self.op.op,'referencia':self.op.referencia})
        self.assertEqual(r.status_code,409)

    def test_archived_product_cannot_be_added_to_recipe(self):
        p=ProdutoQuimico(nome='Produto',ativo=True);db.session.add(p);db.session.commit()
        self.client.delete(f'/api/quimicos/{p.id}',json={'operador':'Ana','motivo':'Fim'})
        r=self.client.post('/api/receitas',json={'nome':'Nova','etapas':[{'produto_quimico_id':p.id,'titulo':'Uso','quantidade':1}]})
        self.assertEqual(r.status_code,409);self.assertEqual(Receita.query.count(),0)

    def test_cpm_snapshot_and_cancelled_cost_audit(self):
        staff=Funcionario(nome='Ana',salario_base=2200,jornada_mensal_h=220,eficiencia_pct=100,ativo=True)
        db.session.add(staff);db.session.commit()
        expected=round(staff.cpm*100,2)
        r=self.mutate('/custos',categoria='mao_obra',descricao='Costura',unidade='min',quantidade_prevista=100,unitario_previsto=0,funcionario_id=staff.id)
        self.assertEqual(r.status_code,200)
        costs=r.get_json()['custos'];self.assertEqual(costs['total_previsto'],expected)
        cid=costs['linhas'][0]['id'];staff.salario_base=4400;db.session.commit()
        self.assertEqual(self.detail()['custos']['total_previsto'],expected)
        self.assertEqual(self.mutate(f'/custos/{cid}/cancelar',motivo='Duplicado').status_code,200)
        self.assertEqual(self.detail()['custos']['linhas'],[])
        self.assertIn('Duplicado',self.detail()['historico'][0]['detalhe'])

    def test_explicit_invoice_link_and_op_identity_preserved(self):
        r=self.client.post('/api/faturamento',json={'op_id':self.op.id,'op_numero':self.op.op,'referencia':self.op.referencia,'valor_total':250})
        self.assertEqual(r.status_code,200)
        self.assertEqual(Faturamento.query.first().op_id,self.op.id)
        self.mutate(method='PUT',cliente='Cliente')
        self.assertEqual(self.client.put(f'/api/ops/{self.op.id}',json={'op':'NOVO'}).status_code,409)

    def test_programada_lavagem_only_washers_and_updates_after_removal(self):
        def scheduled():
            return next(o for o in self.client.get('/api/ops').get_json() if o['id']==self.op.id)['programada_lavagem']
        self.assertFalse(scheduled())
        dryer=Maquina.query.filter_by(tipo='secador').first()
        db.session.add(Carga(maquina_id=dryer.id,op_id=self.op.id,numero=1));db.session.commit()
        self.assertFalse(scheduled())
        washer=Maquina.query.filter_by(tipo='lavar').first()
        c=Carga(maquina_id=washer.id,op_id=self.op.id,numero=1,status='aguardando')
        db.session.add(c);db.session.commit();self.assertTrue(scheduled())
        self.assertEqual(self.client.delete(f'/api/cargas/{c.id}').status_code,200)
        self.assertFalse(scheduled())
        db.session.add(Carga(maquina_id=washer.id,op_id=self.op.id,numero=1,status='concluido'));db.session.commit()
        self.assertTrue(scheduled())

    def test_programada_legacy_requires_unique_number_and_reference(self):
        washer=Maquina.query.filter_by(tipo='lavar').first()
        db.session.add(Carga(maquina_id=washer.id,op_manual=self.op.op,referencia=self.op.referencia,numero=1))
        db.session.commit()
        self.assertTrue(self.client.get('/api/ops').get_json()[0]['programada_lavagem'])
        duplicate=OrdemProducao(op=self.op.op,referencia=self.op.referencia)
        db.session.add(duplicate);db.session.commit()
        self.assertTrue(all(not o['programada_lavagem'] for o in self.client.get('/api/ops').get_json()))


if __name__=='__main__':
    unittest.main()
