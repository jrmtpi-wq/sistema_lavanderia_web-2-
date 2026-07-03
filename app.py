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
    tempo_min   = db.Column(db.Float, default=1.42)
    filas       = db.relationship('LaserFila', backref='equipamento', lazy=True,
                                  cascade='all, delete-orphan', order_by='LaserFila.numero')
    intervalos  = db.relationship('LaserIntervalo', backref='equipamento', lazy=True,
                                  cascade='all, delete-orphan', order_by='LaserIntervalo.hora_inicio')

class LaserIntervalo(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    equipamento_id  = db.Column(db.Integer, db.ForeignKey('laser_equipamento.id'))
    nome            = db.Column(db.String(50))
    hora_inicio     = db.Column(db.String(5))
    hora_fim        = db.Column(db.String(5))

class LaserFila(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    equipamento_id  = db.Column(db.Integer, db.ForeignKey('laser_equipamento.id'))
    numero          = db.Column(db.Integer)
    tipo            = db.Column(db.String(10), default='op')
    op              = db.Column(db.String(20))
    referencia      = db.Column(db.String(50))
    descricao       = db.Column(db.String(200))
    qtde_pecas      = db.Column(db.Integer, default=0)
    tempo_min       = db.Column(db.Float, default=1.42)
    parada_min      = db.Column(db.Integer, default=0)
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
    hora_ref        = db.Column(db.DateTime, nullable=False)
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
    try:
        h, m = s.split(':')
        return int(h) * 60 + int(m)
    except:
        return 0

def _hm_to_dt(base_date, hm_min):
    return datetime.combine(base_date, datetime.min.time()) + timedelta(minutes=hm_min)

def _get_janelas_dia(dia, intervalos_laser):
    turnos = Turno.query.filter_by(data=dia).all()
    if not turnos:
        return []
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
            dt_fim = _hm_to_dt(dia + timedelta(days=1), fim_min)
        janelas_brutas.append((dt_ini, dt_fim))
    janelas_final = []
    for (j_ini, j_fim) in janelas_brutas:
        segmentos = [(j_ini, j_fim)]
        for iv in intervalos_laser:
            if not iv.hora_inicio or not iv.hora_fim:
                continue
            iv_ini_min = _parse_hm(iv.hora_inicio)
            iv_fim_min = _parse_hm(iv.hora_fim)
            novos = []
            for (s_ini, s_fim) in segmentos:
                for offset in [0, 1]:
                    base = dia + timedelta(days=offset)
                    iv_dt_ini = _hm_to_dt(base, iv_ini_min)
                    if iv_fim_min > iv_ini_min:
                        iv_dt_fim = _hm_to_dt(base, iv_fim_min)
                    else:
                        iv_dt_fim = _hm_to_dt(base + timedelta(days=1), iv_fim_min)
                    if iv_dt_ini >= s_fim or iv_dt_fim <= s_ini:
                        novos.append((s_ini, s_fim))
                    else:
                        if s_ini < iv_dt_ini:
                            novos.append((s_ini, iv_dt_ini))
                        if iv_dt_fim < s_fim:
                            novos.append((iv_dt_fim, s_fim))
                    break
            segmentos = novos if novos else segmentos
        janelas_final.extend(segmentos)
    janelas_final = [(a, b) for (a, b) in janelas_final if b > a]
    janelas_final.sort(key=lambda x: x[0])
    return janelas_final

def _calcular_fim_laser(dt_inicio, total_seg, intervalos_laser, max_dias=365):
    if total_seg <= 0:
        return dt_inicio
    dt = dt_inicio
    dias_verificados = 0
    dia_atual = dt.date()
    while total_seg > 0 and dias_verificados < max_dias:
        janelas = _get_janelas_dia(dia_atual, intervalos_laser)
        for (j_ini, j_fim) in janelas:
            if j_fim <= dt:
                continue
            inicio_efetivo = max(dt, j_ini)
            seg_disponiveis = (j_fim - inicio_efetivo).total_seconds()
            if seg_disponiveis <= 0:
                continue
            if total_seg <= seg_disponiveis:
                return inicio_efetivo + timedelta(seconds=total_seg)
            else:
                total_seg -= seg_disponiveis
                dt = j_fim
        dia_atual = dia_atual + timedelta(days=1)
        dt = datetime.combine(dia_atual, datetime.min.time())
        dias_verificados += 1
    return dt

# ── PASSADORIA ───────────────────────────────────────────────────
class PassadoriaItem(db.Model):
    id                = db.Column(db.Integer, primary_key=True)
    numero            = db.Column(db.Integer)
    op                = db.Column(db.String(20))
    referencia        = db.Column(db.String(50))
    descricao_produto = db.Column(db.String(200))
    qtde_pecas        = db.Column(db.Integer, default=0)
    tempo_padrao_min  = db.Column(db.Float, default=0.85)   # tempo padrão por peça (minutos)
    qtde_passadeiras  = db.Column(db.Integer, default=1)    # passadeiras trabalhando em paralelo neste item
    parada_min        = db.Column(db.Integer, default=0)
    data_inicio       = db.Column(db.DateTime, nullable=True)
    data_fim           = db.Column(db.DateTime, nullable=True)
    status            = db.Column(db.String(20), default='aguardando')
    observacao        = db.Column(db.String(200))
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def duracao_seg(self):
        qp = self.qtde_passadeiras or 1
        base = (self.qtde_pecas or 0) * (self.tempo_padrao_min or 0) * 60.0 / qp
        return base + (self.parada_min or 0) * 60.0

    def calcular_fim(self):
        if not self.data_inicio or not self.qtde_pecas:
            return None
        return _calcular_fim_laser(self.data_inicio, self.duracao_seg, [])

    def to_dict(self):
        fim = self.data_fim or self.calcular_fim()
        return {
            'id': self.id, 'numero': self.numero, 'op': self.op, 'referencia': self.referencia,
            'descricao_produto': self.descricao_produto, 'qtde_pecas': self.qtde_pecas,
            'tempo_padrao_min': self.tempo_padrao_min, 'qtde_passadeiras': self.qtde_passadeiras,
            'parada_min': self.parada_min or 0, 'status': self.status, 'observacao': self.observacao,
            'data_inicio': self.data_inicio.strftime('%Y-%m-%dT%H:%M') if self.data_inicio else None,
            'data_fim': fim.strftime('%Y-%m-%dT%H:%M') if fim else None,
            'duracao_min': round(self.duracao_seg / 60, 1),
        }


class TabelaPreco(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    op              = db.Column(db.String(20), nullable=False)
    referencia      = db.Column(db.String(50), nullable=False)
    preco_peca      = db.Column(db.Float, nullable=False, default=0.0)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

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

class Funcionario(db.Model):
    id                   = db.Column(db.Integer, primary_key=True)
    nome                 = db.Column(db.String(100), nullable=False)
    cargo                = db.Column(db.String(80))
    salario_base         = db.Column(db.Float, default=0.0)
    salario_minimo       = db.Column(db.Float, default=1621.00)
    insalubridade_pct    = db.Column(db.Float, default=0.0)
    # Encargos provisionados mensalmente (Grupo A + B da tabela de custos):
    fgts_pct             = db.Column(db.Float, default=8.0)     # FGTS mensal
    ferias_pct           = db.Column(db.Float, default=8.33)    # Férias constitucionais (1/12)
    um_terco_ferias_pct  = db.Column(db.Float, default=2.78)    # 1/3 constitucional de férias
    decimo_terceiro_pct  = db.Column(db.Float, default=8.33)    # 13º salário (1/12)
    outros_encargos_pct  = db.Column(db.Float, default=0.0)     # INSS patronal, RAT/SAT, Terceiros, etc. (Lucro Presumido/Real)
    beneficios_fixos     = db.Column(db.Float, default=0.0)
    jornada_mensal_h     = db.Column(db.Float, default=220.0)
    eficiencia_pct       = db.Column(db.Float, default=85.0)
    ativo                = db.Column(db.Boolean, default=True)
    created_at           = db.Column(db.DateTime, default=datetime.utcnow)

    # ── Cálculo do Custo por Minuto (CPM) — Mão de Obra Direta ──
    @property
    def insalubridade_valor(self):
        return (self.salario_minimo or 0.0) * ((self.insalubridade_pct or 0.0) / 100)

    @property
    def base_salarial(self):
        return (self.salario_base or 0.0) + self.insalubridade_valor

    @property
    def encargos_pct(self):
        """Soma de todos os encargos provisionados mensalmente (FGTS + Férias + 1/3 + 13º + outros)."""
        return ((self.fgts_pct or 0.0) + (self.ferias_pct or 0.0) +
                (self.um_terco_ferias_pct or 0.0) + (self.decimo_terceiro_pct or 0.0) +
                (self.outros_encargos_pct or 0.0))

    @property
    def custo_com_encargos(self):
        return self.base_salarial * (1 + self.encargos_pct / 100)

    @property
    def custo_mensal_total(self):
        return self.custo_com_encargos + (self.beneficios_fixos or 0.0)

    @property
    def minutos_produtivos(self):
        return (self.jornada_mensal_h or 0.0) * 60 * ((self.eficiencia_pct or 100.0) / 100)

    @property
    def cpm(self):
        mp = self.minutos_produtivos
        return round(self.custo_mensal_total / mp, 4) if mp else 0.0

    @property
    def custo_hora(self):
        return round(self.cpm * 60, 2)

    def to_dict(self):
        return {
            'id': self.id, 'nome': self.nome, 'cargo': self.cargo,
            'salario_base': self.salario_base, 'salario_minimo': self.salario_minimo,
            'insalubridade_pct': self.insalubridade_pct,
            'fgts_pct': self.fgts_pct, 'ferias_pct': self.ferias_pct,
            'um_terco_ferias_pct': self.um_terco_ferias_pct,
            'decimo_terceiro_pct': self.decimo_terceiro_pct,
            'outros_encargos_pct': self.outros_encargos_pct,
            'encargos_pct': round(self.encargos_pct, 2),
            'beneficios_fixos': self.beneficios_fixos, 'jornada_mensal_h': self.jornada_mensal_h,
            'eficiencia_pct': self.eficiencia_pct, 'ativo': self.ativo,
            'insalubridade_valor': round(self.insalubridade_valor, 2),
            'base_salarial': round(self.base_salarial, 2),
            'custo_com_encargos': round(self.custo_com_encargos, 2),
            'custo_mensal_total': round(self.custo_mensal_total, 2),
            'minutos_produtivos': round(self.minutos_produtivos, 1),
            'cpm': self.cpm, 'custo_hora': self.custo_hora,
        }

# ── ESTOQUE DE QUÍMICOS E MATÉRIAS-PRIMAS ──────────────────────────
class ProdutoQuimico(db.Model):
    id                    = db.Column(db.Integer, primary_key=True)
    nome                  = db.Column(db.String(120), nullable=False)
    categoria             = db.Column(db.String(40), default='Lavanderia de Jeans')  # Lavanderia de Jeans / Tingimento de Sarja / Consumíveis
    unidade               = db.Column(db.String(10), default='kg')  # kg, L, un
    quantidade_atual      = db.Column(db.Float, default=0.0)
    custo_unitario        = db.Column(db.Float, default=0.0)  # custo por unidade de estoque (kg/L/un)
    estoque_minimo        = db.Column(db.Float, default=0.0)
    estoque_maximo        = db.Column(db.Float, default=0.0)
    unidade_compra        = db.Column(db.String(40))          # Ex: "Saco 25kg", "Rolo 500un"
    fator_conversao       = db.Column(db.Float, default=1.0)  # Ex: 1 saco = 25 kg → fator = 25
    fornecedor             = db.Column(db.String(120))
    lead_time_dias        = db.Column(db.Integer, default=0)  # tempo de atendimento do fornecedor
    ativo                 = db.Column(db.Boolean, default=True)
    created_at            = db.Column(db.DateTime, default=datetime.utcnow)
    movimentacoes         = db.relationship('MovimentacaoEstoque', backref='produto', lazy=True,
                                             cascade='all, delete-orphan',
                                             order_by='MovimentacaoEstoque.data.desc()')

    @property
    def status_estoque(self):
        if self.estoque_minimo and self.quantidade_atual <= self.estoque_minimo * 0.5:
            return 'critico'
        if self.estoque_minimo and self.quantidade_atual <= self.estoque_minimo:
            return 'baixo'
        return 'ok'

    @property
    def sugestao_compra(self):
        if self.quantidade_atual <= self.estoque_minimo and self.estoque_maximo:
            qtd = max(self.estoque_maximo - self.quantidade_atual, 0)
            return round(qtd, 2)
        return 0.0

    @property
    def valor_em_estoque(self):
        return round((self.quantidade_atual or 0.0) * (self.custo_unitario or 0.0), 2)

    def to_dict(self):
        return {
            'id': self.id, 'nome': self.nome, 'categoria': self.categoria, 'unidade': self.unidade,
            'quantidade_atual': self.quantidade_atual, 'custo_unitario': self.custo_unitario,
            'estoque_minimo': self.estoque_minimo, 'estoque_maximo': self.estoque_maximo,
            'unidade_compra': self.unidade_compra, 'fator_conversao': self.fator_conversao,
            'fornecedor': self.fornecedor, 'lead_time_dias': self.lead_time_dias, 'ativo': self.ativo,
            'status_estoque': self.status_estoque, 'sugestao_compra': self.sugestao_compra,
            'valor_em_estoque': self.valor_em_estoque,
        }

class MovimentacaoEstoque(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    produto_id      = db.Column(db.Integer, db.ForeignKey('produto_quimico.id'), nullable=False)
    tipo            = db.Column(db.String(10), nullable=False)  # entrada / saida / ajuste
    quantidade      = db.Column(db.Float, default=0.0)
    lote_fornecedor = db.Column(db.String(60))
    observacao      = db.Column(db.String(200))
    saldo_apos      = db.Column(db.Float, default=0.0)
    data            = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'produto_id': self.produto_id, 'tipo': self.tipo,
            'quantidade': self.quantidade, 'lote_fornecedor': self.lote_fornecedor,
            'observacao': self.observacao, 'saldo_apos': self.saldo_apos,
            'data': self.data.strftime('%d/%m/%Y %H:%M') if self.data else None,
        }


# ── RECEITAS DE LAVAGEM ─────────────────────────────────────────────
class Receita(db.Model):
    id                = db.Column(db.Integer, primary_key=True)
    nome              = db.Column(db.String(120), nullable=False)
    referencia        = db.Column(db.String(50))
    lavacao           = db.Column(db.String(80))
    versao            = db.Column(db.Integer, default=1)
    receita_pai_id    = db.Column(db.Integer, db.ForeignKey('receita.id'), nullable=True)
    status            = db.Column(db.String(20), default='rascunho')  # rascunho / ativa / descontinuada
    observacoes       = db.Column(db.String(300))
    criado_por        = db.Column(db.String(80))
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)
    etapas            = db.relationship('ReceitaEtapa', backref='receita', lazy=True,
                                         cascade='all, delete-orphan', order_by='ReceitaEtapa.ordem')
    versoes_filhas    = db.relationship('Receita', backref=db.backref('receita_pai', remote_side=[id]),
                                         lazy=True)

    @property
    def tempo_total_min(self):
        return sum((e.tempo_min or 0) for e in self.etapas)

    def to_dict(self, with_etapas=True):
        d = {
            'id': self.id, 'nome': self.nome, 'referencia': self.referencia, 'lavacao': self.lavacao,
            'versao': self.versao, 'receita_pai_id': self.receita_pai_id, 'status': self.status,
            'observacoes': self.observacoes, 'criado_por': self.criado_por,
            'created_at': self.created_at.strftime('%d/%m/%Y %H:%M') if self.created_at else None,
            'tempo_total_min': self.tempo_total_min,
            'total_etapas': len(self.etapas),
        }
        if with_etapas:
            d['etapas'] = [e.to_dict() for e in self.etapas]
        return d

class ReceitaEtapa(db.Model):
    id                = db.Column(db.Integer, primary_key=True)
    receita_id        = db.Column(db.Integer, db.ForeignKey('receita.id'), nullable=False)
    ordem             = db.Column(db.Integer, default=1)
    titulo            = db.Column(db.String(120), nullable=False)
    tipo              = db.Column(db.String(20), default='quimico')  # agua/quimico/mecanico/temperatura/secagem/outro
    produto_quimico_id= db.Column(db.Integer, db.ForeignKey('produto_quimico.id'), nullable=True)
    quantidade        = db.Column(db.Float, default=0.0)
    unidade           = db.Column(db.String(10))
    temperatura_agua  = db.Column(db.Float)
    tempo_min         = db.Column(db.Integer, default=0)
    instrucao_texto   = db.Column(db.Text)
    produto           = db.relationship('ProdutoQuimico', lazy=True)

    def to_dict(self):
        return {
            'id': self.id, 'receita_id': self.receita_id, 'ordem': self.ordem, 'titulo': self.titulo,
            'tipo': self.tipo, 'produto_quimico_id': self.produto_quimico_id,
            'produto_nome': self.produto.nome if self.produto else None,
            'quantidade': self.quantidade, 'unidade': self.unidade or (self.produto.unidade if self.produto else None),
            'temperatura_agua': self.temperatura_agua, 'tempo_min': self.tempo_min,
            'instrucao_texto': self.instrucao_texto,
        }

# ── PEÇAS DE AMOSTRA ────────────────────────────────────────────────
class PecaAmostra(db.Model):
    id                 = db.Column(db.Integer, primary_key=True)
    referencia         = db.Column(db.String(50), nullable=False)
    lavacao            = db.Column(db.String(80))
    receita_id         = db.Column(db.Integer, db.ForeignKey('receita.id'), nullable=True)
    numero_lacre       = db.Column(db.String(30))
    status             = db.Column(db.String(20), default='em_teste')  # em_teste/aprovada/reprovada/arquivada
    versao_anterior_id = db.Column(db.Integer, db.ForeignKey('peca_amostra.id'), nullable=True)
    observacoes        = db.Column(db.String(300))
    aprovado_por       = db.Column(db.String(80))
    data_criacao       = db.Column(db.DateTime, default=datetime.utcnow)
    data_aprovacao     = db.Column(db.DateTime, nullable=True)
    receita            = db.relationship('Receita', lazy=True)
    versoes_filhas     = db.relationship('PecaAmostra', backref=db.backref('versao_anterior', remote_side=[id]),
                                          lazy=True)

    def to_dict(self):
        return {
            'id': self.id, 'referencia': self.referencia, 'lavacao': self.lavacao,
            'receita_id': self.receita_id, 'receita_nome': self.receita.nome if self.receita else None,
            'numero_lacre': self.numero_lacre, 'status': self.status,
            'versao_anterior_id': self.versao_anterior_id,
            'observacoes': self.observacoes, 'aprovado_por': self.aprovado_por,
            'data_criacao': self.data_criacao.strftime('%d/%m/%Y %H:%M') if self.data_criacao else None,
            'data_aprovacao': self.data_aprovacao.strftime('%d/%m/%Y %H:%M') if self.data_aprovacao else None,
        }

# ── HELPERS ──────────────────────────────────────────────────────
def safe_int(v, default=0):
    try: return int(float(v or default))
    except: return default

def safe_float(v, default=0.0):
    try: return float(v or default)
    except: return default

# ── INIT DB ──────────────────────────────────────────────────────
def init_db():
    db.create_all()
    tipos = [('lavar',10,80.0,90),('centrifuga',6,80.0,15),('secador',11,60.0,45)]
    for tipo, qtd, cap, tempo in tipos:
        for n in range(1, qtd+1):
            if not Maquina.query.filter_by(tipo=tipo, numero=n).first():
                db.session.add(Maquina(tipo=tipo, numero=n, capacidade=cap, tempo_min=tempo))
    for n in range(1, 4):
        if not LaserEquipamento.query.filter_by(numero=n).first():
            db.session.add(LaserEquipamento(numero=n, tempo_min=1.42))
    db.session.commit()

# ── ROUTES ───────────────────────────────────────────────────────
@app.route('/init_db_agora')
def init_db_route():
    for sql in [
        'ALTER TABLE laser_equipamento RENAME COLUMN tempo_seg TO tempo_min',
        'ALTER TABLE laser_fila RENAME COLUMN tempo_seg TO tempo_min',
    ]:
        try:
            db.session.execute(db.text(sql))
            db.session.commit()
        except Exception:
            db.session.rollback()
    try:
        db.create_all()
        init_db()
    except Exception as e:
        db.session.rollback()
        return f'Erro ao criar tabelas base: {e}'
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
        """CREATE TABLE IF NOT EXISTS funcionario (
            id SERIAL PRIMARY KEY, nome VARCHAR(100) NOT NULL, cargo VARCHAR(80),
            salario_base FLOAT DEFAULT 0.0, salario_minimo FLOAT DEFAULT 1621.00,
            insalubridade_pct FLOAT DEFAULT 0.0, encargos_pct FLOAT DEFAULT 68.0,
            beneficios_fixos FLOAT DEFAULT 0.0, jornada_mensal_h FLOAT DEFAULT 220.0,
            eficiencia_pct FLOAT DEFAULT 85.0, ativo BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW())""",
        'ALTER TABLE funcionario ADD COLUMN IF NOT EXISTS fgts_pct FLOAT DEFAULT 8.0',
        'ALTER TABLE funcionario ADD COLUMN IF NOT EXISTS ferias_pct FLOAT DEFAULT 8.33',
        'ALTER TABLE funcionario ADD COLUMN IF NOT EXISTS um_terco_ferias_pct FLOAT DEFAULT 2.78',
        'ALTER TABLE funcionario ADD COLUMN IF NOT EXISTS decimo_terceiro_pct FLOAT DEFAULT 8.33',
        'ALTER TABLE funcionario ADD COLUMN IF NOT EXISTS outros_encargos_pct FLOAT DEFAULT 0.0',
        'ALTER TABLE funcionario DROP COLUMN IF EXISTS encargos_pct',
        """CREATE TABLE IF NOT EXISTS produto_quimico (
            id SERIAL PRIMARY KEY, nome VARCHAR(120) NOT NULL,
            categoria VARCHAR(40) DEFAULT 'Lavanderia de Jeans', unidade VARCHAR(10) DEFAULT 'kg',
            quantidade_atual FLOAT DEFAULT 0.0, custo_unitario FLOAT DEFAULT 0.0,
            estoque_minimo FLOAT DEFAULT 0.0, estoque_maximo FLOAT DEFAULT 0.0,
            unidade_compra VARCHAR(40), fator_conversao FLOAT DEFAULT 1.0,
            fornecedor VARCHAR(120), lead_time_dias INTEGER DEFAULT 0,
            ativo BOOLEAN DEFAULT TRUE, created_at TIMESTAMP DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS movimentacao_estoque (
            id SERIAL PRIMARY KEY, produto_id INTEGER REFERENCES produto_quimico(id),
            tipo VARCHAR(10) NOT NULL, quantidade FLOAT DEFAULT 0.0,
            lote_fornecedor VARCHAR(60), observacao VARCHAR(200),
            saldo_apos FLOAT DEFAULT 0.0, data TIMESTAMP DEFAULT NOW())""",
        """CREATE TABLE IF NOT EXISTS passadoria_item (
            id SERIAL PRIMARY KEY, numero INTEGER, op VARCHAR(20), referencia VARCHAR(50),
            descricao_produto VARCHAR(200), qtde_pecas INTEGER DEFAULT 0,
            tempo_padrao_min FLOAT DEFAULT 0.85, qtde_passadeiras INTEGER DEFAULT 1,
            parada_min INTEGER DEFAULT 0, data_inicio TIMESTAMP, data_fim TIMESTAMP,
            status VARCHAR(20) DEFAULT 'aguardando', observacao VARCHAR(200),
            created_at TIMESTAMP DEFAULT NOW())""",
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
        db.session.execute(db.text('SELECT 1'))
        resultado.append('✅ Banco conectado')
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

@app.route('/debug_index')
def debug_index():
    import os, hashlib
    path = os.path.join(app.root_path, 'templates', 'index.html')
    with open(path, 'rb') as f:
        content = f.read()
    return jsonify({
        'path': path, 'size_bytes': len(content),
        'md5': hashlib.md5(content).hexdigest(),
        'num_lines': content.count(b'\n')
    })

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
    m.capacidade = safe_float(d.get('capacidade', m.capacidade))
    m.tempo_min  = safe_int(d.get('tempo_min', m.tempo_min))
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
              lavacao=d.get('lavacao',''), qtde_pecas=safe_int(d.get('qtde_pecas',0)),
              peso=safe_float(d.get('peso',0)), data_inicio=dt_inicio,
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
    if 'qtde_pecas' in d: c.qtde_pecas = safe_int(d['qtde_pecas'])
    if 'peso' in d: c.peso = safe_float(d['peso'])
    if 'status' in d: c.status = d['status']
    if 'observacao' in d: c.observacao = d['observacao']
    if 'parada_min' in d: c.parada_min = safe_int(d.get('parada_min', 0))
    if 'data_inicio' in d:
        try: c.data_inicio = datetime.strptime(d['data_inicio'], '%Y-%m-%dT%H:%M')
        except: c.data_inicio = None
    db.session.commit()
    return jsonify({'ok': True,
                    'data_saida': c.data_saida.strftime('%Y-%m-%dT%H:%M') if c.data_saida else None})

@app.route('/api/cargas/<int:cid>', methods=['DELETE'])
def delete_carga(cid):
    try:
        c = Carga.query.get_or_404(cid)
        maquina_id = c.maquina_id
        db.session.delete(c)
        db.session.flush()
        restantes = Carga.query.filter_by(maquina_id=maquina_id).order_by(Carga.numero).all()
        for i, cc in enumerate(restantes, 1):
            cc.numero = i
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as ex:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(ex)}), 500

