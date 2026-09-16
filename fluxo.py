"""Estoque seco e roteiro por passagem, sem reclassificar produção histórica."""
import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from flask import abort, jsonify, render_template, request
from sqlalchemy import or_
from operacao import agora_local

SETORES = {'lavar': 'Lavanderia', 'centrifuga': 'Centrífuga', 'secador': 'Secador',
           'passadoria': 'Passadoria', 'laser': 'Laser', 'manual': 'Diferenciado / outro setor'}
EXEMPLOS = [
    ('estoque_seco', 'Estoque seco', 'estoque', False),
    ('lavar_preparacao', 'Lavanderia preparação', 'lavar', False),
    ('lavar_final', 'Lavanderia final', 'lavar', False),
    ('centrifuga', 'Centrífuga', 'centrifuga', False),
    ('secador', 'Secador', 'secador', False),
    ('passadoria_preparacao', 'Passadoria preparação', 'passadoria', False),
    ('diferenciado', 'Diferenciado', 'manual', False),
    ('laser_inicial', 'Laser inicial', 'laser', False),
    ('laser_meio', 'Laser meio', 'laser', False),
    ('laser_final', 'Laser final', 'laser', True),
    ('lavar_meio', 'Lavanderia meio', 'lavar', False),
    ('passadoria_final', 'Passadoria final', 'passadoria', True),
]


