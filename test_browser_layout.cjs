const {chromium}=require('./.browser-tools/node_modules/playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1366,height:768}}), errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:5001');
  await page.evaluate(()=>openMaqPanel(1,'lavar',1));
  await page.locator('#cargas-list .carga-row').first().waitFor();
  await page.waitForTimeout(350);
  const bounds=await page.locator('#maq-panel .panel').boundingBox();
  assert.equal(bounds.width,1366);assert.equal(bounds.height,768);
  const list=await page.locator('#maq-panel .panel-scroll-body').boundingBox();
  assert.ok(list.y<110);assert.ok(list.height>600);
  await page.screenshot({path:'test-results/maquina-compacta-desktop.png'});
  await page.locator('#maq-programacao summary').click();
  assert.ok(await page.locator('#mc-op').isVisible());
  assert.ok(await page.locator('#calc-op-select').isVisible());
  await page.locator('#mc-op').fill('CONFERENCIA');
  await page.locator('#maq-programacao summary').click();
  await page.locator('#maq-programacao summary').click();
  assert.equal(await page.locator('#mc-op').inputValue(),'CONFERENCIA');
  await page.locator('#maq-programacao summary').click();
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'test-results/maquina-compacta-mobile.png'});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  const mobile=await page.locator('#maq-panel .panel-scroll-body').boundingBox();
  assert.ok(mobile.height>600);
  await page.locator('#maq-panel .panel-scroll-body').evaluate(el=>el.scrollLeft=500);
  assert.ok(await page.locator('#maq-panel .panel-scroll-body').evaluate(el=>el.scrollLeft>0));
  await page.getByRole('button',{name:'Fechar máquina',exact:true}).click();
  assert.ok(await page.locator('#maq-panel').isHidden());
  assert.deepEqual(errors,[]);
  console.log('OK: tela inteira, lista acima de 600px, configuração recolhível preserva campos, rolagem no celular e fechamento.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
