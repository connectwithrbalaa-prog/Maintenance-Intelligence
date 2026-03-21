const { test, expect } = require('@playwright/test');

const { applyReadOnlyIdentity, createPortalHarness, openPortal } = require('./portalTestHarness');

test('portal role guards: read-only users see blocked approval and feedback actions', async ({ page }) => {
  const harness = createPortalHarness();
  await harness.install(page);

  await openPortal(page);
  await applyReadOnlyIdentity(page);

  const pmSuggestionsSection = page.locator('#pmSuggestionsSection');
  const feedbackSection = page.locator('.section').filter({ has: page.getByRole('heading', { name: 'Feedback loop' }) });

  await expect(page.locator('#identityBadge')).toContainText('Role viewer');
  await expect(page.getByRole('button', { name: 'Approval restricted' })).toBeDisabled();
  await expect(pmSuggestionsSection.getByText('Current role viewer is read-only and cannot approve PM proposals.').first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Submit feedback' })).toBeDisabled();
  await expect(feedbackSection.getByText('Current role viewer is read-only and cannot submit feedback.').first()).toBeVisible();

  expect(harness.feedbackPosts).toHaveLength(0);
});