# ── GERAR CARGAS — corrigido safe_int/safe_float ─────────────────
@app.route('/api/maquinas/<int:mid>/gerar_cargas', methods=['POST'])
def gerar_cargas(mid):
    try:
        m   = Maquina.query.get_or_404(mid)
        d   = request.json or {}
        op  = d.get('op', '')
        ref = d.get('referencia', '')
        lav = d.get('lavacao', '')
        n   = safe_int(d.get('quantidade', 10)) or 10
        peso_carga  = safe_float(d.get('peso_carga', m.capacidade)) or m.capacidade
        append_mode = d.get('append', False)

        cargas_existentes = sorted(m.cargas, key=lambda x: x.numero)

        if cargas_existentes and (append_mode or not d.get('data_inicio')):
            ultima = cargas_existentes[-1]
            parada_ultima = ultima.parada_min or 0
            # Herda OP/ref/lav da última carga se não fornecidos
            if not op and ultima.op_manual:
                op = ultima.op_manual
            if not ref and ultima.referencia:
                ref = ultima.referencia
            if not lav and ultima.lavacao:
                lav = ultima.lavacao
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

        # Calcula qtde_pecas automaticamente se não informado
        qtde_pecas_padrao = safe_int(d.get('qtde_pecas', 0))
        if not qtde_pecas_padrao:
            # Tenta calcular pela OP selecionada
            op_id = safe_int(d.get('op_id', 0))
            if op_id:
                op_obj = OrdemProducao.query.get(op_id)
                if op_obj and n > 0:
                    import math as _math
                    qtde_pecas_padrao = _math.floor(op_obj.total_pecas / n)
            # Se não tem op_id, herda da última carga com peças
            if not qtde_pecas_padrao and cargas_existentes:
                ultima_com_pecas = next((c for c in reversed(cargas_existentes) if c.qtde_pecas), None)
                if ultima_com_pecas:
                    qtde_pecas_padrao = ultima_com_pecas.qtde_pecas

        for i in range(num_inicio, num_inicio + n):
            c = Carga(maquina_id=mid, numero=i, op_manual=op,
                      referencia=ref, lavacao=lav, qtde_pecas=qtde_pecas_padrao,
                      peso=peso_carga, data_inicio=dt, status='aguardando')
            db.session.add(c)
            dt = dt + timedelta(minutes=m.tempo_min)
        db.session.commit()
        return jsonify({'ok': True, 'geradas': n})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500

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
        r = TabelaPreco(op=op_val, referencia=ref_val,
                        preco_peca=safe_float(d.get('preco_peca', 0)))
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
        r.op         = d.get('op', r.op).strip().upper()
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
    num_cargas = math.ceil(cargas_raw) if arred_cargas == 'cima' else math.floor(cargas_raw)
    if num_cargas < 1:
        num_cargas = 1
    peso_carga  = round(peso_total / num_cargas, 3)
    pecas_raw   = total_pecas / num_cargas
    pecas_carga = math.ceil(pecas_raw) if arred_pecas == 'cima' else math.floor(pecas_raw)
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

