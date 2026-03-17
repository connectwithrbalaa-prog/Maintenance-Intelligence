const { test, expect } = require('@playwright/test');

const { createPortalHarness, openPortal } = require('./portalTestHarness');

test('portal compare: highlights confidence, feedback, and action drift against another run', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);
  const comparePanel = page.locator('.compare-shell');
  const compareDeltaGrid = comparePanel.locator('.compare-delta-grid');

  await expect(page.getByText('Run comparison')).toBeVisible();
  await expect(page.locator('#compareRunSelect')).toHaveValue('RUN-099');
  await expect(comparePanel.getByText('Confidence drift', { exact: true })).toBeVisible();
  await expect(comparePanel.getByText('Compare ready', { exact: true })).toBeVisible();
  await expect(comparePanel.getByText('+12 pts vs compare run', { exact: true })).toBeVisible();
  await expect(comparePanel.getByText('Title changed from Inspect seal and rebalance coupling', { exact: true })).toBeVisible();
  await expect(comparePanel.getByText('Reject -1', { exact: true })).toBeVisible();
  await expect(comparePanel.getByText('Edited -1', { exact: true })).toBeVisible();
  await expect(compareDeltaGrid.getByText('Bearing wear is increasing vibration', { exact: true })).toBeVisible();
  await expect(compareDeltaGrid.getByText('Seal misalignment is raising load', { exact: true })).toBeVisible();
  await expect(compareDeltaGrid.getByText('Bearing degradation from lubrication loss', { exact: true })).toBeVisible();
  await expect(compareDeltaGrid.getByText('Seal alignment drift', { exact: true })).toBeVisible();
  await expect(compareDeltaGrid.getByText('Lubrication instability', { exact: true })).toBeVisible();
  await expect(compareDeltaGrid.getByText('Recent overload trip', { exact: true })).toBeVisible();
  await expect(compareDeltaGrid.getByText('Recent coupling wear', { exact: true })).toBeVisible();
  await expect(compareDeltaGrid.getByText('Inspect lubrication', { exact: true })).toBeVisible();
  await expect(compareDeltaGrid.getByText('Capture vibration spectrum', { exact: true })).toBeVisible();
  await expect(compareDeltaGrid.getByText('Schedule bearing replacement', { exact: true })).toBeVisible();
  await expect(compareDeltaGrid.getByText('Plan coupling rebalance', { exact: true })).toBeVisible();
  await expect(compareDeltaGrid.getByRole('button', { name: 'Signal SIG-901' })).toBeVisible();
  await expect(compareDeltaGrid.getByRole('button', { name: 'Document DOC-COMMON' })).toBeVisible();
  await expect(compareDeltaGrid.getByRole('button', { name: 'Signal SIG-777' })).toBeVisible();

  await compareDeltaGrid.getByRole('button', { name: 'Signal SIG-901' }).click();
  await expect(page.locator('[data-evidence-ref-id="SIG-901"]')).toHaveClass(/active/);
  await expect(page.locator('[data-evidence-signal-id="SIG-901"]')).toHaveClass(/active/);

  await compareDeltaGrid.getByRole('button', { name: 'Signal SIG-777' }).click();
  await expect(page.locator('#detailStamp')).toContainText('RUN-099');
  await expect(page.locator('[data-evidence-ref-id="SIG-777"]')).toBeVisible();
  await expect(page.locator('#evidenceSection')).toBeVisible();

  await page.getByRole('button', { name: 'Document DOC-COMMON' }).first().click();
  await expect(page).toHaveURL(/#contextMetadataSection$/);

  expect(harness.outcomesCalls).toBeGreaterThan(0);
});

