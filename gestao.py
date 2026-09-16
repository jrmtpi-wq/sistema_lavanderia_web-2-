"""Ficha de OP, roteiro, custos e arquivamento sem remover o histórico."""
import json
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from types import SimpleNamespace
from flask import request, jsonify, abort
from sqlalchemy import or_, and_
from operacao import agora_local

ETAPAS = {'lavar': 'Lavagem', 'centrifuga': 'Centrifugação', 'secador': 'Secagem',
          'laser': 'Laser', 'passadoria': 'Passadoria', 'robo': 'Robô de passadoria',
          'qualidade': 'Qualidade', 'expedicao': 'Expedição'}
CATEGORIAS = {'quimicos': 'Químicos', 'mao_obra': 'Mão de obra', 'agua': 'Água',
              'energia': 'Energia', 'outros': 'Outros'}


def numero(value, label, optional=False):
    if optional and value in (None, ''):
        return None
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0 or n > Decimal('1000000000'):
            raise ValueError()
        return n.quantize(Decimal('.0001'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        abort(400, description=f'{label}: informe um número entre zero e um bilhão.')


def dinheiro(value):
    return float(Decimal(str(value or 0)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def texto(value, label, limit=120, required=False):
    result = str(value or '').strip()
    if len(result) > limit or (required and not result):
        abort(400, description=f'{label}: informe até {limit} caracteres'+(' (obrigatório).' if required else '.'))
    return result


def register_gestao(app, db, models):
    OP, Carga = models['ops'], models['cargas']
    Receita, Produto, Funcionario = models['receitas'], models['quimicos'], models['funcionarios']
    Faturamento, Preco = models['faturamento'], models['precos']
    registry = {k: models[k] for k in ('ops', 'funcionarios', 'quimicos', 'receitas',
                                      'amostras', 'manutencoes', 'faturamento', 'os', 'precos')}

    class CadastroArquivo(db.Model):
        tipo = db.Column(db.String(30), primary_key=True)
        registro_id = db.Column(db.Integer, primary_key=True)
        titulo = db.Column(db.String(240), nullable=False)
        estado_anterior = db.Column(db.Text, nullable=False, default='{}')
        data = db.Column(db.DateTime, nullable=False, default=agora_local)
        operador = db.Column(db.String(80), nullable=False)
        motivo = db.Column(db.String(200), nullable=False)
        restaurado_em = db.Column(db.DateTime)

    class HistoricoGestao(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        tipo = db.Column(db.String(30), nullable=False, index=True)
        registro_id = db.Column(db.Integer, nullable=False, index=True)
        acao = db.Column(db.String(80), nullable=False)
        detalhe = db.Column(db.Text, nullable=False, default='')
        operador = db.Column(db.String(80), nullable=False)
        data = db.Column(db.DateTime, nullable=False, default=agora_local)

    class FichaOP(db.Model):
        op_id = db.Column(db.Integer, db.ForeignKey('ordem_producao.id'), primary_key=True)
        cliente = db.Column(db.String(120), default='')
        responsavel = db.Column(db.String(80), default='')
        prazo = db.Column(db.Date)
        receita_prevista = db.Column(db.Numeric(18, 4))
        revisao = db.Column(db.Integer, nullable=False, default=1)

    class EtapaOP(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        op_id = db.Column(db.Integer, db.ForeignKey('ordem_producao.id'), nullable=False, index=True)
        ordem = db.Column(db.Integer, nullable=False)
        tipo = db.Column(db.String(20), nullable=False)
        responsavel = db.Column(db.String(80), default='')
        status = db.Column(db.String(20), nullable=False, default='aguardando')
        inicio_real = db.Column(db.DateTime)
        fim_real = db.Column(db.DateTime)
        __table_args__ = (db.UniqueConstraint('op_id', 'tipo'),)

    class CustoOP(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        op_id = db.Column(db.Integer, db.ForeignKey('ordem_producao.id'), nullable=False, index=True)
        categoria = db.Column(db.String(20), nullable=False)
        descricao = db.Column(db.String(160), nullable=False)
        unidade = db.Column(db.String(20), nullable=False)
        quantidade_prevista = db.Column(db.Numeric(18, 4), nullable=False)
        unitario_previsto = db.Column(db.Numeric(18, 4), nullable=False)
        quantidade_real = db.Column(db.Numeric(18, 4))
        unitario_real = db.Column(db.Numeric(18, 4))
        origem = db.Column(db.String(160), default='Manual')
        cancelado = db.Column(db.Boolean, nullable=False, default=False)

    class ImportacaoReceitaOP(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        op_id = db.Column(db.Integer, db.ForeignKey('ordem_producao.id'), nullable=False)
        receita_id = db.Column(db.Integer, db.ForeignKey('receita.id'), nullable=False)
        __table_args__ = (db.UniqueConstraint('op_id', 'receita_id'),)

    def log(tipo, rid, acao, operador, detalhe=''):
        db.session.add(HistoricoGestao(tipo=tipo, registro_id=rid, acao=acao,
                                      operador=operador, detalhe=detalhe))

    def archived(tipo, rid):
        a = db.session.get(CadastroArquivo, (tipo, rid))
        return a if a and not a.restaurado_em else None

    def query(model, tipo):
        ids = db.select(CadastroArquivo.registro_id).where(
            CadastroArquivo.tipo == tipo, CadastroArquivo.restaurado_em.is_(None))
        return model.query.filter(~model.id.in_(ids))

    def check_active(tipo, rid):
        if archived(tipo, rid):
            abort(409, description='Cadastro arquivado. Restaure-o antes de alterar ou utilizar.')

    def resolve_op(number, reference, oid=None):
        if oid:
            op = db.get_or_404(OP, oid)
            check_active('ops', op.id)
            if (number and str(number).strip() != op.op) or (reference and str(reference).strip() != op.referencia):
                abort(400, description='Número e referência não correspondem à OP selecionada.')
            return op.id
        matches = OP.query.filter_by(op=str(number or '').strip(), referencia=str(reference or '').strip()).all()
        active = [o for o in matches if not archived('ops', o.id)]
        if matches and not active:
            abort(409, description='A OP está arquivada. Restaure-a antes de programar ou faturar.')
        # OPs duplicadas exigem vínculo explícito, nunca são associadas arbitrariamente.
        return active[0].id if len(matches) == 1 else None

    def author(d):
        return texto(d.get('operador'), 'Responsável pelo registro', 80, True)

    def lock_op(oid, d=None):
        op = OP.query.filter_by(id=oid).with_for_update().first_or_404()
        check_active('ops', oid)
        f = db.session.get(FichaOP, oid)
        revision = f.revisao if f else 0
        if d is not None and d.get('revisao') != revision:
            abort(409, description='Esta OP foi atualizada. Reabra a ficha antes de salvar.')
        if f is None:
            f = FichaOP(op_id=oid, revisao=0)
            db.session.add(f)
        f.revisao += 1
        return op, f

    def related(op):
        # Textos legados só são vinculados quando o par OP/referência é único.
        unique = OP.query.filter(OP.op == op.op, OP.referencia == op.referencia).count() == 1
        condition = Carga.op_id == op.id
        if unique:
            condition = or_(condition, and_(Carga.op_id.is_(None), Carga.op_manual == op.op,
                                           Carga.referencia == op.referencia))
        result = []
        for c in Carga.query.filter(condition).order_by(Carga.numero).all():
            if not c.maquina:
                continue
            started = [a.data for a in c.apontamentos if a.acao == 'iniciar']
            ended = [a.data for a in c.apontamentos if a.acao == 'concluir']
            status = ('pausado' if c.status == 'em_processo' and c.apontamentos
                      and c.apontamentos[-1].acao == 'pausar' else c.status)
            result.append({'tipo': c.maquina.tipo, 'status': status, 'id': c.id,
                           'maquina_id': c.maquina_id, 'nome': f'{ETAPAS.get(c.maquina.tipo, c.maquina.tipo)} {c.maquina.numero} · carga {c.numero}',
                           'inicio_real': min(started) if started else None,
                           'fim_real': max(ended) if ended else None,
                           'previsto': c.data_saida,
                           'eventos': [{'acao': a.acao, 'operador': a.operador, 'motivo': a.motivo,
                                        'data': a.data.isoformat()} for a in c.apontamentos]})
        if unique:
            for tipo, key in [('laser', 'laser'), ('passadoria', 'passadoria'), ('robo', 'robo')]:
                Model = models[key]
                for item in Model.query.filter_by(op=op.op, referencia=op.referencia).all():
                    if getattr(item, 'tipo', 'op') != 'op':
                        continue
                    result.append({'tipo': tipo, 'status': item.status, 'id': item.id, 'maquina_id': None,
                                   'nome': f'{ETAPAS[tipo]} · item {item.id}', 'inicio_real': None, 'fim_real': None,
                                   'previsto': getattr(item, 'data_fim', None), 'eventos': []})
        return result, not unique

    def route(op, production):
        if 'fluxo' in app.extensions:
            current = app.extensions['fluxo'].route(op)
            if current is not None:
                return current
        rows = EtapaOP.query.filter_by(op_id=op.id).order_by(EtapaOP.ordem).all()
        out = []
        prior_end = None
        for e in rows:
            sources = [r for r in production if r['tipo'] == e.tipo]
            status, start, end = e.status, e.inicio_real, e.fim_real
            if sources:
                status = ('concluido' if all(r['status'] == 'concluido' for r in sources) else
                          'pausado' if any(r['status'] == 'pausado' for r in sources) else
                          'em_processo' if any(r['status'] in ('em_processo','concluido') for r in sources) else 'aguardando')
                starts = [r['inicio_real'] for r in sources if r['inicio_real']]
                ends = [r['fim_real'] for r in sources if r['fim_real']]
                start = min(starts) if starts else None
                end = max(ends) if status == 'concluido' and len(ends) == len(sources) else None
            wait = max(0, int(((start or agora_local())-prior_end).total_seconds()/60)) if prior_end else None
            out.append({'id': e.id, 'tipo': e.tipo, 'nome': ETAPAS[e.tipo], 'ordem': e.ordem,
                        'responsavel': e.responsavel, 'status': status, 'automatico': bool(sources),
                        'inicio_real': start.isoformat() if start else None,
                        'fim_real': end.isoformat() if end else None, 'espera_min': wait})
            prior_end = end
        return out

    def cost_dict(c):
        real = c.quantidade_real*c.unitario_real if c.quantidade_real is not None and c.unitario_real is not None else None
        return {'id': c.id, 'categoria': c.categoria, 'descricao': c.descricao, 'unidade': c.unidade,
                'quantidade_prevista': float(c.quantidade_prevista), 'unitario_previsto': float(c.unitario_previsto),
                'quantidade_real': float(c.quantidade_real) if c.quantidade_real is not None else None,
                'unitario_real': float(c.unitario_real) if c.unitario_real is not None else None,
                'previsto': dinheiro(c.quantidade_prevista*c.unitario_previsto),
                'real': dinheiro(real) if real is not None else None, 'origem': c.origem}

    def costs(op, ficha):
        rows = CustoOP.query.filter_by(op_id=op.id, cancelado=False).order_by(CustoOP.id).all()
        linhas = [cost_dict(c) for c in rows]
        unique = OP.query.filter_by(op=op.op, referencia=op.referencia).count() == 1
        cond = Faturamento.op_id == op.id
        if unique:
            cond = or_(cond, and_(Faturamento.op_id.is_(None), Faturamento.op_numero == op.op,
                                 Faturamento.referencia == op.referencia))
        invoices = query(Faturamento, 'faturamento').filter(cond).all()
        revenue = sum(Decimal(str(f.valor_total or 0)) for f in invoices)
        previsto = sum(c.quantidade_prevista*c.unitario_previsto for c in rows)
        realized = sum(c.quantidade_real*c.unitario_real for c in rows if c.quantidade_real is not None and c.unitario_real is not None)
        pending = sum(c.quantidade_real is None or c.unitario_real is None for c in rows)
        expected = ficha.receita_prevista if ficha and ficha.receita_prevista is not None else None
        source = 'Informada na ficha'
        if expected is None:
            price = query(Preco, 'precos').filter_by(op=op.op.strip().upper(), referencia=op.referencia.strip().upper()).first()
            if price:
                expected = Decimal(str(price.preco_peca))*op.total_pecas
                source = 'Tabela de preços atual'
        ready = bool(rows) and pending == 0 and bool(invoices)
        margin = revenue-realized if ready else None
        return {'linhas': linhas, 'total_previsto': dinheiro(previsto), 'total_real': dinheiro(realized),
                'pendentes': pending, 'receita_prevista': dinheiro(expected) if expected is not None else None,
                'origem_receita_prevista': source, 'receita_faturada': dinheiro(revenue), 'tem_faturamento': bool(invoices),
                'margem_prevista': dinheiro(expected-previsto) if expected is not None and rows else None,
                'margem_real': dinheiro(margin) if margin is not None else None,
                'margem_pct': dinheiro(margin/revenue*100) if margin is not None and revenue else None,
                'categorias': {k: {'previsto': dinheiro(sum(c.quantidade_prevista*c.unitario_previsto for c in rows if c.categoria == k)),
                                    'real': dinheiro(sum(c.quantidade_real*c.unitario_real for c in rows if c.categoria == k and c.quantidade_real is not None and c.unitario_real is not None))} for k in CATEGORIAS}}

    def detail(oid):
        op = db.get_or_404(OP, oid)
        f = db.session.get(FichaOP, oid)
        production, ambiguous = related(op)
        etapas = route(op, production)
        finished = app.extensions['fluxo'].ready(oid) if 'fluxo' in app.extensions else False
        for row in production:
            for field in ('inicio_real','fim_real','previsto'):
                row[field] = row[field].isoformat() if row[field] else None
        return {'id': op.id, 'op': op.op, 'referencia': op.referencia, 'lavacao': op.lavacao,
                'pecas': op.total_pecas, 'peso': op.peso_total, 'cliente': f.cliente if f else '',
                'responsavel': f.responsavel if f else '', 'prazo': f.prazo.isoformat() if f and f.prazo else None,
                'receita_prevista_informada': float(f.receita_prevista) if f and f.receita_prevista is not None else None,
                'revisao': f.revisao if f else 0, 'arquivada': bool(archived('ops',oid)),
                'atrasada': bool(f and f.prazo and f.prazo < agora_local().date() and not finished),
                'concluida': finished, 'vinculo_ambiguo': ambiguous, 'etapas': etapas,
                'fluxo_novo': bool('fluxo' in app.extensions and app.extensions['fluxo'].route(op) is not None),
                'producao': production, 'custos': costs(op, f),
                'historico': [{'acao': h.acao, 'detalhe': h.detalhe, 'operador': h.operador, 'data': h.data.isoformat()}
                              for h in HistoricoGestao.query.filter_by(tipo='ops',registro_id=oid).order_by(HistoricoGestao.id.desc()).all()]}

    @app.get('/api/gestao/ops')
    def get_gestao_ops():
        result = []
        for op in query(OP,'ops').order_by(OP.id.desc()).all():
            f = db.session.get(FichaOP,op.id)
            production,_ = related(op)
            etapas = route(op,production)
            done = app.extensions['fluxo'].ready(op.id) if 'fluxo' in app.extensions else False
            result.append({'id':op.id,'op':op.op,'referencia':op.referencia,'cliente':f.cliente if f else '',
                           'responsavel':f.responsavel if f else '', 'prazo':f.prazo.isoformat() if f and f.prazo else None,
                           'etapa_atual':next((e['nome'] for e in etapas if e['status']!='concluido'), 'Concluída' if done else 'Conferir fase final' if etapas else 'Sem roteiro'),
                           'concluida':done,'atrasada':bool(f and f.prazo and f.prazo<agora_local().date() and not done),
                           'etapas_concluidas':sum(e['status']=='concluido' for e in etapas),'total_etapas':len(etapas)})
        return jsonify(result)

    @app.get('/api/gestao/ops/<int:oid>')
    def get_ficha(oid):
        return jsonify(detail(oid))

    @app.put('/api/gestao/ops/<int:oid>')
    def save_ficha(oid):
        d = request.get_json(silent=True) or {}
        operator = author(d)
        cliente = texto(d.get('cliente'),'Cliente')
        responsavel = texto(d.get('responsavel'),'Responsável',80)
        try:
            prazo = date.fromisoformat(d['prazo']) if d.get('prazo') else None
        except (ValueError,TypeError):
            abort(400,description='Prazo inválido.')
        expected = numero(d.get('receita_prevista'),'Receita prevista',True)
        op,f = lock_op(oid,d)
        before = {'cliente': f.cliente, 'responsavel':f.responsavel,'prazo':str(f.prazo),'receita_prevista':str(f.receita_prevista)}
        f.cliente,f.responsavel,f.prazo,f.receita_prevista=cliente,responsavel,prazo,expected
        log('ops',oid,'Ficha atualizada',operator,json.dumps({'antes':before,'depois':{'cliente':cliente,'responsavel':responsavel,'prazo':str(prazo),'receita_prevista':str(expected)}},ensure_ascii=False))
        db.session.commit()
        return jsonify(detail(oid))

    @app.post('/api/gestao/ops/<int:oid>/roteiro')
    def save_roteiro(oid):
        d = request.get_json(silent=True) or {}
        operator=author(d)
        items=d.get('etapas')
        if not isinstance(items,list) or not 1 <= len(items) <= len(ETAPAS):
            abort(400,description='Escolha de uma a oito etapas para o roteiro.')
        types=[e.get('tipo') if isinstance(e,dict) else None for e in items]
        if any(not isinstance(t, str) or t not in ETAPAS for t in types) or len(set(types)) != len(types):
            abort(400,description='Escolha etapas válidas, sem repetição.')
        owners=[texto(e.get('responsavel'),'Responsável da etapa',80) for e in items]
        op,f=lock_op(oid,d)
        existing=EtapaOP.query.filter_by(op_id=oid).order_by(EtapaOP.ordem).all()
        production,_=related(op)
        progress=route(op,production)
        if any(e['status']!='aguardando' for e in progress) and types != [e.tipo for e in existing]:
            abort(409,description='O roteiro já iniciou. Altere apenas os responsáveis para preservar o histórico.')
        for e in existing:
            if e.tipo not in types:
                db.session.delete(e)
        by_type={e.tipo:e for e in existing}
        for idx,t in enumerate(types):
            row=by_type.get(t)
            if row is None:
                row=EtapaOP(op_id=oid,tipo=t,ordem=idx+1)
                db.session.add(row)
            row.ordem=idx+1
            row.responsavel=owners[idx]
        log('ops',oid,'Roteiro atualizado',operator,' → '.join(ETAPAS[t] for t in types))
        db.session.commit()
        return jsonify(detail(oid))

    @app.post('/api/gestao/ops/<int:oid>/etapas/<int:eid>/apontar')
    def apontar_etapa(oid,eid):
        d=request.get_json(silent=True) or {}
        operator=author(d)
        op,f=lock_op(oid,d)
        e=EtapaOP.query.filter_by(id=eid,op_id=oid).first_or_404()
        production,_=related(op)
        steps=route(op,production)
        step=next(s for s in steps if s['id']==eid)
        if step['automatico']:
            abort(409,description='Esta etapa acompanha a programação. Registre o andamento nas cargas ou filas vinculadas.')
        if any(s['status']!='concluido' for s in steps if s['ordem']<e.ordem):
            abort(409,description='Conclua as etapas anteriores antes de avançar.')
        action=d.get('acao')
        if action=='iniciar' and e.status=='aguardando':
            e.status='em_processo';e.inicio_real=agora_local()
        elif action=='concluir' and e.status=='em_processo':
            e.status='concluido';e.fim_real=agora_local()
        else:
            abort(409,description='Ação incompatível com a etapa atual.')
        log('ops',oid,f'{ETAPAS[e.tipo]}: {action}',operator)
        db.session.commit()
        return jsonify(detail(oid))

    @app.post('/api/gestao/ops/<int:oid>/custos')
    def add_custo(oid):
        d=request.get_json(silent=True) or {}
        operator=author(d)
        categoria=d.get('categoria')
        if categoria not in CATEGORIAS:
            abort(400,description='Categoria de custo inválida.')
        descricao=texto(d.get('descricao'),'Descrição',160,True)
        unidade=texto(d.get('unidade'),'Unidade',20,True)
        qty=numero(d.get('quantidade_prevista'),'Quantidade prevista')
        price=numero(d.get('unitario_previsto'),'Custo unitário previsto')
        origem='Manual'
        if categoria=='mao_obra' and d.get('funcionario_id'):
            funcionario=db.get_or_404(Funcionario,d['funcionario_id'])
            check_active('funcionarios',funcionario.id)
            if not funcionario.ativo:
                abort(400,description='Selecione um funcionário ativo.')
            price=numero(funcionario.cpm,'CPM')
            unidade='min';origem=f'CPM de {funcionario.nome} na data do lançamento'
        op,f=lock_op(oid,d)
        row=CustoOP(op_id=oid,categoria=categoria,descricao=descricao,unidade=unidade,
                    quantidade_prevista=qty,unitario_previsto=price,origem=origem)
        db.session.add(row)
        log('ops',oid,'Custo previsto incluído',operator,f'{descricao}: {qty} {unidade} × R$ {price}')
        db.session.commit()
        return jsonify(detail(oid))

    @app.put('/api/gestao/ops/<int:oid>/custos/<int:cid>')
    def update_custo(oid,cid):
        d=request.get_json(silent=True) or {}
        operator=author(d)
        qty=numero(d.get('quantidade_real'),'Quantidade realizada')
        price=numero(d.get('unitario_real'),'Custo unitário realizado')
        op,f=lock_op(oid,d)
        row=CustoOP.query.filter_by(id=cid,op_id=oid,cancelado=False).first_or_404()
        before=cost_dict(row)
        row.quantidade_real,row.unitario_real=qty,price
        log('ops',oid,'Custo realizado atualizado',operator,json.dumps({'antes':before,'depois':cost_dict(row)},ensure_ascii=False))
        db.session.commit()
        return jsonify(detail(oid))

    @app.post('/api/gestao/ops/<int:oid>/custos/<int:cid>/cancelar')
    def cancel_custo(oid,cid):
        d=request.get_json(silent=True) or {}
        operator=author(d)
        motivo=texto(d.get('motivo'),'Motivo',200,True)
        op,f=lock_op(oid,d)
        row=CustoOP.query.filter_by(id=cid,op_id=oid,cancelado=False).first_or_404()
        row.cancelado=True
        log('ops',oid,'Custo cancelado',operator,json.dumps({'custo':cost_dict(row),'motivo':motivo},ensure_ascii=False))
        db.session.commit()
        return jsonify(detail(oid))

    @app.post('/api/gestao/ops/<int:oid>/custos/receita')
    def import_receita(oid):
        d=request.get_json(silent=True) or {}
        operator=author(d)
        if not isinstance(d.get('receita_id'), int):
            abort(400, description='Selecione uma receita válida.')
        recipe=db.get_or_404(Receita,d['receita_id'])
        check_active('receitas',recipe.id)
        multiplier=numero(d.get('repeticoes'),'Repetições')
        if multiplier<=0:
            abort(400,description='Informe o número de execuções da receita, maior que zero.')
        op,f=lock_op(oid,d)
        if ImportacaoReceitaOP.query.filter_by(op_id=oid,receita_id=recipe.id).first():
            abort(409,description='Esta receita já foi importada nesta OP. Ajuste os lançamentos existentes.')
        lines=[]
        for e in recipe.etapas:
            if not e.produto_quimico_id or not e.quantidade:
                continue
            p=e.produto
            check_active('quimicos',p.id)
            if not p.ativo:
                abort(400,description=f'O produto {p.nome} está inativo.')
            unit=(e.unidade or p.unidade).strip().lower()
            if unit != p.unidade.strip().lower():
                abort(400,description=f'Unidade de {p.nome} difere do estoque. Ajuste a receita antes de importar.')
            lines.append(CustoOP(op_id=oid,categoria='quimicos',descricao=f'{p.nome} · {e.titulo}'[:160],
                                unidade=p.unidade,quantidade_prevista=numero(numero(e.quantidade,'Quantidade')*multiplier,'Quantidade total'),
                                unitario_previsto=numero(p.custo_unitario,'Custo'),
                                origem=f'Receita {recipe.nome} v{recipe.versao} · {multiplier} execuções'[:160]))
        if not lines:
            abort(400,description='A receita não possui químicos com quantidade e produto cadastrados.')
        db.session.add_all(lines)
        db.session.add(ImportacaoReceitaOP(op_id=oid,receita_id=recipe.id))
        log('ops',oid,'Custos da receita importados',operator,f'{recipe.nome} v{recipe.versao} · {multiplier} execuções; sem movimentar estoque')
        db.session.commit()
        return jsonify(detail(oid))

    def archive(tipo,rid):
        if tipo not in registry:
            abort(404)
        d=request.get_json(silent=True) or {}
        operator=author(d)
        motivo=texto(d.get('motivo'),'Motivo',200,True)
        row=db.get_or_404(registry[tipo],rid)
        if archived(tipo,rid):
            return jsonify(ok=True)
        if tipo=='ops':
            production,_=related(row)
            if any(p['status']!='concluido' for p in production) or any(
                    e['status'] in ('em_processo','pausado') for e in route(row,production)):
                abort(409,description='Conclua a produção em andamento antes de arquivar a OP.')
        if tipo=='os' and row.status != 'CONCLUIDA':
            abort(409,description='Conclua a ordem de serviço antes de arquivá-la.')
        previous={}
        if hasattr(row,'ativo'):
            previous['ativo']=row.ativo;row.ativo=False
        if tipo in ('receitas','amostras'):
            previous['status']=row.status
            row.status='descontinuada' if tipo=='receitas' else 'arquivada'
        title=getattr(row,'nome',None) or getattr(row,'equipamento',None) or getattr(row,'referencia',None) or str(rid)
        if tipo=='ops':
            title=f'{row.op} · {row.referencia}'
        a=db.session.get(CadastroArquivo,(tipo,rid))
        if a is None:
            a=CadastroArquivo(tipo=tipo,registro_id=rid)
            db.session.add(a)
        a.titulo=title;a.estado_anterior=json.dumps(previous);a.data=agora_local()
        a.operador=operator;a.motivo=motivo;a.restaurado_em=None
        log(tipo,rid,'Arquivado',operator,motivo)
        db.session.commit()
        return jsonify(ok=True)

    @app.post('/api/gestao/cadastros/<tipo>/<int:rid>/arquivar')
    def archive_cadastro(tipo, rid):
        return archive(tipo, rid)

    @app.get('/api/gestao/arquivados')
    def get_archives():
        return jsonify([{'tipo':a.tipo,'id':a.registro_id,'titulo':a.titulo,'data':a.data.isoformat(),
                         'operador':a.operador,'motivo':a.motivo} for a in
                        CadastroArquivo.query.filter_by(restaurado_em=None).order_by(CadastroArquivo.data.desc()).all()])

    @app.post('/api/gestao/arquivados/<tipo>/<int:rid>/restaurar')
    def restore(tipo,rid):
        if tipo not in registry:
            abort(404)
        d=request.get_json(silent=True) or {}
        operator=author(d)
        a=archived(tipo,rid)
        if not a:
            abort(409,description='Este cadastro já está disponível.')
        row=db.get_or_404(registry[tipo],rid)
        for key,val in json.loads(a.estado_anterior).items():
            setattr(row,key,val)
        a.restaurado_em=agora_local()
        log(tipo,rid,'Restaurado',operator)
        db.session.commit()
        return jsonify(ok=True)

    @app.get('/api/gestao/arquivados/<tipo>/<int:rid>/historico')
    def archive_history(tipo,rid):
        if tipo not in registry:
            abort(404)
        row=db.get_or_404(registry[tipo],rid)
        return jsonify(registro=detail(rid) if tipo == 'ops' else row.to_dict() if hasattr(row,'to_dict') else {'id':rid,'referencia':getattr(row,'referencia','')},
                       historico=[{'acao':h.acao,'operador':h.operador,'data':h.data.isoformat(),'detalhe':h.detalhe}
                                  for h in HistoricoGestao.query.filter_by(tipo=tipo,registro_id=rid).order_by(HistoricoGestao.id.desc()).all()])

    @app.before_request
    def protect_archived():
        if request.method not in ('PUT','POST','DELETE'):
            return
        parts=request.path.strip('/').split('/')
        if len(parts)>=3 and parts[0]=='api' and parts[1] in registry and parts[2].isdigit():
            check_active(parts[1],int(parts[2]))
        d = request.get_json(silent=True) or {}
        if not isinstance(d, dict):
            abort(400, description='Envie os campos do formulário como um objeto.')
        if request.endpoint in ('add_laser_fila', 'add_passadoria_fila', 'add_robo_passadoria_fila'):
            if d.get('tipo', 'op') == 'op':
                resolve_op(d.get('op'), d.get('referencia'))
        queue_endpoints = {
            'update_laser_fila': ('laser', 'fid'), 'delete_laser_fila': ('laser', 'fid'),
            'update_passadoria_fila': ('passadoria', 'iid'), 'delete_passadoria_fila': ('passadoria', 'iid'),
            'update_robo_passadoria_fila': ('robo', 'iid'), 'delete_robo_passadoria_fila': ('robo', 'iid'),
        }
        if request.endpoint in queue_endpoints:
            key, arg = queue_endpoints[request.endpoint]
            row = db.get_or_404(models[key], request.view_args[arg])
            if getattr(row, 'tipo', 'op') == 'op':
                resolve_op(row.op, row.referencia)
                if request.method == 'DELETE' and row.status != 'aguardando':
                    abort(409, description='Preserve o histórico de itens com produção iniciada.')
                if request.method == 'PUT':
                    if row.status != 'aguardando' and any(k in d and d[k] != getattr(row, k) for k in ('op', 'referencia')):
                        abort(409, description='Preserve a OP e a referência de itens com produção iniciada.')
                    if row.status == 'concluido' and d.get('status', row.status) != row.status:
                        abort(409, description='Uma produção concluída não pode voltar para a fila. Cadastre um novo item.')
                    resolve_op(d.get('op', row.op), d.get('referencia', row.referencia))
        # Também impede novos vínculos através dos formulários antigos.
        for field, tipo in [('op_id', 'ops'), ('receita_id', 'receitas'),
                            ('produto_quimico_id', 'quimicos'), ('funcionario_id', 'funcionarios')]:
            if d.get(field):
                try:
                    rid = int(d[field])
                except (ValueError, TypeError):
                    abort(400, description=f'{field}: identificação inválida.')
                check_active(tipo, rid)
        if len(parts) >= 2 and parts[1] == 'receitas' and 'etapas' in d:
            if not isinstance(d['etapas'], list):
                abort(400, description='Etapas da receita inválidas.')
            for etapa in d['etapas']:
                if not isinstance(etapa, dict):
                    abort(400, description='Etapa da receita inválida.')
                if etapa.get('produto_quimico_id'):
                    try:
                        pid = int(etapa['produto_quimico_id'])
                    except (ValueError, TypeError):
                        abort(400, description='Produto químico inválido.')
                    check_active('quimicos', pid)
        if len(parts) == 3 and parts[1] == 'ops' and parts[2].isdigit() and request.method == 'PUT':
            op = db.get_or_404(OP, int(parts[2]))
            if any(str(d[k]).strip() != getattr(op, k) for k in ('op', 'referencia') if k in d):
                production, _ = related(op)
                if production or db.session.get(FichaOP, op.id):
                    abort(409, description='Esta OP já possui acompanhamento ou produção vinculada. Preserve seu número e referência.')

    # Novas rotas e os DELETEs que passam a arquivar retornam erros legíveis ao frontend.
    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(409)
    def api_error(error):
        if request.path.startswith('/api/'):
            db.session.rollback()
            return jsonify(error=error.description),error.code
        return error.get_response()

    service=SimpleNamespace(query=query,archive=archive,archived=archived,check_active=check_active,resolve_op=resolve_op,
                            detail=detail,related=related,models=SimpleNamespace(FichaOP=FichaOP,EtapaOP=EtapaOP,
                            CustoOP=CustoOP,CadastroArquivo=CadastroArquivo,HistoricoGestao=HistoricoGestao))
    app.extensions['gestao']=service
    return service
