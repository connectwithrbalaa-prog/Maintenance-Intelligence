const { test, expect } = require('@playwright/test');

const { createPortalHarness, openPortal } = require('./portalTestHarness');

test('portal repair plan snapshot: shows persisted repair-plan details and parts', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);

  const repairPlanSection = page.locator('.section').filter({ has: page.getByRole('heading', { name: 'Repair plan snapshot' }) });

  await expect(repairPlanSection).toContainText('Persisted repair plan');
  await expect(repairPlanSection).toContainText('RP-321');
  await expect(repairPlanSection).toContainText('Replace the inboard bearing and re-align the shaft before the next shift.');
  await expect(repairPlanSection).toContainText('Torque wrench');
  await expect(repairPlanSection).toContainText('Bearing kit');
  await expect(repairPlanSection).toContainText('Spare parts $1,295');
});

test('portal repair plan snapshot: falls back to structured plan when persisted record is unavailable', async ({ page }) => {
  const harness = createPortalHarness({
    runDetailsById: {
      'RUN-123': {
        run_id: 'RUN-123',
        status: 'ok',
        event_id: 'EV-9',
        recommendation_id: 'REC-44',
        repair_plan_id: 'RP-321',
        title: 'Replace bearing before next shift',
        summary: 'Inspect the current RCA run and PM recommendation set.',
        confidence: 0.83,
        hypothesis: ['Bearing wear is increasing vibration'],
        immediate_actions: ['Inspect lubrication'],
        pm_suggestions: ['Schedule bearing replacement'],
        structured: {
          title: 'Replace bearing before next shift',
          summary: 'Inspect the current RCA run and PM recommendation set.',
          confidence: 0.83,
          hypothesis: ['Bearing wear is increasing vibration'],
          immediate_actions: ['Inspect lubrication'],
          pm_suggestions: ['Schedule bearing replacement'],
          repair_plan: {
            plan_id: 'RP-321',
            procedure_steps: [
              { seq: 1, action: 'Verify coupling alignment', safety_note: 'Check guards', estimated_mins: 30 },
            ],
            tools_required: ['Dial indicator'],
            parts_list: [{ part_no: 'SEAL-42', description: 'Seal kit', qty: 1 }],
          },
        },
        repair_plan: {
          plan_id: 'RP-321',
          load_error: 'Repair plan lookup unavailable',
          procedure_steps: [
            { seq: 1, action: 'Verify coupling alignment', safety_note: 'Check guards', estimated_mins: 30 },
          ],
          tools_required: ['Dial indicator'],
          parts_list: [{ part_no: 'SEAL-42', description: 'Seal kit', qty: 1 }],
        },
        model: { name: 'gpt-4.1', version: 'test', latency_ms: 812, confidence: 0.83 },
        context_meta: { asset_id: 'PUMP-101', event_kind: 'anomaly' },
        updated_at: '2026-03-15T10:00:00Z',
        source_file: 'RUN-123.json',
      },
    },
  });
  await harness.install(page);

  await openPortal(page);

  const repairPlanSection = page.locator('.section').filter({ has: page.getByRole('heading', { name: 'Repair plan snapshot' }) });

  await expect(repairPlanSection).toContainText('Repair plan record could not be loaded');
  await expect(repairPlanSection).toContainText('Verify coupling alignment');
  await expect(repairPlanSection).toContainText('SEAL-42');
});