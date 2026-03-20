const { test, expect } = require('@playwright/test');

const { createPortalHarness, openPortal } = require('./portalTestHarness');

test('portal notification filters persist across reload for the same identity', async ({ page }) => {
  const harness = createPortalHarness();
  const notificationQueryCalls = [];

  await page.route('**/api/v1/portal/notifications**', async (route) => {
    const url = new URL(route.request().url());
    notificationQueryCalls.push({
      status: url.searchParams.get('status'),
      destination: url.searchParams.get('destination'),
    });

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await harness.install(page);
  await openPortal(page);

  const statusFilter = page.locator('#notificationStatusFilter');
  const destinationFilter = page.locator('#notificationDestinationFilter');

  await expect(statusFilter).toBeVisible();
  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(0);
  const initialCallCount = notificationQueryCalls.length;

  await statusFilter.selectOption('failed');
  await destinationFilter.fill('hooks.example.test');

  await page.locator('#notificationRefreshButton').click();

  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(initialCallCount);
  await expect.poll(() => notificationQueryCalls[notificationQueryCalls.length - 1]).toMatchObject({
    status: 'failed',
    destination: 'hooks.example.test',
  });

  await page.reload();
  await expect(statusFilter).toBeVisible();

  await expect(statusFilter).toHaveValue('failed');
  await expect(destinationFilter).toHaveValue('hooks.example.test');

  await expect.poll(() => notificationQueryCalls[notificationQueryCalls.length - 1]).toMatchObject({
    status: 'failed',
    destination: 'hooks.example.test',
  });
});

test('portal notification org/site filters persist across reload for the same identity', async ({ page }) => {
  const harness = createPortalHarness();
  const notificationQueryCalls = [];

  await page.route('**/api/v1/portal/notifications**', async (route) => {
    const url = new URL(route.request().url());
    notificationQueryCalls.push({
      orgId: url.searchParams.get('org_id'),
      siteId: url.searchParams.get('site_id'),
    });

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await harness.install(page);
  await openPortal(page);

  const orgIdFilter = page.locator('#notificationOrgIdFilter');
  const siteIdFilter = page.locator('#notificationSiteIdFilter');
  const applyButton = page.locator('#notificationRefreshButton');

  await expect(orgIdFilter).toBeVisible();
  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(0);
  const initialCallCount = notificationQueryCalls.length;

  await page.evaluate(() => {
    const orgInput = document.getElementById('notificationOrgIdFilter');
    const siteInput = document.getElementById('notificationSiteIdFilter');
    if (orgInput) {
      orgInput.value = 'demo-org';
    }
    if (siteInput) {
      siteInput.value = 'site-a';
    }
  });
  await applyButton.click();

  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(initialCallCount);
  await expect
    .poll(() =>
      notificationQueryCalls.slice(initialCallCount).some((call) =>
        call.orgId === 'demo-org' && call.siteId === 'site-a'
      )
    )
    .toBe(true);

  await page.reload();
  await expect(orgIdFilter).toBeVisible();
  await expect(orgIdFilter).toHaveValue('demo-org');
  await expect(siteIdFilter).toHaveValue('site-a');

  await expect.poll(() => notificationQueryCalls[notificationQueryCalls.length - 1]).toMatchObject({
    orgId: 'demo-org',
    siteId: 'site-a',
  });
});

test('portal notification edge-state and sort persist across reload for the same identity', async ({ page }) => {
  const harness = createPortalHarness();
  const notificationQueryCalls = [];

  await page.route('**/api/v1/portal/notifications**', async (route) => {
    const url = new URL(route.request().url());
    notificationQueryCalls.push({
      edgeState: url.searchParams.get('edge_state'),
      sort: url.searchParams.get('sort'),
    });

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await harness.install(page);
  await openPortal(page);

  const edgeStateFilter = page.locator('#notificationEdgeStateFilter');
  const sortFilter = page.locator('#notificationSortFilter');
  const applyButton = page.locator('#notificationRefreshButton');

  await expect(edgeStateFilter).toBeVisible();
  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(0);
  const initialCallCount = notificationQueryCalls.length;

  await edgeStateFilter.selectOption('degraded');
  await sortFilter.selectOption('oldest');
  await applyButton.click();

  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(initialCallCount);
  await expect
    .poll(() =>
      notificationQueryCalls.slice(initialCallCount).some((call) =>
        call.edgeState === 'degraded' && call.sort === 'oldest'
      )
    )
    .toBe(true);

  await page.reload();
  await expect(edgeStateFilter).toBeVisible();
  await expect(edgeStateFilter).toHaveValue('degraded');
  await expect(sortFilter).toHaveValue('oldest');
  await expect.poll(() => notificationQueryCalls[notificationQueryCalls.length - 1]).toMatchObject({
    edgeState: 'degraded',
    sort: 'oldest',
  });
});

test('portal notification filters are identity-scoped across identity switches', async ({ page }) => {
  const harness = createPortalHarness();
  const notificationQueryCalls = [];

  await page.route('**/api/v1/portal/notifications**', async (route) => {
    const url = new URL(route.request().url());
    notificationQueryCalls.push({
      status: url.searchParams.get('status'),
      destination: url.searchParams.get('destination'),
    });

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await harness.install(page);
  await openPortal(page);

  const destinationFilter = page.locator('#notificationDestinationFilter');
  const applyIdentityButton = page.getByRole('button', { name: 'Apply demo identity' });
  const identitySubjectInput = page.locator('#identitySubjectInput');
  const identityRoleSelect = page.locator('#identityRoleSelect');
  const identityOrgInput = page.locator('#identityOrgInput');

  await expect(destinationFilter).toBeVisible();
  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(0);

  const initialSubject = await identitySubjectInput.inputValue();
  const initialRole = await identityRoleSelect.inputValue();
  const initialOrg = await identityOrgInput.inputValue();
  const alternateSubject = `${initialSubject || 'portal.user'}.alt`;
  const alternateRole = initialRole === 'viewer' ? 'planner' : 'viewer';

  await destinationFilter.fill('hooks.a.example.test');
  await destinationFilter.press('Enter');

  await expect(destinationFilter).toHaveValue('hooks.a.example.test');
  await expect.poll(() => notificationQueryCalls[notificationQueryCalls.length - 1]).toMatchObject({
    destination: 'hooks.a.example.test',
  });

  await identitySubjectInput.fill(alternateSubject);
  await identityRoleSelect.selectOption(alternateRole);
  await identityOrgInput.fill(initialOrg);
  await applyIdentityButton.click();

  await expect(destinationFilter).toHaveValue('');
  await expect.poll(() => notificationQueryCalls[notificationQueryCalls.length - 1]).toMatchObject({
    destination: 'all',
  });

  await destinationFilter.fill('hooks.b.example.test');
  await destinationFilter.press('Enter');

  await expect(destinationFilter).toHaveValue('hooks.b.example.test');
  await expect.poll(() => notificationQueryCalls[notificationQueryCalls.length - 1]).toMatchObject({
    destination: 'hooks.b.example.test',
  });

  await identitySubjectInput.fill(initialSubject);
  await identityRoleSelect.selectOption(initialRole);
  await identityOrgInput.fill(initialOrg);
  await applyIdentityButton.click();

  await expect(destinationFilter).toHaveValue('hooks.a.example.test');
  await expect.poll(() => notificationQueryCalls[notificationQueryCalls.length - 1]).toMatchObject({
    destination: 'hooks.a.example.test',
  });
});

test('portal notification filters are org-scoped for same subject and role', async ({ page }) => {
  const harness = createPortalHarness();
  const notificationQueryCalls = [];

  await page.route('**/api/v1/portal/notifications**', async (route) => {
    const url = new URL(route.request().url());
    notificationQueryCalls.push({
      status: url.searchParams.get('status'),
      destination: url.searchParams.get('destination'),
    });

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await harness.install(page);
  await openPortal(page);

  const statusFilter = page.locator('#notificationStatusFilter');
  const destinationFilter = page.locator('#notificationDestinationFilter');
  const applyFiltersButton = page.locator('#notificationRefreshButton');
  const applyIdentityButton = page.getByRole('button', { name: 'Apply demo identity' });
  const identitySubjectInput = page.locator('#identitySubjectInput');
  const identityRoleSelect = page.locator('#identityRoleSelect');
  const identityOrgInput = page.locator('#identityOrgInput');

  await expect(statusFilter).toBeVisible();
  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(0);

  const subject = await identitySubjectInput.inputValue();
  const role = await identityRoleSelect.inputValue();
  const initialOrg = await identityOrgInput.inputValue();
  const alternateOrg = initialOrg === 'demo-org' ? 'ops-demo' : 'demo-org';

  await statusFilter.selectOption('failed');
  await destinationFilter.fill('hooks.primary.example.test');
  await applyFiltersButton.click();

  await expect(statusFilter).toHaveValue('failed');
  await expect(destinationFilter).toHaveValue('hooks.primary.example.test');

  await identitySubjectInput.fill(subject);
  await identityRoleSelect.selectOption(role);
  await identityOrgInput.fill(alternateOrg);
  await applyIdentityButton.click();

  await expect(statusFilter).toHaveValue('all');
  await expect(destinationFilter).toHaveValue('');

  await statusFilter.selectOption('sent');
  await destinationFilter.fill('hooks.alt-org.example.test');
  await applyFiltersButton.click();

  await expect(statusFilter).toHaveValue('sent');
  await expect(destinationFilter).toHaveValue('hooks.alt-org.example.test');

  await identitySubjectInput.fill(subject);
  await identityRoleSelect.selectOption(role);
  await identityOrgInput.fill(initialOrg);
  await applyIdentityButton.click();

  await expect(statusFilter).toHaveValue('failed');
  await expect(destinationFilter).toHaveValue('hooks.primary.example.test');
  await expect.poll(() => notificationQueryCalls[notificationQueryCalls.length - 1]).toMatchObject({
    status: 'failed',
    destination: 'hooks.primary.example.test',
  });
});

test('portal notification destination filter applies on Enter key', async ({ page }) => {
  const harness = createPortalHarness();
  const notificationQueryCalls = [];

  await page.route('**/api/v1/portal/notifications**', async (route) => {
    const url = new URL(route.request().url());
    notificationQueryCalls.push({
      status: url.searchParams.get('status'),
      destination: url.searchParams.get('destination'),
    });

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await harness.install(page);
  await openPortal(page);

  const statusFilter = page.locator('#notificationStatusFilter');
  const destinationFilter = page.locator('#notificationDestinationFilter');

  await expect(statusFilter).toBeVisible();
  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(0);
  const initialCallCount = notificationQueryCalls.length;

  await statusFilter.selectOption('failed');
  await destinationFilter.fill('hooks.example.test');
  await destinationFilter.press('Enter');

  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(initialCallCount);
  await expect.poll(() => notificationQueryCalls[notificationQueryCalls.length - 1]).toMatchObject({
    status: 'failed',
    destination: 'hooks.example.test',
  });
});

test('portal notification route-id filter applies on Enter key', async ({ page }) => {
  const harness = createPortalHarness();
  const notificationQueryCalls = [];

  await page.route('**/api/v1/portal/notifications**', async (route) => {
    const url = new URL(route.request().url());
    notificationQueryCalls.push({
      status: url.searchParams.get('status'),
      routeId: url.searchParams.get('route_id'),
    });

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await harness.install(page);
  await openPortal(page);

  const statusFilter = page.locator('#notificationStatusFilter');
  const routeIdFilter = page.locator('#notificationRouteIdFilter');

  await expect(statusFilter).toBeVisible();
  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(0);
  const initialCallCount = notificationQueryCalls.length;

  await statusFilter.selectOption('failed');
  await routeIdFilter.fill('default');
  await routeIdFilter.press('Enter');

  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(initialCallCount);
  await expect.poll(() => notificationQueryCalls[notificationQueryCalls.length - 1]).toMatchObject({
    status: 'failed',
    routeId: 'default',
  });
});

test('portal notification org/site filters apply on Enter key', async ({ page }) => {
  const harness = createPortalHarness();
  const notificationQueryCalls = [];

  await page.route('**/api/v1/portal/notifications**', async (route) => {
    const url = new URL(route.request().url());
    notificationQueryCalls.push({
      orgId: url.searchParams.get('org_id'),
      siteId: url.searchParams.get('site_id'),
    });

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await harness.install(page);
  await openPortal(page);

  const orgIdFilter = page.locator('#notificationOrgIdFilter');
  const siteIdFilter = page.locator('#notificationSiteIdFilter');

  await expect(orgIdFilter).toBeVisible();
  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(0);

  await orgIdFilter.fill('demo-org');
  await orgIdFilter.press('Enter');

  await expect.poll(() => notificationQueryCalls[notificationQueryCalls.length - 1]).toMatchObject({
    orgId: 'demo-org',
    siteId: 'all',
  });

  await siteIdFilter.fill('site-a');
  await siteIdFilter.press('Enter');

  await expect.poll(() => notificationQueryCalls[notificationQueryCalls.length - 1]).toMatchObject({
    orgId: 'demo-org',
    siteId: 'site-a',
  });
});

test('portal notification apply includes org/site filter query params together', async ({ page }) => {
  const harness = createPortalHarness();
  const notificationQueryCalls = [];

  await page.route('**/api/v1/portal/notifications**', async (route) => {
    const url = new URL(route.request().url());
    notificationQueryCalls.push({
      orgId: url.searchParams.get('org_id'),
      siteId: url.searchParams.get('site_id'),
      status: url.searchParams.get('status'),
    });

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await harness.install(page);
  await openPortal(page);

  const statusFilter = page.locator('#notificationStatusFilter');
  const orgIdFilter = page.locator('#notificationOrgIdFilter');
  const siteIdFilter = page.locator('#notificationSiteIdFilter');
  const applyButton = page.locator('#notificationRefreshButton');

  await expect(orgIdFilter).toBeVisible();
  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(0);
  const initialCallCount = notificationQueryCalls.length;

  await expect(statusFilter).toHaveValue('all');
  await page.evaluate(() => {
    const orgInput = document.getElementById('notificationOrgIdFilter');
    const siteInput = document.getElementById('notificationSiteIdFilter');
    if (orgInput) {
      orgInput.value = 'demo-org';
    }
    if (siteInput) {
      siteInput.value = 'site-a';
    }
  });
  await applyButton.click();

  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(initialCallCount);
  await expect
    .poll(() =>
      notificationQueryCalls.slice(initialCallCount).some((call) =>
        call.status === 'all' && call.orgId === 'demo-org' && call.siteId === 'site-a'
      )
    )
    .toBe(true);
});

test('portal notification filter reset clears persisted values after reload', async ({ page }) => {
  const harness = createPortalHarness();
  const notificationQueryCalls = [];

  await page.route('**/api/v1/portal/notifications**', async (route) => {
    const url = new URL(route.request().url());
    notificationQueryCalls.push({
      status: url.searchParams.get('status'),
      destination: url.searchParams.get('destination'),
    });

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await harness.install(page);
  await openPortal(page);

  const statusFilter = page.locator('#notificationStatusFilter');
  const destinationFilter = page.locator('#notificationDestinationFilter');
  const applyButton = page.locator('#notificationRefreshButton');
  const resetButton = page.locator('#notificationResetButton');

  await expect(statusFilter).toBeVisible();
  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(0);

  await statusFilter.selectOption('failed');
  await destinationFilter.fill('hooks.example.test');
  await applyButton.click();

  await expect(statusFilter).toHaveValue('failed');
  await expect(destinationFilter).toHaveValue('hooks.example.test');

  const afterApplyCallCount = notificationQueryCalls.length;
  await resetButton.click();

  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(afterApplyCallCount);
  await expect(statusFilter).toHaveValue('all');
  await expect(destinationFilter).toHaveValue('');

  await expect.poll(() => notificationQueryCalls[notificationQueryCalls.length - 1]).toMatchObject({
    status: 'all',
    destination: 'all',
  });

  await page.reload();
  await expect(statusFilter).toBeVisible();

  await expect(statusFilter).toHaveValue('all');
  await expect(destinationFilter).toHaveValue('');

  await expect.poll(() => notificationQueryCalls[notificationQueryCalls.length - 1]).toMatchObject({
    status: 'all',
    destination: 'all',
  });
});

test('portal notification org/site reset clears persisted values after reload', async ({ page }) => {
  const harness = createPortalHarness();
  const notificationQueryCalls = [];

  await page.route('**/api/v1/portal/notifications**', async (route) => {
    const url = new URL(route.request().url());
    notificationQueryCalls.push({
      orgId: url.searchParams.get('org_id'),
      siteId: url.searchParams.get('site_id'),
    });

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await harness.install(page);
  await openPortal(page);

  const orgIdFilter = page.locator('#notificationOrgIdFilter');
  const siteIdFilter = page.locator('#notificationSiteIdFilter');
  const applyButton = page.locator('#notificationRefreshButton');
  const resetButton = page.locator('#notificationResetButton');

  await expect(orgIdFilter).toBeVisible();
  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(0);

  await page.evaluate(() => {
    const orgInput = document.getElementById('notificationOrgIdFilter');
    const siteInput = document.getElementById('notificationSiteIdFilter');
    if (orgInput) {
      orgInput.value = 'demo-org';
    }
    if (siteInput) {
      siteInput.value = 'site-a';
    }
  });
  await applyButton.click();

  await expect(orgIdFilter).toHaveValue('demo-org');
  await expect(siteIdFilter).toHaveValue('site-a');
  await expect
    .poll(() => notificationQueryCalls[notificationQueryCalls.length - 1])
    .toMatchObject({ orgId: 'demo-org', siteId: 'site-a' });

  const afterApplyCallCount = notificationQueryCalls.length;
  await resetButton.click();

  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(afterApplyCallCount);
  await expect(orgIdFilter).toHaveValue('');
  await expect(siteIdFilter).toHaveValue('');
  await expect
    .poll(() => notificationQueryCalls[notificationQueryCalls.length - 1])
    .toMatchObject({ orgId: 'all', siteId: 'all' });

  await page.reload();
  await expect(orgIdFilter).toBeVisible();
  await expect(orgIdFilter).toHaveValue('');
  await expect(siteIdFilter).toHaveValue('');
  await expect
    .poll(() => notificationQueryCalls[notificationQueryCalls.length - 1])
    .toMatchObject({ orgId: 'all', siteId: 'all' });
});

test('portal notification edge-state/sort reset restores defaults after reload', async ({ page }) => {
  const harness = createPortalHarness();
  const notificationQueryCalls = [];

  await page.route('**/api/v1/portal/notifications**', async (route) => {
    const url = new URL(route.request().url());
    notificationQueryCalls.push({
      edgeState: url.searchParams.get('edge_state'),
      sort: url.searchParams.get('sort'),
    });

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await harness.install(page);
  await openPortal(page);

  const edgeStateFilter = page.locator('#notificationEdgeStateFilter');
  const sortFilter = page.locator('#notificationSortFilter');
  const applyButton = page.locator('#notificationRefreshButton');
  const resetButton = page.locator('#notificationResetButton');

  await expect(edgeStateFilter).toBeVisible();
  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(0);

  await edgeStateFilter.selectOption('degraded');
  await sortFilter.selectOption('oldest');
  await applyButton.click();

  await expect(edgeStateFilter).toHaveValue('degraded');
  await expect(sortFilter).toHaveValue('oldest');
  await expect
    .poll(() => notificationQueryCalls[notificationQueryCalls.length - 1])
    .toMatchObject({ edgeState: 'degraded', sort: 'oldest' });

  const afterApplyCallCount = notificationQueryCalls.length;
  await resetButton.click();

  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(afterApplyCallCount);
  await expect(edgeStateFilter).toHaveValue('all');
  await expect(sortFilter).toHaveValue('failures_first');
  await expect
    .poll(() => notificationQueryCalls[notificationQueryCalls.length - 1])
    .toMatchObject({ edgeState: 'all', sort: 'failures_first' });

  await page.reload();
  await expect(edgeStateFilter).toBeVisible();
  await expect(edgeStateFilter).toHaveValue('all');
  await expect(sortFilter).toHaveValue('failures_first');
  await expect
    .poll(() => notificationQueryCalls[notificationQueryCalls.length - 1])
    .toMatchObject({ edgeState: 'all', sort: 'failures_first' });
});

test('portal notification route-id persists and reset defaults persist across reload', async ({ page }) => {
  const harness = createPortalHarness();
  const notificationQueryCalls = [];

  await page.route('**/api/v1/portal/notifications**', async (route) => {
    const url = new URL(route.request().url());
    notificationQueryCalls.push({
      routeId: url.searchParams.get('route_id'),
    });

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await harness.install(page);
  await openPortal(page);

  const routeIdFilter = page.locator('#notificationRouteIdFilter');
  const applyButton = page.locator('#notificationRefreshButton');
  const resetButton = page.locator('#notificationResetButton');

  await expect(routeIdFilter).toBeVisible();
  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(0);

  await routeIdFilter.fill('default');
  await applyButton.click();

  await expect(routeIdFilter).toHaveValue('default');
  await expect
    .poll(() => notificationQueryCalls[notificationQueryCalls.length - 1])
    .toMatchObject({ routeId: 'default' });

  await page.reload();
  await expect(routeIdFilter).toBeVisible();
  await expect(routeIdFilter).toHaveValue('default');
  await expect
    .poll(() => notificationQueryCalls[notificationQueryCalls.length - 1])
    .toMatchObject({ routeId: 'default' });

  const afterReloadCallCount = notificationQueryCalls.length;
  await resetButton.click();

  await expect.poll(() => notificationQueryCalls.length).toBeGreaterThan(afterReloadCallCount);
  await expect(routeIdFilter).toHaveValue('');
  await expect
    .poll(() => notificationQueryCalls[notificationQueryCalls.length - 1])
    .toMatchObject({ routeId: 'all' });

  await page.reload();
  await expect(routeIdFilter).toBeVisible();
  await expect(routeIdFilter).toHaveValue('');
  await expect
    .poll(() => notificationQueryCalls[notificationQueryCalls.length - 1])
    .toMatchObject({ routeId: 'all' });
});
