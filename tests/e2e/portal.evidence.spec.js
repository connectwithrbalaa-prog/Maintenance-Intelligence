const { test, expect } = require('@playwright/test');

const { createPortalHarness, openPortal } = require('./portalTestHarness');

test('portal evidence: renders recent signals and rollups for the selected asset', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);
  const evidencePanel = page.locator('.evidence-shell');

  await expect(page.getByRole('heading', { name: 'Live evidence' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Root causes' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Contributing factors' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Evidence references' })).toBeVisible();
  await expect(evidencePanel.getByText('Recent signals', { exact: true })).toBeVisible();
  await expect(evidencePanel.getByText('Rollup summary', { exact: true })).toBeVisible();
  await expect(evidencePanel.getByText('Asset PUMP-101', { exact: true })).toBeVisible();
  await expect(evidencePanel.getByText('Recent signals 4', { exact: true })).toBeVisible();
  await expect(evidencePanel.getByText('Rollups 2', { exact: true })).toBeVisible();
  await expect(evidencePanel.getByText('Overall vibration', { exact: true })).toHaveCount(3);
  await expect(evidencePanel.getByText('Bearing temperature', { exact: true })).toHaveCount(3);
  await expect(evidencePanel.getByText('11.4 mm/s', { exact: true })).toBeVisible();
  await expect(evidencePanel.getByText('84.2 C', { exact: true })).toBeVisible();
  await expect(evidencePanel.getByText('Trend rising', { exact: true })).toHaveCount(3);
  await expect(evidencePanel.getByText('Trend steady', { exact: true })).toHaveCount(1);
  await expect(evidencePanel.getByText('spike detected', { exact: true })).toBeVisible();
  await expect(evidencePanel.getByText('threshold breached', { exact: true })).toHaveCount(2);
  await expect(evidencePanel.getByText('high temp', { exact: true })).toHaveCount(3);
  await expect(evidencePanel.getByText('Signal SIG-901 · Source /api/v1/signals/summary?asset_id=PUMP-101&limit=6', { exact: true })).toBeVisible();
  await expect(page.getByText('Bearing degradation from lubrication loss', { exact: true })).toBeVisible();
  await expect(page.getByText('High ambient temperature', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Event EV-9' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Document DOC-1' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Signal SIG-901' })).toBeVisible();

  await page.getByRole('button', { name: 'Signal SIG-901' }).click();
  await expect(page.locator('[data-evidence-ref-id="SIG-901"]')).toHaveClass(/active/);
  await expect(page.locator('[data-evidence-signal-id="SIG-901"]')).toHaveClass(/active/);

  await page.getByRole('button', { name: 'Document DOC-1' }).click();
  await expect(page).toHaveURL(/#contextMetadataSection$/);
  await expect(page.locator('[data-evidence-ref-id="DOC-1"]')).toHaveClass(/active/);

  await page.getByRole('button', { name: 'Event EV-9' }).click();
  await expect(page).toHaveURL(/#eventMetaTile$/);
  await expect(page.locator('[data-evidence-ref-id="EV-9"]')).toHaveClass(/active/);
  await expect(page.locator('#eventMetaTile')).toHaveClass(/active/);

  expect(harness.outcomesCalls).toBeGreaterThan(0);
});

test('portal evidence: shows the empty state when no signals or rollups are available', async ({ page }) => {
  const harness = createPortalHarness({
    signalsSummaryByAssetId: {
      'PUMP-101': {
        asset_id: 'PUMP-101',
        recent_signals: [],
        rollups: [],
      },
    },
  });
  await harness.install(page);

  await openPortal(page);
  const evidencePanel = page.locator('.evidence-shell');

  await expect(evidencePanel.getByText('No live signal evidence yet', { exact: true })).toBeVisible();
  await expect(evidencePanel.getByText('This asset does not have recent signals or rollups available right now.', { exact: true })).toBeVisible();
});

test('portal evidence: shows the failure state when the evidence summary request fails', async ({ page }) => {
  const harness = createPortalHarness({
    signalsFailuresByAssetId: {
      'PUMP-101': 'Evidence service offline',
    },
  });
  await harness.install(page);

  await openPortal(page);
  const evidencePanel = page.locator('.evidence-shell');

  await expect(evidencePanel.getByText('Evidence unavailable', { exact: true })).toBeVisible();
  await expect(evidencePanel.getByText('Evidence service offline', { exact: true })).toBeVisible();
});