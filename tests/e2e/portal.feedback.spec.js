const { test, expect } = require('@playwright/test');

const { applyAdminIdentity, createPortalHarness, openPortal } = require('./portalTestHarness');

test('portal feedback: submits edits, refreshes history, and updates analytics', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);
  await applyAdminIdentity(page);

  await expect(page.getByText('No operator feedback recorded yet for this run.')).toBeVisible();

  await page.locator('#feedbackActionSelect').selectOption('edited');
  await page.locator('#feedbackReasonInput').fill('Adjusted after field inspection');
  await page.locator('#feedbackTitleInput').click();
  await page.locator('#feedbackTitleInput').pressSequentially('Reinspect bearing housing');
  await expect(page.locator('#feedbackTitleInput')).toHaveValue('Reinspect bearing housing');
  await page.locator('#feedbackActionsInput').fill('Inspect lubrication\nCapture thermography');
  await page.getByRole('button', { name: 'Submit feedback' }).click();

  await expect(page.locator('ol.feedback-history .feedback-item')).toHaveCount(1);
  await expect(page.getByText('Edited 1')).toBeVisible();
  await expect(page.locator('ol.feedback-history')).toContainText('Actor demo.admin');
  await expect(page.locator('ol.feedback-history')).toContainText('Adjusted after field inspection');
  await expect(page.locator('ol.feedback-history')).toContainText('title: Reinspect bearing housing');
  await expect(page.locator('ol.feedback-history')).toContainText('immediate_actions: Inspect lubrication, Capture thermography');
  await expect(page.getByText('Range 50% to 100% across the current window.')).toBeVisible();

  expect(harness.feedbackPosts).toHaveLength(1);
  expect(harness.outcomesCalls).toBeGreaterThan(1);
});