@app.route('/api/laser/equipamentos/<int:eid>/intervalos', methods=['GET'])
def get_laser_intervalos(eid):
    ivs = LaserIntervalo.query.filter_by(equipamento_id=eid).order_by(LaserIntervalo.hora_inicio).all()
    return jsonify([{'id': i.id, 'nome': i.nome, 'hora_inicio': i.hora_inicio, 'hora_fim': i.hora_fim} for i in ivs])

@app.route('/api/laser/equipamentos/<int:eid>/intervalos', methods=['POST'])
def add_laser_intervalo(eid):
    d = request.json
    iv = LaserIntervalo(equipamento_id=eid, nome=d.get('nome',''),
                        hora_inicio=d.get('hora_inicio',''), hora_fim=d.get('hora_fim',''))
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

@app.route('/api/laser/equipamentos/<int:eid>/simular', methods=['POST'])
def simular_laser(eid):
    e = LaserEquipamento.query.get_or_404(eid)
    d = request.json
    try:
        dt_inicio = datetime.strptime(d['data_inicio'], '%Y-%m-%dT%H:%M')
    except:
        return jsonify({'ok': False, 'error': 'data_inicio inválido'}), 400
    qtde  = safe_int(d.get('qtde_pecas', 0))
    tempo = safe_float(d.get('tempo_min', e.tempo_min))
    if qtde <= 0 or tempo <= 0:
        return jsonify({'ok': False, 'error': 'Qtde e tempo devem ser > 0'}), 400
    total_seg = qtde * tempo * 60.0
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
    filas_ord = sorted(e.filas, key=lambda x: x.numero)
    if apos_numero is not None:
        for ff in filas_ord:
            if ff.numero > apos_numero:
                ff.numero += 1
        num = apos_numero + 1
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
    fim = f.calcular_fim(e.intervalos)
    f.data_fim = fim
    db.session.commit()
    return jsonify({'ok': True,
                    'data_fim': f.data_fim.strftime('%Y-%m-%dT%H:%M') if f.data_fim else None})

