/* Painel diário e operação por toque. Texto de cadastros sempre escapado. */
const opEscape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const opLabels = {lavar:'Lavagem',centrifuga:'Centrifugação',secador:'Secagem'};
const opStatus = {aguardando:'Aguardando',em_processo:'Em processo',pausado:'Pausado',concluido:'Concluído'};
const opActions = {iniciar:'Iniciar',pausar:'Pausar',retomar:'Retomar',concluir:'Concluir'};
let operatorRequest = 0;
let summaryRequest = 0;
let operatorSaving = false;

async function operationFetch(url, body){
  const response = await fetch(url, body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {});
  let data;
  try{data=await response.json();}catch{throw new Error('O servidor não respondeu como esperado. Tente atualizar novamente.');}
  if(!response.ok) throw new Error(data.error || 'Não foi possível carregar os dados.');
  return data;
}

async function loadOperationSummary(){
  const requestId = ++summaryRequest;
  const target = document.getElementById('operation-summary');
  target.textContent = 'Carregando resumo…';
  try{
    const data = document.getElementById('operation-date').value;
    const d = await operationFetch('/api/operacao/resumo'+(data?'?data='+encodeURIComponent(data):''));
    if(requestId !== summaryRequest) return;
    document.getElementById('operation-date').value=d.data;
    target.innerHTML=`<div class="operation-stages">${Object.keys(opLabels).map(tipo=>[tipo,d.etapas[tipo]]).map(([tipo,s])=>`<div class="card operation-stage"><h3>${opLabels[tipo]}</h3><strong>${s.realizado_kg.toLocaleString('pt-BR')} kg realizados</strong><p>${s.previsto_kg.toLocaleString('pt-BR')} kg previstos para terminar no dia</p><p class="operation-note">${s.concluidas} cargas concluídas · ${s.realizado_pecas.toLocaleString('pt-BR')} peças realizadas${s.pecas_sem_medicao ? ` · ${s.pecas_sem_medicao} conclusão(ões) sem medição de peças` : ''} · ${s.previstas} previstas</p></div>`).join('')}</div>
      <p class="operation-note">Volumes por etapa, sem somar o mesmo lote entre lavagem, centrifugação e secagem. Realizado considera apenas conclusões registradas pelo modo operador; registros antigos sem horário real não entram neste indicador.</p>
      <h3>Operação agora</h3><p class="operation-note">${d.em_processo} máquinas em processo · ${d.pausadas} pausadas · ${d.atrasadas} cargas com saída prevista vencida. Atualizado em ${opEscape(fmtDT(d.atualizado_em))} (Brasília).</p>
      <div class="operation-alerts"><button class="btn btn-warning" data-page="quimicos">${d.estoque_baixo} produtos com estoque baixo</button><button class="btn btn-warning" data-page="manutencao">${d.manutencoes_vencidas} manutenções vencidas</button><button class="btn btn-ghost" data-page="ordemservico">${d.os_abertas} ordens de serviço pendentes</button></div>
      ${d.pendencias.length?`<details><summary>Cargas com previsão vencida (${d.atrasadas})</summary><div class="operation-alerts">${d.pendencias.map(c=>`<button class="btn btn-ghost" data-machine="${c.maquina_id}">OP ${opEscape(c.op)} · ${opLabels[c.tipo]} ${c.numero} · ${opEscape(fmtDT(c.saida_prevista))}</button>`).join('')}</div>${d.atrasadas>20?'<p class="operation-note">Mostrando as 20 previsões mais antigas.</p>':''}</details>`:'<p class="operation-note">Nenhuma carga com saída prevista vencida.</p>'}`;
    target.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>goPage(b.dataset.page));
    target.querySelectorAll('[data-machine]').forEach(b=>b.onclick=()=>openOperator(Number(b.dataset.machine)));
  }catch(error){if(requestId===summaryRequest) target.textContent='Não foi possível atualizar o painel. '+error.message;}
}

async function openOperator(machineId){
  goPage('operador');
  const select=document.getElementById('operator-machine');
  try{
    if(!select.options.length){
      const machines=(await Promise.all(Object.keys(opLabels).map(tipo=>operationFetch('/api/maquinas?tipo='+tipo)))).flat();
      for(const m of machines) select.add(new Option(`${opLabels[m.tipo]||m.tipo} ${m.numero}`,m.id));
    }
    if(machineId) select.value=String(machineId);
    await loadOperator();
  }catch(error){document.getElementById('operator-list').textContent=error.message;}
}

