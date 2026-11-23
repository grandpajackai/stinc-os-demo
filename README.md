# STINC OS

Public artist workspace for Ralfy the Plug / STINC TEAM. GitHub Pages serves this directory. The admin portal stays on the Mac at `127.0.0.1:8790`.

## Run

Serve this directory with `python3 -m http.server 4173` and open `http://localhost:4173`. No install and no build. The page reads `data/live.json` when that file is present and otherwise keeps the sample rows, which are badged Sample.

Refresh the snapshot on the Mac (stdlib only):

```
python3 ~/Projects/stinc-os-demo/tools/export_live_data.py --platform ~/Projects/stinc-platform --brand ~/Projects/content-engine/brands/ralfy-the-plug
```

The plan, the privacy rules, and the connector states are in `docs/plans/STINC_OS_PRODUCT.md`.

## Included

- Public snapshot on Overview, Content studio, Campaigns, Opportunities, Commerce, and Fans, including the fan-page network, upcoming queue, content pipeline, score breakdown, activity feed, and sponsor/form counts
- Sample rows kept and badged where a live source does not exist yet (chart, calendar, revenue, agents)
- Connections shell for streaming, Shopify or a store URL, socials, and clipping. OAuth stays off until client IDs are set on the Mac
- Campaign drafts, clip scheduling, pitch drafts, roster switching, and local JSON export
- Responsive navigation, keyboard dialog focus, and reduced-motion support

## Boundaries

`data/live.json` is a sanitized public snapshot: audience counts, the fan-page network and upcoming post queue, the content pipeline and top-clip scores, an activity feed, sponsor and form totals (counts only), the merch catalog, and clip candidates. Sponsor or prospect names, contacts, emails, phones, deal terms, and legal-hold rows are not in it. Rows still marked Sample (the chart, campaign cards, calendar, revenue ledger, owned-fan totals, demo storyboards) are not live measurements.

No account is connected. Connectors stay disabled until client IDs exist on the Mac. The site does not send email, post video, collect fan records, or take payment. Do not enter confidential information into this public site.

Only public artist identity and imagery are included. The second roster slot is a fictional workspace, not another real STINC TEAM artist. Images are stored locally to avoid hotlink failures; attribution and research are in `research/market-research.md`.

## Deployment

This directory is the complete GitHub Pages publication root. `.nojekyll` disables unnecessary processing. Hash navigation supports deep links and refreshes without server rewrite configuration. No secret or runtime configuration is needed.

## Tests

```
python3 -m unittest tests.test_export_live_data tests.test_oauth_broker tests.test_live_public
node tests/qa-runtime.cjs
```

## Production path

Phase 1 is the sanitized snapshot in this repo. Phase 2 is the local OAuth broker and a real revenue ledger. Details are in `docs/plans/STINC_OS_PRODUCT.md`. Hosting this site is free. Provider APIs, once a client ID is added, may have their own terms.
