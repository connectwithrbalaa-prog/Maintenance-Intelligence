const { test, expect } = require('@playwright/test');

const { createPortalHarness, openPortal } = require('./portalTestHarness');

test('portal workflow nav: jumps between PM, repair plan, and follow-through sections', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);

  const workflowNav = page.getByLabel('Run workflow navigation');

  await expect(workflowNav).toBeVisible();

  await workflowNav.getByRole('button', { name: 'Open repair plan' }).click();
  await expect.poll(async () => page.evaluate(() => window.location.hash)).toBe('#repairPlanSection');
  await expect.poll(async () => page.evaluate(() => document.activeElement && document.activeElement.id)).toBe('repairPlanSection');

  await workflowNav.getByRole('button', { name: 'Open follow-through' }).click();
  await expect.poll(async () => page.evaluate(() => window.location.hash)).toBe('#followThroughSection');
  await expect.poll(async () => page.evaluate(() => document.activeElement && document.activeElement.id)).toBe('followThroughSection');

  await workflowNav.getByRole('button', { name: 'Open approval history' }).click();
  await expect.poll(async () => page.evaluate(() => window.location.hash)).toBe('#approvalHistorySection');
  await expect.poll(async () => page.evaluate(() => document.activeElement && document.activeElement.id)).toBe('approvalHistorySection');

  expect(harness.feedbackPosts).toHaveLength(0);
});