const assert=require('node:assert/strict');
async function programar(page,base,id,fase='lavar_preparacao',maquina=2){
  const recipe=await page.request.post(base+'/api/receitas',{data:{nome:'Receita do teste',etapas:[{titulo:'Processo de teste',tempo_min:10}]}});
  assert.equal(recipe.status(),200);
  const saved=await page.request.post(base+`/api/fluxo/ops/${id}/roteiro`,{data:{operador:'Teste',revisao:0,nome:'Fluxo de teste',receita_id:(await recipe.json()).id,
    passos:[{fase:'estoque_seco'},{fase},...(fase==='passadoria_final'?[]:[{fase:'passadoria_final'}])]}});
  assert.equal(saved.status(),200);const flow=await saved.json();
  const moved=await page.request.post(base+`/api/fluxo/ops/${id}/movimentar`,{data:{operador:'Teste',revisao:flow.revisao,etapa_id:flow.etapas[1].id,maquina_id:maquina}});
  assert.equal(moved.status(),200);return moved.json();
}
module.exports={programar};