@app.route('/api/laser/fila/<int:fid>', methods=['DELETE'])
def delete_laser_fila(fid):
    try:
        f = LaserFila.query.get_or_404(fid)
        equip_id = f.equipamento_id
        # Desvincula apontamentos que referenciam esta fila (preserva o histórico)
        LaserApontamento.query.filter_by(fila_id=fid).update({'fila_id': None})
        db.session.delete(f)
        db.session.flush()
        restantes = LaserFila.query.filter_by(equipamento_id=equip_id).order_by(LaserFila.numero).all()
        for i, ff in enumerate(restantes, 1):
            ff.numero = i
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as ex:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(ex)}), 500

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

# ── PASSADORIA ────────────────────────────────────────────────────
@app.route('/api/passadoria/fila', methods=['GET'])
def get_passadoria_fila():
    itens = PassadoriaItem.query.order_by(PassadoriaItem.numero).all()
    return jsonify([i.to_dict() for i in itens])

@app.route('/api/passadoria/simular', methods=['POST'])
def simular_passadoria():
    d = request.json or {}
    try:
        dt_inicio = datetime.strptime(d['data_inicio'], '%Y-%m-%dT%H:%M')
    except:
        return jsonify({'ok': False, 'error': 'Data/hora de início inválida'}), 400
    qtde  = safe_int(d.get('qtde_pecas', 0))
    tempo = safe_float(d.get('tempo_padrao_min', 0.85))
    qp    = safe_int(d.get('qtde_passadeiras', 1)) or 1
    if qtde <= 0 or tempo <= 0:
        return jsonify({'ok': False, 'error': 'Qtde de peças e tempo padrão devem ser maiores que zero'}), 400
    total_seg = (qtde * tempo * 60.0) / qp
    fim = _calcular_fim_laser(dt_inicio, total_seg, [])
    duracao_h = total_seg / 3600
    return jsonify({
        'ok': True,
        'data_inicio': dt_inicio.strftime('%d/%m/%Y %H:%M'),
        'data_fim': fim.strftime('%d/%m/%Y %H:%M') if fim else None,
        'duracao_horas': round(duracao_h, 2),
        'duracao_fmt': f"{int(duracao_h)}h{int((duracao_h%1)*60):02d}min",
        'pecas_hora_passadeira': round(60/tempo, 1) if tempo > 0 else 0,
        'pecas_hora_total': round((60/tempo) * qp, 1) if tempo > 0 else 0,
    })

