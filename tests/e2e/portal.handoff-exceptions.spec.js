const { test, expect } = require('@playwright/test');

const { applyAdminIdentity, createPortalHarness, openPortal } = require('./portalTestHarness');

test('portal handoff exceptions: ranks blocked PM proposals and highlights the current run', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);
  const handoffPanel = page.locator('.handoff-panel');
  const leadItem = handoffPanel.locator('.handoff-item').first();
  const currentItem = handoffPanel.locator('.handoff-item.current-proposal');

  await expect(page.getByRole('heading', { name: 'Handoff exceptions queue' })).toBeVisible();
  await expect(handoffPanel.getByText('Current proposal exception state', { exact: true })).toBeVisible();
  await expect(handoffPanel.locator('.handoff-hero-value')).toHaveText('Admin retry required');
  await expect(handoffPanel.locator('.handoff-hero-meta')).toHaveText('REC-44 is waiting on an admin or maintainer retry after 1 attempt.');
  await expect(page.getByLabel('Handoff queue view')).toHaveValue('all');
  await expect(page.getByLabel('Handoff queue sort')).toHaveValue('priority');
  await expect(handoffPanel.getByText('More urgent handoffs exist', { exact: true })).toBeVisible();
  await expect(handoffPanel.getByText('REC-77 currently ranks above REC-44 in the exceptions queue.', { exact: true })).toBeVisible();
  await expect(handoffPanel.getByText('View All exceptions', { exact: true })).toBeVisible();
  await expect(handoffPanel.getByText('Source /api/v1/agents/pm/proposals', { exact: true })).toBeVisible();
  await expect(handoffPanel.getByText('Lead proposal REC-77', { exact: true })).toBeVisible();
  await expect(leadItem).toContainText('#1 · REC-77');
  await expect(leadItem).toContainText('Retry limit reached');
  await expect(leadItem).toContainText(/SLA watch|Aging risk/);
  await expect(leadItem).toContainText('Age');
  await expect(leadItem.getByRole('link', { name: 'Open audit trail' })).toBeVisible();
  await expect(leadItem.getByRole('button', { name: 'Run admin retry' })).toBeDisabled();
  await expect(currentItem).toContainText('#3 · REC-44');
  await expect(currentItem).toContainText('Current run proposal');
  await expect(currentItem).toContainText('Admin role required for retry.');
  await expect(currentItem.getByRole('button', { name: 'Open follow-through' })).toBeVisible();
});

test('portal handoff exceptions: admin can trigger queue retry and clear the lead exception', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);
  await applyAdminIdentity(page);

  const handoffPanel = page.locator('.handoff-panel');
  const rec44Item = handoffPanel.locator('.handoff-item.current-proposal');

  await expect(rec44Item).toBeVisible();
  page.once('dialog', async (dialog) => {
    await dialog.accept();
  });
  await rec44Item.getByRole('button', { name: 'Run admin retry' }).click();

  await expect(handoffPanel.getByText('Current proposal is clear', { exact: true })).toBeVisible();
  await expect(handoffPanel.locator('.handoff-item').filter({ hasText: 'REC-44' })).toHaveCount(0);
});

test('portal handoff exceptions: queue view can focus retry limits only', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);

  const handoffPanel = page.locator('.handoff-panel');
  await page.getByLabel('Handoff queue view').selectOption('limit-reached');

  await expect(handoffPanel.getByText('View Retry limits', { exact: true })).toBeVisible();
  await expect(handoffPanel.locator('.handoff-item')).toHaveCount(1);
  await expect(handoffPanel.locator('.handoff-item').first()).toContainText('REC-77');
  await expect(handoffPanel.locator('.handoff-item').first()).toContainText('Retry limit reached');
  await expect(handoffPanel.locator('.handoff-item').first()).not.toContainText('REC-44');
});

