# Changelog

## Unreleased

### Added

- Added a command-center shell with grouped sidebar navigation.
- Added the PM Advisor page for reviewing and approving maintenance proposals.
- Added the Outcomes page for KPI, trend, and bad-actor analytics.
- Added the System Health page for deep backend health polling.
- Added the shared GenAICallout component for AI-generated recommendation presentation.

### Changed

- Expanded the RunDetail experience into a richer RCA runs workflow.
- Added a typewriter-style summary reveal in the run detail view.
- Added user feedback actions for recommendation review.
- Updated the app routing to center the experience on `/runs` and command-center navigation.
- Extended `src/lib/api.ts` with compatibility exports required by the imported pages.

### Build

- Installed and validated the frontend build with `recharts` included.
- Verified the app builds successfully in production mode.
