const { test, expect } = require('@playwright/test');

const { createPortalHarness, openPortal } = require('./portalTestHarness');

test('portal smoke: loads the portal shell and default outcomes view', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);
  const outcomesPanel = page.locator('.outcomes-panel');

  await expect(page.getByText('Current identity')).toBeVisible();
  await expect(page.locator('#identityBadge')).toContainText('portal.user');
  await expect(page.getByRole('button', { name: 'Approve PM proposal' })).toBeVisible();
  await expect(page.locator('#outcomesScopeSelect')).toHaveValue('asset');
  await expect(page.locator('#outcomesEntitySelect')).toHaveValue('PUMP-101');
  await expect(outcomesPanel.getByText('Workorder volume', { exact: true })).toBeVisible();
  await expect(page.locator('#outcomesPrimaryKpiLabel')).toHaveText('Acceptance rate');
  await expect(outcomesPanel.getByText('Range 50% to 75% across the current window.', { exact: true })).toBeVisible();

  expect(harness.outcomesCalls).toBeGreaterThan(0);
});
