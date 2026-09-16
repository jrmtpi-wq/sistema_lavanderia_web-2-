(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = n => Number(n || 0).toLocaleString('pt-BR', {maximumFractionDigits:3});
  const when = s => s ? new Date(s).toLocaleString('pt-BR') : '—';
  const states = {aguardando:'Aguardando transferência',programado:'Programado no setor',em_processo:'Em processo',concluido:'Concluído'};
  let catalog, recipes=[], ops=[], current=null, submitAction, busy=false;
  async function api(url, method='GET', data) {
    const r=await fetch(url,{method,headers:{'Content-Type':'application/json'},...(data?{body:JSON.stringify(data)}:{})});
    let body;try{body=await r.json();}catch{throw new Error('Não foi possível ler a resposta do servidor.');}
    if(!r.ok)throw new Error(body.error||`Falha (${r.status}).`);return body;
  }
  function actor(){const v=$('actor').value.trim();if(!v)throw new Error('Informe o responsável pelos registros no topo da página.');return v;}
  function feedback(e){$('feedback').textContent=e.message||e;}
  function options(items,value){return items.map(i=>`<option value="${esc(i.id)}" ${String(i.id)===String(value)?'selected':''}>${esc(i.nome)}</option>`).join('');}
  async function reload(){
    [catalog,recipes,ops]=await Promise.all([api('/api/fluxo/catalogo'),api('/api/receitas'),api('/api/fluxo/ops')]);
    $('list-section').hidden=false;$('detail').hidden=true;current=null;renderList();
  }
  function renderList(){
    const search=$('search').value.toLocaleLowerCase('pt-BR'),filter=$('filter').value;
    const filtered=ops.filter(o=>(`${o.op} ${o.referencia}`).toLocaleLowerCase('pt-BR').includes(search)&&(!filter||
      (filter==='seco'&&!o.iniciado&&!o.legado)||(filter==='processo'&&o.iniciado&&!o.pronta)||
      (filter==='prontas'&&o.pronta)||(filter==='legado'&&o.legado)));
    $('totals').innerHTML=[['Peças no estoque seco',ops.reduce((n,o)=>n+o.saldo_seco,0)],['OPs em produção',ops.filter(o=>o.iniciado&&!o.pronta).length],['OPs prontas para faturar',ops.filter(o=>o.pronta).length]].map(([k,v])=>`<article><h3>${k}</h3><p>${fmt(v)}</p></article>`).join('');
    $('ops').innerHTML=filtered.map(o=>`<tr><td><b>${esc(o.op)}</b><br>${esc(o.referencia)}</td><td>${fmt(o.pecas)}</td><td>${fmt(o.peso)}</td><td>${o.legado?'A conferir':fmt(o.saldo_seco)}</td><td>${o.legado?'Produção anterior — saldo não presumido':esc(o.etapa)}${o.pesos_pendentes.length?`<br>Faltam pesos: ${esc(o.pesos_pendentes.join(', '))}`:''}</td><td><button data-open="${o.id}">Abrir OP</button></td></tr>`).join('')||'<tr><td colspan="6">Nenhuma OP encontrada.</td></tr>';
    $('ops').querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>open(Number(b.dataset.open)).catch(feedback));
  }
  async function open(id){
    current=await api(`/api/fluxo/ops/${id}`);const o=current;
    $('list-section').hidden=true;$('detail').hidden=false;
    const next=o.etapas.find(s=>s.status!=='concluido');
    $('detail').innerHTML=`<div class="actions"><button id="back">Voltar às OPs</button><button id="refresh-op">Atualizar andamento</button><button id="edit-op" ${o.iniciado?'disabled':''}>Editar grade e pesos</button>${!o.iniciado?'<button id="configure">Definir receita e roteiro</button>':''}</div>
      <h2>OP ${esc(o.op)} · ${esc(o.referencia)}</h2><p>${fmt(o.pecas)} peças · ${fmt(o.peso)} kg</p>
      ${o.legado?'<p class="nota">Esta OP já possui produção anterior. Seu histórico foi preservado. O saldo seco não foi criado automaticamente. Defina o roteiro e confira a posição atual após concluir as cargas e filas anteriores.</p>':''}
      ${o.conferencia?'<p class="nota">Posição inicial declarada em conferência. Consulte o histórico; datas anteriores permanecem sem apontamento.</p>':''}${o.pronta?'<p class="nota"><strong>OP pronta e liberada para faturamento.</strong> Todas as fases foram concluídas.</p><a class="button-link" href="/?pagina=faturamento">Abrir faturamento</a>':''}
      <div class="summary-grid">${Object.entries(o.qtd).map(([t,q])=>`<div><b>${esc(t)}</b><br>${fmt(q)} peças<br>${fmt(o.pesos[t])} kg/peça</div>`).join('')}</div>
      <h3>${esc(o.nome||'Roteiro não cadastrado')}</h3><p>O roteiro avança com a quantidade integral da OP. Cada passagem pelo mesmo setor é controlada separadamente.</p>
      ${next?`<div class="actions">${!next.movimentado_em?'<button id="move">Movimentar para '+esc(next.nome)+'</button>':next.setor==='manual'?'<button id="finish">Concluir '+esc(next.nome)+'</button>':`<a class="button-link" href="/?pagina=${next.setor==='lavar'?'lavadoras':next.setor==='centrifuga'?'centrifugas':next.setor==='secador'?'secadores':next.setor}">Abrir setor: ${esc(next.destino)}</a><span>Conclua as cargas/filas no setor e atualize o andamento aqui.</span>`}</div>`:''}
      <ol class="flow-steps">${o.etapas.map(s=>`<li class="${s.status==='concluido'?'done':s.id===next?.id?'current':''}"><b>${s.ordem}. ${esc(s.nome)}</b> <span class="badge">${states[s.status]}</span>${s.finalizadora&&s.ordem===o.etapas.length?' · Última fase: libera faturamento':''}<p>Destino: ${esc(s.destino||'A definir')} · Transferência: ${when(s.movimentado_em)}<br>Início real: ${when(s.inicio_real)} · Conclusão: ${when(s.fim_real)}</p><details><summary>Receita: ${esc(s.receita.nome)} · versão ${s.receita.versao}</summary><p>Versão preservada para esta OP.</p>${(s.receita.etapas||[]).map(e=>`<p class="recipe"><b>${esc(e.titulo)}</b> · ${fmt(e.tempo_min)} min<br>${esc(e.instrucao_texto||'')}${e.produto_nome?'<br>'+esc(e.produto_nome)+' · '+fmt(e.quantidade)+' '+esc(e.unidade):''}</p>`).join('')}</details></li>`).join('')}</ol>
      <details class="history"><summary>Histórico de movimentações (${o.historico.length})</summary>${o.historico.map(h=>`<p><b>${esc(h.acao)}</b> · ${esc(h.operador)} · ${when(h.data)}<br>${esc(h.detalhe.fase||h.detalhe.roteiro||'')}${h.detalhe.destino?' → '+esc(h.detalhe.destino):''}${h.detalhe.qtd?' · '+fmt(Object.values(h.detalhe.qtd).reduce((a,b)=>a+b,0))+' peças':''}</p>`).join('')}</details>`;
    $('back').onclick=()=>reload().catch(feedback);$('refresh-op').onclick=()=>open(id).catch(feedback);
    $('edit-op').onclick=()=>editOP(o);if($('configure'))$('configure').onclick=()=>routeEditor(o);
    if($('move'))$('move').onclick=()=>moveDialog(next).catch(feedback);
    if($('finish'))$('finish').onclick=()=>dialog('Concluir etapa',`<p>Confirme a conclusão de todas as peças em ${esc(next.nome)}.</p><label>Peças concluídas<input id="finish-pieces" type="number" min="1" step="1" value="${o.pecas}" required></label>`,async()=>{
      await api(`/api/fluxo/ops/${o.id}/concluir-manual`,'POST',{operador:actor(),revisao:o.revisao,etapa_id:next.id,pecas:$('finish-pieces').value});await open(o.id);
    });
  }
  function dialog(title,fields,action){$('editor-title').textContent=title;$('fields').innerHTML=fields;$('form-error').textContent='';submitAction=action;$('editor').showModal();}
  $('cancel').onclick=()=>{if(!busy)$('editor').close();};
  $('editor').addEventListener('cancel',e=>{if(busy)e.preventDefault();});
  $('edit-form').onsubmit=async e=>{e.preventDefault();if(busy)return;busy=true;$('save').disabled=true;$('cancel').disabled=true;
    try{await submitAction();$('editor').close();feedback('Registro salvo.');}catch(err){$('form-error').textContent=err.message;}finally{busy=false;$('save').disabled=false;$('cancel').disabled=false;}};
  function editOP(o){
    dialog(o?'Editar OP no estoque seco':'Cadastrar OP no estoque seco',`<div class="row"><label>Número da OP<input id="op-number" maxlength="20" value="${esc(o?.op)}" required></label><label>Referência<input id="op-reference" maxlength="50" value="${esc(o?.referencia)}" required></label></div><p>Quantidade por tamanho e peso de uma peça em kg. Pesos pendentes impedem a movimentação.</p><div class="grade">${window.fluxoTamanhos.map(t=>`<article><b>${t}</b><label>Peças<input data-q="${t}" type="number" min="0" max="10000000" step="1" value="${o?.qtd[t]||''}"></label><label>Kg por peça<input data-p="${t}" type="number" min="0" max="10000" step="0.001" value="${o?.pesos[t]||''}"></label></article>`).join('')}</div>`,async()=>{
      const qtd={},peso_unit={};document.querySelectorAll('[data-q]').forEach(n=>{if(Number(n.value))qtd[n.dataset.q]=Number(n.value);});document.querySelectorAll('[data-p]').forEach(n=>{if(Number(n.value))peso_unit[n.dataset.p]=Number(n.value);});
      const result=await api('/api/ops'+(o?'/'+o.id:''),o?'PUT':'POST',{op:$('op-number').value.trim(),referencia:$('op-reference').value.trim(),qtd,peso_unit});await reload();await open(o?.id||result.id);
    });
  }
  function routeRow(p={fase:'lavar_preparacao'}){
    const row=document.createElement('div');row.className='row route-row';
    row.innerHTML=`<label>Fase<select class="phase">${options(catalog.fases,p.fase)}</select></label><label>Receita desta fase<select class="recipe-select"><option value="">Usar receita principal</option>${options(recipes,p.receita_id)}</select></label><div class="actions"><button type="button" aria-label="Mover fase para cima">↑</button><button type="button" aria-label="Mover fase para baixo">↓</button><button type="button" aria-label="Retirar fase">Remover</button></div>`;
    const [up,down,remove]=row.querySelectorAll('button');up.onclick=()=>{if(row.previousElementSibling)row.before(row.previousElementSibling);};down.onclick=()=>{if(row.nextElementSibling)row.after(row.nextElementSibling);};remove.onclick=()=>row.remove();$('route-rows').append(row);
  }
  function routeEditor(o){
    const reconciliation=o?.legado?`<fieldset><legend>Conferência de produção anterior</legend><p>Informe quantas fases do roteiro acima já foram concluídas, contando Estoque seco como fase 1. Os horários históricos permanecem sem apontamento.</p><label>Fases já concluídas<input id="reconciled-count" type="number" min="2" max="40" step="1" required></label><label>Motivo / posição conferida<input id="reconciled-reason" maxlength="300" required></label><label><input id="reconciled-check" type="checkbox" required> Confirmei a quantidade integral da OP e a conclusão das fases informadas.</label></fieldset>`:'';
    dialog(o?'Receita e roteiro da OP':'Criar roteiro reutilizável',`<label>Nome do roteiro<input id="route-name" value="${esc(o?.nome)}" maxlength="100" required></label><label>Carregar um modelo<select id="route-template"><option value="">Montar minha sequência</option>${options(catalog.modelos,'')}</select></label>${o?`<label>Receita principal obrigatória<select id="main-recipe" required><option value="">Selecione</option>${options(recipes,o.etapas[0]?.receita?.id)}</select></label><p>Cadastre receitas em Receitas de lavagem no sistema. Você pode escolher uma receita diferente em cada fase.</p>`:''}<p>Comece pelo estoque seco e termine em Passadoria final ou Laser final. Use apenas as fases necessárias, na ordem desejada; setores podem se repetir.</p><div id="route-rows"></div>${reconciliation}<div class="actions"><button type="button" id="add-step">Adicionar fase</button></div>`,async()=>{
      const passos=[...document.querySelectorAll('.route-row')].map(row=>({fase:row.querySelector('.phase').value,receita_id:Number(row.querySelector('.recipe-select').value)||null}));
      const payload={nome:$('route-name').value.trim(),passos};
      if(o){await api(`/api/fluxo/ops/${o.id}/roteiro`,'POST',{...payload,operador:actor(),revisao:o.revisao,receita_id:Number($('main-recipe').value),conferir_legado:!!$('reconciled-check')?.checked,fases_concluidas:Number($('reconciled-count')?.value),motivo_conferencia:$('reconciled-reason')?.value});await open(o.id);}
      else{await api('/api/fluxo/modelos','POST',payload);await reload();}
    });
    const initial=o?.etapas.length?o.etapas.map(s=>({fase:s.fase,receita_id:s.receita.id})):['estoque_seco','lavar_preparacao','centrifuga','secador','passadoria_final'].map(fase=>({fase}));
    initial.forEach(routeRow);$('add-step').onclick=()=>routeRow();$('route-template').onchange=()=>{const m=catalog.modelos.find(m=>m.id===Number($('route-template').value));if(m){$('route-name').value=m.nome;$('route-rows').replaceChildren();m.passos.forEach(routeRow);}};
  }
  async function moveDialog(step){
    actor();let machines=[];
    if(['lavar','centrifuga','secador'].includes(step.setor)){machines=(await api('/api/maquinas?tipo='+step.setor)).map(m=>({id:m.id,nome:`${window.fluxoSetores[step.setor]} ${m.numero} · ${fmt(m.capacidade)} kg`}));}
    if(step.setor==='laser'){machines=(await api('/api/laser/equipamentos')).map(m=>({id:m.id,nome:`Laser ${m.numero}`}));}
    const o=current;
    dialog('Movimentar OP para '+step.nome,`<p>Transferir ${fmt(o.pecas)} peças (${fmt(o.peso)} kg) para a próxima fase. A distribuição em cargas respeita a capacidade da máquina e conserva as quantidades.</p>${machines.length?`<label>Para qual máquina?<select id="destination" required><option value="">Selecione a máquina</option>${options(machines,'')}</select></label>`:step.setor==='manual'||step.setor==='passadoria'?'<p>Destino: '+esc(step.nome)+'</p>':'<p>Nenhum equipamento disponível neste setor.</p>'}<label>Início planejado<input type="datetime-local" id="planned"></label><p>Confira o horário disponível da máquina. Sem horário informado, as cargas entram após a última previsão pendente da máquina.</p>`,async()=>{
      await api(`/api/fluxo/ops/${o.id}/movimentar`,'POST',{operador:actor(),revisao:o.revisao,etapa_id:step.id,maquina_id:Number($('destination')?.value)||null,data_inicio:$('planned').value});await open(o.id);
    });
  }
  $('refresh').onclick=()=>reload().catch(feedback);$('new-op').onclick=()=>editOP(null);$('templates').onclick=()=>routeEditor(null);
  $('new-phase').onclick=()=>dialog('Cadastrar fase de produção',`<label>Nome da fase<input id="phase-name" maxlength="80" required></label><label>Setor<select id="phase-sector">${options(Object.entries(window.fluxoSetores).map(([id,nome])=>({id,nome})),'manual')}</select></label><p>Para encerrar uma OP, utilize as fases Passadoria final ou Laser final já disponíveis.</p>`,async()=>{await api('/api/fluxo/fases','POST',{nome:$('phase-name').value.trim(),setor:$('phase-sector').value});catalog=await api('/api/fluxo/catalogo');});
  $('search').oninput=renderList;$('filter').onchange=renderList;
  reload().then(()=>{const oid=Number(new URLSearchParams(location.search).get('op'));if(oid)return open(oid);}).catch(feedback);
})();
