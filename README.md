# STINC OS — Artist operations concept

A free, static, interactive presentation demo for a conversation with EVOL / STINC TEAM. This is an independent concept, not an official STINC TEAM product or endorsement.

## Run

Serve this directory using `python3 -m http.server 4173`. Open `http://localhost:4173`. No dependency installation, paid API, or build step is required.

## Included

- Label roster and artist context switching
- Campaign creation, rollout plans, activation and completion
- Source references and explicitly simulated clip storyboards
- Editable hooks/captions, platform selection and demo calendar scheduling
- Separate brand and PR pipelines, editable saved pitch drafts
- Fan-capture briefs, commerce overview and sample revenue ledger
- Visible simulated agent history, pause/resume controls and execution preferences
- Local browser persistence and downloadable JSON workspace export
- Responsive navigation, keyboard dialog focus management and reduced-motion support

## Boundaries

Metrics, finance, scores, prospects, agent activity and content generation are illustrative. No account is connected. The app does not perform AI inference, process videos, send outreach, publish social posts, collect real fan information, collect money or reconcile royalties. Schedules are stored plans and do not run background jobs. The demo is single-browser local storage, without authentication or a shared backend. Do not enter confidential information into a public demo.

Only public artist identity and imagery are included. The second roster slot is a fictional workspace, not another real STINC TEAM artist. Images are stored locally to avoid hotlink failures; attribution and research are in `research/market-research.md`.

## Deployment

This directory is the complete GitHub Pages publication root. `.nojekyll` disables unnecessary processing. Hash navigation supports deep links and refreshes without server rewrite configuration. No secret or runtime configuration is needed.

## Production path

1. Run a service-led pilot with one artist and one measurable campaign. Agree on account access, baseline data, goals, publishing permissions and outreach review.
2. Add authenticated multi-tenant workspaces, a database, encrypted credential storage, roles, audit history and backups.
3. Integrate supported provider APIs and a clipping provider, starting with the sources and destinations the pilot actually uses.
4. Add a durable job queue, retries, idempotency, rate limits, approval gates and delivery receipts. Replace sample metrics with timestamped provider data.
5. Add consent-aware fan CRM and Shopify integration, followed by verified opportunity research and reporting/reconciliation imports.
6. Productize validated workflows with onboarding, plans, billing, limits and support. Keep advanced storefront design and mobile apps for later phases.

The hosting demo is free. Production AI, video processing, messaging, account integrations and backend infrastructure may have operating costs.