test('portal handoff exceptions: queue preferences persist per user identity', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);

  await page.getByLabel('Handoff queue view').selectOption('limit-reached');
  await page.getByLabel('Handoff queue sort').selectOption('age');
  await page.reload();

  await expect(page.getByLabel('Handoff queue view')).toHaveValue('limit-reached');
  await expect(page.getByLabel('Handoff queue sort')).toHaveValue('age');

  await applyAdminIdentity(page);
  await expect(page.getByLabel('Handoff queue view')).toHaveValue('all');
  await expect(page.getByLabel('Handoff queue sort')).toHaveValue('priority');

  await page.getByLabel('Handoff queue view').selectOption('admin-retry');
  await page.getByLabel('Handoff queue sort').selectOption('age');
  await page.reload();

  await expect(page.getByLabel('Handoff queue view')).toHaveValue('admin-retry');
  await expect(page.getByLabel('Handoff queue sort')).toHaveValue('age');

  await page.locator('#identitySubjectInput').fill('portal.user');
  await page.locator('#identityRoleSelect').selectOption('planner');
  await page.locator('#identityOrgInput').fill('demo-org');
  await page.getByRole('button', { name: 'Apply demo identity' }).click();

  await expect(page.getByLabel('Handoff queue view')).toHaveValue('limit-reached');
  await expect(page.getByLabel('Handoff queue sort')).toHaveValue('age');
});

test('portal handoff exceptions: age bucket chips filter queue and persist on reload', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);
  const handoffPanel = page.locator('.handoff-panel');

  const agingRiskChip = handoffPanel.locator('[data-handoff-age-bucket="aging-risk"]');
  await expect(agingRiskChip).toHaveAttribute('aria-pressed', 'false');
  await agingRiskChip.click();
  await expect(agingRiskChip).toHaveAttribute('aria-pressed', 'true');
  await expect(handoffPanel.getByText('Age filter Aging risk', { exact: true })).toBeVisible();
  await expect(handoffPanel.locator('.handoff-item')).toHaveCount(1);
  await expect(handoffPanel.locator('.handoff-item').first()).toContainText('Aging risk');

  await page.reload();
  await expect(handoffPanel.locator('[data-handoff-age-bucket="aging-risk"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(handoffPanel.getByText('Age filter Aging risk', { exact: true })).toBeVisible();
  await expect(handoffPanel.locator('.handoff-item')).toHaveCount(1);

  const allAgesChip = handoffPanel.locator('[data-handoff-age-bucket="all"]');
  await allAgesChip.click();
  await expect(allAgesChip).toHaveAttribute('aria-pressed', 'true');
  const visibleRows = await handoffPanel.locator('.handoff-item').count();
  expect(visibleRows).toBeGreaterThan(1);
});

test('portal handoff exceptions: reset control restores default queue preferences', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);

  await page.getByLabel('Handoff queue view').selectOption('admin-retry');
  await page.getByLabel('Handoff queue sort').selectOption('age');
  await page.locator('[data-handoff-age-bucket="aging-risk"]').click();
  await page.getByRole('button', { name: 'Reset handoff queue preferences' }).click();

  await expect(page.getByLabel('Handoff queue view')).toHaveValue('all');
  await expect(page.getByLabel('Handoff queue sort')).toHaveValue('priority');
  await expect(page.locator('[data-handoff-age-bucket="all"]')).toHaveAttribute('aria-pressed', 'true');
  await page.reload();
  await expect(page.getByLabel('Handoff queue view')).toHaveValue('all');
  await expect(page.getByLabel('Handoff queue sort')).toHaveValue('priority');
  await expect(page.locator('[data-handoff-age-bucket="all"]')).toHaveAttribute('aria-pressed', 'true');
});

test('portal handoff exceptions: shows a failure state when the proposal queue is unavailable', async ({ page }) => {
  const harness = createPortalHarness({
    pmProposalsFailure: 'Proposal queue unavailable',
  });
  await harness.install(page);

  await openPortal(page);
  const handoffPanel = page.locator('.handoff-panel');

  await expect(handoffPanel.getByText('Handoff exceptions unavailable', { exact: true })).toBeVisible();
  await expect(handoffPanel.getByText('We could not load the PM handoff queue right now: Proposal queue unavailable', { exact: true })).toBeVisible();
});