from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
import json, math, calendar

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres.xjkgqqshpdbpssnugwfd:NkgivoWymEzGQFYM@aws-1-us-west-1.pooler.supabase.com:5432/postgres'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

TAMANHOS = ['PP','P','M','G','GG','XG',
            '32','34','36','38','40','42','44','46','48','50',
            '01','02','03','04','06','08','10','12','14','16']

# ── MODELS ───────────────────────────────────────────────────────
class OrdemProducao(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    op          = db.Column(db.String(20), nullable=False)
    referencia  = db.Column(db.String(50), nullable=False)
    lavacao     = db.Column(db.String(80))
    cap_pecas   = db.Column(db.Integer, default=0)
    qtd         = db.Column(db.Text, default='{}')
    peso_unit   = db.Column(db.Text, default='{}')
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def qtd_dict(self):
        return json.loads(self.qtd or '{}')
    @property
    def peso_dict(self):
        return json.loads(self.peso_unit or '{}')
    @property
    def total_pecas(self):
        return sum(self.qtd_dict.values())
    @property
    def peso_total(self):
        q = self.qtd_dict; p = self.peso_dict
        return sum(q.get(t,0)*p.get(t,0.0) for t in TAMANHOS)

class Turno(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    data        = db.Column(db.Date, nullable=False)
    turno_num   = db.Column(db.Integer)
    entrada     = db.Column(db.String(5))
    saida       = db.Column(db.String(5))
    he_inicio   = db.Column(db.String(5))
    he_fim      = db.Column(db.String(5))
    observacao  = db.Column(db.String(200))

class Maquina(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    tipo        = db.Column(db.String(20))
    numero      = db.Column(db.Integer)
    capacidade  = db.Column(db.Float, default=80.0)
    tempo_min   = db.Column(db.Integer, default=90)
    cargas      = db.relationship('Carga', backref='maquina', lazy=True,
                                  cascade='all, delete-orphan',
                                  order_by='Carga.numero')

class Carga(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    maquina_id  = db.Column(db.Integer, db.ForeignKey('maquina.id'))
    numero      = db.Column(db.Integer)
    op_id       = db.Column(db.Integer, db.ForeignKey('ordem_producao.id'), nullable=True)
    op_manual   = db.Column(db.String(20))
    referencia  = db.Column(db.String(50))
    lavacao     = db.Column(db.String(80))
    qtde_pecas  = db.Column(db.Integer, default=0)
    peso        = db.Column(db.Float, default=0.0)
    data_inicio = db.Column(db.DateTime, nullable=True)
    status      = db.Column(db.String(20), default='aguardando')
    observacao  = db.Column(db.String(200))
    parada_min  = db.Column(db.Integer, default=0)  # tempo de parada APÓS esta carga

    @property
    def data_saida(self):
        if self.data_inicio and self.maquina:
            return self.data_inicio + timedelta(minutes=self.maquina.tempo_min)
        return None

# ── FATURAMENTO MODELS ────────────────────────────────────────────
class TabelaPreco(db.Model):
    """Tabela de preços por referência + sigla de finalização."""
    id              = db.Column(db.Integer, primary_key=True)
    referencia      = db.Column(db.String(50), nullable=False, unique=True)
    preco_peca      = db.Column(db.Float, nullable=False, default=0.0)
    sigla_fim       = db.Column(db.String(30), nullable=False)  # sigla que indica produto finalizado
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

class Faturamento(db.Model):
    """Registro de faturamento — criado quando OP com sigla_fim é faturada."""
    id              = db.Column(db.Integer, primary_key=True)
    op_id           = db.Column(db.Integer, db.ForeignKey('ordem_producao.id'), nullable=True)
    op_numero       = db.Column(db.String(20), nullable=False)
    referencia      = db.Column(db.String(50), nullable=False)
    lavacao         = db.Column(db.String(80))
    qtd_pecas       = db.Column(db.Integer, default=0)
    preco_peca      = db.Column(db.Float, default=0.0)
    valor_total     = db.Column(db.Float, default=0.0)
    data_faturamento = db.Column(db.Date, default=date.today)
    observacao      = db.Column(db.String(200))
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

# ── INIT DB ──────────────────────────────────────────────────────
def init_db():
    db.create_all()
    tipos = [('lavar',10,80.0,90),('centrifuga',6,80.0,15),('secador',11,60.0,45)]
    for tipo, qtd, cap, tempo in tipos:
        for n in range(1, qtd+1):
            if not Maquina.query.filter_by(tipo=tipo, numero=n).first():
                db.session.add(Maquina(tipo=tipo, numero=n,
                                       capacidade=cap, tempo_min=tempo))
    db.session.commit()

# ── ROUTES ───────────────────────────────────────────────────────
@app.route('/init_db_agora')
def init_db_route():
    db.create_all()
    init_db()
    return 'Banco criado!'

@app.route('/')
def index():
    return render_template('index.html')

# ─ OP ─
@app.route('/api/ops', methods=['GET'])
def get_ops():
    ops = OrdemProducao.query.order_by(OrdemProducao.id.desc()).all()
    return jsonify([{
        'id': o.id, 'op': o.op, 'referencia': o.referencia,
        'lavacao': o.lavacao, 'cap_pecas': o.cap_pecas,
        'qtd': o.qtd_dict, 'peso_unit': o.peso_dict,
        'total_pecas': o.total_pecas, 'peso_total': round(o.peso_total,3),
        'created_at': o.created_at.strftime('%d/%m/%Y %H:%M')
    } for o in ops])

def safe_int(v, default=0):
    try: return int(float(v or default))
    except: return default

def safe_float(v, default=0.0):
    try: return float(v or default)
    except: return default

@app.route('/api/ops', methods=['POST'])
def create_op():
    try:
        d = request.json
        if not d:
            return jsonify({'ok': False, 'error': 'Dados inválidos'}), 400
        if not d.get('op') or not d.get('referencia'):
            return jsonify({'ok': False, 'error': 'OP e Referência são obrigatórios'}), 400
        op = OrdemProducao(
            op=str(d['op']).strip(),
            referencia=str(d['referencia']).strip(),
            lavacao=d.get('lavacao',''),
            cap_pecas=safe_int(d.get('cap_pecas', 0)),
            qtd=json.dumps({k: safe_int(v) for k, v in d.get('qtd', {}).items() if safe_int(v) > 0}),
            peso_unit=json.dumps({k: safe_float(v) for k, v in d.get('peso_unit', {}).items() if safe_float(v) > 0})
        )
        db.session.add(op)
        db.session.commit()
        return jsonify({'id': op.id, 'ok': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/ops/<int:oid>', methods=['PUT'])
def update_op(oid):
    try:
        op = OrdemProducao.query.get_or_404(oid)
        d = request.json
        if not d:
            return jsonify({'ok': False, 'error': 'Dados inválidos'}), 400
        op.op = str(d.get('op', op.op)).strip()
        op.referencia = str(d.get('referencia', op.referencia)).strip()
        op.lavacao = d.get('lavacao', op.lavacao)
        op.cap_pecas = safe_int(d.get('cap_pecas', op.cap_pecas))
        op.qtd = json.dumps({k: safe_int(v) for k, v in d.get('qtd', {}).items() if safe_int(v) > 0})
        op.peso_unit = json.dumps({k: safe_float(v) for k, v in d.get('peso_unit', {}).items() if safe_float(v) > 0})
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/ops/<int:oid>', methods=['DELETE'])
def delete_op(oid):
    op = OrdemProducao.query.get_or_404(oid)
    db.session.delete(op); db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/ops/<int:oid>/arredondar', methods=['GET'])
def arredondar_op(oid):
    op = OrdemProducao.query.get_or_404(oid)
    cap = float(request.args.get('cap', 80))
    total = op.peso_total
    if cap <= 0:
        return jsonify({'cargas': 0, 'peso_total': total})
    cargas = math.ceil(total / cap)
    return jsonify({'cargas': cargas, 'peso_total': round(total,3),
                    'cap': cap, 'ultimo_peso': round(total - (cargas-1)*cap, 3)})

# ─ TURNOS ─
@app.route('/api/turnos', methods=['GET'])
def get_turnos():
    ano  = int(request.args.get('ano', date.today().year))
    mes  = int(request.args.get('mes', date.today().month))
    d1   = date(ano, mes, 1)
    d2   = date(ano, mes, calendar.monthrange(ano,mes)[1])
    rows = Turno.query.filter(Turno.data.between(d1,d2)).all()
    return jsonify([{
        'id': t.id, 'data': t.data.strftime('%Y-%m-%d'),
        'turno_num': t.turno_num, 'entrada': t.entrada,
        'saida': t.saida, 'he_inicio': t.he_inicio,
        'he_fim': t.he_fim, 'observacao': t.observacao
    } for t in rows])

@app.route('/api/turnos', methods=['POST'])
def save_turno():
    d = request.json
    data_obj = datetime.strptime(d['data'], '%Y-%m-%d').date()
    t = Turno.query.filter_by(data=data_obj, turno_num=d['turno_num']).first()
    if not t:
        t = Turno(data=data_obj, turno_num=d['turno_num'])
        db.session.add(t)
    t.entrada = d.get('entrada',''); t.saida = d.get('saida','')
    t.he_inicio = d.get('he_inicio',''); t.he_fim = d.get('he_fim','')
    t.observacao = d.get('observacao','')
    db.session.commit()
    return jsonify({'ok': True, 'id': t.id})

# ─ MÁQUINAS ─
@app.route('/api/maquinas', methods=['GET'])
def get_maquinas():
    tipo = request.args.get('tipo','lavar')
    maquinas = Maquina.query.filter_by(tipo=tipo).order_by(Maquina.numero).all()
    return jsonify([{
        'id': m.id, 'tipo': m.tipo, 'numero': m.numero,
        'capacidade': m.capacidade, 'tempo_min': m.tempo_min,
        'total_cargas': len(m.cargas),
        'peso_total': round(sum(c.peso for c in m.cargas), 3)
    } for m in maquinas])

@app.route('/api/maquinas/<int:mid>', methods=['PUT'])
def update_maquina(mid):
    m = Maquina.query.get_or_404(mid)
    d = request.json
    m.capacidade = float(d.get('capacidade', m.capacidade))
    m.tempo_min  = int(d.get('tempo_min', m.tempo_min))
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/maquinas/<int:mid>/cargas', methods=['GET'])
def get_cargas(mid):
    m = Maquina.query.get_or_404(mid)
    cargas = sorted(m.cargas, key=lambda x: x.numero)
    resultado = []
    for c in cargas:
        ds = c.data_saida
        resultado.append({
            'id': c.id, 'numero': c.numero,
            'op_manual': c.op_manual, 'referencia': c.referencia,
            'lavacao': c.lavacao, 'qtde_pecas': c.qtde_pecas,
            'peso': c.peso, 'status': c.status, 'observacao': c.observacao,
            'parada_min': c.parada_min or 0,
            'data_inicio': c.data_inicio.strftime('%Y-%m-%dT%H:%M') if c.data_inicio else None,
            'data_saida': ds.strftime('%Y-%m-%dT%H:%M') if ds else None,
        })
    return jsonify({
        'maquina': {'id': m.id, 'tipo': m.tipo, 'numero': m.numero,
                    'capacidade': m.capacidade, 'tempo_min': m.tempo_min},
        'cargas': resultado
    })

@app.route('/api/maquinas/<int:mid>/cargas', methods=['POST'])
def add_carga(mid):
    m = Maquina.query.get_or_404(mid)
    d = request.json
    num = len(m.cargas) + 1
    dt_inicio = None
    if d.get('data_inicio'):
        try:
            dt_inicio = datetime.strptime(d['data_inicio'], '%Y-%m-%dT%H:%M')
        except:
            pass
    elif m.cargas:
        last = sorted(m.cargas, key=lambda x: x.numero)[-1]
        if last.data_saida:
            dt_inicio = last.data_saida
    c = Carga(maquina_id=mid, numero=num,
              op_manual=d.get('op',''), referencia=d.get('referencia',''),
              lavacao=d.get('lavacao',''), qtde_pecas=int(d.get('qtde_pecas',0)),
              peso=float(d.get('peso',0)), data_inicio=dt_inicio,
              status='aguardando', observacao=d.get('observacao',''))
    db.session.add(c); db.session.commit()
    return jsonify({'ok': True, 'id': c.id,
                    'data_inicio': c.data_inicio.strftime('%Y-%m-%dT%H:%M') if c.data_inicio else None,
                    'data_saida': c.data_saida.strftime('%Y-%m-%dT%H:%M') if c.data_saida else None})

@app.route('/api/cargas/<int:cid>', methods=['PUT'])
def update_carga(cid):
    c = Carga.query.get_or_404(cid)
    d = request.json
    if 'op' in d: c.op_manual = d['op']
    if 'referencia' in d: c.referencia = d['referencia']
    if 'lavacao' in d: c.lavacao = d['lavacao']
    if 'qtde_pecas' in d: c.qtde_pecas = int(d['qtde_pecas'])
    if 'peso' in d: c.peso = float(d['peso'])
    if 'status' in d: c.status = d['status']
    if 'observacao' in d: c.observacao = d['observacao']
    if 'parada_min' in d: c.parada_min = int(d['parada_min'] or 0)
    if 'data_inicio' in d:
        try: c.data_inicio = datetime.strptime(d['data_inicio'], '%Y-%m-%dT%H:%M')
        except: c.data_inicio = None
    db.session.commit()
    return jsonify({'ok': True,
                    'data_saida': c.data_saida.strftime('%Y-%m-%dT%H:%M') if c.data_saida else None})

@app.route('/api/cargas/<int:cid>', methods=['DELETE'])
def delete_carga(cid):
    c = Carga.query.get_or_404(cid); m = c.maquina
    db.session.delete(c)
    for i, cc in enumerate(sorted(m.cargas, key=lambda x: x.numero), 1):
        cc.numero = i
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/maquinas/<int:mid>/gerar_cargas', methods=['POST'])
def gerar_cargas(mid):
    m   = Maquina.query.get_or_404(mid)
    d   = request.json
    op  = d.get('op',''); ref = d.get('referencia',''); lav = d.get('lavacao','')
    n   = int(d.get('quantidade', 1))
    peso_carga = float(d.get('peso_carga', m.capacidade))
    dt  = datetime.strptime(d['data_inicio'], '%Y-%m-%dT%H:%M')
    Carga.query.filter_by(maquina_id=mid).delete()
    db.session.commit()
    for i in range(1, n+1):
        c = Carga(maquina_id=mid, numero=i, op_manual=op,
                  referencia=ref, lavacao=lav, qtde_pecas=0,
                  peso=peso_carga, data_inicio=dt, status='aguardando')
        db.session.add(c)
        dt = dt + timedelta(minutes=m.tempo_min)
    db.session.commit()
    return jsonify({'ok': True, 'geradas': n})

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    result = {}
    for tipo in ['lavar','centrifuga','secador']:
        maquinas = Maquina.query.filter_by(tipo=tipo).order_by(Maquina.numero).all()
        result[tipo] = [{
            'numero': m.numero, 'capacidade': m.capacidade, 'tempo_min': m.tempo_min,
            'total_cargas': len(m.cargas),
            'peso_total': round(sum(c.peso for c in m.cargas), 2),
            'concluidas': sum(1 for c in m.cargas if c.status=='concluido'),
            'em_processo': sum(1 for c in m.cargas if c.status=='em_processo'),
            'aguardando': sum(1 for c in m.cargas if c.status=='aguardando'),
        } for m in maquinas]
    return jsonify(result)

# ─ TABELA DE PREÇOS ─
@app.route('/api/precos', methods=['GET'])
def get_precos():
    rows = TabelaPreco.query.order_by(TabelaPreco.referencia).all()
    return jsonify([{
        'id': r.id, 'referencia': r.referencia,
        'preco_peca': r.preco_peca, 'sigla_fim': r.sigla_fim,
        'created_at': r.created_at.strftime('%d/%m/%Y %H:%M')
    } for r in rows])

@app.route('/api/precos', methods=['POST'])
def create_preco():
    try:
        d = request.json
        if not d.get('referencia') or not d.get('sigla_fim'):
            return jsonify({'ok': False, 'error': 'Referência e Sigla são obrigatórias'}), 400
        existing = TabelaPreco.query.filter_by(referencia=d['referencia'].strip().upper()).first()
        if existing:
            return jsonify({'ok': False, 'error': 'Referência já cadastrada. Use editar.'}), 400
        r = TabelaPreco(
            referencia=d['referencia'].strip().upper(),
            preco_peca=safe_float(d.get('preco_peca', 0)),
            sigla_fim=d['sigla_fim'].strip().upper()
        )
        db.session.add(r); db.session.commit()
        return jsonify({'ok': True, 'id': r.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/precos/<int:pid>', methods=['PUT'])
def update_preco(pid):
    try:
        r = TabelaPreco.query.get_or_404(pid)
        d = request.json
        r.referencia = d.get('referencia', r.referencia).strip().upper()
        r.preco_peca = safe_float(d.get('preco_peca', r.preco_peca))
        r.sigla_fim  = d.get('sigla_fim', r.sigla_fim).strip().upper()
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/precos/<int:pid>', methods=['DELETE'])
def delete_preco(pid):
    r = TabelaPreco.query.get_or_404(pid)
    db.session.delete(r); db.session.commit()
    return jsonify({'ok': True})

# ─ OPs PRONTAS PARA FATURAR ─
@app.route('/api/ops_prontas', methods=['GET'])
def get_ops_prontas():
    """Retorna OPs cuja lavação contém a sigla de finalização cadastrada para a referência."""
    ops = OrdemProducao.query.order_by(OrdemProducao.id.desc()).all()
    precos = TabelaPreco.query.all()
    # mapa referencia -> tabela_preco
    mapa = {p.referencia.upper(): p for p in precos}

    prontas = []
    for o in ops:
        ref_key = o.referencia.strip().upper()
        tp = mapa.get(ref_key)
        if not tp:
            continue
        lav = (o.lavacao or '').upper()
        if tp.sigla_fim.upper() not in lav:
            continue
        # verifica se já foi faturada
        ja_faturada = Faturamento.query.filter_by(op_numero=o.op, referencia=o.referencia).first()
        prontas.append({
            'id': o.id, 'op': o.op, 'referencia': o.referencia,
            'lavacao': o.lavacao, 'total_pecas': o.total_pecas,
            'peso_total': round(o.peso_total, 3),
            'preco_peca': tp.preco_peca,
            'sigla_fim': tp.sigla_fim,
            'valor_total': round(o.total_pecas * tp.preco_peca, 2),
            'ja_faturada': bool(ja_faturada),
            'created_at': o.created_at.strftime('%d/%m/%Y %H:%M')
        })
    return jsonify(prontas)

# ─ FATURAMENTO ─
@app.route('/api/faturamento', methods=['GET'])
def get_faturamento():
    ano = int(request.args.get('ano', date.today().year))
    mes = int(request.args.get('mes', date.today().month))
    d1  = date(ano, mes, 1)
    d2  = date(ano, mes, calendar.monthrange(ano,mes)[1])
    rows = Faturamento.query.filter(
        Faturamento.data_faturamento.between(d1, d2)
    ).order_by(Faturamento.data_faturamento.desc()).all()
    return jsonify([{
        'id': f.id, 'op_numero': f.op_numero, 'referencia': f.referencia,
        'lavacao': f.lavacao, 'qtd_pecas': f.qtd_pecas,
        'preco_peca': f.preco_peca, 'valor_total': f.valor_total,
        'data_faturamento': f.data_faturamento.strftime('%d/%m/%Y'),
        'observacao': f.observacao
    } for r in rows for f in [r]])

@app.route('/api/faturamento', methods=['POST'])
def create_faturamento():
    try:
        d = request.json
        f = Faturamento(
            op_numero=str(d.get('op_numero','')).strip(),
            referencia=str(d.get('referencia','')).strip(),
            lavacao=d.get('lavacao',''),
            qtd_pecas=safe_int(d.get('qtd_pecas',0)),
            preco_peca=safe_float(d.get('preco_peca',0)),
            valor_total=safe_float(d.get('valor_total',0)),
            data_faturamento=datetime.strptime(d['data_faturamento'], '%Y-%m-%d').date() if d.get('data_faturamento') else date.today(),
            observacao=d.get('observacao','')
        )
        db.session.add(f); db.session.commit()
        return jsonify({'ok': True, 'id': f.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/faturamento/<int:fid>', methods=['DELETE'])
def delete_faturamento(fid):
    f = Faturamento.query.get_or_404(fid)
    db.session.delete(f); db.session.commit()
    return jsonify({'ok': True})

# ─ DRE ─
@app.route('/api/dre', methods=['GET'])
def get_dre():
    ano = int(request.args.get('ano', date.today().year))
    mes = int(request.args.get('mes', date.today().month))
    d1  = date(ano, mes, 1)
    d2  = date(ano, mes, calendar.monthrange(ano,mes)[1])
    rows = Faturamento.query.filter(
        Faturamento.data_faturamento.between(d1, d2)
    ).all()
    total_faturado = round(sum(r.valor_total for r in rows), 2)
    total_pecas    = sum(r.qtd_pecas for r in rows)
    total_ops      = len(rows)
    # por semana
    semanas = {}
    for r in rows:
        sem = r.data_faturamento.isocalendar()[1]
        semanas[sem] = semanas.get(sem, 0) + r.valor_total
    return jsonify({
        'ano': ano, 'mes': mes,
        'total_faturado': total_faturado,
        'total_pecas': total_pecas,
        'total_ops': total_ops,
        'por_semana': [{'semana': k, 'valor': round(v,2)} for k,v in sorted(semanas.items())],
        'registros': [{
            'op_numero': r.op_numero, 'referencia': r.referencia,
            'qtd_pecas': r.qtd_pecas, 'preco_peca': r.preco_peca,
            'valor_total': r.valor_total,
            'data_faturamento': r.data_faturamento.strftime('%d/%m/%Y')
        } for r in rows]
    })

@app.route('/api/ops/<int:oid>/calcular_cargas', methods=['POST'])
def calcular_cargas_op(oid):
    """Calcula distribuição de cargas a partir do peso/peças da OP."""
    op = OrdemProducao.query.get_or_404(oid)
    d  = request.json
    capacidade   = safe_float(d.get('capacidade', 80))
    arred_cargas = d.get('arred_cargas', 'baixo')   # 'cima' ou 'baixo'
    arred_pecas  = d.get('arred_pecas', 'baixo')

    peso_total  = op.peso_total
    total_pecas = op.total_pecas

    if capacidade <= 0:
        return jsonify({'ok': False, 'error': 'Capacidade inválida'}), 400

    cargas_raw = peso_total / capacidade
    if arred_cargas == 'cima':
        num_cargas = math.ceil(cargas_raw)
    else:
        num_cargas = math.floor(cargas_raw)
    if num_cargas < 1:
        num_cargas = 1

    peso_carga  = round(peso_total / num_cargas, 3)
    pecas_raw   = total_pecas / num_cargas
    if arred_pecas == 'cima':
        pecas_carga = math.ceil(pecas_raw)
    else:
        pecas_carga = math.floor(pecas_raw)

    return jsonify({
        'ok': True,
        'peso_total': round(peso_total, 3),
        'total_pecas': total_pecas,
        'num_cargas': num_cargas,
        'peso_carga': peso_carga,
        'pecas_carga': pecas_carga,
        'cargas_raw': round(cargas_raw, 4)
    })

@app.route('/api/maquinas/<int:mid>/reordenar', methods=['POST'])
def reordenar_cargas(mid):
    """Reordena cargas e recalcula horários em cascata."""
    d = request.json
    ordem = d.get('ordem', [])  # lista de IDs na nova ordem
    m = Maquina.query.get_or_404(mid)
    cargas = {c.id: c for c in m.cargas}

    # Reordenar numeração
    for i, cid in enumerate(ordem, 1):
        if cid in cargas:
            cargas[cid].numero = i

    db.session.flush()

    # Recalcular horários em cascata
    cargas_ord = sorted([cargas[cid] for cid in ordem if cid in cargas], key=lambda x: x.numero)
    _recalcular_horarios(cargas_ord, m.tempo_min)

    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/maquinas/<int:mid>/recalcular_horarios', methods=['POST'])
def recalcular_horarios(mid):
    """Recalcula horários em cascata mantendo a ordem atual."""
    m = Maquina.query.get_or_404(mid)
    cargas = sorted(m.cargas, key=lambda x: x.numero)
    _recalcular_horarios(cargas, m.tempo_min)
    db.session.commit()
    return jsonify({'ok': True})

def _recalcular_horarios(cargas, tempo_min):
    """Recalcula data_inicio de cada carga em cascata, respeitando parada_min."""
    dt_atual = None
    for c in cargas:
        if c.numero == 1:
            dt_atual = c.data_inicio  # mantém o horário da 1ª carga
        else:
            if dt_atual:
                c.data_inicio = dt_atual
        if dt_atual and c.data_inicio:
            dt_atual = c.data_inicio + timedelta(minutes=tempo_min + (c.parada_min or 0))

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
