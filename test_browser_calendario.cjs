const {chromium} = require('./.browser-tools/node_modules/playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({channel:'msedge', headless:true});
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('http://127.0.0.1:5001/relatorios?inicio=2026-09-01&fim=2026-09-12');
    await page.getByRole('button', {name:'Abrir calendário de início', exact:true}).click();
    const inicio = page.locator('#calendario-inicio');
    await inicio.getByRole('button', {name:'Mês anterior', exact:true}).click();
    await inicio.locator('[data-date="2026-08-31"]').click();
    assert.equal(await page.locator('#inicio').inputValue(), '2026-08-31');
    assert.ok(await inicio.isHidden());
    assert.ok(await page.locator('#alterado').isVisible());
    await page.getByRole('button', {name:'Abrir calendário de fim', exact:true}).click();
    await page.locator('#calendario-fim [data-date="2026-09-10"]').click();
    await page.getByRole('button', {name:'Gerar relatório', exact:true}).click();
    await page.waitForURL('**/*inicio=2026-08-31&fim=2026-09-10*');
    assert.equal(await page.locator('#fim').inputValue(), '2026-09-10');
    await page.locator('#inicio').fill('2026-09-11');
    await page.getByRole('button', {name:'Gerar relatório', exact:true}).click();
    assert.equal(await page.locator('#fim').evaluate(el => el.validity.customError), true);
    await page.locator('#inicio').fill('2026-09-01');
    assert.equal(await page.locator('#fim').evaluate(el => el.validity.customError), false);
    await page.setViewportSize({width:390, height:844});
    await page.getByRole('button', {name:'Abrir calendário de fim', exact:true}).click();
    await page.locator('#calendario-fim [data-date="2026-09-12"]').click();
    assert.equal(await page.locator('#fim').inputValue(), '2026-09-12');
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.getByRole('button', {name:'Abrir calendário de fim', exact:true}).click();
    await page.screenshot({path:'test-results/calendario-mobile.png', fullPage:true});
    await page.keyboard.press('Escape');
    assert.ok(await page.locator('#calendario-fim').isHidden());
    assert.deepEqual(errors, []);
    console.log('OK: seleção de datas, troca de mês, geração, validação de período, digitação, celular e Escape.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
