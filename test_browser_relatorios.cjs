const {chromium}=require('./.browser-tools/node_modules/playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:5001');
 await page.getByRole('button',{name:'Abrir menu',exact:true}).click();
 await page.getByRole('link',{name:'Relatórios',exact:true}).click();
 await page.getByRole('heading',{name:'Produção por máquina',exact:true}).waitFor();
 assert.ok(await page.locator('tbody tr').count()>0);
 await page.pdf({path:'test-results/relatorios-producao.pdf',preferCSSPageSize:true,printBackground:true});
 await page.screenshot({path:'test-results/relatorios-desktop.png',fullPage:true});
 const downloadPromise=page.waitForEvent('download');
 await page.getByRole('button',{name:'Exportar CSV (Excel)',exact:true}).click();
 const download=await downloadPromise;
 assert.match(download.suggestedFilename(),/^chrona-producao/);
 await page.locator('[name=busca]').fill('inexistente');
 assert.ok(await page.locator('#imprimir').isDisabled());
 await page.getByRole('button',{name:'Gerar relatório',exact:true}).click();
 await page.getByText('Nenhum registro encontrado.',{exact:false}).waitFor();
 await page.locator('#tipo').selectOption('custos');
 assert.ok(await page.locator('[name=maquina]').isDisabled());
 await page.getByRole('button',{name:'Gerar relatório',exact:true}).click();
 await page.getByRole('heading',{name:'Custos por OP',exact:true}).waitFor();
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:'test-results/relatorios-mobile.png',fullPage:true});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.deepEqual(errors,[]);
 console.log('OK: menu, produção, CSV, filtros, estado vazio, custos, impressão PDF e celular.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
