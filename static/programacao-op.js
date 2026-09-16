/* O indicador vem das cargas de lavagem, sem retirar OPs da seleção. */
function programacaoBadge(programada){
  return `<span class="op-programacao ${programada?'op-programada':'op-sem-programar'}">${programada?'● Programada':'● Sem programar'}</span>`;
}
const programacaoFiltrarOps=filtrarOps;
filtrarOps=function(){
  programacaoFiltrarOps();
  document.querySelectorAll('#ops-tbody tr').forEach(row=>{
    const id=row.querySelector('[onclick^="deleteOp("]')?.getAttribute('onclick')?.match(/deleteOp\((\d+)\)/)?.[1];
    const op=_allOps.find(o=>String(o.id)===id);
    if(!op)return;
    const cell=document.createElement('td');
    cell.innerHTML=programacaoBadge(op.programada_lavagem);
    row.insertBefore(cell,row.lastElementChild);
  });
  const empty=document.querySelector('#ops-tbody td[colspan]');if(empty)empty.colSpan=8;
};
loadOpsParaCalc=async function(){
  const ops=await api('/api/ops');
  const select=document.getElementById('calc-op-select');if(!select)return;
  const selected=select.value;
  select.replaceChildren(new Option('-- Selecione --',''));
  for(const op of ops){
    const option=new Option(`${op.op} — ${op.referencia} (${op.peso_total} kg / ${op.total_pecas} pç) — ${op.programada_lavagem?'🟢 Programada':'🔴 Sem programar'}`,op.id);
    option.dataset.programada=String(op.programada_lavagem);
    option.style.color=op.programada_lavagem?'#15803d':'#b91c1c';
    option.style.backgroundColor=op.programada_lavagem?'#dcfce7':'#fee2e2';
    select.add(option);
  }
  if([...select.options].some(o=>o.value===selected))select.value=selected;
  programacaoSelecionada();
};
function programacaoSelecionada(){
  const select=document.getElementById('calc-op-select');
  const option=select.selectedOptions[0];
  document.getElementById('calc-op-programacao').innerHTML=select.value?programacaoBadge(option.dataset.programada==='true'):'';
}
const programacaoLoadCargas=loadCargas;
loadCargas=async function(){
  await programacaoLoadCargas();
  await loadOpsParaCalc();
  if(document.getElementById('page-ops').classList.contains('active'))await loadOps();
};
const programacaoHeader=document.querySelector('#ops-tbody').closest('table').querySelector('thead tr');
const programacaoTh=document.createElement('th');programacaoTh.textContent='Programação na lavagem';
programacaoHeader.insertBefore(programacaoTh,programacaoHeader.lastElementChild);
document.getElementById('calc-op-select').insertAdjacentHTML('afterend','<div id="calc-op-programacao" aria-live="polite" style="margin-top:6px"></div>');
document.getElementById('calc-op-select').addEventListener('change',()=>{
  programacaoSelecionada();
  _calcResultado=null;document.getElementById('calc-resultado').style.display='none';
});
