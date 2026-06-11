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
    parada_min  = db.Column(db.Integer, default=0)

    @property
    def data_saida(self):
        if self.data_inicio and self.maquina:
            return self.data_inicio + timedelta(minutes=self.maquina.tempo_min + (self.parada_min or 0))
        return None

# ── LASER MODELS ─────────────────────────────────────────────────
class LaserEquipamento(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    numero      = db.Column(db.Integer, nullable=False)
    tempo_min   = db.Column(db.Float, default=1.42)   # tempo padrão por peça em MINUTOS (ex: 1.42 = 1min25seg)
    filas       = db.relationship('LaserFila', backref='equipamento', lazy=True,
                                  cascade='all, delete-orphan', order_by='LaserFila.numero')
    intervalos  = db.relationship('LaserIntervalo', backref='equipamento', lazy=True,
                                  cascade='all, delete-orphan', order_by='LaserIntervalo.hora_inicio')

class LaserIntervalo(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    equipamento_id  = db.Column(db.Integer, db.ForeignKey('laser_equipamento.id'))
    nome            = db.Column(db.String(50))        # ex: "Almoço Turno 1"
    hora_inicio     = db.Column(db.String(5))         # "12:00"
    hora_fim        = db.Column(db.String(5))         # "13:00"

class LaserFila(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    equipamento_id  = db.Column(db.Integer, db.ForeignKey('laser_equipamento.id'))
    numero          = db.Column(db.Integer)
    tipo            = db.Column(db.String(10), default='op')   # 'op' ou 'parada'
    op              = db.Column(db.String(20))
    referencia      = db.Column(db.String(50))
    descricao       = db.Column(db.String(200))   # usado para paradas
    qtde_pecas      = db.Column(db.Integer, default=0)
    tempo_min       = db.Column(db.Float, default=1.42)
    parada_min      = db.Column(db.Integer, default=0)   # duração da parada em minutos
    data_inicio     = db.Column(db.DateTime, nullable=True)
    data_fim        = db.Column(db.DateTime, nullable=True)
    status          = db.Column(db.String(20), default='aguardando')
    observacao      = db.Column(db.String(200))
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def duracao_seg(self):
        if self.tipo == 'parada':
            return (self.parada_min or 0) * 60.0
        return (self.qtde_pecas or 0) * (self.tempo_min or 1.42) * 60.0

    def calcular_fim(self, intervalos):
        if not self.data_inicio:
            return None
        if self.tipo == 'parada':
            return self.data_inicio + timedelta(minutes=self.parada_min or 0)
        if not self.qtde_pecas:
            return None
        return _calcular_fim_laser(self.data_inicio, self.duracao_seg, intervalos)

class LaserApontamento(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    equipamento_id  = db.Column(db.Integer, db.ForeignKey('laser_equipamento.id'))
    fila_id         = db.Column(db.Integer, db.ForeignKey('laser_fila.id'), nullable=True)
    hora_ref        = db.Column(db.DateTime, nullable=False)  # hora do apontamento
    op              = db.Column(db.String(20))
    referencia      = db.Column(db.String(50))
    projetado       = db.Column(db.Integer, default=0)
    realizado       = db.Column(db.Integer, default=0)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def eficiencia(self):
        if not self.projetado:
            return 0.0
        return round((self.realizado / self.projetado) * 100, 1)

def _parse_hm(s):
    """Converte 'HH:MM' em minutos desde meia-noite."""
    try:
        h, m = s.split(':')
        return int(h) * 60 + int(m)
    except:
        return 0

def _hm_to_dt(base_date, hm_min):
    """Converte minutos desde meia-noite em datetime para um dia base."""
    return datetime.combine(base_date, datetime.min.time()) + timedelta(minutes=hm_min)

def _get_janelas_dia(dia, intervalos_laser):
    """
    Retorna lista de (dt_inicio, dt_fim) com janelas de trabalho disponíveis
    para um dado dia, baseado nos turnos do calendário e subtraindo os
    intervalos de refeição do laser.

    Turnos que 'passam da meia-noite' (ex: T3: 02:20 → 07:00 do dia seguinte
    ou T2: 17:00 → 02:40) são tratados corretamente.
    """
    # Busca turnos cadastrados para este dia
    turnos = Turno.query.filter_by(data=dia).all()

    # Se não há turnos cadastrados, dia não trabalha
    if not turnos:
        return []

    # Monta janelas brutas de cada turno (podem atravessar meia-noite)
    janelas_brutas = []
    for t in turnos:
        if not t.entrada or not t.saida:
            continue
        ini_min = _parse_hm(t.entrada)
        fim_min = _parse_hm(t.saida)
        dt_ini = _hm_to_dt(dia, ini_min)
        if fim_min > ini_min:
            dt_fim = _hm_to_dt(dia, fim_min)
        else:
            # turno passa meia-noite
            dt_fim = _hm_to_dt(dia + timedelta(days=1), fim_min)
        janelas_brutas.append((dt_ini, dt_fim))

    # Subtrai os intervalos de refeição de cada janela
    # Intervalos são definidos como HH:MM e podem também passar meia-noite
    janelas_final = []
    for (j_ini, j_fim) in janelas_brutas:
        segmentos = [(j_ini, j_fim)]
        for iv in intervalos_laser:
            if not iv.hora_inicio or not iv.hora_fim:
                continue
            iv_ini_min = _parse_hm(iv.hora_inicio)
            iv_fim_min = _parse_hm(iv.hora_fim)
            # tenta encaixar o intervalo dentro da janela do turno
            novos = []
            for (s_ini, s_fim) in segmentos:
                # gera candidatos de intervalo tanto no dia base quanto no seguinte
                for offset in [0, 1]:
                    base = dia + timedelta(days=offset)
                    iv_dt_ini = _hm_to_dt(base, iv_ini_min)
                    if iv_fim_min > iv_ini_min:
                        iv_dt_fim = _hm_to_dt(base, iv_fim_min)
                    else:
                        iv_dt_fim = _hm_to_dt(base + timedelta(days=1), iv_fim_min)
                    # corta segmento pelo intervalo
                    if iv_dt_ini >= s_fim or iv_dt_fim <= s_ini:
                        # sem sobreposição
                        novos.append((s_ini, s_fim))
                    else:
                        if s_ini < iv_dt_ini:
                            novos.append((s_ini, iv_dt_ini))
                        if iv_dt_fim < s_fim:
                            novos.append((iv_dt_fim, s_fim))
                    break  # usa só o primeiro offset que faz sentido
            segmentos = novos if novos else segmentos
        janelas_final.extend(segmentos)

    # Ordena e remove janelas vazias
    janelas_final = [(a, b) for (a, b) in janelas_final if b > a]
    janelas_final.sort(key=lambda x: x[0])
    return janelas_final

def _calcular_fim_laser(dt_inicio, total_seg, intervalos_laser, max_dias=365):
    """
    Avança 'total_seg' segundos de produção a partir de dt_inicio,
    respeitando as janelas de trabalho (turnos do calendário) e
    subtraindo os intervalos de refeição do laser.
    """
    if total_seg <= 0:
        return dt_inicio

    dt = dt_inicio
    dias_verificados = 0

    # Começa pelo dia do início; pode precisar avançar vários dias
    dia_atual = dt.date()

    while total_seg > 0 and dias_verificados < max_dias:
        janelas = _get_janelas_dia(dia_atual, intervalos_laser)

        for (j_ini, j_fim) in janelas:
            # se já passamos desta janela, pula
            if j_fim <= dt:
                continue
            # ajusta início da janela se dt já está dentro dela
            inicio_efetivo = max(dt, j_ini)
            seg_disponiveis = (j_fim - inicio_efetivo).total_seconds()

            if seg_disponiveis <= 0:
                continue

            if total_seg <= seg_disponiveis:
                # termina dentro desta janela
                return inicio_efetivo + timedelta(seconds=total_seg)
            else:
                # consome toda a janela e continua
                total_seg -= seg_disponiveis
                dt = j_fim  # avança para o fim da janela

        # Avança para o próximo dia
        dia_atual = dia_atual + timedelta(days=1)
        # dt deve ser o início do próximo dia (será ajustado pela primeira janela)
        dt = datetime.combine(dia_atual, datetime.min.time())
        dias_verificados += 1

    return dt  # fallback: retorna último dt calculado

# ── FATURAMENTO MODELS ────────────────────────────────────────────
class TabelaPreco(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    op              = db.Column(db.String(20), nullable=False)          # ← NOVO: OP vinculada
    referencia      = db.Column(db.String(50), nullable=False)
    preco_peca      = db.Column(db.Float, nullable=False, default=0.0)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    # sigla_fim REMOVIDA

class Faturamento(db.Model):
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
    # Criar 3 equipamentos de laser
    for n in range(1, 4):
        if not LaserEquipamento.query.filter_by(numero=n).first():
            db.session.add(LaserEquipamento(numero=n, tempo_min=1.42))
    db.session.commit()

# ── ROUTES ───────────────────────────────────────────────────────
@app.route('/init_db_agora')
def init_db_route():
    # 1. Renomeia colunas tempo_seg->tempo_min ANTES de init_db() para evitar erro de coluna
    for sql in [
        'ALTER TABLE laser_equipamento RENAME COLUMN tempo_seg TO tempo_min',
        'ALTER TABLE laser_fila RENAME COLUMN tempo_seg TO tempo_min',
    ]:
        try:
            db.session.execute(db.text(sql))
            db.session.commit()
        except Exception:
            db.session.rollback()

    # 2. Cria tabelas e dados iniciais
    try:
        db.create_all()
        init_db()
    except Exception as e:
        db.session.rollback()
        return f'Erro ao criar tabelas base: {e}'

    # 3. Demais migrações individuais
    erros = []
    sqls = [
        'ALTER TABLE carga ADD COLUMN IF NOT EXISTS parada_min INTEGER DEFAULT 0',
        'ALTER TABLE carga ADD COLUMN IF NOT EXISTS observacao VARCHAR(200)',
        "ALTER TABLE tabela_preco ADD COLUMN IF NOT EXISTS op VARCHAR(20) NOT NULL DEFAULT ''",
        'ALTER TABLE tabela_preco DROP COLUMN IF EXISTS sigla_fim',
        """CREATE TABLE IF NOT EXISTS laser_equipamento (
            id SERIAL PRIMARY KEY, numero INTEGER NOT NULL, tempo_min FLOAT DEFAULT 1.42)""",
        """CREATE TABLE IF NOT EXISTS laser_intervalo (
            id SERIAL PRIMARY KEY, equipamento_id INTEGER REFERENCES laser_equipamento(id),
            nome VARCHAR(50), hora_inicio VARCHAR(5), hora_fim VARCHAR(5))""",
        """CREATE TABLE IF NOT EXISTS laser_fila (
            id SERIAL PRIMARY KEY, equipamento_id INTEGER REFERENCES laser_equipamento(id),
            numero INTEGER, op VARCHAR(20), referencia VARCHAR(50), lavacao VARCHAR(80),
            qtde_pecas INTEGER DEFAULT 0, tempo_min FLOAT DEFAULT 1.42,
            data_inicio TIMESTAMP, data_fim TIMESTAMP, status VARCHAR(20) DEFAULT 'aguardando',
            observacao VARCHAR(200), created_at TIMESTAMP DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS laser_apontamento (
            id SERIAL PRIMARY KEY, equipamento_id INTEGER REFERENCES laser_equipamento(id),
            fila_id INTEGER REFERENCES laser_fila(id),
            hora_ref TIMESTAMP NOT NULL, op VARCHAR(20), referencia VARCHAR(50),
            projetado INTEGER DEFAULT 0, realizado INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW())""",
        'ALTER TABLE laser_equipamento ADD COLUMN IF NOT EXISTS tempo_min FLOAT DEFAULT 1.42',
        'ALTER TABLE laser_fila ADD COLUMN IF NOT EXISTS tempo_min FLOAT DEFAULT 1.42',
        "ALTER TABLE laser_fila ADD COLUMN IF NOT EXISTS tipo VARCHAR(10) DEFAULT 'op'",
        'ALTER TABLE laser_fila ADD COLUMN IF NOT EXISTS parada_min INTEGER DEFAULT 0',
        'ALTER TABLE laser_fila ADD COLUMN IF NOT EXISTS descricao VARCHAR(200)',
        "INSERT INTO laser_equipamento (numero, tempo_min) SELECT 1, 1.42 WHERE NOT EXISTS (SELECT 1 FROM laser_equipamento WHERE numero=1)",
        "INSERT INTO laser_equipamento (numero, tempo_min) SELECT 2, 1.42 WHERE NOT EXISTS (SELECT 1 FROM laser_equipamento WHERE numero=2)",
        "INSERT INTO laser_equipamento (numero, tempo_min) SELECT 3, 1.42 WHERE NOT EXISTS (SELECT 1 FROM laser_equipamento WHERE numero=3)",
        'ALTER TABLE tabela_preco DROP CONSTRAINT IF EXISTS tabela_preco_referencia_key',
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_tabela_preco_op_ref ON tabela_preco(op, referencia)',
    ]
    for sql in sqls:
        try:
            db.session.execute(db.text(sql))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            erros.append(f'AVISO [{sql[:50]}]: {e}')

    if erros:
        return 'Banco migrado com avisos:<br>' + '<br>'.join(erros)
    return 'Banco criado e migrado com sucesso!'

@app.route('/diagnostico')
def diagnostico():
    import traceback
    resultado = []
    try:
        resultado.append('✅ Flask OK')
        resultado.append(f'✅ Models carregados')
        # testa conexão
        db.session.execute(db.text('SELECT 1'))
        resultado.append('✅ Banco conectado')
        # testa cada tabela
        for tabela in ['ordem_producao','maquina','carga','turno','tabela_preco','faturamento','laser_equipamento','laser_fila','laser_intervalo','laser_apontamento']:
            try:
                db.session.execute(db.text(f'SELECT COUNT(*) FROM {tabela}'))
                resultado.append(f'✅ Tabela {tabela} OK')
            except Exception as e:
                resultado.append(f'❌ Tabela {tabela}: {e}')
                db.session.rollback()
    except Exception as e:
        resultado.append(f'❌ ERRO: {traceback.format_exc()}')
    return '<br>'.join(resultado)

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

@app.route('/api/ops/<int:oid>', methods=['GET'])
def get_op(oid):
    o = OrdemProducao.query.get_or_404(oid)
    return jsonify({
        'id': o.id, 'op': o.op, 'referencia': o.referencia,
        'lavacao': o.lavacao, 'cap_pecas': o.cap_pecas,
        'qtd': o.qtd_dict, 'peso_unit': o.peso_dict,
        'total_pecas': o.total_pecas, 'peso_total': round(o.peso_total,3),
        'created_at': o.created_at.strftime('%d/%m/%Y %H:%M')
    })

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
    peso_carga  = float(d.get('peso_carga', m.capacidade))
    append_mode = d.get('append', False)

    cargas_existentes = sorted(m.cargas, key=lambda x: x.numero)

    if append_mode and cargas_existentes:
        ultima = cargas_existentes[-1]
        parada_ultima = ultima.parada_min or 0
        if ultima.data_inicio:
            dt = ultima.data_inicio + timedelta(minutes=m.tempo_min + parada_ultima)
        else:
            return jsonify({'ok': False, 'error': 'Última carga sem horário definido'}), 400
        num_inicio = len(cargas_existentes) + 1
    else:
        if not d.get('data_inicio'):
            return jsonify({'ok': False, 'error': 'data_inicio obrigatório'}), 400
        Carga.query.filter_by(maquina_id=mid).delete()
        db.session.commit()
        dt = datetime.strptime(d['data_inicio'], '%Y-%m-%dT%H:%M')
        num_inicio = 1

    for i in range(num_inicio, num_inicio + n):
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
    rows = TabelaPreco.query.order_by(TabelaPreco.op, TabelaPreco.referencia).all()
    return jsonify([{
        'id': r.id, 'op': r.op, 'referencia': r.referencia,
        'preco_peca': r.preco_peca,
        'created_at': r.created_at.strftime('%d/%m/%Y %H:%M')
    } for r in rows])

@app.route('/api/precos', methods=['POST'])
def create_preco():
    try:
        d = request.json
        if not d.get('op') or not d.get('referencia'):
            return jsonify({'ok': False, 'error': 'OP e Referência são obrigatórios'}), 400
        op_val  = d['op'].strip().upper()
        ref_val = d['referencia'].strip().upper()
        existing = TabelaPreco.query.filter_by(op=op_val, referencia=ref_val).first()
        if existing:
            return jsonify({'ok': False, 'error': 'OP + Referência já cadastrada. Use editar.'}), 400
        r = TabelaPreco(
            op=op_val,
            referencia=ref_val,
            preco_peca=safe_float(d.get('preco_peca', 0))
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
        r.op        = d.get('op', r.op).strip().upper()
        r.referencia = d.get('referencia', r.referencia).strip().upper()
        r.preco_peca = safe_float(d.get('preco_peca', r.preco_peca))
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

# ─ BUSCAR PREÇO POR OP + REFERÊNCIA (usado pelo botão Faturar na tela de OPs) ─
@app.route('/api/precos/buscar', methods=['GET'])
def buscar_preco():
    op  = request.args.get('op', '').strip().upper()
    ref = request.args.get('referencia', '').strip().upper()
    if not op or not ref:
        return jsonify({'ok': False, 'error': 'OP e Referência obrigatórios'}), 400
    r = TabelaPreco.query.filter_by(op=op, referencia=ref).first()
    if not r:
        return jsonify({'ok': False, 'error': f'Preço não cadastrado para OP {op} / Ref {ref}'}), 404
    return jsonify({'ok': True, 'id': r.id, 'op': r.op,
                    'referencia': r.referencia, 'preco_peca': r.preco_peca})

# ─ OPs PRONTAS PARA FATURAR ─
# Agora valida por OP + Referência (sem sigla_fim)
@app.route('/api/ops_prontas', methods=['GET'])
def get_ops_prontas():
    ops = OrdemProducao.query.order_by(OrdemProducao.id.desc()).all()
    prontas = []
    for o in ops:
        op_key  = o.op.strip().upper()
        ref_key = o.referencia.strip().upper()
        tp = TabelaPreco.query.filter_by(op=op_key, referencia=ref_key).first()
        if not tp:
            continue
        ja_faturada = Faturamento.query.filter_by(op_numero=o.op, referencia=o.referencia).first()
        prontas.append({
            'id': o.id, 'op': o.op, 'referencia': o.referencia,
            'lavacao': o.lavacao, 'total_pecas': o.total_pecas,
            'peso_total': round(o.peso_total, 3),
            'preco_peca': tp.preco_peca,
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
    } for f in rows])

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
    op = OrdemProducao.query.get_or_404(oid)
    d  = request.json
    capacidade   = safe_float(d.get('capacidade', 80))
    arred_cargas = d.get('arred_cargas', 'baixo')
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
    d = request.json
    ordem = d.get('ordem', [])
    m = Maquina.query.get_or_404(mid)
    cargas = {c.id: c for c in m.cargas}
    for i, cid in enumerate(ordem, 1):
        if cid in cargas:
            cargas[cid].numero = i
    db.session.flush()
    cargas_ord = sorted([cargas[cid] for cid in ordem if cid in cargas], key=lambda x: x.numero)
    _recalcular_horarios(cargas_ord, m.tempo_min)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/maquinas/<int:mid>/recalcular_horarios', methods=['POST'])
def recalcular_horarios(mid):
    m = Maquina.query.get_or_404(mid)
    cargas = sorted(m.cargas, key=lambda x: x.numero)
    _recalcular_horarios(cargas, m.tempo_min)
    db.session.commit()
    return jsonify({'ok': True})

def _recalcular_horarios(cargas, tempo_min):
    dt_atual = None
    for c in cargas:
        if c.numero == 1:
            dt_atual = c.data_inicio
        else:
            if dt_atual:
                c.data_inicio = dt_atual
        if dt_atual and c.data_inicio:
            dt_atual = c.data_inicio + timedelta(minutes=tempo_min + (c.parada_min or 0))

# ── LASER ─────────────────────────────────────────────────────────

@app.route('/api/laser/equipamentos', methods=['GET'])
def get_laser_equipamentos():
    equips = LaserEquipamento.query.order_by(LaserEquipamento.numero).all()
    result = []
    for e in equips:
        filas = sorted(e.filas, key=lambda x: x.numero)
        result.append({
            'id': e.id, 'numero': e.numero, 'tempo_min': e.tempo_min,
            'total_filas': len(filas),
            'aguardando': sum(1 for f in filas if f.status == 'aguardando'),
            'em_processo': sum(1 for f in filas if f.status == 'em_processo'),
            'concluido': sum(1 for f in filas if f.status == 'concluido'),
            'total_pecas': sum(f.qtde_pecas or 0 for f in filas),
        })
    return jsonify(result)

@app.route('/api/laser/equipamentos/<int:eid>', methods=['PUT'])
def update_laser_equipamento(eid):
    e = LaserEquipamento.query.get_or_404(eid)
    d = request.json
    e.tempo_min = safe_float(d.get('tempo_min', e.tempo_min))
    db.session.commit()
    return jsonify({'ok': True})

# ─ Intervalos ─
@app.route('/api/laser/equipamentos/<int:eid>/intervalos', methods=['GET'])
def get_laser_intervalos(eid):
    ivs = LaserIntervalo.query.filter_by(equipamento_id=eid).order_by(LaserIntervalo.hora_inicio).all()
    return jsonify([{'id': i.id, 'nome': i.nome, 'hora_inicio': i.hora_inicio, 'hora_fim': i.hora_fim} for i in ivs])

@app.route('/api/laser/equipamentos/<int:eid>/intervalos', methods=['POST'])
def add_laser_intervalo(eid):
    d = request.json
    iv = LaserIntervalo(equipamento_id=eid, nome=d.get('nome',''), hora_inicio=d.get('hora_inicio',''), hora_fim=d.get('hora_fim',''))
    db.session.add(iv); db.session.commit()
    return jsonify({'ok': True, 'id': iv.id})

@app.route('/api/laser/intervalos/<int:iid>', methods=['PUT'])
def update_laser_intervalo(iid):
    iv = LaserIntervalo.query.get_or_404(iid)
    d = request.json
    iv.nome = d.get('nome', iv.nome)
    iv.hora_inicio = d.get('hora_inicio', iv.hora_inicio)
    iv.hora_fim = d.get('hora_fim', iv.hora_fim)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/laser/intervalos/<int:iid>', methods=['DELETE'])
def delete_laser_intervalo(iid):
    iv = LaserIntervalo.query.get_or_404(iid)
    db.session.delete(iv); db.session.commit()
    return jsonify({'ok': True})

# ─ Fila ─
@app.route('/api/laser/equipamentos/<int:eid>/simular', methods=['POST'])
def simular_laser(eid):
    """Simula o cálculo de fim sem salvar — usado pelo frontend para preview."""
    e = LaserEquipamento.query.get_or_404(eid)
    d = request.json
    try:
        dt_inicio = datetime.strptime(d['data_inicio'], '%Y-%m-%dT%H:%M')
    except:
        return jsonify({'ok': False, 'error': 'data_inicio inválido'}), 400
    qtde = safe_int(d.get('qtde_pecas', 0))
    tempo = safe_float(d.get('tempo_min', e.tempo_min))
    if qtde <= 0 or tempo <= 0:
        return jsonify({'ok': False, 'error': 'Qtde e tempo devem ser > 0'}), 400
    total_seg = qtde * tempo * 60.0  # tempo_min → segundos
    fim = _calcular_fim_laser(dt_inicio, total_seg, e.intervalos)
    duracao_h = total_seg / 3600
    return jsonify({
        'ok': True,
        'data_inicio': dt_inicio.strftime('%d/%m/%Y %H:%M'),
        'data_fim': fim.strftime('%d/%m/%Y %H:%M') if fim else None,
        'duracao_horas': round(duracao_h, 2),
        'duracao_fmt': f"{int(duracao_h)}h{int((duracao_h%1)*60):02d}min",
        'total_seg': round(total_seg, 1),
        'pecas_hora': round(60/tempo, 1) if tempo > 0 else 0,
    })

@app.route('/api/laser/equipamentos/<int:eid>/fila', methods=['GET'])
def get_laser_fila(eid):
    e = LaserEquipamento.query.get_or_404(eid)
    filas = sorted(e.filas, key=lambda x: x.numero)
    intervalos = e.intervalos
    result = []
    for f in filas:
        fim = f.data_fim or f.calcular_fim(intervalos)
        result.append({
            'id': f.id, 'numero': f.numero, 'tipo': f.tipo or 'op',
            'op': f.op, 'referencia': f.referencia,
            'descricao': f.descricao or '',
            'qtde_pecas': f.qtde_pecas, 'tempo_min': f.tempo_min,
            'parada_min': f.parada_min or 0,
            'status': f.status, 'observacao': f.observacao,
            'data_inicio': f.data_inicio.strftime('%Y-%m-%dT%H:%M') if f.data_inicio else None,
            'data_fim': fim.strftime('%Y-%m-%dT%H:%M') if fim else None,
            'duracao_min': round(f.duracao_seg / 60, 1),
        })
    return jsonify({
        'equipamento': {'id': e.id, 'numero': e.numero, 'tempo_min': e.tempo_min},
        'fila': result
    })

@app.route('/api/laser/equipamentos/<int:eid>/fila', methods=['POST'])
def add_laser_fila(eid):
    e = LaserEquipamento.query.get_or_404(eid)
    d = request.json
    num = len(e.filas) + 1
    dt_inicio = None
    if d.get('data_inicio'):
        try: dt_inicio = datetime.strptime(d['data_inicio'], '%Y-%m-%dT%H:%M')
        except: pass
    elif e.filas:
        last = sorted(e.filas, key=lambda x: x.numero)[-1]
        fim = last.data_fim or last.calcular_fim(e.intervalos)
        if fim: dt_inicio = fim
    tipo = d.get('tipo', 'op')
    tempo = safe_float(d.get('tempo_min', e.tempo_min))
    apos_numero = d.get('apos_numero', None)

    # Se inserção após um item específico, reordena numeração
    filas_ord = sorted(e.filas, key=lambda x: x.numero)
    if apos_numero is not None:
        # Incrementa número de todos os itens após a posição
        for ff in filas_ord:
            if ff.numero > apos_numero:
                ff.numero += 1
        num = apos_numero + 1
        # Data início = data_fim do item anterior
        item_anterior = next((ff for ff in filas_ord if ff.numero == apos_numero), None)
        if item_anterior:
            dt_inicio = item_anterior.data_fim or item_anterior.calcular_fim(e.intervalos)
    else:
        num = len(e.filas) + 1

    f = LaserFila(
        equipamento_id=eid, numero=num, tipo=tipo,
        op=d.get('op',''), referencia=d.get('referencia',''),
        descricao=d.get('descricao',''),
        qtde_pecas=safe_int(d.get('qtde_pecas',0)),
        parada_min=safe_int(d.get('parada_min',0)),
        tempo_min=tempo, data_inicio=dt_inicio, status='aguardando',
        observacao=d.get('observacao','')
    )
    db.session.add(f)
    db.session.flush()
    fim = f.calcular_fim(e.intervalos)
    f.data_fim = fim
    db.session.commit()
    return jsonify({'ok': True, 'id': f.id,
                    'data_inicio': f.data_inicio.strftime('%Y-%m-%dT%H:%M') if f.data_inicio else None,
                    'data_fim': f.data_fim.strftime('%Y-%m-%dT%H:%M') if f.data_fim else None})

@app.route('/api/laser/fila/<int:fid>', methods=['PUT'])
def update_laser_fila(fid):
    f = LaserFila.query.get_or_404(fid)
    e = f.equipamento
    d = request.json
    if 'op' in d: f.op = d['op']
    if 'referencia' in d: f.referencia = d['referencia']
    if 'descricao' in d: f.descricao = d['descricao']
    if 'qtde_pecas' in d: f.qtde_pecas = safe_int(d['qtde_pecas'])
    if 'parada_min' in d: f.parada_min = safe_int(d['parada_min'])
    if 'tempo_min' in d: f.tempo_min = safe_float(d['tempo_min'])
    if 'status' in d: f.status = d['status']
    if 'observacao' in d: f.observacao = d['observacao']
    if 'data_inicio' in d:
        try: f.data_inicio = datetime.strptime(d['data_inicio'], '%Y-%m-%dT%H:%M')
        except: f.data_inicio = None
    # Recalcular fim
    fim = f.calcular_fim(e.intervalos)
    f.data_fim = fim
    db.session.commit()
    return jsonify({'ok': True,
                    'data_fim': f.data_fim.strftime('%Y-%m-%dT%H:%M') if f.data_fim else None})

@app.route('/api/laser/fila/<int:fid>', methods=['DELETE'])
def delete_laser_fila(fid):
    f = LaserFila.query.get_or_404(fid)
    e = f.equipamento
    db.session.delete(f)
    for i, ff in enumerate(sorted(e.filas, key=lambda x: x.numero), 1):
        ff.numero = i
    db.session.commit()
    return jsonify({'ok': True})

# ─ Apontamento ─
@app.route('/api/laser/equipamentos/<int:eid>/apontamentos', methods=['GET'])
def get_laser_apontamentos(eid):
    data_str = request.args.get('data', date.today().strftime('%Y-%m-%d'))
    try:
        d = datetime.strptime(data_str, '%Y-%m-%d')
        d1 = d.replace(hour=0, minute=0, second=0)
        d2 = d.replace(hour=23, minute=59, second=59)
    except:
        d1 = datetime.now().replace(hour=0, minute=0, second=0)
        d2 = datetime.now().replace(hour=23, minute=59, second=59)
    rows = LaserApontamento.query.filter(
        LaserApontamento.equipamento_id == eid,
        LaserApontamento.hora_ref.between(d1, d2)
    ).order_by(LaserApontamento.hora_ref).all()
    total_proj = sum(r.projetado for r in rows)
    total_real = sum(r.realizado for r in rows)
    ef_geral = round((total_real / total_proj * 100), 1) if total_proj else 0
    return jsonify({
        'apontamentos': [{
            'id': r.id, 'hora_ref': r.hora_ref.strftime('%H:%M'),
            'op': r.op, 'referencia': r.referencia,
            'projetado': r.projetado, 'realizado': r.realizado,
            'eficiencia': r.eficiencia
        } for r in rows],
        'totais': {'projetado': total_proj, 'realizado': total_real, 'eficiencia': ef_geral}
    })

@app.route('/api/laser/equipamentos/<int:eid>/apontamentos', methods=['POST'])
def add_laser_apontamento(eid):
    d = request.json
    hora_ref = datetime.strptime(d['hora_ref'], '%Y-%m-%dT%H:%M')
    # Calcula projetado: (3600 / tempo_seg) peças/hora para a fila ativa
    fila_ativa = LaserFila.query.filter_by(equipamento_id=eid, status='em_processo').first()
    tempo_peca_min = fila_ativa.tempo_min if fila_ativa else safe_float(d.get('tempo_min', 1.42))
    projetado = safe_int(d.get('projetado')) or (int(60 / tempo_peca_min) if tempo_peca_min > 0 else 0)
    a = LaserApontamento(
        equipamento_id=eid,
        fila_id=fila_ativa.id if fila_ativa else None,
        hora_ref=hora_ref,
        op=d.get('op', fila_ativa.op if fila_ativa else ''),
        referencia=d.get('referencia', fila_ativa.referencia if fila_ativa else ''),
        projetado=projetado,
        realizado=safe_int(d.get('realizado', 0))
    )
    db.session.add(a); db.session.commit()
    return jsonify({'ok': True, 'id': a.id, 'eficiencia': a.eficiencia})

@app.route('/api/laser/apontamentos/<int:aid>', methods=['PUT'])
def update_laser_apontamento(aid):
    a = LaserApontamento.query.get_or_404(aid)
    d = request.json
    if 'realizado' in d: a.realizado = safe_int(d['realizado'])
    if 'projetado' in d: a.projetado = safe_int(d['projetado'])
    db.session.commit()
    return jsonify({'ok': True, 'eficiencia': a.eficiencia})

@app.route('/api/laser/apontamentos/<int:aid>', methods=['DELETE'])
def delete_laser_apontamento(aid):
    a = LaserApontamento.query.get_or_404(aid)
    db.session.delete(a); db.session.commit()
    return jsonify({'ok': True})

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
