const {chromium}=require('./.browser-tools/node_modules/playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1366,height:768}}), errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:5001');
  assert.equal((await page.locator('.main').boundingBox()).x,0);
  await page.getByRole('button',{name:'Abrir menu',exact:true}).click();
  await page.getByRole('button',{name:'Ordens de Produção',exact:true}).click();
  assert.equal(await page.locator('#mobile-menu-button').getAttribute('aria-expanded'),'false');
  const pages=await page.locator('.page').evaluateAll(els=>els.map(el=>el.id.replace('page-','')));
  for(const width of [1366,390]) {
   await page.setViewportSize({width,height:844});
   for(const name of pages) {
    await page.evaluate(name=>goPage(name),name);
    await page.waitForTimeout(120);
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
    assert.equal(overflow,false,`Rolagem horizontal fora das tabelas: ${width}px / ${name}`);
   }
  }
  await page.setViewportSize({width:1366,height:768});
  await page.evaluate(()=>goPage('passadoria'));
  assert.equal(await page.locator('#page-passadoria details').getAttribute('open'),null);
  await page.locator('#page-passadoria summary').click();
  await page.locator('#pass-calc-turno-min').fill('480');
  await page.locator('#page-passadoria summary').click();
  await page.locator('#page-passadoria summary').click();
  assert.equal(await page.locator('#pass-calc-turno-min').inputValue(),'480');
  await page.locator('#page-passadoria summary').click();
  await page.screenshot({path:'test-results/layout-global-passadoria.png'});
  for(const id of await page.locator('.panel-overlay').evaluateAll(els=>els.map(el=>el.id))) {
   await page.evaluate(id=>document.getElementById(id).classList.add('open'),id);
   await page.waitForTimeout(320);
   const box=await page.locator(`#${id}>.panel`).boundingBox();
   assert.equal(box.width,1366,id);assert.equal(box.height,768,id);
   await page.evaluate(id=>document.getElementById(id).classList.remove('open'),id);
  }
  await page.getByRole('button',{name:'Abrir menu',exact:true}).click();
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#mobile-menu-button').getAttribute('aria-expanded'),'false');
  assert.deepEqual(errors,[]);
  console.log('OK: todas as páginas navegáveis, painéis em tela inteira, menu e calculadora preservados.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
