const { test, expect } = require('@playwright/test');

const { applyAdminIdentity, createPortalHarness, openPortal } = require('./portalTestHarness');

test('portal analytics: switches asset, operator, and org outcome views', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);
	const outcomesPanel = page.locator('.outcomes-panel');
  const cmmsHealthCard = outcomesPanel.locator('.compare-card').filter({ hasText: 'CMMS handoff health' });
  const cmmsRetryCard = outcomesPanel.locator('.compare-card').filter({ hasText: 'CMMS retry pressure' });
  const cmmsFailureSplitCard = outcomesPanel.locator('.compare-card').filter({ hasText: 'CMMS failure split' });
  const cmmsAssetCard = outcomesPanel.locator('.compare-card').filter({ hasText: 'CMMS breakdown by asset' });
  const cmmsBackendCard = outcomesPanel.locator('.compare-card').filter({ hasText: 'CMMS breakdown by backend' });

  await expect(page.getByText('Current identity')).toBeVisible();
  await expect(page.locator('#identityControls')).toBeVisible();
  await expect(page.locator('#identityBadge')).toContainText('portal.user');
  await expect(page.getByText('Asset trend snapshot')).toBeVisible();
  await expect(cmmsHealthCard).toBeVisible();
  await expect(cmmsHealthCard.getByText('Success 2')).toBeVisible();
  await expect(cmmsHealthCard.getByText('Pending 1')).toBeVisible();
  await expect(cmmsHealthCard.getByText('Failure 1')).toBeVisible();
  await expect(cmmsRetryCard).toBeVisible();
  await expect(cmmsRetryCard.getByText('Admin retry 2')).toBeVisible();
  await expect(cmmsRetryCard.getByText('Limit reached 1')).toBeVisible();
  await expect(cmmsRetryCard.getByText('Avg lead time 8m')).toBeVisible();
  await expect(cmmsRetryCard.getByText('Source outcomes.cmms_summary')).toBeVisible();
  await expect(cmmsFailureSplitCard).toBeVisible();
  await expect(cmmsFailureSplitCard.getByText('Retryable 1')).toBeVisible();
  await expect(cmmsFailureSplitCard.getByText('Terminal 0')).toBeVisible();
  await expect(cmmsAssetCard).toBeVisible();
  await expect(cmmsAssetCard.getByText('PUMP-202')).toBeVisible();
  await expect(cmmsAssetCard.getByText('PUMP-101')).toBeVisible();
  await expect(cmmsBackendCard).toBeVisible();
  await expect(cmmsBackendCard.getByText('maximo')).toBeVisible();
  await expect(cmmsBackendCard.getByText('mock')).toBeVisible();
  await expect(cmmsBackendCard.getByText('Avg lead time 5m')).toBeVisible();
  await expect(cmmsBackendCard.getByText('Avg lead time 10m')).toBeVisible();
  await expect(page.getByText('Workorder volume')).toBeVisible();
  await expect(page.locator('#outcomesPrimaryKpiLabel')).toHaveText('Acceptance rate');
  await expect(page.locator('#outcomesScopeSelect')).toHaveValue('asset');
  await expect(page.locator('#outcomesEntitySelect')).toHaveValue('PUMP-101');
  await expect(page.locator('.chart-svg')).toHaveCount(2);

  await cmmsAssetCard.locator('.follow-stage').filter({ hasText: 'PUMP-202' }).getByRole('button', { name: 'Open asset trends' }).click();
  await expect(page.locator('#outcomesScopeSelect')).toHaveValue('asset');
  await expect(page.locator('#outcomesEntitySelect')).toHaveValue('PUMP-202');
  await expect(page.getByText('Showing the nearest live series')).toBeVisible();
  await expect(page.getByText('The run points to PUMP-101, but this window only has trend lines for PUMP-202. You are looking at the closest live asset instead.')).toBeVisible();
  await expect(page.getByText('Peak daily volume 6 · Low 0.')).toBeVisible();
  await expect(page.getByText('Range 20% to 80% across the current window.')).toBeVisible();
  await expect(page.locator('.chart-stat').filter({ hasText: '6' })).toBeVisible();
  await expect(page.locator('.chart-stat').filter({ hasText: '80%' })).toBeVisible();

  await cmmsBackendCard.locator('.follow-stage').filter({ hasText: 'mock' }).getByRole('button', { name: 'Open backend trends' }).click();
  await expect(page.locator('#outcomesScopeSelect')).toHaveValue('backend');
  await expect(page.locator('#outcomesEntitySelect')).toHaveValue('mock');
  await expect(page.locator('#outcomesPrimaryKpiLabel')).toHaveText('Handoff success rate');
  await expect(page.locator('#outcomesPrimaryKpiValue')).toHaveText('50%');
  await expect(page.getByText('Source outcomes.backend_metrics')).toBeVisible();
  await expect(page.getByText('Handoff total 2')).toBeVisible();
  await expect(page.getByText('Top connector maximo')).toBeVisible();
  await expect(page.getByText('Peak daily volume 1 · Low 0.')).toBeVisible();
  await expect(page.getByText('Range 0% to 100% across the current window.')).toBeVisible();

  await applyAdminIdentity(page);

  await expect(page.locator('#identityBadge')).toContainText('demo.admin');
  await expect(page.locator('#identityBadge')).toContainText('Role admin');
  await expect(page.locator('#identityBadge')).toContainText('Org ops-demo');

  await page.locator('#outcomesScopeSelect').selectOption('user');
  await expect(page.locator('#outcomesScopeSelect')).toHaveValue('user');
  await expect(page.locator('#outcomesEntitySelect')).toHaveValue('demo.admin');
  await expect(page.getByText('Feedback volume')).toBeVisible();
  await expect(page.getByText('Source outcomes.user_metrics')).toBeVisible();
  await expect(page.locator('#outcomesPrimaryKpiValue')).toHaveText('67%');
  await expect(page.getByText('Feedback total 3')).toBeVisible();
  await expect(page.getByText('Top contributor demo.admin')).toBeVisible();
  await expect(page.getByText('Peak daily volume 2 · Low 0.')).toBeVisible();
  await expect(page.getByText('Range 50% to 100% across the current window.')).toBeVisible();

  await page.locator('#outcomesScopeSelect').selectOption('org');
  await expect(page.locator('#outcomesScopeSelect')).toHaveValue('org');
  await expect(page.locator('#outcomesEntitySelect')).toHaveValue('ops-demo');
  await expect(page.getByText('Source outcomes.org_metrics')).toBeVisible();
  await expect(page.locator('#outcomesPrimaryKpiValue')).toHaveText('75%');
  await expect(page.getByText('Feedback total 6')).toBeVisible();
  await expect(page.getByText('Top contributor ops-demo')).toBeVisible();
  await expect(page.getByText('Peak daily volume 3 · Low 1.')).toBeVisible();
  await expect(page.getByText('Range 50% to 100% across the current window.')).toBeVisible();

  await page.locator('#outcomesScopeSelect').selectOption('asset');
  await page.locator('#outcomesEntitySelect').selectOption('PUMP-101');
  await expect(page.locator('#outcomesScopeSelect')).toHaveValue('asset');
  await expect(page.locator('#outcomesEntitySelect')).toHaveValue('PUMP-101');
  await expect(page.getByText('Range 50% to 75% across the current window.')).toBeVisible();

  expect(harness.outcomesCalls).toBeGreaterThan(0);
});