test('portal compare: falls back to the most recent cross-asset run when no same-asset peer exists', async ({ page }) => {
  const harness = createPortalHarness({
    runSummaries: [
      {
        run_id: 'RUN-123',
        status: 'ok',
        event_id: 'EV-9',
        recommendation_id: 'REC-44',
        title: 'Replace bearing before next shift',
        summary: 'Inspect the current RCA run and PM recommendation set.',
        confidence: 0.83,
        pm_suggestions: ['Schedule bearing replacement'],
        context_meta: { asset_id: 'PUMP-101', event_kind: 'anomaly' },
        model: { name: 'gpt-4.1', version: 'test', latency_ms: 812, confidence: 0.83 },
        updated_at: '2026-03-15T10:00:00Z',
        source_file: 'RUN-123.json',
      },
      {
        run_id: 'RUN-777',
        status: 'warn',
        event_id: 'EV-77',
        recommendation_id: 'REC-77',
        title: 'Inspect motor cooling loop',
        summary: 'A different asset showed cooling flow degradation.',
        confidence: 0.88,
        pm_suggestions: ['Flush cooling circuit'],
        context_meta: { asset_id: 'COMP-9', event_kind: 'inspection' },
        model: { name: 'gpt-4.1', version: 'test', latency_ms: 701, confidence: 0.88 },
        updated_at: '2026-03-15T09:30:00Z',
        source_file: 'RUN-777.json',
      },
    ],
    runDetailsById: {
      'RUN-777': {
        run_id: 'RUN-777',
        status: 'warn',
        event_id: 'EV-77',
        recommendation_id: 'REC-77',
        title: 'Inspect motor cooling loop',
        summary: 'A different asset showed cooling flow degradation.',
        confidence: 0.88,
        hypothesis: ['Cooling flow restriction is increasing motor temperature'],
        immediate_actions: ['Capture thermal snapshot'],
        pm_suggestions: ['Flush cooling circuit'],
        structured: {
          title: 'Inspect motor cooling loop',
          summary: 'A different asset showed cooling flow degradation.',
          confidence: 0.88,
          hypothesis: ['Cooling flow restriction is increasing motor temperature'],
          immediate_actions: ['Capture thermal snapshot'],
          pm_suggestions: ['Flush cooling circuit'],
        },
        model: { name: 'gpt-4.1', version: 'test', latency_ms: 701, confidence: 0.88 },
        context_meta: { asset_id: 'COMP-9', event_kind: 'inspection' },
        updated_at: '2026-03-15T09:30:00Z',
        source_file: 'RUN-777.json',
      },
    },
    feedbackHistoryByRunId: {
      'RUN-777': [],
    },
  });
  await harness.install(page);

  await openPortal(page);
  const comparePanel = page.locator('.compare-shell');

  await expect(page.locator('#compareRunSelect')).toHaveValue('RUN-777');
  await expect(comparePanel.getByText('Compare 88%', { exact: true })).toBeVisible();
  await expect(comparePanel.getByText('-5 pts vs compare run', { exact: true })).toBeVisible();
  await expect(comparePanel.getByText('COMP-9 · RUN-777', { exact: true })).toBeVisible();
  await expect(comparePanel.getByText('Flush cooling circuit', { exact: true })).toBeVisible();
});

test('portal compare: stays usable when compare feedback history fails to load', async ({ page }) => {
  const harness = createPortalHarness({
    feedbackFailuresByRunId: {
      'RUN-099': 'Compare feedback unavailable',
    },
  });
  await harness.install(page);

  await openPortal(page);
  const comparePanel = page.locator('.compare-shell');

  await expect(page.locator('#compareRunSelect')).toHaveValue('RUN-099');
  await expect(comparePanel.getByText('Compare ready', { exact: true })).toBeVisible();
  await expect(comparePanel.getByText('Reject 0', { exact: true })).toBeVisible();
  await expect(comparePanel.getByText('Edited 0', { exact: true })).toBeVisible();
  await expect(comparePanel.getByText('Plan coupling rebalance', { exact: true })).toBeVisible();
  await expect(comparePanel.getByText('Compare run unavailable', { exact: true })).toHaveCount(0);
});