@app.route('/api/passadoria/fila', methods=['POST'])
def add_passadoria_fila():
    d = request.json or {}
    dt_inicio = None
    if d.get('data_inicio'):
        try: dt_inicio = datetime.strptime(d['data_inicio'], '%Y-%m-%dT%H:%M')
        except: pass
    else:
        ultimo = PassadoriaItem.query.order_by(PassadoriaItem.numero.desc()).first()
        if ultimo:
            fim = ultimo.data_fim or ultimo.calcular_fim()
            if fim: dt_inicio = fim
    num = (db.session.query(db.func.max(PassadoriaItem.numero)).scalar() or 0) + 1
    item = PassadoriaItem(
        numero=num, op=d.get('op',''), referencia=d.get('referencia',''),
        descricao_produto=d.get('descricao_produto',''),
        qtde_pecas=safe_int(d.get('qtde_pecas',0)),
        tempo_padrao_min=safe_float(d.get('tempo_padrao_min', 0.85)),
        qtde_passadeiras=safe_int(d.get('qtde_passadeiras', 1)) or 1,
        parada_min=safe_int(d.get('parada_min', 0)),
        data_inicio=dt_inicio, status='aguardando',
        observacao=d.get('observacao',''),
    )
    db.session.add(item)
    db.session.flush()
    item.data_fim = item.calcular_fim()
    db.session.commit()
    return jsonify({'ok': True, 'item': item.to_dict()})

