const {chromium}=require('./.browser-tools/node_modules/playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const base='http://127.0.0.1:5001',op='COR-'+Date.now();
  const create=await page.request.post(base+'/api/ops',{data:{op,referencia:'TESTE COR',qtd:{M:100},peso_unit:{M:.8}}});
  const {id}=await create.json();assert.equal(create.status(),200);
  await page.goto(base);
  await page.getByRole('button',{name:'Abrir menu',exact:true}).click();
  await page.getByRole('button',{name:'Ordens de Produção',exact:true}).click();
  const row=page.locator('#ops-tbody tr').filter({hasText:op});
  await row.locator('.op-sem-programar').waitFor();
  await page.evaluate(()=>openMaqPanel(1,'lavar',1));
  await page.locator('#maq-programacao summary').click();
  await page.locator('#calc-op-select').selectOption(String(id));
  await page.locator('#calc-op-programacao .op-sem-programar').waitFor();
  const flow=await require('./test_fluxo_helpers.cjs').programar(page,base,id,'lavar_preparacao',1);
  const carga={id:flow.etapas[1].vinculos[0].carga_id};
  await page.evaluate(()=>loadCargas());
  await page.locator('#calc-op-programacao .op-programada').waitFor();
  await row.locator('.op-programada').waitFor({state:'attached'});
  assert.equal(await page.locator('#calc-op-select').inputValue(),String(id));
  assert.match(await page.locator(`#calc-op-select option[value="${id}"]`).textContent(),/Programada/);
  const response=await page.request.delete(base+`/api/cargas/${carga.id}`);assert.equal(response.status(),409);
  await page.evaluate(()=>loadCargas());
  await page.locator('#calc-op-programacao .op-programada').waitFor();
  await row.locator('.op-programada').waitFor({state:'attached'});
  assert.equal(await page.locator('#calc-op-select').inputValue(),String(id));
  assert.deepEqual(errors,[]);
  console.log('OK: OP vermelha antes da transferência, verde após programar e protegida contra remoção da carga vinculada.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
