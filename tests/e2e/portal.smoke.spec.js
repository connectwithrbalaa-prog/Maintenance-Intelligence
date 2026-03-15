const { test, expect } = require('@playwright/test');

test('portal smoke: role toggle, PM approval banner, and load more audit history', async ({ page }) => {
  let historyPageOneCalls = 0;

  await page.route('**/api/v1/whoami', async (route) => {
    const headers = route.request().headers();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        authenticated: true,
        user: {
          subject: headers['x-user-id'] || 'portal.user',
          role: headers['x-user-role'] || 'planner',
          org_id: headers['x-org-id'] || 'demo-org',
          auth_source: 'dev-header',
        },
      }),
    });
  });

  await page.route('**/api/v1/portal/runs?limit=24', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
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
      ]),
    });
  });

  await page.route('**/api/v1/portal/runs/RUN-123', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        run_id: 'RUN-123',
        status: 'ok',
        event_id: 'EV-9',
        recommendation_id: 'REC-44',
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
        },
        model: { name: 'gpt-4.1', version: 'test', latency_ms: 812, confidence: 0.83 },
        context_meta: { asset_id: 'PUMP-101', event_kind: 'anomaly' },
        updated_at: '2026-03-15T10:00:00Z',
        source_file: 'RUN-123.json',
      }),
    });
  });

  await page.route('**/api/v1/agents/pm/advisor/analyze', async (route) => {
    const payload = route.request().postDataJSON();
    expect(payload).toEqual({ run_id: 'RUN-123' });
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        proposal: { proposal_id: 'REC-44' },
        requested_by: 'demo.admin',
      }),
    });
  });

  await page.route('**/api/v1/agents/pm/proposals/REC-44/approve', async (route) => {
    const headers = route.request().headers();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'approved',
        handoff_state: 'success',
        detail: 'PM proposal approved and handed off to the CMMS backend',
        approved: true,
        reused_result: false,
        attempt_count: 1,
        attempts_remaining: 2,
        max_attempts: 3,
        retry_allowed: false,
        attempt_status: 'success',
        last_attempt_info: {
          attempt_number: 1,
          attempted_at: '2026-03-15T10:05:00Z',
          approved_by: headers['x-user-id'] || 'demo.admin',
          origin: 'approval',
          handoff_state: 'success',
          connector_result: { status: 'DRAFT', message: 'Draft work order created' },
          error_message: '',
        },
        admin_retry_required: false,
        proposal_id: 'REC-44',
        approved_by: headers['x-user-id'] || 'demo.admin',
        approved_at: '2026-03-15T10:05:00Z',
        proposal: {
          proposal_id: 'REC-44',
          approved_by: headers['x-user-id'] || 'demo.admin',
          approved_at: '2026-03-15T10:05:00Z',
          work_order_id: 'WO-REC-44',
        },
        work_order: { wo_id: 'WO-REC-44', status: 'DRAFT', message: 'Draft work order created' },
      }),
    });
  });

  await page.route('**/api/v1/agents/pm/proposals/REC-44/history**', async (route) => {
    const url = new URL(route.request().url());
    const pageNumber = Number(url.searchParams.get('page') || '1');
    const size = Number(url.searchParams.get('size') || '3');
    if (pageNumber === 1) {
      historyPageOneCalls += 1;
      if (historyPageOneCalls === 1) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            proposal_id: 'REC-44',
            handoff_state: 'pending',
            attempts: [],
            total_count: 0,
            page: 1,
            size,
            has_more: false,
            attempt_count: 0,
            attempts_remaining: 3,
            max_attempts: 3,
            retry_allowed: true,
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          proposal_id: 'REC-44',
          handoff_state: 'success',
          attempts: [
            {
              attempt_number: 4,
              attempted_at: '2026-03-15T10:05:00Z',
              approved_by: 'demo.admin',
              origin: 'approval',
              handoff_state: 'success',
              connector_result: { message: 'Draft work order created' },
              error_message: '',
            },
            {
              attempt_number: 3,
              attempted_at: '2026-03-15T09:55:00Z',
              approved_by: 'ops.admin',
              origin: 'admin',
              handoff_state: 'failure',
              connector_result: {},
              error_message: 'Connector timeout',
            },
            {
              attempt_number: 2,
              attempted_at: '2026-03-15T09:45:00Z',
              approved_by: 'planner.user',
              origin: 'approval',
              handoff_state: 'pending',
              connector_result: { message: 'Queued for connector retry' },
              error_message: '',
            },
          ],
          total_count: 4,
          page: 1,
          size,
          has_more: true,
          attempt_count: 4,
          attempts_remaining: 0,
          max_attempts: 4,
          retry_allowed: false,
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        proposal_id: 'REC-44',
        handoff_state: 'success',
        attempts: [
          {
            attempt_number: 1,
            attempted_at: '2026-03-15T09:35:00Z',
            approved_by: 'planner.user',
            origin: 'approval',
            handoff_state: 'failure',
            connector_result: {},
            error_message: 'Malformed payload',
          },
        ],
        total_count: 4,
        page: 2,
        size,
        has_more: false,
        attempt_count: 4,
        attempts_remaining: 0,
        max_attempts: 4,
        retry_allowed: false,
      }),
    });
  });

  await page.goto('/portal?portalDev=1');

  await expect(page.getByText('Current identity')).toBeVisible();
  await expect(page.locator('#identityControls')).toBeVisible();
  await expect(page.locator('#identityBadge')).toContainText('portal.user');
  await expect(page.getByRole('button', { name: 'Approve PM proposal' })).toBeVisible();

  await page.locator('#identitySubjectInput').fill('demo.admin');
  await page.locator('#identityRoleSelect').selectOption('admin');
  await page.locator('#identityOrgInput').fill('ops-demo');
  await page.getByRole('button', { name: 'Apply demo identity' }).click();

  await expect(page.locator('#identityBadge')).toContainText('demo.admin');
  await expect(page.locator('#identityBadge')).toContainText('Role admin');
  await expect(page.locator('#identityBadge')).toContainText('Org ops-demo');

  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('Approve the PM proposal for RUN-123?');
    await dialog.accept();
  });
  await page.getByRole('button', { name: 'Approve PM proposal' }).click();

  await expect(page.getByText('PM proposal approved and handed off to the CMMS backend')).toBeVisible();
  await expect(page.getByText('Draft work order created', { exact: true })).toBeVisible();
  await expect(page.locator('.audit-badge.actor').filter({ hasText: 'Actor demo.admin' })).toBeVisible();
  await expect(page.locator('.audit-badge.origin-admin').filter({ hasText: 'Origin admin' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Load more' })).toBeVisible();

  await page.getByRole('button', { name: 'Load more' }).click();
  await expect(page.getByText('All recorded audit attempts are visible.')).toBeVisible();
  await expect(page.getByText('Malformed payload')).toBeVisible();
  await expect(page.getByText('Showing 4 of 4 attempts.')).toBeVisible();
});
