const { test, expect } = require('@playwright/test');

const { createPortalHarness, openPortal } = require('./portalTestHarness');

test('portal triage: ranks prioritized assets and highlights the current run asset', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);
  const triagePanel = page.locator('.triage-panel');

  await expect(page.getByRole('heading', { name: 'Asset triage queue' })).toBeVisible();
  await expect(triagePanel.getByText('Current asset queue rank', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('#2', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('PUMP-101 is ranked #2 with priority score 19.', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('Higher-pressure assets exist', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('PUMP-202 currently ranks above PUMP-101 in the triage queue.', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('Source /api/v1/reports/prioritized-assets', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('Lead asset PUMP-202', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('Lead score 28', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('Lead severity high', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('#1 · PUMP-202', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('#2 · PUMP-101', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('Open WOs 2', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('Signal risk 6', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('Acceptance 25%', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('Current run asset', { exact: true })).toBeVisible();
  await expect(page.locator('[data-triage-asset-id="PUMP-202"]')).toBeVisible();
  await expect(page.locator('[data-triage-evidence-asset-id="PUMP-202"]')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Open latest evidence' }).first()).toBeVisible();
});

test('portal triage: drills into asset trends and matching evidence runs', async ({ page }) => {
  const harness = createPortalHarness({
    runSummaries: [
      {
        run_id: 'RUN-123',
        status: 'ok',
        event_id: 'EV-9',
        recommendation_id: 'REC-44',
        repair_plan_id: 'RP-321',
        title: 'Replace bearing before next shift',
        summary: 'Inspect the current RCA run and PM recommendation set.',
        confidence: 0.83,
        pm_suggestions: ['Schedule bearing replacement'],
        context_meta: { asset_id: 'PUMP-101', event_kind: 'anomaly' },
        model: { name: 'gpt-4.1', version: 'test', latency_ms: 812, confidence: 0.83 },
        updated_at: '2026-03-15T10:00:00Z',
        source_file: 'RUN-123.json',
      },
    ],
    runDetailsById: {
      'RUN-202': {
        run_id: 'RUN-202',
        status: 'warn',
        event_id: 'EV-22',
        recommendation_id: 'REC-202',
        title: 'Inspect cavitation and suction pressure',
        summary: 'Latest RCA run for PUMP-202 with fresh signal context.',
        confidence: 0.77,
        hypothesis: ['Suction restriction is causing cavitation'],
        immediate_actions: ['Inspect suction strainer'],
        pm_suggestions: ['Verify suction pressure instrumentation'],
        structured: {
          title: 'Inspect cavitation and suction pressure',
          summary: 'Latest RCA run for PUMP-202 with fresh signal context.',
          confidence: 0.77,
          hypothesis: ['Suction restriction is causing cavitation'],
          immediate_actions: ['Inspect suction strainer'],
          pm_suggestions: ['Verify suction pressure instrumentation'],
        },
        model: { name: 'gpt-4.1', version: 'test', latency_ms: 702, confidence: 0.77 },
        context_meta: { asset_id: 'PUMP-202', event_kind: 'anomaly' },
        updated_at: '2026-03-15T10:30:00Z',
        source_file: 'RUN-202.json',
      },
    },
    latestRunByAssetId: {
      'PUMP-202': {
        run_id: 'RUN-202',
        status: 'warn',
        event_id: 'EV-22',
        recommendation_id: 'REC-202',
        title: 'Inspect cavitation and suction pressure',
        summary: 'Latest RCA run for PUMP-202 with fresh signal context.',
        confidence: 0.77,
        pm_suggestions: ['Inspect suction strainer'],
        context_meta: { asset_id: 'PUMP-202', event_kind: 'anomaly' },
        model: { name: 'gpt-4.1', version: 'test', latency_ms: 702, confidence: 0.77 },
        updated_at: '2026-03-15T10:30:00Z',
        source_file: 'RUN-202.json',
      },
    },
    feedbackHistoryByRunId: {
      'RUN-202': [],
    },
    signalsSummaryByAssetId: {
      'PUMP-202': {
        asset_id: 'PUMP-202',
        recent_signals: [
          {
            signal_id: 'SIG-202',
            signal_type: 'Inlet pressure',
            value: 2.1,
            unit: 'bar',
            timestamp: '2026-03-15T10:28:00Z',
            metadata: {
              cavitation_risk: true,
            },
          },
        ],
        rollups: [
          {
            signal_type: 'Inlet pressure',
            period: 'Rolling 24h',
            mean: 2.8,
            min: 2.1,
            max: 3.4,
            anomalies: {
              cavitation_risk: true,
            },
            end_time: '2026-03-15T10:30:00Z',
          },
        ],
      },
    },
  });
  await harness.install(page);

  await openPortal(page);

  await page.locator('[data-triage-asset-id="PUMP-202"]').click();
  await expect(page.locator('#outcomesEntitySelect')).toHaveValue('PUMP-202');
  await expect(page.locator('.outcomes-summary')).toContainText('Current PUMP-202');

  await page.locator('[data-triage-evidence-asset-id="PUMP-202"]').click();
  await expect(page.locator('#detailStamp')).toContainText('RUN-202');
  await expect(page.locator('.evidence-shell')).toContainText('Signal SIG-202 · Source /api/v1/signals/summary?asset_id=PUMP-202&limit=6');
});

test('portal triage: shows a failure state when the prioritized-assets report is unavailable', async ({ page }) => {
  const harness = createPortalHarness({
    badActorsFailure: 'Triage report unavailable',
  });
  await harness.install(page);

  await openPortal(page);
  const triagePanel = page.locator('.triage-panel');

  await expect(triagePanel.getByText('Triage queue unavailable', { exact: true })).toBeVisible();
  await expect(triagePanel.getByText('We could not load the prioritized asset queue right now: Triage report unavailable', { exact: true })).toBeVisible();
});