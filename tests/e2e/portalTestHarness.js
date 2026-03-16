const { expect } = require('@playwright/test');

function buildOutcomesReport(feedbackHistory) {
  const pump101Acceptance = feedbackHistory.length
    ? [
        { date: '2026-03-13', value: 0.5 },
        { date: '2026-03-14', value: 0.75 },
        { date: '2026-03-15', value: 1.0 },
      ]
    : [
        { date: '2026-03-13', value: 0.5 },
        { date: '2026-03-14', value: 0.75 },
        { date: '2026-03-15', value: 0.75 },
      ];
  const demoAdminFeedbackVolume = feedbackHistory.length
    ? [
        { date: '2026-03-13', value: 0 },
        { date: '2026-03-14', value: 1 },
        { date: '2026-03-15', value: 3 },
      ]
    : [
        { date: '2026-03-13', value: 0 },
        { date: '2026-03-14', value: 1 },
        { date: '2026-03-15', value: 2 },
      ];
  const opsDemoFeedbackVolume = feedbackHistory.length
    ? [
        { date: '2026-03-13', value: 1 },
        { date: '2026-03-14', value: 2 },
        { date: '2026-03-15', value: 4 },
      ]
    : [
        { date: '2026-03-13', value: 1 },
        { date: '2026-03-14', value: 2 },
        { date: '2026-03-15', value: 3 },
      ];

  return {
    window_days: 30,
    status: 'ok',
    warnings: [],
    top_assets_by_wo_volume: [
      { asset_id: 'PUMP-202', count: 6 },
      { asset_id: 'PUMP-101', count: 4 },
    ],
    top_users_by_feedback: [
      { user_id: 'demo.admin', count: feedbackHistory.length ? 4 : 3 },
      { user_id: 'planner.user', count: 2 },
    ],
    top_orgs_by_feedback: [
      { org_id: 'ops-demo', count: feedbackHistory.length ? 7 : 6 },
      { org_id: 'demo-org', count: 2 },
    ],
    asset_metrics: {
      'PUMP-101': {
        workorder_volume: [
          { date: '2026-03-13', value: 2 },
          { date: '2026-03-14', value: 4 },
          { date: '2026-03-15', value: 3 },
        ],
        acceptance_rate: pump101Acceptance,
      },
      'PUMP-202': {
        workorder_volume: [
          { date: '2026-03-13', value: 0 },
          { date: '2026-03-14', value: 2 },
          { date: '2026-03-15', value: 6 },
        ],
        acceptance_rate: [
          { date: '2026-03-13', value: 0.2 },
          { date: '2026-03-14', value: 0.4 },
          { date: '2026-03-15', value: 0.8 },
        ],
      },
    },
    user_metrics: {
      'demo.admin': {
        feedback_counts: { accept: 2, reject: 1, edited: feedbackHistory.length ? 1 : 0 },
        feedback_total: feedbackHistory.length ? 4 : 3,
        acceptance_rate: 2 / 3,
        feedback_volume: demoAdminFeedbackVolume,
        acceptance_rate_series: [
          { date: '2026-03-13', value: null },
          { date: '2026-03-14', value: 1.0 },
          { date: '2026-03-15', value: 0.5 },
        ],
      },
      'planner.user': {
        feedback_counts: { accept: 1, reject: 1, edited: 0 },
        feedback_total: 2,
        acceptance_rate: 0.5,
        feedback_volume: [
          { date: '2026-03-13', value: 1 },
          { date: '2026-03-14', value: 0 },
          { date: '2026-03-15', value: 1 },
        ],
        acceptance_rate_series: [
          { date: '2026-03-13', value: 1.0 },
          { date: '2026-03-14', value: null },
          { date: '2026-03-15', value: 0.0 },
        ],
      },
    },
    org_metrics: {
      'ops-demo': {
        feedback_counts: { accept: 3, reject: 1, edited: feedbackHistory.length ? 3 : 2 },
        feedback_total: feedbackHistory.length ? 7 : 6,
        acceptance_rate: 0.75,
        feedback_volume: opsDemoFeedbackVolume,
        acceptance_rate_series: [
          { date: '2026-03-13', value: 1.0 },
          { date: '2026-03-14', value: 0.5 },
          { date: '2026-03-15', value: 0.75 },
        ],
      },
      'demo-org': {
        feedback_counts: { accept: 1, reject: 1, edited: 0 },
        feedback_total: 2,
        acceptance_rate: 0.5,
        feedback_volume: [
          { date: '2026-03-13', value: 0 },
          { date: '2026-03-14', value: 1 },
          { date: '2026-03-15', value: 1 },
        ],
        acceptance_rate_series: [
          { date: '2026-03-13', value: null },
          { date: '2026-03-14', value: 1.0 },
          { date: '2026-03-15', value: 0.0 },
        ],
      },
    },
  };
}