async function loadOperator(){
  const id=document.getElementById('operator-machine').value;
  const target=document.getElementById('operator-list');
  if(!id){target.textContent='Nenhuma máquina cadastrada.';return;}
  const requestId=++operatorRequest;
  target.textContent='Carregando cargas…';
  try{
    const d=await operationFetch(`/api/operacao/maquinas/${id}`);
    if(requestId!==operatorRequest)return;
    const showDone=document.getElementById('operator-completed').checked;
    const cargas=d.cargas.filter(c=>showDone||c.status!=='concluido');
    if(!cargas.length){target.innerHTML='<p class="operation-feedback">Nenhuma carga nesta seleção. Cadastre cargas na programação da máquina ou marque “Mostrar concluídas”.</p>';return;}
    target.innerHTML=cargas.map(c=>{
      const actions={aguardando:['iniciar'],em_processo:['pausar','concluir'],pausado:['retomar'],concluido:[]}[c.status]||[];
      return `<article class="card operator-card" data-status="${opEscape(c.status)}"><h3>Carga ${c.numero} · OP ${opEscape(c.op||'não informada')}</h3><p><b>${opStatus[c.status]||opEscape(c.status)}</b> · ${c.peso.toLocaleString('pt-BR')} kg · ${c.pecas} peças</p><p>${opEscape(c.referencia)} · ${opEscape(c.lavacao)}</p><p class="operation-note">Início previsto: ${opEscape(fmtDT(c.inicio_previsto))}<br>Saída prevista: ${opEscape(fmtDT(c.saida_prevista))}</p>
        ${c.status==='em_processo'?`<label for="pause-${c.id}">Motivo da pausa</label><textarea class="form-control" id="pause-${c.id}" maxlength="200" placeholder="Ex.: manutenção, falta de insumo, troca de turno"></textarea>`:''}
        <div class="operator-actions">${actions.map(a=>`<button class="btn ${a==='pausar'?'btn-warning':'btn-primary'}" data-id="${c.id}" data-revision="${c.revisao}" data-action="${a}">${opActions[a]}</button>`).join('')}</div>
        <details><summary>Histórico de apontamentos (${c.historico.length})</summary><ol>${c.historico.map(a=>`<li>${opEscape(fmtDT(a.data))} · ${opActions[a.acao]} · ${opEscape(a.operador)}${a.motivo?' — '+opEscape(a.motivo):''}${a.acao==='concluir' ? ` · ${Number(a.peso).toLocaleString('pt-BR')} kg · ${a.pecas == null ? 'peças sem medição' : Number(a.pecas).toLocaleString('pt-BR') + ' peças'}` : ''}</li>`).join('')}</ol></details></article>`;
    }).join('');
    target.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>saveOperatorAction(b));
  }catch(error){if(requestId===operatorRequest)target.textContent='Não foi possível carregar a fila. '+error.message;}
}

async function saveOperatorAction(button){
  if(operatorSaving)return;
  const feedback=document.getElementById('operator-feedback');
  const operador=document.getElementById('operator-name').value.trim();
  const motivo=document.getElementById('pause-'+button.dataset.id)?.value.trim()||'';
  if(!operador){feedback.textContent='Informe seu nome antes de registrar a ação.';document.getElementById('operator-name').focus();return;}
  if(button.dataset.action==='pausar'&&!motivo){feedback.textContent='Informe o motivo da pausa.';document.getElementById('pause-'+button.dataset.id).focus();return;}
  operatorSaving=true;
  document.querySelectorAll('#operator-list button').forEach(b=>b.disabled=true);
  feedback.textContent='Salvando apontamento…';
  try{
    await operationFetch(`/api/operacao/cargas/${button.dataset.id}/apontar`,{acao:button.dataset.action,revisao:Number(button.dataset.revision),operador,motivo});
    feedback.textContent='Apontamento registrado com sucesso.';
    await loadOperator();
  }catch(error){feedback.textContent=error.message;}
  finally{operatorSaving=false;document.querySelectorAll('#operator-list button').forEach(b=>b.disabled=false);}
}

const originalGoPage=goPage;
goPage=function(page){
  originalGoPage(page);
  document.querySelector('.sidebar').classList.remove('open');
  document.getElementById('mobile-menu-backdrop').classList.remove('visible');
  document.getElementById('mobile-menu-button').setAttribute('aria-expanded','false');
  document.querySelectorAll('.nav-btn').forEach(b=>b.classList.toggle('active',(b.getAttribute('onclick')||'').includes(`'${page}'`)));
  if(page==='operador'){
    document.getElementById('topbar-title').textContent='Modo operador';
    document.querySelectorAll('.nav-btn').forEach(b=>b.classList.toggle('active',(b.getAttribute('onclick')||'')==='openOperator()'));
  }
  if(page==='dashboard')loadOperationSummary();
};
function toggleMobileMenu(){
  const open=document.querySelector('.sidebar').classList.toggle('open');
  document.getElementById('mobile-menu-backdrop').classList.toggle('visible',open);
  document.getElementById('mobile-menu-button').setAttribute('aria-expanded',String(open));
}
loadOperationSummary();
