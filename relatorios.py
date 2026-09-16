"""Consultas e exportações somente leitura da produção e das OPs."""
import csv
import io
from datetime import date
from decimal import Decimal
from flask import request, render_template, make_response, abort
from sqlalchemy.orm import selectinload
from operacao import agora_local

TIPOS = {'producao': 'Produção por máquina', 'ops': 'Acompanhamento de OPs',
         'custos': 'Custos por OP'}
ETAPAS = {'lavar': 'Lavagem', 'centrifuga': 'Centrifugação', 'secador': 'Secagem'}


def register_relatorios(app, db, Carga, Maquina, OP, gestao):
    @app.get('/relatorios')
    def relatorios():
        tipo = request.args.get('tipo', 'producao')
        if tipo not in TIPOS:
            abort(400, description='Relatório inválido.')
        hoje = agora_local().date()
        inicio = request.args.get('inicio', hoje.replace(day=1).isoformat())
        fim = request.args.get('fim', hoje.isoformat())
        try:
            di, df = date.fromisoformat(inicio), date.fromisoformat(fim)
            if di > df:
                raise ValueError()
        except ValueError:
            abort(400, description='Informe um período válido, com início anterior ou igual ao fim.')
        busca = request.args.get('busca', '').strip()
        maquina = request.args.get('maquina', '')
        sem_data = request.args.get('sem_data') == '1' and tipo == 'producao'
        maquinas = Maquina.query.order_by(Maquina.tipo, Maquina.numero).all()
        if maquina and maquina not in {str(m.id) for m in maquinas}:
            abort(400, description='Máquina inválida.')
        linhas, resumo = [], []
        def numero(v):
            return f'{v:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')
        def money(v):
            return 'Pendente' if v is None else 'R$ ' + numero(v)
        def data(v):
            return v.strftime('%d/%m/%Y %H:%M') if v else '—'
        def match(*values):
            return busca.casefold() in ' '.join(str(v or '') for v in values).casefold()
        if tipo == 'producao':
            colunas = ['Máquina', 'Carga', 'OP', 'Referência', 'Saída prevista',
                       'Conclusão real', 'Situação atual', 'Previsto no período (kg)',
                       'Realizado no período (kg)', 'Concluído sem data real (kg)',
                       'Peças concluídas', 'Base da seleção']
            nota = ('O período considera a saída prevista e/ou a conclusão real. Realizado usa o peso '
                    'registrado ao concluir no modo operador. Previsão e realização podem se referir '
                    'a cargas diferentes. Os kg são apresentados por etapa para evitar contar a mesma '
                    'produção como peças distintas. Conclusões antigas sem data real usam a saída '
                    'programada como referência e aparecem separadas dos apontamentos reais. '
                    'Peças realizadas usam a quantidade confirmada na conclusão. No legado sem data real, '
                    'usam a quantidade cadastrada na carga. Apontamentos antigos sem medição de peças '
                    'ficam pendentes. Não se trata de uma contagem de peças únicas; '
                    'relavagens podem repetir peças.')
            if sem_data:
                nota = ('CONFERÊNCIA SEM DATA REAL: mostra todas as cargas marcadas como concluídas '
                        'sem apontamento de conclusão, independentemente do período informado. '
                        'Os totais não comprovam a produção entre as datas selecionadas. '
                        'Peças são as quantidades cadastradas nas cargas; relavagens podem repetir peças.')
            totals = {t: [0, 0, 0, 0] for t in ETAPAS}
            pendentes_data = 0
            pendentes_pecas = 0
            query = Carga.query.options(selectinload(Carga.maquina), selectinload(Carga.apontamentos))
            if maquina:
                query = query.filter_by(maquina_id=int(maquina))
            for c in query.order_by(Carga.maquina_id, Carga.numero, Carga.id).all():
                m = c.maquina
                if not m or m.tipo not in ETAPAS or not match(c.op_manual, c.referencia):
                    continue
                prevista = c.data_saida
                conclusoes = [a for a in c.apontamentos if a.acao == 'concluir']
                antiga = c.status == 'concluido' and not conclusoes
                if antiga:
                    pendentes_data += 1
                no_periodo = [a for a in conclusoes if di <= a.data.date() <= df]
                prevista_no_periodo = bool(prevista and di <= prevista.date() <= df)
                if sem_data and not antiga:
                    continue
                if not sem_data and not prevista_no_periodo and not no_periodo:
                    continue
                previsto = (c.peso or 0) if prevista_no_periodo else 0
                real = sum(a.peso for a in no_periodo)
                legado = (c.peso or 0) if antiga and (prevista_no_periodo or sem_data) else 0
                sem_pecas = sum(1 for a in no_periodo if a.medicao is None)
                pendentes_pecas += sem_pecas
                pecas = sum(a.medicao.pecas for a in no_periodo if a.medicao)
                if antiga and (prevista_no_periodo or sem_data):
                    pecas += c.qtde_pecas or 0
                totals[m.tipo][0] += previsto
                totals[m.tipo][1] += real
                totals[m.tipo][2] += legado
                totals[m.tipo][3] += pecas
                status = {'aguardando': 'Aguardando', 'em_processo': 'Em processo', 'concluido': 'Concluído'}.get(c.status, c.status)
                if c.status == 'em_processo' and c.apontamentos and c.apontamentos[-1].acao == 'pausar':
                    status = 'Pausado'
                linhas.append([f'{ETAPAS[m.tipo]} {m.numero}', c.numero, c.op_manual or '',
                               c.referencia or '', data(prevista),
                               data(conclusoes[-1].data) if conclusoes else 'Sem apontamento',
                               status, numero(previsto), numero(real), numero(legado),
                               f'{pecas:,}'.replace(',', '.') + (' + pendente' if sem_pecas else ''),
                               'Sem data real — todos os períodos' if sem_data else
                               'Programação (sem data real)' if antiga else
                               'Conclusão real' if no_periodo else 'Previsão'])
            lavagem = totals['lavar']
            resumo = [('Total de quilos lavados' + (' — sem data real' if sem_data else ' — seleção'),
                       f'{numero(lavagem[1] + lavagem[2])} kg'),
                      ('Total de peças lavadas' + (' — sem data real' if sem_data else ' — seleção'),
                       f'{lavagem[3]:,}'.replace(',', '.'))]
            resumo += [(ETAPAS[t], f'Previsto: {numero(v[0])} kg · Realizado: {numero(v[1])} kg · '
                        f'Concluído sem data real: {numero(v[2])} kg · Peças concluídas: ' + f'{v[3]:,}'.replace(',', '.'))
                      for t, v in totals.items()]
            if pendentes_data:
                nota += (f' Há {pendentes_data} carga(s) concluída(s) sem data real nos filtros de máquina '
                         'e busca. Use “Concluídas sem data real — todos os períodos” para conferir todas.')
            if pendentes_pecas:
                nota += f' Há {pendentes_pecas} conclusão(ões) antiga(s) sem medição de peças; o total de peças é parcial.'
        else:
            nota = ('O período filtra o prazo de entrega da OP; OPs sem prazo não entram nesta seleção. '
                    'Inclui apenas OPs ativas. Situação, custos e faturamento são acumulados atuais '
                    'das OPs selecionadas, não movimentações financeiras do período.')
            colunas = (['OP', 'Referência', 'Cliente', 'Responsável', 'Prazo', 'Situação', 'Etapa atual', 'Peças']
                       if tipo == 'ops' else ['OP', 'Referência', 'Cliente', 'Prazo', 'Custo previsto',
                       'Realizado registrado', 'Lançamentos pendentes', 'Faturado', 'Margem disponível'])
            previstos, reais, pendentes = Decimal('0'), Decimal('0'), 0
            for op in gestao.query(OP, 'ops').order_by(OP.op, OP.id).all():
                ficha = db.session.get(gestao.models.FichaOP, op.id)
                if not ficha or not ficha.prazo or not di <= ficha.prazo <= df:
                    continue
                if not match(op.op, op.referencia, ficha.cliente, ficha.responsavel):
                    continue
                d = gestao.detail(op.id)
                prazo = ficha.prazo.strftime('%d/%m/%Y')
                if tipo == 'ops':
                    status = 'Concluída' if d['concluida'] else 'Atrasada' if d['atrasada'] else 'Em aberto'
                    etapa = next((e['nome'] for e in d['etapas'] if e['status'] != 'concluido'),
                                 'Concluída' if d['concluida'] else 'Sem roteiro')
                    linhas.append([op.op, op.referencia, d['cliente'], d['responsavel'], prazo,
                                   status, etapa, d['pecas']])
                else:
                    c = d['custos']
                    previstos += Decimal(str(c['total_previsto']))
                    reais += Decimal(str(c['total_real']))
                    pendentes += c['pendentes']
                    linhas.append([op.op, op.referencia, d['cliente'], prazo, money(c['total_previsto']),
                                   money(c['total_real']), c['pendentes'], money(c['receita_faturada']),
                                   money(c['margem_real'])])
            resumo = [('OPs selecionadas', str(len(linhas)))]
            if tipo == 'custos':
                nota += (' Realizado registrado é parcial quando há pendências. Sem custos lançados '
                         'ou faturamento, a margem fica pendente. Faturamento parcial gera margem parcial; '
                         'a margem considera apenas os custos lançados, não representa lucro líquido.')
                resumo += [('Custo previsto', money(previstos)), ('Realizado registrado', money(reais)),
                           ('Lançamentos pendentes', str(pendentes))]
        gerado = agora_local().strftime('%d/%m/%Y %H:%M')
        if request.args.get('formato') == 'csv':
            buf = io.StringIO(newline='')
            writer = csv.writer(buf, delimiter=';')
            def safe(value):
                text = str(value)
                return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')) else text
            writer.writerow(['Chrona Lavanderia', TIPOS[tipo]])
            writer.writerow(['Período', 'Todos — sem data real' if sem_data else di.strftime('%d/%m/%Y'),
                             '' if sem_data else df.strftime('%d/%m/%Y'), 'Gerado em', gerado])
            writer.writerow(['Busca', safe(busca), 'Máquina', maquina or 'Todas'])
            writer.writerow([nota])
            writer.writerows(resumo)
            writer.writerow([])
            writer.writerow(colunas)
            writer.writerows([[safe(v) for v in row] for row in linhas])
            response = make_response('\ufeff' + buf.getvalue())
            response.headers['Content-Type'] = 'text/csv; charset=utf-8'
            response.headers['Content-Disposition'] = f'attachment; filename="chrona-{tipo}-{inicio}-{fim}.csv"'
        else:
            response = make_response(render_template('relatorios.html', tipos=TIPOS, tipo=tipo,
                inicio=inicio, fim=fim, busca=busca, maquina=maquina, maquinas=maquinas,
                etapas=ETAPAS, colunas=colunas, linhas=linhas, resumo=resumo, nota=nota, sem_data=sem_data,
                gerado=gerado, periodo='Todos — conclusões sem data real' if sem_data else f'{di:%d/%m/%Y} a {df:%d/%m/%Y}'))
        response.headers['Cache-Control'] = 'no-store'
        return response
