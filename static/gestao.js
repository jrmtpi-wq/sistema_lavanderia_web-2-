/* Gestão da OP e cadastros preservados. Valores do usuário são escapados. */
const ge = opEscape;
const gStages = {lavar:'Lavagem',centrifuga:'Centrifugação',secador:'Secagem',laser:'Laser',passadoria:'Passadoria',robo:'Robô de passadoria',qualidade:'Qualidade',expedicao:'Expedição'};
const gCategories = {quimicos:'Químicos',mao_obra:'Mão de obra',agua:'Água',energia:'Energia',outros:'Outros'};
const gTypes = {ops:'Ordens de produção',funcionarios:'Funcionários',quimicos:'Químicos',receitas:'Receitas',amostras:'Amostras',manutencoes:'Planos de manutenção',os:'Ordens de serviço',faturamento:'Faturamento',precos:'Preços'};
const gMoney = n => n == null ? 'A apurar' : Number(n).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
let gFicha=null, gList=[], gRequest=0, gBusy=false;
const gValue=id=>document.getElementById(id).value.trim();
const gField=(label,id,value='',type='text',extra='')=>`<label class="gestao-field">${ge(label)}<input id="${id}" type="${type}" value="${ge(value??'')}" ${extra}></label>`;
const gOptions=(map,selected)=>Object.entries(map).map(([k,v])=>`<option value="${ge(k)}" ${k===selected?'selected':''}>${ge(v)}</option>`).join('');
const gDate=v=>v?ge(fmtDT(v)):'Sem apontamento';
function gHistoryDetail(value){
  const labels={antes:'Antes',depois:'Depois',cliente:'Cliente',responsavel:'Responsável',prazo:'Prazo',receita_prevista:'Receita prevista',custo:'Custo',motivo:'Motivo',categoria:'Categoria',descricao:'Descrição',unidade:'Unidade',quantidade_prevista:'Quantidade prevista',unitario_previsto:'Valor unitário previsto',quantidade_real:'Quantidade realizada',unitario_real:'Valor unitário realizado',previsto:'Total previsto',real:'Total realizado',origem:'Origem'};
  const render=data=>Object.entries(data).filter(([k])=>k!=='id').map(([k,v])=>`<div><b>${ge(labels[k]||k)}:</b> ${v&&typeof v==='object'?render(v):ge(v==null||v==='None'?'Não informado':gCategories[v]||v)}</div>`).join('');
  try{const parsed=JSON.parse(value);return parsed&&typeof parsed==='object'?render(parsed):ge(value);}catch{return ge(value);}
}
function gArchivedRecord(r){
  if(!r.etapas)return '';
  return `<h3>OP ${ge(r.op)} · ${ge(r.referencia)}</h3><p>${r.pecas} peças · ${ge(r.cliente||'Cliente não informado')}</p><h3>Roteiro preservado</h3>${r.etapas.map(e=>`<p>${ge(e.nome)} · ${ge(opStatus[e.status]||e.status)}</p>`).join('')}<h3>Custos preservados</h3><p>Previsto: ${gMoney(r.custos.total_previsto)} · Realizado registrado: ${gMoney(r.custos.total_real)}</p>${r.custos.linhas.map(c=>`<p>${ge(c.descricao)} · previsto ${gMoney(c.previsto)} · realizado ${gMoney(c.real)}</p>`).join('')}`;
}
function gFeedback(message){document.getElementById('gestao-feedback').textContent=message;}
async function gFetch(url,method='GET',body){
  const response=await fetch(url,{method,headers:{'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
  let data;try{data=await response.json();}catch{throw new Error('Não foi possível ler a resposta. Atualize e tente novamente.');}
  if(!response.ok)throw new Error(data.error||`Falha ao salvar (${response.status}).`);
  return data;
}
function gActor(){return document.getElementById('gestao-actor').value.trim();}
async function gMutate(path,method,body){
  if(gBusy)return;
  if(!gActor()){gFeedback('Informe seu nome em Responsável pelo registro.');document.getElementById('gestao-actor').focus();return;}
  gBusy=true;document.querySelectorAll('#gestao-detail button').forEach(b=>b.disabled=true);
  try{
    gFicha=await gFetch(`/api/gestao/ops/${gFicha.id}${path}`,method,{...body,operador:gActor(),revisao:gFicha.revisao});
    gRenderFicha();gFeedback('Registro salvo.');
  }catch(e){gFeedback(e.message);}
  finally{gBusy=false;document.querySelectorAll('#gestao-detail button').forEach(b=>b.disabled=false);}
}
async function gLoad(){
  const seq=++gRequest;gFicha=null;document.getElementById('gestao-detail').innerHTML='';gFeedback('Carregando OPs…');
  try{const rows=await gFetch('/api/gestao/ops');if(seq!==gRequest)return;gList=rows;gRenderList();gFeedback('');}catch(e){if(seq===gRequest)gFeedback(e.message);}
}
function gRenderList(){
  const search=gValue('gestao-search').toLocaleLowerCase('pt-BR'), status=gValue('gestao-filter');
  const rows=gList.filter(o=>`${o.op} ${o.referencia} ${o.cliente} ${o.responsavel}`.toLocaleLowerCase('pt-BR').includes(search)&&(!status||(status==='atrasadas'?o.atrasada:status==='concluidas'?o.concluida:!o.concluida)));
  const target=document.getElementById('gestao-list');
  target.innerHTML=rows.length?`<div class="gestao-grid">${rows.map(o=>`<article class="gestao-card"><h3>OP ${ge(o.op)} · ${ge(o.referencia)}</h3><p>${ge(o.cliente||'Cliente não informado')}</p><p>${ge(o.etapa_atual)} · ${o.etapas_concluidas}/${o.total_etapas} etapas</p><p class="${o.atrasada?'gestao-warning':'gestao-note'}">Prazo: ${ge(o.prazo||'não informado')}${o.atrasada?' · Atrasada':''}</p><button class="btn btn-primary" data-ficha="${o.id}">Abrir ficha da OP</button></article>`).join('')}</div>`:'<p class="gestao-note">Nenhuma OP nesta seleção. Cadastre uma em Ordens de Produção.</p>';
  target.querySelectorAll('[data-ficha]').forEach(b=>b.onclick=()=>gOpen(Number(b.dataset.ficha)));
}
async function gOpen(id){
  const seq=++gRequest;gFeedback('Carregando ficha…');
  try{const data=await gFetch('/api/gestao/ops/'+id);if(seq!==gRequest)return;gFicha=data;document.getElementById('gestao-list').innerHTML='';gRenderFicha();gFeedback('');}catch(e){if(seq===gRequest)gFeedback(e.message);}
}
function gRenderFicha(){
  const o=gFicha,c=o.custos;
  document.getElementById('gestao-detail').innerHTML=`
    <div class="gestao-actions"><button class="btn btn-ghost" id="g-back">Voltar às OPs</button><button class="btn btn-ghost" id="g-reload">Reabrir ficha</button></div>
    <h2>OP ${ge(o.op)} · ${ge(o.referencia)}</h2><p class="gestao-note">${o.pecas} peças · ${Number(o.peso).toLocaleString('pt-BR')} kg · ${ge(o.lavacao||'Lavação não informada')}</p>
    ${o.vinculo_ambiguo?'<p class="gestao-warning">Existe outra OP com o mesmo número e referência. Apenas cargas e faturamentos vinculados pelo cadastro são considerados; confira os lançamentos antigos.</p>':''}
    <form id="g-ficha-form" class="gestao-card"><h3>Dados de acompanhamento</h3><div class="gestao-grid">${gField('Cliente','g-client',o.cliente,'text','maxlength="120"')}${gField('Responsável pela OP','g-owner',o.responsavel,'text','maxlength="80"')}${gField('Prazo','g-deadline',o.prazo,'date')}${gField('Receita prevista total (R$)','g-revenue',o.receita_prevista_informada,'number','min="0" max="1000000000" step="0.0001"')}</div><button class="btn btn-primary">Salvar dados da OP</button></form>
    <section class="gestao-card"><h3>Roteiro de produção</h3><p class="gestao-note">Cargas e filas vinculadas atualizam as etapas correspondentes. Etapas sem programação vinculada podem ser iniciadas e concluídas aqui, na sequência do roteiro.</p>
    <ol class="gestao-route">${o.etapas.map(e=>`<li><b>${e.ordem}. ${ge(e.nome)}</b> · ${ge(opStatus[e.status]||e.status)}<p>Responsável: ${ge(e.responsavel||'não informado')}</p><p class="gestao-note">Início: ${gDate(e.inicio_real)} · Conclusão: ${gDate(e.fim_real)}${e.espera_min!=null?` · Espera: ${e.espera_min} min`:''}</p>${e.automatico?'<p class="gestao-note">Andamento recebido da programação vinculada.</p>':e.status!=='concluido'?`<button class="btn btn-primary" data-step="${e.id}" data-action="${e.status==='aguardando'?'iniciar':'concluir'}">${e.status==='aguardando'?'Iniciar':'Concluir'} ${ge(e.nome)}</button>`:''}</li>`).join('')||'<li>Roteiro ainda não definido.</li>'}</ol>
    <details><summary>Configurar roteiro e responsáveis</summary><p class="gestao-note">Depois do início, somente os responsáveis podem ser alterados.</p><div id="g-route-editor"></div><div class="gestao-actions"><button class="btn btn-ghost" id="g-add-step">Adicionar etapa</button><button class="btn btn-primary" id="g-save-route">Salvar roteiro</button></div></details></section>
    <section class="gestao-card"><h3>Custos e margem da OP</h3><div class="gestao-grid">${[['Receita prevista',c.receita_prevista],['Custo previsto',c.total_previsto],['Margem prevista',c.margem_prevista],['Receita faturada',c.receita_faturada],['Custo realizado registrado',c.total_real],['Margem sobre o faturamento',c.margem_real]].map(([label,n])=>`<div><p>${label}</p><strong>${gMoney(n)}</strong></div>`).join('')}</div>
    <p class="gestao-note">${c.pendentes} custos aguardam valores realizados. A margem sobre o faturamento aparece quando há custos, todos realizados, e faturamento registrado; faturamentos parciais produzem margem parcial. ${c.margem_pct==null?'':`Margem: ${c.margem_pct}%.`} Receita prevista: ${ge(c.origem_receita_prevista)}.</p>
    <div class="gestao-table"><table><thead><tr><th>Categoria</th><th>Previsto</th><th>Realizado registrado</th></tr></thead><tbody>${Object.entries(c.categorias).map(([k,v])=>`<tr><td>${gCategories[k]}</td><td>${gMoney(v.previsto)}</td><td>${gMoney(v.real)}</td></tr>`).join('')}</tbody></table></div>
    <div class="gestao-actions"><button class="btn btn-primary" id="g-add-cost">Adicionar custo</button><button class="btn btn-ghost" id="g-import">Importar químicos de receita</button></div>
    <div class="gestao-grid">${c.linhas.map(l=>`<article class="gestao-card"><h3>${ge(l.descricao)}</h3><p>${gCategories[l.categoria]} · ${ge(l.unidade)}</p><p>Previsto: ${l.quantidade_prevista} × ${gMoney(l.unitario_previsto)} = ${gMoney(l.previsto)}</p><p>Realizado: ${gMoney(l.real)}</p><p class="gestao-note">${ge(l.origem)}</p><div class="gestao-actions"><button class="btn btn-ghost" data-cost="${l.id}">Apontar realizado</button><button class="btn btn-ghost" data-cancel="${l.id}">Cancelar custo</button></div></article>`).join('')||'<p class="gestao-note">Nenhum custo lançado.</p>'}</div></section>
    <section class="gestao-card"><h3>Produção vinculada</h3>${o.producao.map(p=>`<p><b>${ge(p.nome)}</b> · ${ge(opStatus[p.status]||p.status)} · previsão: ${gDate(p.previsto)}</p>`).join('')||'<p>Nenhuma carga ou fila vinculada.</p>'}</section>
    <section class="gestao-card"><h3>Histórico de alterações</h3><ol class="gestao-history">${o.historico.map(h=>`<li><b>${ge(h.acao)}</b> · ${ge(h.operador)} · ${gDate(h.data)}<details><summary>Detalhes</summary><p>${gHistoryDetail(h.detalhe)}</p></details></li>`).join('')||'<li>Nenhuma alteração registrada.</li>'}</ol></section>`;
  document.getElementById('g-back').onclick=gLoad;document.getElementById('g-reload').onclick=()=>gOpen(o.id);
  document.getElementById('g-ficha-form').onsubmit=e=>{e.preventDefault();gMutate('','PUT',{cliente:gValue('g-client'),responsavel:gValue('g-owner'),prazo:gValue('g-deadline'),receita_prevista:gValue('g-revenue')});};
  document.querySelectorAll('[data-step]').forEach(b=>b.onclick=()=>gMutate(`/etapas/${b.dataset.step}/apontar`,'POST',{acao:b.dataset.action}));
  o.etapas.forEach(e=>gRouteRow(e.tipo,e.responsavel));
  document.getElementById('g-add-step').onclick=()=>gRouteRow();
  document.getElementById('g-save-route').onclick=()=>gMutate('/roteiro','POST',{etapas:[...document.querySelectorAll('.g-route-row')].map(r=>({tipo:r.querySelector('select').value,responsavel:r.querySelector('input').value.trim()}))});
  document.getElementById('g-add-cost').onclick=()=>gCostDialog();document.getElementById('g-import').onclick=gImportDialog;
  document.querySelectorAll('[data-cost]').forEach(b=>b.onclick=()=>gCostDialog(c.linhas.find(l=>l.id===Number(b.dataset.cost))));
  document.querySelectorAll('[data-cancel]').forEach(b=>b.onclick=()=>gDialog('Cancelar custo',gField('Motivo','gd-reason','','text','required maxlength="200"'),async()=>{await gDialogMutation(`/custos/${b.dataset.cancel}/cancelar`,'POST',{motivo:gValue('gd-reason')});}));
}
function gRouteRow(tipo,responsavel=''){
  const editor=document.getElementById('g-route-editor');if(editor.children.length>=8)return;
  if(!tipo){const used=[...editor.querySelectorAll('select')].map(s=>s.value);tipo=Object.keys(gStages).find(k=>!used.includes(k));}
  const row=document.createElement('div');row.className='g-route-row gestao-actions';
  row.innerHTML=`<label class="gestao-field">Etapa<select>${gOptions(gStages,tipo)}</select></label><label class="gestao-field">Responsável<input maxlength="80" value="${ge(responsavel)}"></label><button class="btn btn-ghost" type="button" aria-label="Mover etapa para cima">↑</button><button class="btn btn-ghost" type="button">Retirar etapa</button>`;
  row.querySelectorAll('button')[0].onclick=()=>{if(row.previousElementSibling)editor.insertBefore(row,row.previousElementSibling);};row.querySelectorAll('button')[1].onclick=()=>row.remove();editor.append(row);
}
function gDialog(title,fields,save){
  const d=document.getElementById('gestao-dialog');
  d.innerHTML=`<form><h2>${ge(title)}</h2>${fields}<p id="gd-error" role="alert"></p><div class="gestao-actions"><button class="btn btn-primary" type="submit">Confirmar</button><button class="btn btn-ghost" type="button" id="gd-close">Fechar</button></div></form>`;
  d.querySelector('#gd-close').onclick=()=>d.close();
  d.querySelector('form').onsubmit=async e=>{e.preventDefault();const buttons=d.querySelectorAll('button');buttons.forEach(b=>b.disabled=true);try{await save();d.close();}catch(err){d.querySelector('#gd-error').textContent=err.message;}finally{buttons.forEach(b=>b.disabled=false);}};
  d.showModal();
}
async function gDialogMutation(path,method,body){
  if(!gActor())throw new Error('Feche esta janela e informe seu nome em Responsável pelo registro.');
  gFicha=await gFetch(`/api/gestao/ops/${gFicha.id}${path}`,method,{...body,operador:gActor(),revisao:gFicha.revisao});gRenderFicha();gFeedback('Registro salvo.');
}
async function gCostDialog(line){
  try{
    if(line){
      gDialog('Apontar custo realizado',`<p>${ge(line.descricao)} · unidade: ${ge(line.unidade)}</p>${gField('Quantidade realizada','gd-qty',line.quantidade_real??'','number','required min="0" max="1000000000" step="0.0001"')}${gField('Custo unitário realizado (R$)','gd-price',line.unitario_real??'','number','required min="0" max="1000000000" step="0.0001"')}`,()=>gDialogMutation(`/custos/${line.id}`,'PUT',{quantidade_real:gValue('gd-qty'),unitario_real:gValue('gd-price')}));return;
    }
    const staff=await gFetch('/api/funcionarios?ativos=1');
    gDialog('Adicionar custo previsto',`<label class="gestao-field">Categoria<select id="gd-cat">${gOptions(gCategories,'quimicos')}</select></label>${gField('Descrição','gd-desc','','text','required maxlength="160"')}${gField('Unidade (kg, min, kWh, m³…)','gd-unit','kg','text','required maxlength="20"')}${gField('Quantidade prevista','gd-qty','','number','required min="0" max="1000000000" step="0.0001"')}${gField('Custo unitário previsto (R$)','gd-price','','number','required min="0" max="1000000000" step="0.0001"')}<label class="gestao-field">Funcionário para usar CPM (mão de obra)<select id="gd-staff"><option value="">Custo manual</option>${staff.map(f=>`<option value="${f.id}">${ge(f.nome)} · ${gMoney(f.cpm)}/min</option>`).join('')}</select></label><p class="gestao-note">Ao selecionar mão de obra e funcionário, a quantidade será em minutos e o valor unitário será o CPM cadastrado.</p>`,()=>gDialogMutation('/custos','POST',{categoria:gValue('gd-cat'),descricao:gValue('gd-desc'),unidade:gValue('gd-unit'),quantidade_prevista:gValue('gd-qty'),unitario_previsto:gValue('gd-price'),funcionario_id:gValue('gd-staff')?Number(gValue('gd-staff')):null}));
    const sync=()=>{const automatic=gValue('gd-cat')==='mao_obra'&&gValue('gd-staff');const price=document.getElementById('gd-price');price.readOnly=!!automatic;if(automatic){price.value=staff.find(f=>f.id===Number(gValue('gd-staff'))).cpm;document.getElementById('gd-unit').value='min';}};
    document.getElementById('gd-staff').onchange=sync;document.getElementById('gd-cat').onchange=sync;
  }catch(e){gFeedback(e.message);}
}
async function gImportDialog(){
  try{const recipes=await gFetch('/api/receitas');gDialog('Importar químicos da receita',`<label class="gestao-field">Receita<select required id="gd-recipe"><option value="">Selecione</option>${recipes.map(r=>`<option value="${r.id}">${ge(r.nome)} · v${ge(r.versao)}</option>`).join('')}</select></label>${gField('Quantidade de execuções da receita','gd-repeat',1,'number','required min="0.0001" max="1000000000" step="0.0001"')}<p class="gestao-note">Gera custos previstos com os preços atuais. Não movimenta estoque. A receita só pode ser importada uma vez por OP.</p>`,()=>gDialogMutation('/custos/receita','POST',{receita_id:Number(gValue('gd-recipe')),repeticoes:gValue('gd-repeat')}));}catch(e){gFeedback(e.message);}
}
function gArchive(tipo,id,refresh){
  gDialog('Arquivar cadastro',`<p>O cadastro sairá das listas de uso. Seu histórico será preservado e poderá ser consultado ou restaurado em Arquivados.</p>${gField('Responsável pelo registro','gd-actor',gActor(),'text','required maxlength="80"')}${gField('Motivo','gd-reason','','text','required maxlength="200"')}`,async()=>{await gFetch(`/api/gestao/cadastros/${tipo}/${id}/arquivar`,'POST',{operador:gValue('gd-actor'),motivo:gValue('gd-reason')});await refresh();toast('Cadastro arquivado. Histórico preservado.','info');});
}
async function gArchives(){
  const target=document.getElementById('gestao-archives');target.textContent='Carregando…';
  try{const rows=await gFetch('/api/gestao/arquivados');target.innerHTML=rows.length?`<div class="gestao-grid">${rows.map(a=>`<article class="gestao-card"><h3>${ge(a.titulo)}</h3><p>${ge(gTypes[a.tipo]||a.tipo)} · ${gDate(a.data)}</p><p>${ge(a.motivo)} · ${ge(a.operador)}</p><div class="gestao-actions"><button class="btn btn-ghost" data-history="${a.id}" data-type="${ge(a.tipo)}">Consultar histórico</button><button class="btn btn-primary" data-restore="${a.id}" data-type="${ge(a.tipo)}">Restaurar</button></div></article>`).join('')}</div>`:'<p>Nenhum cadastro arquivado.</p>';
    target.querySelectorAll('[data-restore]').forEach(b=>b.onclick=()=>gDialog('Restaurar cadastro',gField('Responsável pelo registro','gd-actor',gActor(),'text','required maxlength="80"'),async()=>{await gFetch(`/api/gestao/arquivados/${b.dataset.type}/${b.dataset.restore}/restaurar`,'POST',{operador:gValue('gd-actor')});await gArchives();}));
    target.querySelectorAll('[data-history]').forEach(b=>b.onclick=async()=>{try{const h=await gFetch(`/api/gestao/arquivados/${b.dataset.type}/${b.dataset.history}/historico`);gDialog('Histórico do cadastro',`<div class="gestao-note">${gArchivedRecord(h.registro)}${h.historico.map(r=>`<p>${ge(r.acao)} · ${ge(r.operador)} · ${gDate(r.data)}<br>${gHistoryDetail(r.detalhe)}</p>`).join('')}</div>`,async()=>{});}catch(e){toast(e.message,'error');}});
  }catch(e){target.textContent=e.message;}
}
// Mantém os atalhos antigos, com arquivamento no lugar da exclusão definitiva.
deleteOp=id=>gArchive('ops',id,loadOps);
deleteFuncionario=id=>gArchive('funcionarios',id,loadFuncionarios);
deleteQuimico=id=>gArchive('quimicos',id,loadQuimicos);
deleteReceita=id=>gArchive('receitas',id,loadReceitas);
deleteAmostra=id=>gArchive('amostras',id,loadAmostras);
deleteManutencao=id=>gArchive('manutencoes',id,loadManutencoes);
deleteOS=id=>gArchive('os',id,loadOrdensServico);
deleteFaturamento=id=>gArchive('faturamento',id,loadHistorico);
deletePreco=id=>gArchive('precos',id,loadPrecos);
document.querySelector('.content').insertAdjacentHTML('beforeend',`<section class="page" id="page-gestao"><h2>Acompanhamento de OPs</h2><p class="gestao-note">Roteiro, prazos, custos e margem em uma ficha por ordem de produção.</p><div class="gestao-toolbar">${gField('Responsável pelo registro','gestao-actor','','text','maxlength="80"')}${gField('Buscar OP, referência ou cliente','gestao-search')}<label class="gestao-field">Situação<select id="gestao-filter"><option value="">Todas</option><option value="abertas">Em andamento</option><option value="atrasadas">Atrasadas</option><option value="concluidas">Concluídas</option></select></label><button class="btn btn-ghost" id="g-refresh">Atualizar lista</button></div><p id="gestao-feedback" role="status"></p><div id="gestao-list"></div><div id="gestao-detail"></div></section><section class="page" id="page-arquivados"><h2>Cadastros arquivados</h2><p class="gestao-note">Consulte o histórico ou restaure um cadastro para voltar a utilizá-lo.</p><div id="gestao-archives"></div></section>`);
document.body.insertAdjacentHTML('beforeend','<dialog id="gestao-dialog" aria-label="Formulário de gestão"></dialog>');
document.getElementById('gestao-search').oninput=gRenderList;document.getElementById('gestao-filter').onchange=gRenderList;document.getElementById('g-refresh').onclick=gLoad;
const gOldGoPage=goPage;goPage=function(page){gOldGoPage(page);if(page==='gestao'){document.getElementById('topbar-title').textContent='Acompanhamento de OPs';gLoad();}if(page==='arquivados'){document.getElementById('topbar-title').textContent='Cadastros arquivados';gArchives();}};
// Agrupa o menu por atividade, preservando os botões e seus comandos existentes.
const gNav=document.querySelector('.sidebar nav');
const gButtons=[...gNav.querySelectorAll('.nav-btn')];
const gFind=page=>gButtons.find(b=>(b.getAttribute('onclick')||'').includes(`'${page}'`));
gNav.replaceChildren();
for(const [title,pages] of [['Visão geral',['dashboard','operador','gestao']],['Produção',['ops','lavar','centrifuga','secador','laser','passadoria','passadoriarobo','calendario']],['Cadastros',['funcionarios','quimicos','receitas','amostras','arquivados']],['Manutenção',['manutencao','checklist','ordemservico']],['Financeiro',['faturamento','dre']]]){
  const group=document.createElement('details');group.className='nav-group';group.open=true;const summary=document.createElement('summary');summary.textContent=title;group.append(summary);
  for(const page of pages){let b=page==='operador'?gButtons.find(b=>b.getAttribute('onclick')==='openOperator()'):gFind(page);if(!b){b=document.createElement('button');b.className='nav-btn';b.textContent=page==='gestao'?'Acompanhamento de OPs':'Arquivados';b.setAttribute('onclick',`goPage('${page}')`);}group.append(b);}gNav.append(group);
}

// Acesso à central de relatórios, com navegação e impressão próprias.
const relatoriosLink = document.createElement("a");
relatoriosLink.className = "nav-btn";
relatoriosLink.href = "/relatorios";
relatoriosLink.textContent = "Relatórios";
relatoriosLink.style.textDecoration = "none";
gNav.querySelector(".nav-group").append(relatoriosLink);
