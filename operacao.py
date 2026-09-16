"""Painel diário e apontamentos reais, separados dos horários planejados."""
from datetime import datetime, timedelta, timezone, date
from flask import jsonify, request
from sqlalchemy.orm import selectinload
from decimal import Decimal, InvalidOperation

# Horário operacional de Içara/SC. Datas planejadas existentes são locais.
LOCAL = timezone(timedelta(hours=-3))


def agora_local():
    return datetime.now(LOCAL).replace(tzinfo=None)


def register_operacao(app, db, Carga, Maquina, Produto, Manutencao, OrdemServico):
    class ApontamentoCarga(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        carga_id = db.Column(db.Integer, db.ForeignKey('carga.id'), nullable=False, index=True)
        acao = db.Column(db.String(20), nullable=False)
        data = db.Column(db.DateTime, nullable=False, default=agora_local)
        operador = db.Column(db.String(80), nullable=False)
        motivo = db.Column(db.String(200), default='')
        peso = db.Column(db.Float, nullable=False, default=0)
        carga = db.relationship(Carga, backref=db.backref('apontamentos', order_by='ApontamentoCarga.id', lazy='selectin'))

    class MedicaoConclusao(db.Model):
        apontamento_id = db.Column(db.Integer, db.ForeignKey('apontamento_carga.id'), primary_key=True)
        pecas = db.Column(db.Integer, nullable=False)
        apontamento = db.relationship(ApontamentoCarga, backref=db.backref('medicao', uselist=False, lazy='selectin'))

    def estado(c):
        if c.status == 'em_processo' and c.apontamentos and c.apontamentos[-1].acao == 'pausar':
            return 'pausado'
        return c.status

    def serialize(c):
        return {
            'id': c.id, 'numero': c.numero, 'op': c.op_manual or '',
            'referencia': c.referencia or '', 'lavacao': c.lavacao or '',
            'peso': c.peso or 0, 'pecas': c.qtde_pecas or 0,
            'status': estado(c), 'revisao': c.apontamentos[-1].id if c.apontamentos else 0,
            'inicio_previsto': c.data_inicio.isoformat() if c.data_inicio else None,
            'saida_prevista': c.data_saida.isoformat() if c.data_saida else None,
            'historico': [{'acao': a.acao, 'data': a.data.isoformat(), 'operador': a.operador,
                           'motivo': a.motivo, 'peso': a.peso,
                           'pecas': a.medicao.pecas if a.medicao else None} for a in c.apontamentos],
        }

    @app.get('/api/operacao/maquinas/<int:mid>')
    def fila_operador(mid):
        m = db.get_or_404(Maquina, mid)
        return jsonify(maquina={'id': m.id, 'tipo': m.tipo, 'numero': m.numero},
                       cargas=[serialize(c) for c in sorted(m.cargas, key=lambda c: c.numero)])

    @app.post('/api/operacao/cargas/<int:cid>/apontar')
    def apontar(cid):
        d = request.get_json(silent=True) or {}
        acao = d.get('acao')
        operador = str(d.get('operador') or '').strip()
        motivo = str(d.get('motivo') or '').strip()
        if not operador or len(operador) > 80:
            return jsonify(error='Informe o operador (até 80 caracteres).'), 400
        if len(motivo) > 200 or (acao == 'pausar' and not motivo):
            return jsonify(error='Informe o motivo da pausa (até 200 caracteres).'), 400
        c = db.get_or_404(Carga, cid)
        # Serializa ações concorrentes na mesma máquina no PostgreSQL.
        db.session.query(Maquina).filter_by(id=c.maquina_id).with_for_update().one()
        db.session.refresh(c)
        atual = estado(c)
        revisao = c.apontamentos[-1].id if c.apontamentos else 0
        if d.get('revisao') != revisao:
            return jsonify(error='A carga foi atualizada. Atualize a fila e tente novamente.'), 409
        permitidas = {'aguardando': ['iniciar', 'concluir'], 'em_processo': ['pausar', 'concluir'],
                      'pausado': ['retomar'], 'concluido': []}
        if acao not in permitidas.get(atual, []):
            return jsonify(error='Ação incompatível com o estado atual. Atualize a fila.'), 409
        peso, pecas = c.peso or 0, None
        if acao == 'concluir':
            try:
                if isinstance(d.get('peso'), bool) or isinstance(d.get('pecas'), bool):
                    raise ValueError()
                kg = Decimal(str(d.get('peso', '')))
                qtd = Decimal(str(d.get('pecas', '')))
                if not kg.is_finite() or not qtd.is_finite() or not (0 < kg <= 1000000) or not (0 < qtd <= 10000000):
                    raise ValueError()
                if qtd != qtd.to_integral_value() or kg != kg.quantize(Decimal('0.001')):
                    raise ValueError()
                peso, pecas = float(kg), int(qtd)
            except (InvalidOperation, ValueError, TypeError):
                return jsonify(error='Informe o peso realizado em kg (até três casas decimais) e a quantidade inteira de peças, ambos maiores que zero.'), 400
        if acao == 'iniciar' and Carga.query.filter(
                Carga.maquina_id == c.maquina_id, Carga.id != c.id,
                Carga.status == 'em_processo').first():
            return jsonify(error='Conclua a carga em andamento nesta máquina antes de iniciar outra.'), 409
        novo_status = 'concluido' if acao == 'concluir' else 'em_processo'
        changed = Carga.query.filter(Carga.id == c.id, Carga.status == c.status,
            ~Carga.apontamentos.any(ApontamentoCarga.id > revisao)).update(
                {Carga.status: novo_status}, synchronize_session=False)
        if changed != 1:
            db.session.rollback()
            return jsonify(error='A carga foi atualizada. Atualize a fila e tente novamente.'), 409
        evento = ApontamentoCarga(carga=c, acao=acao, operador=operador,
                                 motivo=motivo, peso=peso)
        db.session.add(evento)
        if acao == 'concluir':
            db.session.add(MedicaoConclusao(apontamento=evento, pecas=pecas))
        db.session.flush()
        db.session.refresh(c)
        if 'fluxo' in app.extensions:
            app.extensions['fluxo'].sync_source('carga', c.id, operador)
        db.session.commit()
        return jsonify(ok=True, carga=serialize(c))

    @app.get('/api/operacao/resumo')
    def resumo():
        agora = agora_local()
        try:
            dia = date.fromisoformat(request.args.get('data', agora.date().isoformat()))
        except ValueError:
            return jsonify(error='Data inválida. Use AAAA-MM-DD.'), 400
        inicio = datetime.combine(dia, datetime.min.time())
        fim = inicio + timedelta(days=1)
        etapas = {t: {'previsto_kg': 0, 'realizado_kg': 0, 'realizado_pecas': 0,
                      'pecas_sem_medicao': 0, 'previstas': 0, 'concluidas': 0}
                  for t in ('lavar', 'centrifuga', 'secador')}
        cargas = Carga.query.options(selectinload(Carga.maquina), selectinload(Carga.apontamentos)).all()
        em_processo, pausadas, atrasadas = set(), set(), []
        for c in cargas:
            if not c.maquina or c.maquina.tipo not in etapas:
                continue
            etapa = etapas[c.maquina.tipo]
            if c.data_saida and inicio <= c.data_saida < fim:
                etapa['previsto_kg'] += c.peso or 0
                etapa['previstas'] += 1
            for a in c.apontamentos:
                if a.acao == 'concluir' and inicio <= a.data < fim:
                    etapa['realizado_kg'] += a.peso
                    if a.medicao:
                        etapa['realizado_pecas'] += a.medicao.pecas
                    else:
                        etapa['pecas_sem_medicao'] += 1
                    etapa['concluidas'] += 1
            if estado(c) == 'pausado':
                pausadas.add(c.maquina_id)
            elif c.status == 'em_processo':
                em_processo.add(c.maquina_id)
            if c.status != 'concluido' and c.data_saida and c.data_saida < agora:
                atrasadas.append({'id': c.id, 'maquina_id': c.maquina_id, 'op': c.op_manual or 'Sem OP',
                                  'tipo': c.maquina.tipo, 'numero': c.maquina.numero,
                                  'saida_prevista': c.data_saida.isoformat()})
        for etapa in etapas.values():
            etapa['previsto_kg'] = round(etapa['previsto_kg'], 2)
            etapa['realizado_kg'] = round(etapa['realizado_kg'], 2)
        atrasadas.sort(key=lambda c: c['saida_prevista'])
        estoque = sum(p.status_estoque != 'ok' for p in Produto.query.filter_by(ativo=True).all())
        manutencoes = Manutencao.query.filter(Manutencao.ativo.is_(True),
                                            Manutencao.data_proxima < agora.date()).count()
        os_abertas = OrdemServico.query.filter(OrdemServico.status != 'CONCLUIDA').count()
        return jsonify(data=dia.isoformat(), atualizado_em=agora.isoformat(), etapas=etapas,
                       em_processo=len(em_processo), pausadas=len(pausadas),
                       atrasadas=len(atrasadas), pendencias=atrasadas[:20],
                       estoque_baixo=estoque, manutencoes_vencidas=manutencoes, os_abertas=os_abertas)
