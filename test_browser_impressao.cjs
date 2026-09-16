const {chromium}=require('./.browser-tools/node_modules/playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const base=process.env.PRINT_TEST_URL||'http://127.0.0.1:5001';
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const data=await (await page.request.get(base+'/api/maquinas/1/cargas')).json();
  const expected=data.cargas.filter(c=>['em_processo','pausado','aguardando'].includes(c.status));
  assert.ok(expected.length>0,'Servidor deve conter uma carga eleg?vel para impress?o.');
  await page.goto(base);
  await page.evaluate(()=>openMaqPanel(1,'lavar',1));
  await page.getByRole('button',{name:'Imprimir cargas',exact:true}).click();
  await page.waitForURL('**/imprimir/maquinas/1');
  assert.equal(await page.locator('tbody tr').count(),expected.length);
  assert.equal(await page.locator('tbody tr').first().isVisible(),true);
  await page.evaluate(()=>{window.printCalls=0;window.print=()=>window.printCalls++;});
  await page.getByRole('button',{name:'Imprimir / Salvar PDF',exact:true}).click();
  assert.equal(await page.evaluate(()=>window.printCalls),1);
  await page.emulateMedia({media:'print'});
  assert.equal(await page.locator('tbody tr').first().isVisible(),true);
  assert.equal(await page.locator('.actions').isVisible(),false);
  fs.mkdirSync('test-results',{recursive:true});
  await page.screenshot({path:'test-results/impressao-relatorio.png',fullPage:true});
  const pdf=await page.pdf({path:'test-results/impressao-relatorio.pdf',preferCSSPageSize:true});
  assert.ok(pdf.length>1000);
  assert.ok((pdf.toString('latin1').match(/\/Type\s*\/Page\b/g)||[]).length>=1);
  assert.deepEqual(errors,[]);
  console.log('OK: '+expected.length+' cargas reais da API vis?veis na tela e no modo de impress?o; PDF gerado. Nenhum dado alterado.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