@app.route('/api/passadoria/fila/<int:iid>', methods=['PUT'])
def update_passadoria_fila(iid):
    item = PassadoriaItem.query.get_or_404(iid)
    d = request.json or {}
    if 'op' in d: item.op = d['op']
    if 'referencia' in d: item.referencia = d['referencia']
    if 'descricao_produto' in d: item.descricao_produto = d['descricao_produto']
    if 'qtde_pecas' in d: item.qtde_pecas = safe_int(d['qtde_pecas'])
    if 'tempo_padrao_min' in d: item.tempo_padrao_min = safe_float(d['tempo_padrao_min'])
    if 'qtde_passadeiras' in d: item.qtde_passadeiras = safe_int(d['qtde_passadeiras']) or 1
    if 'parada_min' in d: item.parada_min = safe_int(d['parada_min'])
    if 'status' in d: item.status = d['status']
    if 'observacao' in d: item.observacao = d['observacao']
    if 'data_inicio' in d:
        try: item.data_inicio = datetime.strptime(d['data_inicio'], '%Y-%m-%dT%H:%M')
        except: item.data_inicio = None
    item.data_fim = item.calcular_fim()
    db.session.commit()
    return jsonify({'ok': True, 'item': item.to_dict()})

@app.route('/api/passadoria/fila/<int:iid>', methods=['DELETE'])
def delete_passadoria_fila(iid):
    try:
        item = PassadoriaItem.query.get_or_404(iid)
        db.session.delete(item)
        db.session.flush()
        restantes = PassadoriaItem.query.order_by(PassadoriaItem.numero).all()
        for i, it in enumerate(restantes, 1):
            it.numero = i
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as ex:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(ex)}), 500

# ── FUNCIONÁRIOS / CUSTO DE MÃO DE OBRA (CPM) ──────────────────────
@app.route('/api/funcionarios', methods=['GET'])
def get_funcionarios():
    q = Funcionario.query
    if request.args.get('ativos') == '1':
        q = q.filter_by(ativo=True)
    rows = q.order_by(Funcionario.nome).all()
    return jsonify([f.to_dict() for f in rows])

@app.route('/api/funcionarios/<int:fid>', methods=['GET'])
def get_funcionario(fid):
    f = Funcionario.query.get_or_404(fid)
    return jsonify(f.to_dict())

@app.route('/api/funcionarios', methods=['POST'])
def add_funcionario():
    d = request.json or {}
    if not d.get('nome'):
        return jsonify({'error': 'Nome é obrigatório'}), 400
    f = Funcionario(
        nome=d.get('nome', '').strip(),
        cargo=(d.get('cargo') or '').strip(),
        salario_base=safe_float(d.get('salario_base')),
        salario_minimo=safe_float(d.get('salario_minimo'), 1621.00),
        insalubridade_pct=safe_float(d.get('insalubridade_pct')),
        fgts_pct=safe_float(d.get('fgts_pct'), 8.0),
        ferias_pct=safe_float(d.get('ferias_pct'), 8.33),
        um_terco_ferias_pct=safe_float(d.get('um_terco_ferias_pct'), 2.78),
        decimo_terceiro_pct=safe_float(d.get('decimo_terceiro_pct'), 8.33),
        outros_encargos_pct=safe_float(d.get('outros_encargos_pct')),
        beneficios_fixos=safe_float(d.get('beneficios_fixos')),
        jornada_mensal_h=safe_float(d.get('jornada_mensal_h'), 220.0),
        eficiencia_pct=safe_float(d.get('eficiencia_pct'), 85.0),
        ativo=bool(d.get('ativo', True)),
    )
    db.session.add(f); db.session.commit()
    return jsonify(f.to_dict())

@app.route('/api/funcionarios/<int:fid>', methods=['PUT'])
def update_funcionario(fid):
    f = Funcionario.query.get_or_404(fid)
    d = request.json or {}
    if 'nome' in d: f.nome = (d['nome'] or '').strip()
    if 'cargo' in d: f.cargo = (d['cargo'] or '').strip()
    if 'salario_base' in d: f.salario_base = safe_float(d['salario_base'])
    if 'salario_minimo' in d: f.salario_minimo = safe_float(d['salario_minimo'], 1621.00)
    if 'insalubridade_pct' in d: f.insalubridade_pct = safe_float(d['insalubridade_pct'])
    if 'fgts_pct' in d: f.fgts_pct = safe_float(d['fgts_pct'], 8.0)
    if 'ferias_pct' in d: f.ferias_pct = safe_float(d['ferias_pct'], 8.33)
    if 'um_terco_ferias_pct' in d: f.um_terco_ferias_pct = safe_float(d['um_terco_ferias_pct'], 2.78)
    if 'decimo_terceiro_pct' in d: f.decimo_terceiro_pct = safe_float(d['decimo_terceiro_pct'], 8.33)
    if 'outros_encargos_pct' in d: f.outros_encargos_pct = safe_float(d['outros_encargos_pct'])
    if 'beneficios_fixos' in d: f.beneficios_fixos = safe_float(d['beneficios_fixos'])
    if 'jornada_mensal_h' in d: f.jornada_mensal_h = safe_float(d['jornada_mensal_h'], 220.0)
    if 'eficiencia_pct' in d: f.eficiencia_pct = safe_float(d['eficiencia_pct'], 85.0)
    if 'ativo' in d: f.ativo = bool(d['ativo'])
    db.session.commit()
    return jsonify(f.to_dict())

@app.route('/api/funcionarios/<int:fid>', methods=['DELETE'])
def delete_funcionario(fid):
    f = Funcionario.query.get_or_404(fid)
    db.session.delete(f); db.session.commit()
    return jsonify({'ok': True})

# ── ESTOQUE DE QUÍMICOS ─────────────────────────────────────────────
@app.route('/api/quimicos', methods=['GET'])
def get_quimicos():
    q = ProdutoQuimico.query
    if request.args.get('ativos') == '1':
        q = q.filter_by(ativo=True)
    categoria = request.args.get('categoria')
    if categoria:
        q = q.filter_by(categoria=categoria)
    rows = q.order_by(ProdutoQuimico.nome).all()
    return jsonify([p.to_dict() for p in rows])

@app.route('/api/quimicos/<int:pid>', methods=['GET'])
def get_quimico(pid):
    p = ProdutoQuimico.query.get_or_404(pid)
    return jsonify(p.to_dict())

