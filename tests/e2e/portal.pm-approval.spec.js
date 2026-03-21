const { test, expect } = require('@playwright/test');

const { applyAdminIdentity, createPortalHarness, openPortal } = require('./portalTestHarness');

test('portal PM approval: approves proposal and loads paginated audit history', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);
  await applyAdminIdentity(page);

  await expect(page.getByRole('button', { name: 'Approve PM proposal' })).toBeVisible();

  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('Approve the PM proposal for RUN-123?');
    await dialog.accept();
  });

  await page.getByRole('button', { name: 'Approve PM proposal' }).click();

  await expect(page.getByText('PM proposal approved and handed off to the CMMS backend')).toBeVisible();
  await expect(page.locator('.approval-connector-note')).toContainText('Draft work order created');
  await expect(page.locator('.audit-badge.actor').filter({ hasText: 'Actor demo.admin' })).toBeVisible();
  await expect(page.locator('.audit-badge.origin-admin').filter({ hasText: 'Origin admin' })).toBeVisible();
  const followThroughSection = page.locator('.section').filter({ has: page.getByRole('heading', { name: 'Recommendation follow-through snapshot' }) });
  await expect(followThroughSection).toContainText('Draft work order created');
  await expect(followThroughSection).toContainText('WO-REC-44');
  await expect(page.getByRole('button', { name: 'Load more' })).toBeVisible();

  await page.getByRole('button', { name: 'Load more' }).click();
  await expect(page.getByText('All recorded audit attempts are visible.')).toBeVisible();
  await expect(page.getByText('Malformed payload')).toBeVisible();
  await expect(page.getByText('Showing 4 of 4 attempts')).toBeVisible();

  expect(harness.feedbackPosts).toHaveLength(0);
});