async function fulfillJson(route, body) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function fulfillError(route, status, detail) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify({ detail }),
  });
}

function createPortalHarness(options = {}) {
  let historyPageOneCalls = 0;
  let outcomesCalls = 0;
  const feedbackHistory = [];
  const feedbackPosts = [];
  const compareFeedbackHistory = [
    {
      feedback_id: 'FB-COMPARE-2',
      run_id: 'RUN-099',
      recommendation_id: 'REC-21',
      org_id: 'ops-demo',
      asset_id: 'PUMP-101',
      action: 'edited',
      changes: {
        immediate_actions: ['Capture vibration spectrum', 'Inspect seal alignment'],
      },
      reason: 'Required more evidence before approving action set',
      user_id: 'planner.user',
      created_at: '2026-03-14T08:15:00Z',
    },
    {
      feedback_id: 'FB-COMPARE-1',
      run_id: 'RUN-099',
      recommendation_id: 'REC-21',
      org_id: 'ops-demo',
      asset_id: 'PUMP-101',
      action: 'reject',
      changes: {},
      reason: 'Need better root-cause evidence before scheduling PM work',
      user_id: 'demo.admin',
      created_at: '2026-03-14T07:40:00Z',
    },
  ];
  const defaultRunSummaries = [
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
      run_id: 'RUN-099',
      status: 'warn',
      event_id: 'EV-4',
      recommendation_id: 'REC-21',
      title: 'Inspect seal and rebalance coupling',
      summary: 'Previous run pointed to seal alignment and coupling drift.',
      confidence: 0.71,
      pm_suggestions: ['Plan coupling rebalance'],
      context_meta: { asset_id: 'PUMP-101', event_kind: 'inspection' },
      model: { name: 'gpt-4.1', version: 'test', latency_ms: 764, confidence: 0.71 },
      updated_at: '2026-03-14T08:00:00Z',
      source_file: 'RUN-099.json',
    },
  ];
  const defaultRunDetailsById = {
    'RUN-123': {
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
    },
    'RUN-099': {
      run_id: 'RUN-099',
      status: 'warn',
      event_id: 'EV-4',
      recommendation_id: 'REC-21',
      title: 'Inspect seal and rebalance coupling',
      summary: 'Previous run pointed to seal alignment and coupling drift.',
      confidence: 0.71,
      hypothesis: ['Seal misalignment is raising load'],
      immediate_actions: ['Capture vibration spectrum'],
      pm_suggestions: ['Plan coupling rebalance'],
      structured: {
        title: 'Inspect seal and rebalance coupling',
        summary: 'Previous run pointed to seal alignment and coupling drift.',
        confidence: 0.71,
        hypothesis: ['Seal misalignment is raising load'],
        immediate_actions: ['Capture vibration spectrum'],
        pm_suggestions: ['Plan coupling rebalance'],
      },
      model: { name: 'gpt-4.1', version: 'test', latency_ms: 764, confidence: 0.71 },
      context_meta: { asset_id: 'PUMP-101', event_kind: 'inspection' },
      updated_at: '2026-03-14T08:00:00Z',
      source_file: 'RUN-099.json',
    },
  };
  const runSummaries = options.runSummaries || defaultRunSummaries;
  const runDetailsById = {
    ...defaultRunDetailsById,
    ...(options.runDetailsById || {}),
  };
  const defaultBadActorsReport = [
    {
      asset_id: 'PUMP-202',
      score: 16,
      events_90d: 4,
      workorders_90d: 6,
      latest_severity: 'high',
      last_event_at: '2026-03-15T09:30:00Z',
    },
    {
      asset_id: 'PUMP-101',
      score: 11,
      events_90d: 3,
      workorders_90d: 4,
      latest_severity: 'medium',
      last_event_at: '2026-03-15T08:55:00Z',
    },
    {
      asset_id: 'FAN-9',
      score: 7,
      events_90d: 1,
      workorders_90d: 3,
      latest_severity: 'medium',
      last_event_at: '2026-03-14T17:10:00Z',
    },
  ];
  const badActorsReport = options.badActorsReport || defaultBadActorsReport;
  const badActorsFailure = options.badActorsFailure || '';
  const defaultPmProposals = [
    {
      proposal_id: 'REC-77',
      run_id: 'RUN-177',
      recommendation_id: 'REC-77',
      asset_id: 'COMP-7',
      title: 'Repair compressor seals',
      status: 'pending',
      handoff_state: 'failure',
      attempt_count: 3,
      attempts_remaining: 0,
      max_attempts: 3,
      retry_allowed: false,
      admin_retry_required: true,
      updated_at: '2026-03-15T09:52:00Z',
      last_attempt_info: {
        attempt_number: 3,
        attempted_at: '2026-03-15T09:52:00Z',
        approved_by: 'ops.admin',
        origin: 'admin',
        handoff_state: 'failure',
        connector_result: {},
        error_message: 'Connector timeout',
      },
      approval_history: [
        {
          attempt_number: 3,
          attempted_at: '2026-03-15T09:52:00Z',
          approved_by: 'ops.admin',
          origin: 'admin',
          handoff_state: 'failure',
          connector_result: {},
          error_message: 'Connector timeout',
        },
      ],
    },
    {
      proposal_id: 'REC-44',
      run_id: 'RUN-123',
      recommendation_id: 'REC-44',
      asset_id: 'PUMP-101',
      title: 'Replace bearing before next shift',
      status: 'pending',
      handoff_state: 'pending',
      attempt_count: 1,
      attempts_remaining: 2,
      max_attempts: 3,
      retry_allowed: true,
      admin_retry_required: true,
      updated_at: '2026-03-15T10:00:00Z',
      last_attempt_info: {
        attempt_number: 1,
        attempted_at: '2026-03-15T10:00:00Z',
        approved_by: 'planner.user',
        origin: 'approval',
        handoff_state: 'pending',
        connector_result: { message: 'Queued for connector retry' },
        error_message: '',
      },
      approval_history: [
        {
          attempt_number: 1,
          attempted_at: '2026-03-15T10:00:00Z',
          approved_by: 'planner.user',
          origin: 'approval',
          handoff_state: 'pending',
          connector_result: { message: 'Queued for connector retry' },
          error_message: '',
        },
      ],
      work_order_snapshot: {},
    },
    {
      proposal_id: 'REC-21',
      run_id: 'RUN-099',
      recommendation_id: 'REC-21',
      asset_id: 'PUMP-101',
      title: 'Inspect seal and rebalance coupling',
      status: 'pending',
      handoff_state: 'failure',
      attempt_count: 1,
      attempts_remaining: 2,
      max_attempts: 3,
      retry_allowed: true,
      admin_retry_required: true,
      updated_at: '2026-03-14T08:05:00Z',
      last_attempt_info: {
        attempt_number: 1,
        attempted_at: '2026-03-14T08:05:00Z',
        approved_by: 'planner.user',
        origin: 'approval',
        handoff_state: 'failure',
        connector_result: {},
        error_message: 'Payload validation failed',
      },
      approval_history: [
        {
          attempt_number: 1,
          attempted_at: '2026-03-14T08:05:00Z',
          approved_by: 'planner.user',
          origin: 'approval',
          handoff_state: 'failure',
          connector_result: {},
          error_message: 'Payload validation failed',
        },
      ],
    },
    {
      proposal_id: 'REC-88',
      run_id: 'RUN-188',
      recommendation_id: 'REC-88',
      asset_id: 'FAN-9',
      title: 'Replace fan belt',
      status: 'approved',
      handoff_state: 'success',
      attempt_count: 1,
      attempts_remaining: 2,
      max_attempts: 3,
      retry_allowed: false,
      admin_retry_required: false,
      updated_at: '2026-03-15T07:20:00Z',
      last_attempt_info: {
        attempt_number: 1,
        attempted_at: '2026-03-15T07:20:00Z',
        approved_by: 'demo.admin',
        origin: 'approval',
        handoff_state: 'success',
        connector_result: { message: 'Draft work order created' },
        error_message: '',
      },
      approval_history: [
        {
          attempt_number: 1,
          attempted_at: '2026-03-15T07:20:00Z',
          approved_by: 'demo.admin',
          origin: 'approval',
          handoff_state: 'success',
          connector_result: { message: 'Draft work order created' },
          error_message: '',
        },
      ],
      work_order_id: 'WO-REC-88',
      approved_by: 'demo.admin',
      approved_at: '2026-03-15T07:20:00Z',
      work_order_snapshot: {
        wo_id: 'WO-REC-88',
        asset_id: 'FAN-9',
        status: 'COMPLETE',
        title: 'Replace fan belt',
        priority: 'medium',
        workorder_created_at: '2026-03-15T07:25:00Z',
        handoff_completed_at: '2026-03-15T07:21:00Z',
        workorder_completed_at: '2026-03-15T11:40:00Z',
        metadata: {},
      },
    },
  ];
  const pmProposals = JSON.parse(JSON.stringify(options.pmProposals || defaultPmProposals));
  const pmProposalsFailure = options.pmProposalsFailure || '';
  const defaultSignalsSummaryByAssetId = {
    'PUMP-101': {
      asset_id: 'PUMP-101',
      recent_signals: [
        {
          signal_id: 'SIG-901',
          signal_type: 'Overall vibration',
          value: 11.4,
          unit: 'mm/s',
          timestamp: '2026-03-15T09:58:00Z',
          metadata: {
            spike_detected: true,
            threshold_breached: true,
          },
        },
        {
          signal_id: 'SIG-903',
          signal_type: 'Overall vibration',
          value: 8.8,
          unit: 'mm/s',
          timestamp: '2026-03-15T08:58:00Z',
          metadata: {},
        },
        {
          signal_id: 'SIG-902',
          signal_type: 'Bearing temperature',
          value: 84.2,
          unit: 'C',
          timestamp: '2026-03-15T09:54:00Z',
          metadata: {
            high_temp: true,
          },
        },
        {
          signal_id: 'SIG-904',
          signal_type: 'Bearing temperature',
          value: 88.1,
          unit: 'C',
          timestamp: '2026-03-15T08:54:00Z',
          metadata: {
            high_temp: true,
          },
        },
      ],
      rollups: [
        {
          signal_type: 'Overall vibration',
          period: 'Rolling 24h',
          mean: 8.4,
          min: 4.6,
          max: 11.4,
          anomalies: {
            threshold_breached: true,
          },
          end_time: '2026-03-15T10:00:00Z',
        },
        {
          signal_type: 'Bearing temperature',
          period: 'Rolling 24h',
          mean: 78.1,
          min: 70.3,
          max: 84.2,
          anomalies: {
            high_temp: true,
          },
          end_time: '2026-03-15T10:00:00Z',
        },
      ],
    },
  };
  const signalsSummaryByAssetId = {
    ...defaultSignalsSummaryByAssetId,
    ...(options.signalsSummaryByAssetId || {}),
  };
  const signalsFailuresByAssetId = new Map(Object.entries(options.signalsFailuresByAssetId || {}));
  const feedbackHistoryByRunId = {
    'RUN-123': feedbackHistory,
    'RUN-099': compareFeedbackHistory,
    ...(options.feedbackHistoryByRunId || {}),
  };
  const feedbackFailuresByRunId = new Map(Object.entries(options.feedbackFailuresByRunId || {}));

  async function install(page) {
    await page.route('**/api/v1/whoami', async (route) => {
      const headers = route.request().headers();
      await fulfillJson(route, {
        authenticated: true,
        user: {
          subject: headers['x-user-id'] || 'portal.user',
          role: headers['x-user-role'] || 'planner',
          org_id: headers['x-org-id'] || 'demo-org',
          auth_source: 'dev-header',
        },
      });
    });

    await page.route('**/api/v1/portal/runs?limit=24', async (route) => {
      await fulfillJson(route, runSummaries);
    });

    await page.route('**/api/v1/portal/runs/*', async (route) => {
      const runId = decodeURIComponent(route.request().url().split('/').pop() || '');
      const detail = runDetailsById[runId];
      if (!detail) {
        await fulfillError(route, 404, `Unknown run: ${runId}`);
        return;
      }
      await fulfillJson(route, detail);
    });

    await page.route('**/api/v1/signals/summary**', async (route) => {
      const url = new URL(route.request().url());
      const assetId = url.searchParams.get('asset_id');
      expect(url.searchParams.get('limit')).toBe('6');
      if (!assetId) {
        await fulfillError(route, 400, 'asset_id is required');
        return;
      }
      if (signalsFailuresByAssetId.has(assetId)) {
        await fulfillError(route, 503, signalsFailuresByAssetId.get(assetId));
        return;
      }
      if (Object.prototype.hasOwnProperty.call(signalsSummaryByAssetId, assetId)) {
        await fulfillJson(route, signalsSummaryByAssetId[assetId]);
        return;
      }
      throw new Error(`Unexpected signals summary asset_id: ${assetId}`);
    });

    await page.route('**/api/v1/rca/feedback**', async (route) => {
      if (route.request().method() === 'GET') {
        const url = new URL(route.request().url());
        const runId = url.searchParams.get('run_id');
        expect(url.searchParams.get('limit')).toBe('12');
        if (runId && feedbackFailuresByRunId.has(runId)) {
          await fulfillError(route, 503, feedbackFailuresByRunId.get(runId));
          return;
        }
        if (runId && Object.prototype.hasOwnProperty.call(feedbackHistoryByRunId, runId)) {
          await fulfillJson(route, feedbackHistoryByRunId[runId]);
          return;
        }
        throw new Error(`Unexpected feedback history run_id: ${runId}`);
        return;
      }

      const headers = route.request().headers();
      const payload = route.request().postDataJSON();
      expect(payload).toEqual({
        run_id: 'RUN-123',
        recommendation_id: 'REC-44',
        action: 'edited',
        reason: 'Adjusted after field inspection',
        changes: {
          title: 'Reinspect bearing housing',
          immediate_actions: ['Inspect lubrication', 'Capture thermography'],
        },
      });

      const feedback = {
        feedback_id: `FB-${feedbackPosts.length + 1}`,
        run_id: 'RUN-123',
        recommendation_id: 'REC-44',
        org_id: headers['x-org-id'] || 'ops-demo',
        asset_id: 'PUMP-101',
        action: 'edited',
        changes: payload.changes,
        reason: payload.reason,
        user_id: headers['x-user-id'] || 'demo.admin',
        created_at: '2026-03-15T10:07:00Z',
      };

      feedbackPosts.push(payload);
      feedbackHistory.unshift(feedback);

      await fulfillJson(route, { status: 'ok', feedback });
    });

    await page.route('**/api/v1/reports/rca-outcomes?window=30', async (route) => {
      outcomesCalls += 1;
      await fulfillJson(route, buildOutcomesReport(feedbackHistory));
    });

    await page.route('**/api/v1/reports/bad-actors**', async (route) => {
      const url = new URL(route.request().url());
      expect(url.searchParams.get('limit')).toBe('6');
      if (badActorsFailure) {
        await fulfillError(route, 503, badActorsFailure);
        return;
      }
      await fulfillJson(route, badActorsReport);
    });

    await page.route('**/api/v1/agents/pm/proposals', async (route) => {
      if (pmProposalsFailure) {
        await fulfillError(route, 503, pmProposalsFailure);
        return;
      }
      await fulfillJson(route, pmProposals);
    });

    await page.route('**/api/v1/agents/pm/advisor/analyze', async (route) => {
      const payload = route.request().postDataJSON();
      expect(payload).toEqual({ run_id: 'RUN-123' });
      await fulfillJson(route, {
        status: 'ok',
        proposal: { proposal_id: 'REC-44' },
        requested_by: 'demo.admin',
      });
    });

    await page.route('**/api/v1/agents/pm/proposals/REC-44/approve', async (route) => {
      const headers = route.request().headers();
      const proposal = pmProposals.find((item) => item.proposal_id === 'REC-44');
      if (proposal) {
        Object.assign(proposal, {
          status: 'approved',
          handoff_state: 'success',
          approved_by: headers['x-user-id'] || 'demo.admin',
          approved_at: '2026-03-15T10:05:00Z',
          work_order_id: 'WO-REC-44',
          attempt_count: 1,
          attempts_remaining: 2,
          max_attempts: 3,
          retry_allowed: false,
          admin_retry_required: false,
          updated_at: '2026-03-15T10:05:00Z',
          last_attempt_info: {
            attempt_number: 1,
            attempted_at: '2026-03-15T10:05:00Z',
            approved_by: headers['x-user-id'] || 'demo.admin',
            origin: 'approval',
            handoff_state: 'success',
            connector_result: { status: 'DRAFT', message: 'Draft work order created' },
            error_message: '',
          },
          approval_history: [
            {
              attempt_number: 1,
              attempted_at: '2026-03-15T10:05:00Z',
              approved_by: headers['x-user-id'] || 'demo.admin',
              origin: 'approval',
              handoff_state: 'success',
              connector_result: { status: 'DRAFT', message: 'Draft work order created' },
              error_message: '',
            },
          ],
          work_order_snapshot: {
            wo_id: 'WO-REC-44',
            asset_id: 'PUMP-101',
            status: 'DRAFT',
            title: 'Replace bearing before next shift',
            priority: 'medium',
            workorder_created_at: '2026-03-15T10:06:00Z',
            handoff_completed_at: '2026-03-15T10:05:00Z',
            workorder_completed_at: null,
            metadata: {},
          },
        });
      }
      await fulfillJson(route, {
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
      });
    });

    await page.route('**/api/v1/agents/pm/proposals/REC-44/history**', async (route) => {
      const url = new URL(route.request().url());
      const pageNumber = Number(url.searchParams.get('page') || '1');
      const size = Number(url.searchParams.get('size') || '3');
      if (pageNumber === 1) {
        historyPageOneCalls += 1;
        if (historyPageOneCalls === 1) {
          await fulfillJson(route, {
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
          });
          return;
        }

        await fulfillJson(route, {
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
        });
        return;
      }

      await fulfillJson(route, {
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
      });
    });
  }

  return {
    install,
    feedbackPosts,
    feedbackHistory,
    get outcomesCalls() {
      return outcomesCalls;
    },
  };
}

async function openPortal(page) {
  await page.goto('/portal?portalDev=1');
}

async function applyAdminIdentity(page) {
  await page.locator('#identitySubjectInput').fill('demo.admin');
  await page.locator('#identityRoleSelect').selectOption('admin');
  await page.locator('#identityOrgInput').fill('ops-demo');
  await page.getByRole('button', { name: 'Apply demo identity' }).click();
}

module.exports = {
  applyAdminIdentity,
  createPortalHarness,
  openPortal,
};