@app.route('/api/quimicos', methods=['POST'])
def add_quimico():
    d = request.json or {}
    if not d.get('nome'):
        return jsonify({'error': 'Nome é obrigatório'}), 400
    p = ProdutoQuimico(
        nome=d.get('nome', '').strip(),
        categoria=d.get('categoria') or 'Lavanderia de Jeans',
        unidade=d.get('unidade') or 'kg',
        quantidade_atual=safe_float(d.get('quantidade_atual')),
        custo_unitario=safe_float(d.get('custo_unitario')),
        estoque_minimo=safe_float(d.get('estoque_minimo')),
        estoque_maximo=safe_float(d.get('estoque_maximo')),
        unidade_compra=(d.get('unidade_compra') or '').strip(),
        fator_conversao=safe_float(d.get('fator_conversao'), 1.0),
        fornecedor=(d.get('fornecedor') or '').strip(),
        lead_time_dias=safe_int(d.get('lead_time_dias')),
        ativo=bool(d.get('ativo', True)),
    )
    db.session.add(p); db.session.commit()
    # Se já entrou com saldo inicial, registra como movimentação de ajuste inicial
    if p.quantidade_atual:
        db.session.add(MovimentacaoEstoque(produto_id=p.id, tipo='ajuste', quantidade=p.quantidade_atual,
                                            observacao='Saldo inicial de cadastro', saldo_apos=p.quantidade_atual))
        db.session.commit()
    return jsonify(p.to_dict())

@app.route('/api/quimicos/<int:pid>', methods=['PUT'])
def update_quimico(pid):
    p = ProdutoQuimico.query.get_or_404(pid)
    d = request.json or {}
    if 'nome' in d: p.nome = (d['nome'] or '').strip()
    if 'categoria' in d: p.categoria = d['categoria']
    if 'unidade' in d: p.unidade = d['unidade']
    if 'custo_unitario' in d: p.custo_unitario = safe_float(d['custo_unitario'])
    if 'estoque_minimo' in d: p.estoque_minimo = safe_float(d['estoque_minimo'])
    if 'estoque_maximo' in d: p.estoque_maximo = safe_float(d['estoque_maximo'])
    if 'unidade_compra' in d: p.unidade_compra = (d['unidade_compra'] or '').strip()
    if 'fator_conversao' in d: p.fator_conversao = safe_float(d['fator_conversao'], 1.0)
    if 'fornecedor' in d: p.fornecedor = (d['fornecedor'] or '').strip()
    if 'lead_time_dias' in d: p.lead_time_dias = safe_int(d['lead_time_dias'])
    if 'ativo' in d: p.ativo = bool(d['ativo'])
    # quantidade_atual não é editada direto aqui — usa /movimentar para manter rastreabilidade
    db.session.commit()
    return jsonify(p.to_dict())

@app.route('/api/quimicos/<int:pid>', methods=['DELETE'])
def delete_quimico(pid):
    p = ProdutoQuimico.query.get_or_404(pid)
    db.session.delete(p); db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/quimicos/<int:pid>/movimentar', methods=['POST'])
def movimentar_quimico(pid):
    p = ProdutoQuimico.query.get_or_404(pid)
    d = request.json or {}
    tipo = d.get('tipo')  # entrada / saida
    qtd = safe_float(d.get('quantidade'))
    if tipo not in ('entrada', 'saida') or qtd <= 0:
        return jsonify({'error': 'Informe tipo (entrada/saida) e uma quantidade maior que zero'}), 400
    if tipo == 'saida' and qtd > p.quantidade_atual:
        return jsonify({'error': f'Saldo insuficiente. Estoque atual: {p.quantidade_atual} {p.unidade}'}), 400
    p.quantidade_atual = (p.quantidade_atual or 0.0) + (qtd if tipo == 'entrada' else -qtd)
    mov = MovimentacaoEstoque(
        produto_id=p.id, tipo=tipo, quantidade=qtd,
        lote_fornecedor=(d.get('lote_fornecedor') or '').strip(),
        observacao=(d.get('observacao') or '').strip(),
        saldo_apos=p.quantidade_atual,
    )
    db.session.add(mov); db.session.commit()
    return jsonify({'ok': True, 'produto': p.to_dict(), 'movimentacao': mov.to_dict()})

@app.route('/api/quimicos/<int:pid>/movimentacoes', methods=['GET'])
def get_movimentacoes(pid):
    ProdutoQuimico.query.get_or_404(pid)
    rows = MovimentacaoEstoque.query.filter_by(produto_id=pid).order_by(MovimentacaoEstoque.data.desc()).limit(50).all()
    return jsonify([m.to_dict() for m in rows])

@app.route('/api/quimicos/compras', methods=['GET'])
def relatorio_compras():
    """Relatório de Necessidade de Compras: itens no ou abaixo do estoque mínimo."""
    rows = ProdutoQuimico.query.filter(ProdutoQuimico.ativo == True,
                                        ProdutoQuimico.quantidade_atual <= ProdutoQuimico.estoque_minimo,
                                        ProdutoQuimico.estoque_minimo > 0).order_by(ProdutoQuimico.nome).all()
    return jsonify([p.to_dict() for p in rows])

# ── RECEITAS DE LAVAGEM ──────────────────────────────────────────────
@app.route('/api/receitas', methods=['GET'])
def get_receitas():
    q = Receita.query
    status = request.args.get('status')
    if status:
        q = q.filter_by(status=status)
    rows = q.order_by(Receita.created_at.desc()).all()
    return jsonify([r.to_dict(with_etapas=False) for r in rows])

@app.route('/api/receitas/<int:rid>', methods=['GET'])
def get_receita(rid):
    r = Receita.query.get_or_404(rid)
    return jsonify(r.to_dict())

@app.route('/api/receitas', methods=['POST'])
def add_receita():
    d = request.json or {}
    if not d.get('nome'):
        return jsonify({'error': 'Nome da receita é obrigatório'}), 400
    r = Receita(
        nome=d.get('nome', '').strip(),
        referencia=(d.get('referencia') or '').strip(),
        lavacao=(d.get('lavacao') or '').strip(),
        status=d.get('status') or 'rascunho',
        observacoes=(d.get('observacoes') or '').strip(),
        criado_por=(d.get('criado_por') or '').strip(),
    )
    db.session.add(r); db.session.commit()
    for i, e in enumerate(d.get('etapas') or []):
        _add_etapa(r.id, e, i + 1)
    db.session.commit()
    return jsonify(r.to_dict())

@app.route('/api/receitas/<int:rid>', methods=['PUT'])
def update_receita(rid):
    r = Receita.query.get_or_404(rid)
    d = request.json or {}
    if 'nome' in d: r.nome = (d['nome'] or '').strip()
    if 'referencia' in d: r.referencia = (d['referencia'] or '').strip()
    if 'lavacao' in d: r.lavacao = (d['lavacao'] or '').strip()
    if 'status' in d: r.status = d['status']
    if 'observacoes' in d: r.observacoes = (d['observacoes'] or '').strip()
    if 'criado_por' in d: r.criado_por = (d['criado_por'] or '').strip()
    # Se vieram etapas, substitui todas (forma simples de salvar a lista editada)
    if 'etapas' in d:
        for e in list(r.etapas):
            db.session.delete(e)
        db.session.flush()
        for i, e in enumerate(d.get('etapas') or []):
            _add_etapa(r.id, e, i + 1)
    db.session.commit()
    return jsonify(r.to_dict())

