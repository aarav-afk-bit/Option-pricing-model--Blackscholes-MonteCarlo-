// End-to-end checks of the main user journeys.
import { fileURLToPath } from 'node:url';
import { test, expect } from '@playwright/test';

const CHART_JS = fileURLToPath(new URL('./node_modules/chart.js/dist/chart.umd.js', import.meta.url));

test.beforeEach(async ({ page }) => {
  // Point the frontend at the local backend instead of the deployed one.
  await page.route('**/js/config.js', (route) => route.fulfill({
    contentType: 'application/javascript', body: 'window.OPTIONS_API_BASE = "http://localhost:5000";',
  }));
  // Keep the tests independent of outside sites: Chart.js from the pinned local copy, no web fonts.
  await page.route('**/cdnjs.cloudflare.com/ajax/libs/Chart.js/**', (route) => route.fulfill({
    contentType: 'application/javascript', path: CHART_JS,
  }));
  await page.route('**/fonts.googleapis.com/**', (route) => route.abort());
  page.errors = [];
  page.on('pageerror', (err) => page.errors.push(err.message));
});

test.afterEach(async ({ page }) => {
  expect(page.errors, 'uncaught errors in the page').toEqual([]);
});

const status = (page) => page.locator('#statusText');

async function pickNifty(page){
  await page.goto('/');
  await expect(status(page)).toContainText('CONNECTED');
  await page.locator('.chip[data-symbol="NIFTY"]').click();
  await expect(status(page)).toContainText('LIVE CHAIN LOADED — NIFTY');
}

test('loads, connects to the backend and fills the option chain', async ({ page }) => {
  await pickNifty(page);
  await expect(page.locator('#pSpot')).toHaveValue('24512.35');
  await expect(page.locator('#strikeSelect')).toHaveValue('24500');
  await expect(page.locator('#chainTable tbody tr')).toHaveCount(21);
  await expect(page.locator('#chainStats')).toContainText('PCR');
});

test('Fetch Live runs the full analysis', async ({ page }) => {
  await pickNifty(page);
  await page.locator('#fetchBtn').click();
  await expect(status(page)).toContainText('LIVE — NIFTY 24500 CALL');
  await expect(page.locator('#bsCall')).toHaveText(/₹[\d,]+\.\d\d/);
  await expect(page.locator('#greeksTable tbody tr')).toHaveCount(8);
  await expect(page.locator('#summaryCard')).toBeVisible();
  await expect(page.locator('#sugVerdict')).not.toHaveText('SELECT A CONTRACT');
});

test('Recalc Local reprices a what-if without the backend', async ({ page }) => {
  await pickNifty(page);
  await page.locator('#fetchBtn').click();
  await expect(status(page)).toContainText('LIVE —');
  const before = await page.locator('#bsCall').textContent();
  await page.locator('#pVol').fill('30');
  await page.locator('#recalcBtn').click();
  await expect(status(page)).toContainText('LOCAL RECALC');
  await expect(page.locator('#bsCall')).not.toHaveText(before);
});

test('switching to a put and another expiry works', async ({ page }) => {
  await pickNifty(page);
  const expiries = await page.locator('#expirySelect option').evaluateAll((o) => o.map((x) => x.value));
  await page.locator('#expirySelect').selectOption(expiries[1]);
  await expect(page.locator('#strikeSelect')).toBeEnabled();
  await page.locator('#btnPut').click();
  await page.locator('#fetchBtn').click();
  await expect(status(page)).toContainText(`PUT · ${expiries[1]}`);
});

test('Monte Carlo Lab simulates and calibrates to the chain', async ({ page }) => {
  await pickNifty(page);
  await page.locator('#fetchBtn').click();
  await expect(page.locator('#mcStatus')).toContainText('Done', { timeout: 45_000 });
  await expect(page.locator('.mc-model')).toHaveCount(6);   // BS, 4 models, market
  await page.locator('#mcCalibrate').click();
  await expect(page.locator('#mcStatus')).toContainText('Calibrated', { timeout: 45_000 });
  await expect(page.locator('#mcCalibTable tr')).toHaveCount(4);
});

test('the page never scrolls sideways', async ({ page }) => {
  await pickNifty(page);
  await page.locator('#fetchBtn').click();
  await expect(status(page)).toContainText('LIVE —');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
