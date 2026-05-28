/**
 * LaundryPro – Patch de Modificações
 * ════════════════════════════════════
 * Adicione ao final do seu HTML, antes de </body>:
 *   <script src="patch.js"></script>
 *
 * Alterações implementadas:
 *  1. Botão "Copiar OP" na lista de Ordens de Produção
 *  2. Impressão: exibe apenas cargas "Em Processo"
 *  3. Impressão: substitui Anotações por linhas de Entrada / Saída
 */

// ═══════════════════════════════════════════════════════
//  PATCH 1 + NOVO: renderOps() com botão Copiar
// ═══════════════════════════════════════════════════════
const _renderOps_original = window.renderOps;
window.renderOps = function renderOps() {
  const ops = DB.ops();
  if (!ops.length) {
    document.getElementById('ops-tbody').innerHTML = `
      <tr><td colspan="8" style="text-align:center;padding:32px;color:var(--muted)">
        <i class="fas fa-folder-open" style="font-size:24px;display:block;margin-bottom:8px"></i>
        Nenhuma OP cadastrada. Clique em "Nova OP" para começar.
      </td></tr>`;
    return;
  }
  document.getElementById('ops-tbody').innerHTML = ops.map(op => {
    const { pecas, peso } = calcTotaisOP(op);
    const dt = new Date(op.created || op.updated).toLocaleString('pt-BR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });
    return `<tr>
      <td class="mono" style="color:var(--ice);font-weight:600">${op.op}</td>
      <td><b>${op.ref}</b></td>
      <td style="color:var(--muted)">${op.lav || '--'}</td>
      <td class="mono">${op.cap || '--'}</td>
      <td class="mono">${pecas.toLocaleString('pt-BR')}</td>
      <td class="mono" style="color:var(--ice)">${numBR(peso, 3)} kg</td>
      <td style="color:var(--muted);font-size:11px">${dt}</td>
      <td><div style="display:flex;gap:5px;flex-wrap:wrap;align-items:center">
        <button class="btn btn-g btn-xs" onclick='editarOP("${op.id}")' title="Editar">
          <i class="fas fa-edit"></i>
        </button>
        <button class="btn btn-xs"
          style="background:linear-gradient(135deg,#7c3aed,#8b5cf6);color:#fff;padding:3px 9px;border-radius:6px;font-size:11px;font-weight:700;border:none;cursor:pointer;display:inline-flex;align-items:center;gap:4px"
          onclick='copiarOP("${op.id}")' title="Copiar OP – duplica todos os dados, deixa nº OP editável">
          <i class="fas fa-copy"></i> Copiar
        </button>
        <button class="btn btn-d btn-xs" onclick='excluirOP("${op.id}")' title="Excluir">
          <i class="fas fa-trash"></i>
        </button>
      </div></td>
    </tr>`;
  }).join('');
};

// ═══════════════════════════════════════════════════════
//  PATCH 2: função copiarOP() — duplica OP com campo
//           número em branco e destacado para reedição
// ═══════════════════════════════════════════════════════
window.copiarOP = function copiarOP(id) {
  const op = DB.ops().find(o => o.id === id);
  if (!op) return;

  // Limpa ID → ao salvar, cria nova OP (não sobrescreve a original)
  document.getElementById('op-id').value = '';
  document.getElementById('op-panel-title').textContent =
    `📋 Cópia de: OP ${op.op} · ${op.ref || ''} — Digite o NOVO número de OP`;

  // Campo OP em branco — todos os outros dados preenchidos
  document.getElementById('f-op').value  = '';
  document.getElementById('f-ref').value = op.ref || '';
  document.getElementById('f-lav').value = op.lav || '';
  document.getElementById('f-cap').value = op.cap || '';
  document.getElementById('f-cap-arr').value = '';
  document.getElementById('arr-result').style.display = 'none';

  // Preenche tamanhos (quantidades e pesos)
  buildAllSzGrids();
  fillSzGrids(op);
  liveCalc();

  openOv('ov-op');

  // Destaca o campo OP com borda âmbar pulsante por 6 segundos
  setTimeout(() => {
    const opField = document.getElementById('f-op');
    opField.focus();
    opField.style.borderColor     = '#f59e0b';
    opField.style.boxShadow       = '0 0 0 4px rgba(245,158,11,0.4)';
    opField.style.backgroundColor = 'rgba(245,158,11,0.09)';
    opField.placeholder = '⚠ Digite o NOVO número de OP aqui';
    setTimeout(() => {
      opField.style.borderColor     = '';
      opField.style.boxShadow       = '';
      opField.style.backgroundColor = '';
      opField.placeholder = 'Ex: 48000';
    }, 6000);
  }, 220);

  toast(`📋 OP ${op.op} copiada — informe o novo número de OP!`, 'in');
};

// ═══════════════════════════════════════════════════════
//  PATCH 3: imprimirMaquina() — somente "Em Processo"
//           + Entrada/Saída no lugar de Anotações
// ═══════════════════════════════════════════════════════
window.imprimirMaquina = function imprimirMaquina() {
  const info   = MAQ_INFO[_maqTipo];
  const m      = getMaqAtual();
  const cargas = m.cargas || [];
  const blocos = m.opBlocos || [];
  const reais  = cargas.filter(c => c.tipo !== 'intervalo');

  // ── Filtra somente "Em Processo" para exibir/imprimir ──
  const emProcesso = reais.filter(c => c.status === 'pr');

  const totalPecas = reais.reduce((a, c) => a + fNum(c.pecas), 0);
  const totalPeso  = reais.reduce((a, c) => a + fFlt(c.peso), 0);
  const conc  = reais.filter(c => c.status === 'ok').length;
  const proc  = reais.filter(c => c.status === 'pr').length;
  const ag    = reais.filter(c => c.status === 'ag').length;
  const now   = new Date().toLocaleString('pt-BR');

  const coresBlocos = {};
  const CORES_BLOCO = ['#1a6fd4','#7c3aed','#e86020','#059669','#c0392b','#0891b2','#7c2d12','#4338ca'];
  blocos.forEach((b, i) => { coresBlocos[b.id] = CORES_BLOCO[i % CORES_BLOCO.length]; });

  // ── CABEÇALHO ──────────────────────────────────────────
  const headerHtml = `
  <div class="print-header">
    <div class="print-header-left">
      <div class="print-logo">🧺 LaundryPro</div>
      <div class="print-subtitle">Sistema de Lavanderia — Programação de Máquina</div>
      <div class="print-maq-name">${info.ico} ${info.sigla} ${String(_maqNum).padStart(2,'0')}</div>
    </div>
    <div class="print-header-right">
      <div>Emitido em: <b>${now}</b></div>
      <div>Capacidade: <b>${numBR(m.cap || info.capDef, 1)} kg/carga</b></div>
      <div>Tempo/carga: <b>${m.tempo || info.tempoDef} min</b></div>
      ${m.dataInicio && m.horaInicio
        ? `<div>Início: <b>${fmtDT(new Date(m.dataInicio + 'T' + m.horaInicio))}</b></div>` : ''}
    </div>
  </div>`;

  // ── KPIs ───────────────────────────────────────────────
  const kpiHtml = `
  <div class="print-summary">
    <div class="print-kpi"><div class="print-kpi-val">${blocos.length}</div><div class="print-kpi-lbl">OPs</div></div>
    <div class="print-kpi"><div class="print-kpi-val">${reais.length}</div><div class="print-kpi-lbl">Total Cargas</div></div>
    <div class="print-kpi"><div class="print-kpi-val" style="color:#d97706;font-size:20px">${proc}</div><div class="print-kpi-lbl">🔄 Em Processo</div></div>
    <div class="print-kpi"><div class="print-kpi-val">${totalPecas.toLocaleString('pt-BR')}</div><div class="print-kpi-lbl">Total Peças</div></div>
    <div class="print-kpi"><div class="print-kpi-val">${numBR(totalPeso, 1)}</div><div class="print-kpi-lbl">Peso Total (kg)</div></div>
    <div class="print-kpi"><div class="print-kpi-val" style="color:#059669">${conc}</div><div class="print-kpi-lbl">✅ Concluídas</div></div>
  </div>
  <div style="background:#fff7ed;border:1.5px solid #d97706;border-radius:5px;padding:4px 12px;
    margin-bottom:8px;font-size:9px;font-weight:700;color:#b45309;text-align:center">
    ★ Exibindo apenas cargas EM PROCESSO — ${proc} carga${proc !== 1 ? 's' : ''}
  </div>`;

  // ── RESUMO DAS OPs ─────────────────────────────────────
  let opsSummaryHtml = '';
  if (blocos.length) {
    opsSummaryHtml = `<div style="margin-bottom:8px">
      <div style="font-size:9px;font-weight:700;color:#0d47a1;text-transform:uppercase;
        letter-spacing:1px;margin-bottom:5px;border-bottom:1px solid #0d47a1;padding-bottom:3px">
        OPs Programadas
      </div>`;
    blocos.forEach((b, i) => {
      const cor = CORES_BLOCO[i % CORES_BLOCO.length];
      const cb  = cargas.filter(c => c.blocoId === b.id && c.tipo !== 'intervalo');
      const pb  = cb.reduce((a, c) => a + fFlt(c.peso), 0);
      const pcb = cb.reduce((a, c) => a + fNum(c.pecas), 0);
      opsSummaryHtml += `<div class="print-op-section">
        <span class="print-op-badge" style="background:${cor}">${i + 1}</span>
        <div class="print-op-detail">
          <b>OP ${b.op || '—'}</b> ${b.ref ? `· ${b.ref}` : ''} ${b.lav ? `· <i>${b.lav}</i>` : ''}
          <span style="color:#888;margin-left:4px">(${cb.length} cargas · ${pcb.toLocaleString('pt-BR')} pç · ${numBR(pb, 1)} kg)</span>
        </div>
      </div>`;
    });
    opsSummaryHtml += '</div>';
  }

  // ── TABELA DE CARGAS (somente Em Processo) ─────────────
  let rowsHtml = '';
  if (!emProcesso.length) {
    rowsHtml = `<tr><td colspan="9" style="text-align:center;padding:20px;color:#666;font-style:italic">
      Nenhuma carga com status "Em Processo" encontrada nesta máquina.
    </td></tr>`;
  } else {
    emProcesso.forEach((c, i) => {
      const cor    = c.blocoId && coresBlocos[c.blocoId] ? coresBlocos[c.blocoId] : '#1a6fd4';
      const stLabel = { ag: '⏳ Aguard.', pr: '🔄 Em Proc.', ok: '✅ Conc.' }[c.status || 'ag'] || '—';
      rowsHtml += `<tr>
        <td class="print-td-num" style="border-left:3px solid ${cor}">${c.num || i + 1}</td>
        <td class="print-td-op">${c.op || '—'}</td>
        <td>${c.ref || '—'}</td>
        <td style="font-size:9px;color:#444">${c.lav || '—'}</td>
        <td style="text-align:right">${fNum(c.pecas).toLocaleString('pt-BR')}</td>
        <td style="text-align:right">${numBR(fFlt(c.peso), 3)}</td>
        <td style="font-size:9px">${fmtDT(c.inicio)}</td>
        <td style="font-size:9px;color:#b45309">${fmtDT(c.saida)}</td>
        <td class="print-td-st pr">🔄 Em Proc.</td>
      </tr>`;
    });
  }

  const tableHtml = `
  <table class="print-table">
    <thead><tr>
      <th style="width:28px">#</th>
      <th>OP</th><th>Referência</th><th>Lavação</th>
      <th style="text-align:right">Peças</th>
      <th style="text-align:right">Peso (kg)</th>
      <th>Início</th><th>Saída</th><th>Status</th>
    </tr></thead>
    <tbody>${rowsHtml}</tbody>
  </table>`;

  // ── ENTRADA / SAÍDA (substituiu Anotações) ─────────────
  const entradaSaidaHtml = `
  <div class="print-notes-area" style="min-height:auto;padding-bottom:8px">
    <div class="print-notes-title">📋 Controle de Entrada / Saída</div>
    ${opsSummaryHtml}
    <table style="width:100%;border-collapse:collapse;margin-top:8px">
      <thead><tr>
        <th style="background:#0d47a1;color:#fff;padding:5px 8px;font-size:8.5px;
          text-align:left;text-transform:uppercase;letter-spacing:.5px;border:1px solid #0d47a1">
          Carga
        </th>
        <th style="background:#0d47a1;color:#fff;padding:5px 8px;font-size:8.5px;
          text-align:left;text-transform:uppercase;letter-spacing:.5px;border:1px solid #0d47a1;width:43%">
          Entrada
        </th>
        <th style="background:#0d47a1;color:#fff;padding:5px 8px;font-size:8.5px;
          text-align:left;text-transform:uppercase;letter-spacing:.5px;border:1px solid #0d47a1;width:43%">
          Saída
        </th>
      </tr></thead>
      <tbody>
        ${emProcesso.map((c, i) => `
        <tr>
          <td style="border:1px solid #ccc;padding:5px 8px;font-size:9px;font-weight:700;
            color:#0d47a1;white-space:nowrap;vertical-align:middle">
            #${c.num || i + 1} · OP ${c.op || '—'}
          </td>
          <td style="border:1px solid #ccc;padding:5px 8px;height:28px;vertical-align:bottom">
            <span style="display:block;border-bottom:1px solid #aaa;width:100%;height:16px"></span>
          </td>
          <td style="border:1px solid #ccc;padding:5px 8px;height:28px;vertical-align:bottom">
            <span style="display:block;border-bottom:1px solid #aaa;width:100%;height:16px"></span>
          </td>
        </tr>`).join('')}
        ${emProcesso.length === 0 ? `
        <tr>
          <td colspan="3" style="border:1px solid #ccc;padding:10px;text-align:center;
            color:#666;font-style:italic;font-size:9px">
            Sem cargas Em Processo para registrar
          </td>
        </tr>` : ''}
      </tbody>
    </table>
  </div>`;

  // ── RODAPÉ ─────────────────────────────────────────────
  const footerHtml = `
  <div class="print-footer">
    <span>LaundryPro – Sistema de Lavanderia</span>
    <span>${info.sigla} ${String(_maqNum).padStart(2,'0')} &nbsp;|&nbsp; ${proc} em processo de ${reais.length} total &nbsp;|&nbsp; ${numBR(totalPeso, 1)} kg</span>
    <span>Impresso: ${now}</span>
  </div>`;

  // ── MONTA E IMPRIME ─────────────────────────────────────
  document.getElementById('print-area').innerHTML = `
    ${headerHtml}
    ${kpiHtml}
    <div class="print-body">
      <div class="print-table-wrap">${tableHtml}</div>
      ${entradaSaidaHtml}
    </div>
    ${footerHtml}`;

  window.print();
};

console.log('✅ LaundryPro patch carregado: Copiar OP + Impressão Em Processo + Entrada/Saída');