def _add_etapa(receita_id, e, ordem_default):
    db.session.add(ReceitaEtapa(
        receita_id=receita_id,
        ordem=safe_int(e.get('ordem'), ordem_default),
        titulo=(e.get('titulo') or '').strip() or f'Etapa {ordem_default}',
        tipo=e.get('tipo') or 'quimico',
        produto_quimico_id=e.get('produto_quimico_id') or None,
        quantidade=safe_float(e.get('quantidade')),
        unidade=(e.get('unidade') or '').strip(),
        temperatura_agua=safe_float(e.get('temperatura_agua')) if e.get('temperatura_agua') not in (None, '') else None,
        tempo_min=safe_int(e.get('tempo_min')),
        instrucao_texto=(e.get('instrucao_texto') or '').strip(),
    ))

@app.route('/api/receitas/<int:rid>', methods=['DELETE'])
def delete_receita(rid):
    r = Receita.query.get_or_404(rid)
    db.session.delete(r); db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/receitas/<int:rid>/duplicar', methods=['POST'])
def duplicar_receita(rid):
    """Cria uma nova versão da receita (usado quando uma amostra é reprovada e precisa de ajuste)."""
    original = Receita.query.get_or_404(rid)
    nova = Receita(
        nome=original.nome, referencia=original.referencia, lavacao=original.lavacao,
        versao=(original.versao or 1) + 1, receita_pai_id=original.id, status='rascunho',
        observacoes=original.observacoes, criado_por=original.criado_por,
    )
    db.session.add(nova); db.session.commit()
    for e in original.etapas:
        _add_etapa(nova.id, e.to_dict(), e.ordem)
    db.session.commit()
    return jsonify(nova.to_dict())

@app.route('/api/receitas/<int:rid>/executar', methods=['POST'])
def executar_receita(rid):
    """Dá baixa no estoque de químicos de todas as etapas da receita que usam produto cadastrado."""
    r = Receita.query.get_or_404(rid)
    etapas_com_produto = [e for e in r.etapas if e.produto_quimico_id and (e.quantidade or 0) > 0]
    # valida saldo de todos antes de aplicar qualquer baixa
    faltantes = []
    for e in etapas_com_produto:
        p = e.produto
        if not p or p.quantidade_atual < e.quantidade:
            faltantes.append(f'{e.produto.nome if e.produto else "produto removido"} (necessário {e.quantidade}, disponível {p.quantidade_atual if p else 0})')
    if faltantes:
        return jsonify({'error': 'Estoque insuficiente para: ' + '; '.join(faltantes)}), 400
    d = request.json or {}
    movimentacoes = []
    for e in etapas_com_produto:
        p = e.produto
        p.quantidade_atual = (p.quantidade_atual or 0.0) - e.quantidade
        mov = MovimentacaoEstoque(
            produto_id=p.id, tipo='saida', quantidade=e.quantidade,
            observacao=f'Baixa automática — Receita "{r.nome}" (etapa: {e.titulo})' + (f' — OP {d.get("op")}' if d.get('op') else ''),
            saldo_apos=p.quantidade_atual,
        )
        db.session.add(mov)
        movimentacoes.append(mov)
    db.session.commit()
    return jsonify({'ok': True, 'movimentacoes': [m.to_dict() for m in movimentacoes]})

# ── PEÇAS DE AMOSTRA ─────────────────────────────────────────────────
@app.route('/api/amostras', methods=['GET'])
def get_amostras():
    q = PecaAmostra.query
    status = request.args.get('status')
    if status:
        q = q.filter_by(status=status)
    rows = q.order_by(PecaAmostra.data_criacao.desc()).all()
    return jsonify([a.to_dict() for a in rows])

@app.route('/api/amostras/<int:aid>', methods=['GET'])
def get_amostra(aid):
    a = PecaAmostra.query.get_or_404(aid)
    return jsonify(a.to_dict())

@app.route('/api/amostras', methods=['POST'])
def add_amostra():
    d = request.json or {}
    if not d.get('referencia'):
        return jsonify({'error': 'Referência é obrigatória'}), 400
    a = PecaAmostra(
        referencia=d.get('referencia', '').strip(),
        lavacao=(d.get('lavacao') or '').strip(),
        receita_id=d.get('receita_id') or None,
        observacoes=(d.get('observacoes') or '').strip(),
        status='em_teste',
    )
    db.session.add(a); db.session.commit()
    return jsonify(a.to_dict())

@app.route('/api/amostras/<int:aid>', methods=['PUT'])
def update_amostra(aid):
    a = PecaAmostra.query.get_or_404(aid)
    d = request.json or {}
    if 'referencia' in d: a.referencia = (d['referencia'] or '').strip()
    if 'lavacao' in d: a.lavacao = (d['lavacao'] or '').strip()
    if 'receita_id' in d: a.receita_id = d['receita_id'] or None
    if 'observacoes' in d: a.observacoes = (d['observacoes'] or '').strip()
    db.session.commit()
    return jsonify(a.to_dict())

@app.route('/api/amostras/<int:aid>', methods=['DELETE'])
def delete_amostra(aid):
    a = PecaAmostra.query.get_or_404(aid)
    db.session.delete(a); db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/amostras/<int:aid>/aprovar', methods=['POST'])
def aprovar_amostra(aid):
    a = PecaAmostra.query.get_or_404(aid)
    d = request.json or {}
    ano = datetime.utcnow().year
    total_ano = PecaAmostra.query.filter(PecaAmostra.numero_lacre.like(f'LAC-{ano}-%')).count()
    a.numero_lacre = f'LAC-{ano}-{total_ano + 1:04d}'
    a.status = 'aprovada'
    a.aprovado_por = (d.get('aprovado_por') or '').strip()
    a.data_aprovacao = datetime.utcnow()
    if a.receita_id:
        rec = Receita.query.get(a.receita_id)
        if rec:
            rec.status = 'ativa'
    db.session.commit()
    return jsonify(a.to_dict())

@app.route('/api/amostras/<int:aid>/reprovar', methods=['POST'])
def reprovar_amostra(aid):
    a = PecaAmostra.query.get_or_404(aid)
    d = request.json or {}
    a.status = 'reprovada'
    if d.get('observacoes'):
        a.observacoes = (d.get('observacoes') or '').strip()
    db.session.commit()
    return jsonify(a.to_dict())

@app.route('/api/amostras/<int:aid>/nova_versao', methods=['POST'])
def nova_versao_amostra(aid):
    """Cria uma nova peça de amostra a partir de uma reprovada, para retestar o ajuste."""
    original = PecaAmostra.query.get_or_404(aid)
    d = request.json or {}
    nova_receita_id = d.get('receita_id', original.receita_id)
    nova = PecaAmostra(
        referencia=original.referencia, lavacao=original.lavacao,
        receita_id=nova_receita_id, versao_anterior_id=original.id,
        status='em_teste', observacoes=(d.get('observacoes') or '').strip(),
    )
    db.session.add(nova); db.session.commit()
    return jsonify(nova.to_dict())

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)

