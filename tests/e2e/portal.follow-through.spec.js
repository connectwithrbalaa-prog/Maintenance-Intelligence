const { test, expect } = require('@playwright/test');

const { createPortalHarness, openPortal } = require('./portalTestHarness');

test('portal follow-through snapshot: shows admin retry state for the active recommendation', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);

  const followThroughSection = page.locator('.section').filter({ has: page.getByRole('heading', { name: 'Recommendation follow-through snapshot' }) });

  await expect(followThroughSection).toContainText('Admin retry required');
  await expect(followThroughSection).toContainText('Proposal REC-44');
  await expect(followThroughSection).toContainText('Work order creation');
  await expect(followThroughSection).toContainText('Not created');
  await expect(followThroughSection).toContainText(/SLA watch|Aging risk/);
});

test('portal follow-through snapshot: shows completed work order lifecycle when present', async ({ page }) => {
  const harness = createPortalHarness({
    pmProposals: [
      {
        proposal_id: 'REC-44',
        run_id: 'RUN-123',
        recommendation_id: 'REC-44',
        asset_id: 'PUMP-101',
        title: 'Replace bearing before next shift',
        status: 'approved',
        handoff_state: 'success',
        attempt_count: 1,
        attempts_remaining: 2,
        max_attempts: 3,
        retry_allowed: false,
        admin_retry_required: false,
        approved_by: 'demo.admin',
        approved_at: '2026-03-15T10:05:00Z',
        updated_at: '2026-03-15T12:15:00Z',
        work_order_id: 'WO-REC-44',
        last_attempt_info: {
          attempt_number: 1,
          attempted_at: '2026-03-15T10:05:00Z',
          approved_by: 'demo.admin',
          origin: 'approval',
          handoff_state: 'success',
          connector_result: { message: 'Draft work order created' },
          error_message: '',
        },
        approval_history: [
          {
            attempt_number: 1,
            attempted_at: '2026-03-15T10:05:00Z',
            approved_by: 'demo.admin',
            origin: 'approval',
            handoff_state: 'success',
            connector_result: { message: 'Draft work order created' },
            error_message: '',
          },
        ],
        work_order_snapshot: {
          wo_id: 'WO-REC-44',
          asset_id: 'PUMP-101',
          status: 'COMPLETE',
          title: 'Replace bearing before next shift',
          priority: 'medium',
          workorder_created_at: '2026-03-15T10:06:00Z',
          handoff_completed_at: '2026-03-15T10:05:00Z',
          workorder_completed_at: '2026-03-15T12:15:00Z',
          metadata: {
            handoff: {
              proposal_id: 'REC-44',
              recommendation_id: 'REC-44',
              approved_by: 'demo.admin',
              origin: 'approval',
              backend: 'maximo',
              lifecycle_phase: 'completed',
              status_before: 'created',
              status_after: 'complete',
              attempt_count: 1,
              last_attempt: {
                attempted_at: '2026-03-15T10:05:00Z',
                handoff_state: 'success',
              },
            },
          },
        },
      },
    ],
  });
  await harness.install(page);

  await openPortal(page);

  const followThroughSection = page.locator('.section').filter({ has: page.getByRole('heading', { name: 'Recommendation follow-through snapshot' }) });

  await expect(followThroughSection).toContainText('Work order completed');
  await expect(followThroughSection).toContainText('WO-REC-44');
  await expect(followThroughSection).toContainText('Work order follow-through complete');
  await expect(followThroughSection).toContainText('Completed at');
  await expect(followThroughSection).toContainText('Lifecycle merge');
  await expect(followThroughSection).toContainText('Phase Completed');
  await expect(followThroughSection).toContainText('Transition Created to Complete');
  await expect(followThroughSection).toContainText('Handoff provenance');
  await expect(followThroughSection).toContainText('Origin Approval');
  await expect(followThroughSection).toContainText('Approved by demo.admin');
  await expect(followThroughSection).toContainText('Backend Maximo');
  await expect(followThroughSection).toContainText('Mar 15');
});