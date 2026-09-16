/* Integra o estoque seco às telas de operação existentes. */
(() => {
  const link=document.createElement('a');link.className='nav-btn';link.href='/estoque-seco';link.textContent='Estoque seco e roteiros';
  document.querySelector('.nav-group').append(link);
  const note=document.createElement('p');note.className='operation-note';
  note.innerHTML='Novas OPs são programadas pela movimentação do roteiro. <a href="/estoque-seco">Abrir estoque seco e fluxo das OPs</a>.';
  document.getElementById('maq-programacao').append(note);
  const originalAPI=api;
  api=async function(url,method='GET',body=null){
    if(method==='PUT'&&body?.status&&(/^\/api\/laser\/fila\/\d+$/.test(url)||/^\/api\/passadoria\/fila\/\d+$/.test(url))){
      const actor=prompt('Operador responsável por registrar esta etapa:',document.getElementById('operator-name').value||'');
      if(!actor?.trim())throw new Error('Informe o operador para registrar o andamento.');
      body={...body,operador:actor.trim()};document.getElementById('operator-name').value=actor.trim();
    }
    return originalAPI(url,method,body);
  };
  const renderOps=filtrarOps;
  filtrarOps=function(){renderOps();document.querySelectorAll('#ops-tbody tr').forEach(row=>{
    const invoice=row.querySelector('button[onclick^="abrirFaturarOp"]');
    if(!invoice)return;
    const arg=invoice.getAttribute('onclick');const match=arg.match(/"id":(\d+)/);
    const op=match&&_allOps.find(o=>o.id===Number(match[1]));
    if(!op)return;
    invoice.disabled=!op.liberada_faturamento;invoice.title=op.liberada_faturamento?'OP pronta para faturar':'Conclua o roteiro para faturar';
    const anchor=document.createElement('a');anchor.className='btn btn-ghost btn-xs';anchor.href='/estoque-seco?op='+op.id;anchor.textContent='Estoque / roteiro';invoice.parentElement.append(anchor);
  });};
  const originalFicha=gRenderFicha;
  gRenderFicha=function(){originalFicha();{
    const editor=document.getElementById('g-route-editor');const section=editor.closest('section');
    editor.closest('details').hidden=true;
    const anchor=document.createElement('a');anchor.className='btn btn-primary';anchor.href='/estoque-seco?op='+gFicha.id;anchor.textContent='Abrir fluxo e movimentações';section.prepend(anchor);
  }};
  const page=new URLSearchParams(location.search).get('pagina');
  if(page&&document.getElementById('page-'+page))goPage(page);
  const machineType={lavadoras:'lavar',centrifugas:'centrifuga',secadores:'secador'}[page];
  if(machineType)goMaqPage(machineType);
})();
