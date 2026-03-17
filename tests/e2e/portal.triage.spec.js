const { test, expect } = require('@playwright/test');

const { createPortalHarness, openPortal } = require('./portalTestHarness');

test('portal triage: ranks bad actors and highlights the current run asset', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);
  const triagePanel = page.locator('.triage-panel');

  await expect(page.getByRole('heading', { name: 'Asset triage queue' })).toBeVisible();
  await expect(triagePanel.getByText('Current asset queue rank', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('#2', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('PUMP-101 is ranked #2 with score 11.', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('Higher-pressure assets exist', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('PUMP-202 currently ranks above PUMP-101 in the triage queue.', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('Source /api/v1/reports/bad-actors', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('Lead asset PUMP-202', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('Lead score 16', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('#1 · PUMP-202', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('#2 · PUMP-101', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('Current run asset', { exact: true })).toBeVisible();
});

test('portal triage: shows a failure state when the bad-actors report is unavailable', async ({ page }) => {
  const harness = createPortalHarness({
    badActorsFailure: 'Triage report unavailable',
  });
  await harness.install(page);

  await openPortal(page);
  const triagePanel = page.locator('.triage-panel');

  await expect(triagePanel.getByText('Triage queue unavailable', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('We could not load the bad-actor queue right now: Triage report unavailable', { exact: true })).toBeVisible();
});