def register_fluxo(app, db, OP, Carga, Maquina, Receita, Laser, LaserFila, Passadoria, Faturamento, gestao, tamanhos):
    class FaseFluxo(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        nome = db.Column(db.String(80), nullable=False)
        setor = db.Column(db.String(20), nullable=False)

    class ModeloFluxo(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        nome = db.Column(db.String(100), nullable=False)
        passos = db.Column(db.Text, nullable=False)
        criado_em = db.Column(db.DateTime, default=agora_local, nullable=False)

    class FluxoOP(db.Model):
        op_id = db.Column(db.Integer, db.ForeignKey('ordem_producao.id'), primary_key=True)
        nome = db.Column(db.String(100), nullable=False)
        revisao = db.Column(db.Integer, nullable=False, default=1)
        qtd = db.Column(db.Text, nullable=False)
        pesos = db.Column(db.Text, nullable=False)
        conferencia = db.Column(db.Boolean, nullable=False, default=False)
        criado_em = db.Column(db.DateTime, default=agora_local, nullable=False)

    class PassagemOP(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        op_id = db.Column(db.Integer, db.ForeignKey('fluxo_op.op_id'), nullable=False, index=True)
        ordem = db.Column(db.Integer, nullable=False)
        fase = db.Column(db.String(80), nullable=False)
        nome = db.Column(db.String(80), nullable=False)
        setor = db.Column(db.String(20), nullable=False)
        finalizadora = db.Column(db.Boolean, nullable=False, default=False)
        receita = db.Column(db.Text, nullable=False)
        status = db.Column(db.String(20), nullable=False, default='aguardando')
        destino = db.Column(db.String(100))
        movimentado_em = db.Column(db.DateTime)
        inicio_real = db.Column(db.DateTime)
        fim_real = db.Column(db.DateTime)
        __table_args__ = (db.UniqueConstraint('op_id', 'ordem'),)

    class VinculoPassagem(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        passagem_id = db.Column(db.Integer, db.ForeignKey('passagem_op.id'), nullable=False, index=True)
        carga_id = db.Column(db.Integer, db.ForeignKey('carga.id'), unique=True)
        laser_id = db.Column(db.Integer, db.ForeignKey('laser_fila.id'), unique=True)
        passadoria_id = db.Column(db.Integer, db.ForeignKey('passadoria_item.id'), unique=True)

    class MovimentoFluxo(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        op_id = db.Column(db.Integer, db.ForeignKey('ordem_producao.id'), nullable=False, index=True)
        data = db.Column(db.DateTime, default=agora_local, nullable=False)
        operador = db.Column(db.String(80), nullable=False)
        acao = db.Column(db.String(100), nullable=False)
        detalhe = db.Column(db.Text, nullable=False)

    def txt(value, label, limit=100):
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            abort(400, description=f'Informe {label} (até {limit} caracteres).')
        return value.strip()

    def num(value, label, integer=False, zero=False):
        try:
            if isinstance(value, bool):
                raise ValueError()
            n = Decimal(str(value))
            if not n.is_finite() or n < 0 or (not zero and n == 0) or n > 10000000:
                raise ValueError()
            if integer and n != n.to_integral_value():
                raise ValueError()
            return int(n) if integer else n
        except (InvalidOperation, ValueError, TypeError):
            abort(400, description=f'{label}: informe um número válido' + (' inteiro.' if integer else '.'))

    def audit(oid, actor, action, detail):
        db.session.add(MovimentoFluxo(op_id=oid, operador=actor, acao=action,
                                     detalhe=json.dumps(detail, ensure_ascii=False)))

    def phases():
        rows = [{'id': k, 'nome': n, 'setor': s, 'finalizadora': f} for k, n, s, f in EXEMPLOS]
        rows += [{'id': f'custom_{p.id}', 'nome': p.nome, 'setor': p.setor, 'finalizadora': False}
                 for p in FaseFluxo.query.order_by(FaseFluxo.id).all()]
        return rows

    def validate_steps(items):
        catalog = {p['id']: p for p in phases()}
        if not isinstance(items, list) or not 2 <= len(items) <= 40:
            abort(400, description='O roteiro deve ter de 2 a 40 fases, incluindo estoque seco.')
        result = []
        for item in items:
            key = item.get('fase') if isinstance(item, dict) else None
            if not isinstance(key, str) or key not in catalog:
                abort(400, description='Escolha uma fase válida para cada passagem.')
            result.append({**catalog[key], 'receita_id': item.get('receita_id')})
        if result[0]['id'] != 'estoque_seco' or any(p['setor'] == 'estoque' for p in result[1:]):
            abort(400, description='O roteiro deve começar pelo estoque seco, sem repeti-lo.')
        if not result[-1]['finalizadora']:
            abort(400, description='A última fase deve ser Passadoria final ou Laser final.')
        return result

    def recipe_snapshot(rid):
        rid = num(rid, 'Receita', integer=True)
        r = db.get_or_404(Receita, rid)
        gestao.check_active('receitas', rid)
        if r.status == 'descontinuada' or not r.etapas:
            abort(400, description='Selecione uma receita com instruções cadastradas e não descontinuada.')
        return json.dumps(r.to_dict(), ensure_ascii=False)

    def weights(op):
        q, p = op.qtd_dict, op.peso_dict
        if not isinstance(q, dict) or not isinstance(p, dict):
            abort(400, description='Confira a grade de tamanhos da OP.')
        total, weight = 0, Decimal(0)
        for size, value in q.items():
            quantity = num(value, f'Quantidade {size}', integer=True, zero=True)
            if quantity:
                if size not in tamanhos:
                    abort(400, description=f'Tamanho inválido: {size}.')
                unit = num(p.get(size), f'Peso por peça do tamanho {size}')
                if unit != unit.quantize(Decimal('0.001')):
                    abort(400, description=f'Peso do tamanho {size}: use até três casas decimais em kg.')
                total += quantity
                weight += quantity * unit
        if not total or total > 10000000:
            abort(400, description='Cadastre as quantidades por tamanho na OP.')
        return total, weight

    def rows(oid):
        return PassagemOP.query.filter_by(op_id=oid).order_by(PassagemOP.ordem).all()

    def ready(oid):
        steps = rows(oid)
        return bool(steps and steps[-1].finalizadora and all(s.status == 'concluido' for s in steps))

    def lock(oid, d):
        op = OP.query.filter_by(id=oid).with_for_update().first_or_404()
        gestao.check_active('ops', oid)
        flow = db.session.get(FluxoOP, oid)
        revision = flow.revisao if flow else 0
        if type(d.get('revisao')) is not int or d['revisao'] != revision:
            abort(409, description='A OP foi atualizada. Reabra o fluxo antes de salvar.')
        if flow:
            changed = FluxoOP.query.filter_by(op_id=oid, revisao=revision).update(
                {'revisao': revision + 1}, synchronize_session='fetch')
            if changed != 1:
                abort(409, description='A OP foi atualizada. Reabra o fluxo.')
        return op, flow

    def legacy(op):
        return bool(gestao.related(op)[0] or
                    gestao.models.EtapaOP.query.filter(gestao.models.EtapaOP.op_id == op.id,
                        gestao.models.EtapaOP.status != 'aguardando').first() or
                    gestao.query(Faturamento, 'faturamento').filter(or_(Faturamento.op_id == op.id,
                        (Faturamento.op_numero == op.op) & (Faturamento.referencia == op.referencia))).first())

    def detail(oid):
        op = db.get_or_404(OP, oid)
        flow = db.session.get(FluxoOP, oid)
        steps = rows(oid)
        started = any(s.movimentado_em for s in steps) or bool(flow and flow.conferencia)
        out = []
        for s in steps:
            links = VinculoPassagem.query.filter_by(passagem_id=s.id).all()
            out.append({'id': s.id, 'ordem': s.ordem, 'fase': s.fase, 'nome': s.nome,
                        'setor': s.setor, 'finalizadora': s.finalizadora, 'status': s.status,
                        'receita': json.loads(s.receita), 'destino': s.destino,
                        'movimentado_em': s.movimentado_em.isoformat() if s.movimentado_em else None,
                        'inicio_real': s.inicio_real.isoformat() if s.inicio_real else None,
                        'fim_real': s.fim_real.isoformat() if s.fim_real else None,
                        'vinculos': [{'carga_id': v.carga_id, 'laser_id': v.laser_id,
                                     'passadoria_id': v.passadoria_id} for v in links]})
        history = MovimentoFluxo.query.filter_by(op_id=oid).order_by(MovimentoFluxo.id.desc()).all()
        return {'id': oid, 'op': op.op, 'referencia': op.referencia, 'qtd': op.qtd_dict,
                'pesos': op.peso_dict, 'pecas': op.total_pecas, 'peso': round(op.peso_total, 3),
                'revisao': flow.revisao if flow else 0, 'nome': flow.nome if flow else '',
                'etapas': out, 'iniciado': started, 'pronta': ready(oid),
                'legado': not flow and legacy(op), 'conferencia': bool(flow and flow.conferencia),
                'arquivada': bool(gestao.archived('ops', oid)),
                'historico': [{'data': h.data.isoformat(), 'operador': h.operador,
                               'acao': h.acao, 'detalhe': json.loads(h.detalhe)} for h in history]}

    @app.get('/estoque-seco')
    def estoque_seco():
        return render_template('estoque_seco.html', tamanhos=tamanhos, setores=SETORES)

    @app.get('/api/fluxo/catalogo')
    def catalogo_fluxo():
        return jsonify(fases=phases(), modelos=[{'id': m.id, 'nome': m.nome, 'passos': json.loads(m.passos)}
                       for m in ModeloFluxo.query.order_by(ModeloFluxo.nome).all()])

    @app.post('/api/fluxo/fases')
    def create_fase_fluxo():
        d = request.get_json() or {}
        nome = txt(d.get('nome'), 'o nome da fase', 80)
        if d.get('setor') not in SETORES:
            abort(400, description='Selecione o setor da fase.')
        if any(p['nome'].casefold() == nome.casefold() for p in phases()):
            abort(409, description='Já existe uma fase com esse nome.')
        p = FaseFluxo(nome=nome, setor=d['setor'])
        db.session.add(p); db.session.commit()
        return jsonify(id=f'custom_{p.id}')

    @app.post('/api/fluxo/modelos')
    def create_modelo_fluxo():
        d = request.get_json() or {}
        nome = txt(d.get('nome'), 'o nome do roteiro')
        validate_steps(d.get('passos'))
        if ModeloFluxo.query.filter_by(nome=nome).first():
            abort(409, description='Já existe um modelo com esse nome. Use outro nome para a nova versão.')
        m = ModeloFluxo(nome=nome, passos=json.dumps(d['passos'], ensure_ascii=False))
        db.session.add(m); db.session.commit()
        return jsonify(id=m.id)

    @app.get('/api/fluxo/ops')
    def list_fluxo():
        result = []
        for op in gestao.query(OP, 'ops').order_by(OP.id.desc()).all():
            f = db.session.get(FluxoOP, op.id)
            steps = rows(op.id)
            started = any(s.movimentado_em for s in steps) or bool(f and f.conferencia)
            historical = not f and legacy(op)
            pending_weights = [t for t, q in op.qtd_dict.items() if q and not op.peso_dict.get(t)]
            result.append({'id': op.id, 'op': op.op, 'referencia': op.referencia,
                           'pecas': op.total_pecas, 'peso': round(op.peso_total, 3),
                           'saldo_seco': 0 if started or historical else op.total_pecas,
                           'legado': historical, 'pronta': ready(op.id), 'iniciado': started,
                           'pesos_pendentes': pending_weights, 'roteiro': bool(f),
                           'etapa': next((s.nome for s in steps if s.status != 'concluido'),
                                         'Pronta para faturar' if ready(op.id) else 'Sem roteiro')})
        return jsonify(result)

    @app.get('/api/fluxo/ops/<int:oid>')
    def get_fluxo(oid):
        return jsonify(detail(oid))

    @app.post('/api/fluxo/ops/<int:oid>/roteiro')
    def save_fluxo(oid):
        d = request.get_json() or {}
        actor = txt(d.get('operador'), 'o responsável', 80)
        steps = validate_steps(d.get('passos'))
        default_recipe = recipe_snapshot(d.get('receita_id'))
        snapshots = [recipe_snapshot(s['receita_id']) if s['receita_id'] else default_recipe for s in steps]
        op, flow = lock(oid, d)
        existing = rows(oid)
        if any(s.movimentado_em for s in existing) or (flow and flow.conferencia):
            abort(409, description='O roteiro já foi movimentado. Preserve a sequência e as receitas desta OP.')
        historical = not flow and legacy(op)
        completed = 1
        reason = None
        if historical:
            if d.get('conferir_legado') is not True:
                abort(409, description='OP com produção anterior. Confirme a posição atual antes de adotar o roteiro.')
            if any(p['status'] != 'concluido' for p in gestao.related(op)[0]):
                abort(409, description='Conclua as cargas/filas anteriores antes de conferir a posição desta OP. O histórico não será apagado.')
            reason = txt(d.get('motivo_conferencia'), 'o motivo e a posição conferida', 300)
            completed = num(d.get('fases_concluidas'), 'Quantidade de fases já concluídas, incluindo estoque seco', integer=True)
            if completed < 2 or completed > len(steps):
                abort(400, description='Na adoção de produção anterior, confira ao menos a primeira fase produtiva. Não recrie saldo seco já utilizado.')
            weights(op)
        before = detail(oid)['etapas']
        if not flow:
            flow = FluxoOP(op_id=oid, nome='', qtd=op.qtd, pesos=op.peso_unit)
            db.session.add(flow)
        flow.nome = txt(d.get('nome'), 'o nome do roteiro')
        flow.conferencia = historical
        flow.qtd, flow.pesos = op.qtd, op.peso_unit
        for s in existing:
            db.session.delete(s)
        db.session.flush()
        for i, (s, recipe) in enumerate(zip(steps, snapshots), 1):
            db.session.add(PassagemOP(op_id=oid, ordem=i, fase=s['id'], nome=s['nome'], setor=s['setor'],
                           finalizadora=s['finalizadora'], receita=recipe,
                           status='concluido' if i <= completed else 'aguardando'))
        audit(oid, actor, 'Roteiro e receitas cadastrados', {'antes': before, 'roteiro': flow.nome,
                                                        'fases': [s['nome'] for s in steps]})
        if historical:
            audit(oid, actor, 'Posição inicial conferida — produção anterior',
                  {'motivo': reason, 'fases_concluidas': completed, 'pecas': op.total_pecas,
                   'nota': 'Conclusões declaradas na conferência; horários reais anteriores não reconstruídos.'})
        db.session.commit()
        return jsonify(detail(oid))

    def batches(op, capacity):
        """Distribui peças inteiras por tamanho, sem exceder capacidade nem arredondar estoque."""
        batches_out, current, current_weight = [], {}, Decimal(0)
        for size in tamanhos:
            remaining = int(op.qtd_dict.get(size, 0))
            if not remaining:
                continue
            unit = Decimal(str(op.peso_dict[size]))
            if unit > capacity:
                abort(400, description=f'Uma peça do tamanho {size} excede a capacidade da máquina.')
            while remaining:
                fits = int((capacity - current_weight) // unit)
                if not fits:
                    batches_out.append((current, current_weight))
                    current, current_weight = {}, Decimal(0)
                    if len(batches_out) >= 1000:
                        abort(400, description='A transferência excede 1.000 cargas. Confira capacidade e pesos.')
                    continue
                count = min(remaining, fits)
                current[size] = current.get(size, 0) + count
                current_weight += count * unit
                remaining -= count
        if current:
            batches_out.append((current, current_weight))
        return batches_out

    @app.post('/api/fluxo/ops/<int:oid>/movimentar')
    def move_fluxo(oid):
        d = request.get_json() or {}
        actor = txt(d.get('operador'), 'o responsável', 80)
        op, flow = lock(oid, d)
        if not flow:
            abort(409, description='Cadastre a receita e o roteiro antes de movimentar.')
        quantity, weight = weights(op)
        step = next((s for s in rows(oid) if s.status != 'concluido'), None)
        if not step or step.movimentado_em or step.id != d.get('etapa_id'):
            abort(409, description='Movimente apenas a próxima fase após concluir a etapa anterior inteira.')
        now = agora_local()
        try:
            planned = datetime.strptime(d['data_inicio'], '%Y-%m-%dT%H:%M') if d.get('data_inicio') else now.replace(second=0, microsecond=0)
        except (ValueError, TypeError):
            abort(400, description='Data e hora de programação inválidas.')
        allocated = []
        if step.setor in ('lavar', 'centrifuga', 'secador'):
            mid = num(d.get('maquina_id'), 'Máquina de destino', integer=True)
            machine = Maquina.query.filter_by(id=mid).with_for_update().first_or_404()
            if machine.tipo != step.setor:
                abort(400, description='A máquina deve pertencer ao setor da próxima fase.')
            capacity = num(machine.capacidade, 'Capacidade da máquina')
            minutes = num(machine.tempo_min, 'Tempo de carga', integer=True)
            step.destino = f'{SETORES[step.setor]} {machine.numero}'
            if not d.get('data_inicio'):
                planned = max([planned] + [c.data_saida for c in machine.cargas
                                           if c.status != 'concluido' and c.data_saida])
            n = db.session.query(db.func.max(Carga.numero)).filter_by(maquina_id=mid).scalar() or 0
            for i, (grade, kg) in enumerate(batches(op, capacity), 1):
                c = Carga(maquina_id=mid, numero=n+i, op_id=oid, op_manual=op.op, referencia=op.referencia,
                          lavacao=op.lavacao, peso=float(kg), qtde_pecas=sum(grade.values()),
                          data_inicio=planned + timedelta(minutes=minutes*(i-1)), status='aguardando',
                          observacao=f'Roteiro: {step.ordem}. {step.nome}')
                db.session.add(c); db.session.flush()
                db.session.add(VinculoPassagem(passagem_id=step.id, carga_id=c.id))
                allocated.append({'carga_id': c.id, 'qtd': grade, 'peso': float(kg)})
        elif step.setor == 'laser':
            mid = num(d.get('maquina_id'), 'Laser de destino', integer=True)
            machine = Laser.query.filter_by(id=mid).with_for_update().first_or_404()
            step.destino = f'Laser {machine.numero}'
            if not d.get('data_inicio'):
                planned = max([planned] + [c.data_fim for c in machine.filas
                                           if c.status != 'concluido' and c.data_fim])
            n = db.session.query(db.func.max(LaserFila.numero)).filter_by(equipamento_id=mid).scalar() or 0
            c = LaserFila(equipamento_id=mid, numero=n+1, tipo='op', op=op.op, referencia=op.referencia,
                          qtde_pecas=quantity, tempo_min=machine.tempo_min, data_inicio=planned,
                          status='aguardando', observacao=f'Roteiro: {step.ordem}. {step.nome}')
            db.session.add(c); db.session.flush()
            c.data_fim = c.calcular_fim(machine.intervalos)
            db.session.add(VinculoPassagem(passagem_id=step.id, laser_id=c.id))
        elif step.setor == 'passadoria':
            step.destino = 'Passadoria'
            if not d.get('data_inicio'):
                planned = max([planned] + [c.data_fim for c in Passadoria.query.filter(
                    Passadoria.status != 'concluido').all() if c.data_fim])
            n = db.session.query(db.func.max(Passadoria.numero)).scalar() or 0
            c = Passadoria(numero=n+1, op=op.op, referencia=op.referencia, qtde_pecas=quantity,
                           data_inicio=planned, status='aguardando', tempo_padrao_min=0.85, qtde_passadeiras=1,
                           observacao=f'Roteiro: {step.ordem}. {step.nome}')
            db.session.add(c); db.session.flush()
            c.data_fim = c.calcular_fim()
            db.session.add(VinculoPassagem(passagem_id=step.id, passadoria_id=c.id))
        else:
            step.destino = step.nome
            step.inicio_real = now
        step.movimentado_em = now
        step.status = 'em_processo' if step.setor == 'manual' else 'programado'
        flow.qtd, flow.pesos = op.qtd, op.peso_unit
        audit(oid, actor, 'Transferência de setor', {'etapa': step.ordem, 'fase': step.nome,
              'destino': step.destino, 'qtd': op.qtd_dict, 'peso': float(weight), 'cargas': allocated})
        db.session.commit()
        return jsonify(detail(oid))

    @app.post('/api/fluxo/ops/<int:oid>/concluir-manual')
    def finish_manual(oid):
        d = request.get_json() or {}
        actor = txt(d.get('operador'), 'o responsável', 80)
        op, flow = lock(oid, d)
        step = next((s for s in rows(oid) if s.status != 'concluido'), None)
        if not step or step.id != d.get('etapa_id') or step.setor != 'manual' or step.status != 'em_processo':
            abort(409, description='Esta etapa não permite conclusão manual neste momento.')
        if num(d.get('pecas'), 'Peças concluídas', integer=True) != op.total_pecas:
            abort(400, description='Confirme a quantidade total de peças desta OP para concluir a etapa.')
        step.status, step.fim_real = 'concluido', agora_local()
        audit(oid, actor, 'Etapa concluída', {'fase': step.nome, 'pecas': op.total_pecas})
        db.session.commit()
        return jsonify(detail(oid))

    def source_link(kind, rid):
        field = {'carga': 'carga_id', 'laser': 'laser_id', 'passadoria': 'passadoria_id'}[kind]
        return VinculoPassagem.query.filter_by(**{field: rid}).first()

    def sync_source(kind, rid, actor):
        link = source_link(kind, rid)
        if not link:
            return
        step = db.session.get(PassagemOP, link.passagem_id)
        db.session.flush()
        statuses = []
        starts = []
        for v in VinculoPassagem.query.filter_by(passagem_id=step.id).all():
            record = db.session.get(Carga, v.carga_id) if v.carga_id else db.session.get(LaserFila, v.laser_id) if v.laser_id else db.session.get(Passadoria, v.passadoria_id)
            statuses.append(record.status if record else 'ausente')
            if v.carga_id and record:
                starts.extend(a.data for a in record.apontamentos if a.acao == 'iniciar')
        new = 'concluido' if statuses and all(s == 'concluido' for s in statuses) else 'em_processo' if any(s in ('em_processo', 'concluido') for s in statuses) else 'programado'
        if new != step.status:
            step.status = new
            if new in ('em_processo', 'concluido') and not step.inicio_real:
                if starts:
                    step.inicio_real = min(starts)
                elif kind != 'carga' and new == 'em_processo':
                    step.inicio_real = agora_local()
            if new == 'concluido':
                step.fim_real = agora_local()
            audit(step.op_id, actor, 'Andamento recebido do setor', {'fase': step.nome, 'status': new})
            FluxoOP.query.filter_by(op_id=step.op_id).update({'revisao': FluxoOP.revisao+1}, synchronize_session='fetch')

    def gestao_route(op):
        if not db.session.get(FluxoOP, op.id):
            return None
        return [{'id': s.id, 'tipo': s.setor, 'nome': s.nome, 'ordem': s.ordem, 'responsavel': '',
                 'status': 'aguardando' if s.status == 'programado' else s.status, 'automatico': True,
                 'inicio_real': s.inicio_real.isoformat() if s.inicio_real else None,
                 'fim_real': s.fim_real.isoformat() if s.fim_real else None, 'espera_min': None}
                for s in rows(op.id)]

    @app.before_request
    def protect_fluxo():
        if request.method not in ('POST', 'PUT', 'DELETE'):
            return
        d = request.get_json(silent=True) or {}
        endpoint = request.endpoint
        args = request.view_args or {}
        if endpoint in ('create_op', 'update_op'):
            for field in ('qtd', 'peso_unit'):
                if field not in d:
                    continue
                if not isinstance(d[field], dict):
                    abort(400, description='Informe a grade por tamanho.')
                for size, value in d[field].items():
                    if size not in tamanhos:
                        abort(400, description='Tamanho não cadastrado.')
                    n = num(value, f'{field}: {size}', integer=field == 'qtd', zero=True)
                    if field == 'peso_unit' and n != n.quantize(Decimal('0.001')):
                        abort(400, description='Informe pesos em kg com até três casas decimais.')
            if endpoint == 'update_op':
                OP.query.filter_by(id=args['oid']).with_for_update().first_or_404()
        if endpoint in ('add_carga', 'gerar_cargas', 'add_laser_fila', 'add_passadoria_fila', 'add_robo_passadoria_fila'):
            if endpoint == 'add_laser_fila' and d.get('tipo') == 'parada':
                return
            abort(409, description='Programe a OP pelo Estoque seco / Fluxo: cadastre receita e roteiro, depois escolha a máquina ao movimentar.')
        if endpoint in ('save_roteiro', 'apontar_etapa') and db.session.get(FluxoOP, args.get('oid')):
            abort(409, description='Gerencie este roteiro em Estoque seco / Fluxo da OP.')
        if endpoint == 'update_op':
            steps = rows(args['oid'])
            flow = db.session.get(FluxoOP, args['oid'])
            if any(s.movimentado_em for s in steps) or (flow and flow.conferencia):
                op = db.get_or_404(OP, args['oid'])
                for key, original in [('op', op.op), ('referencia', op.referencia), ('qtd', op.qtd_dict), ('peso_unit', op.peso_dict)]:
                    if key in d and d[key] != original:
                        abort(409, description='Preserve a identidade, as quantidades e os pesos da OP já movimentada.')
        if endpoint in ('archive_cadastro', 'delete_op'):
            oid = args.get('oid') if endpoint == 'delete_op' else args.get('rid') if args.get('tipo') == 'ops' else None
            if oid:
                OP.query.filter_by(id=oid).with_for_update().first_or_404()
                f = db.session.get(FluxoOP, oid)
                if f and (f.conferencia or any(s.movimentado_em for s in rows(oid))) and not ready(oid):
                    abort(409, description='Conclua o roteiro em andamento antes de arquivar a OP.')
        if endpoint == 'create_faturamento':
            oid = gestao.resolve_op(d.get('op_numero'), d.get('referencia'), d.get('op_id'))
            if oid:
                OP.query.filter_by(id=oid).with_for_update().one()
            if not oid or not ready(oid):
                abort(409, description='A OP só pode ser faturada após concluir todo o roteiro, terminando em Passadoria final ou Laser final.')
        mapping = {'update_carga': ('carga', 'cid'), 'delete_carga': ('carga', 'cid'),
                   'apontar': ('carga', 'cid'), 'update_laser_fila': ('laser', 'fid'),
                   'delete_laser_fila': ('laser', 'fid'), 'update_passadoria_fila': ('passadoria', 'iid'),
                   'delete_passadoria_fila': ('passadoria', 'iid')}
        if endpoint not in mapping:
            return
        kind, param = mapping[endpoint]
        link = source_link(kind, args[param])
        if not link:
            # Impede anexar uma carga histórica a uma OP controlada pelo novo fluxo.
            if endpoint == 'update_carga' and ('op_id' in d or 'op' in d or 'referencia' in d):
                c = db.get_or_404(Carga, args[param])
                oid = gestao.resolve_op(d.get('op', c.op_manual), d.get('referencia', c.referencia), d.get('op_id', c.op_id))
                if oid and db.session.get(FluxoOP, oid):
                    abort(409, description='Vincule a produção a esta OP somente pela movimentação do roteiro.')
            if kind != 'carga' and request.method == 'PUT' and ('op' in d or 'referencia' in d):
                row = db.get_or_404(LaserFila if kind == 'laser' else Passadoria, args[param])
                oid = gestao.resolve_op(d.get('op', row.op), d.get('referencia', row.referencia))
                if oid and db.session.get(FluxoOP, oid):
                    abort(409, description='Vincule a produção a esta OP somente pela movimentação do roteiro.')
            return
        step = db.session.get(PassagemOP, link.passagem_id)
        OP.query.filter_by(id=step.op_id).with_for_update().one()
        db.session.refresh(step)
        gestao.check_active('ops', step.op_id)
        if request.method == 'DELETE':
            abort(409, description='Preserve as cargas e filas geradas pela movimentação do estoque.')
        if endpoint == 'apontar':
            c = db.get_or_404(Carga, args[param])
            if d.get('acao') == 'concluir' and num(d.get('pecas'), 'Peças concluídas', integer=True) != c.qtde_pecas:
                abort(400, description=f'Esta carga do roteiro contém {c.qtde_pecas} peças. A conclusão deve conferir a quantidade integral.')
            return
        record = db.get_or_404({'carga': Carga, 'laser': LaserFila, 'passadoria': Passadoria}[kind], args[param])
        db.session.refresh(record)
        for field in ('op', 'op_id', 'referencia', 'qtde_pecas', 'peso'):
            if field in d:
                original = getattr(record, 'op_manual' if field == 'op' and kind == 'carga' else field, None)
                if str(d[field]) != str(original):
                    abort(409, description='Identidade, peças e peso vêm da transferência. Edite somente horários e parâmetros da máquina.')
        if kind != 'carga' and 'status' in d and d['status'] != record.status:
            allowed = {'aguardando': ('em_processo', 'concluido'), 'em_processo': ('concluido',), 'concluido': ()}
            if d['status'] not in allowed.get(record.status, ()):
                abort(409, description='Transição inválida. Preserve o andamento do roteiro.')
            txt(d.get('operador'), 'o operador da etapa', 80)

    service = SimpleNamespace(detail=detail, ready=ready, route=gestao_route, sync_source=sync_source,
                              models=SimpleNamespace(FluxoOP=FluxoOP, PassagemOP=PassagemOP,
                                                     VinculoPassagem=VinculoPassagem, MovimentoFluxo=MovimentoFluxo))
    app.extensions['fluxo'] = service
    return service
