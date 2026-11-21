# STINC OS product plan

This repository is the product surface for Ralfy the Plug / STINC TEAM. The local portal at `127.0.0.1:8790` (`stinc-platform/dashboard/`) stays the admin tool on Brandon's Mac. GitHub Pages (`https://grandpajackai.github.io/stinc-os-demo/`) is the public workspace.

Phase 1 is this document, a stdlib exporter, a sanitized `data/live.json`, and the existing UI reading that file. Later phases turn on the local OAuth broker and fold provider revenue into the ledger.

## Architecture

```
Brandon's Mac
  ~/Projects/content-engine/brands/ralfy-the-plug/     clips, viral scores, render tracker
  ~/Projects/stinc-platform/                           catalog, emails, sponsor tracker, fan pages
  127.0.0.1:8790   admin portal (unchanged, local only)
  127.0.0.1:8791   OAuth broker (this repo, off until client IDs exist)
        |
        |  python3 tools/export_live_data.py
        v
  data/live.json + assets/email-previews/   (sanitized, committed, public)
        |
        v
  GitHub Pages  index.html + app.js         reads live.json, falls back to sample rows
```

Nothing in the static site can send email, post a clip, charge a card, or hold a token. Ongoing operations stay on the Mac: the content engine, the sponsor sender, and the portal. This site only displays a sanitized snapshot plus the demo workspace Brandon already had (campaign drafts, calendar plans, pitch templates, agent controls).

The exporter is stdlib Python so it can be called from the existing launchd jobs (`com.gilventures.contentengine.ralfy`, `com.gilventures.stinc.ralfysponsors`, `com.gilventures.stinc.autosync`) without a new dependency. It does not push git by itself.

## Data flow

`tools/export_live_data.py` reads, in order:

| Input | Path | Used for |
|---|---|---|
| Public platform counts | `stinc-platform/data/platforms.json` | YouTube, Spotify, Instagram, and the other public profiles |
| Catalog | `stinc-platform/ecommerce/data/catalog.json` | Product title, store URL, store price, stock, image |
| Email specs | `stinc-platform/ecommerce/emails/specs/*.json` | Series, segment, subject, preheader |
| Email HTML | `stinc-platform/ecommerce/emails/*.html` | Gate for preview PNGs only. The HTML is not copied |
| Preview PNG | `ecommerce/emails/previews/*-mobile.png` | Copied only when the HTML twin passes the safety scan |
| Sponsor tracker | `campaigns/ralfy-sponsors/tracker.csv`, else `tracker.sample.csv` | Counts only |
| Daily cap | `campaigns/ralfy-sponsors/config.json` key `daily_cap` only | Integer cap |
| Clips | `content-engine/.../candidates/*.md` and `candidates-music/*.md` | Title, hook, viral score, duration, public watch URL |
| Fallback clips | `stinc-platform/dashboard/data/dashboard.json` `content.studio` | Used only when the brand folder is not on this machine |

Clip markdown is parsed with the same C-line shape as `scripts/candidates_lib.py` (`- [ ] C1 | viral N | ...`). Local paths, transcripts, and "picked by" lines are dropped. A `yt-VIDEOID` stem becomes `https://www.youtube.com/watch?v=VIDEOID`.

The page loads `data/live.json` with `fetch`. If the file is missing, invalid, or the artist switch is the sample roster slot, the original sample figures stay, with a Sample badge.

`live.json` schema is `stinc-os.live.v1`:

- `highlights` and `pipeline_highlights` — the Overview numbers
- `clips` — Content studio
- `sponsors` — integer counts for Campaigns and Opportunities
- `commerce.products` and `commerce.emails` — Commerce
- `fans.accounts` — official profiles plus Ralfy Clips fan pages
- `platforms` and `videos` — public profile facts
- `sources` — which local inputs were present (`content-engine`, `dashboard-snapshot`, or `missing`)

## Security model

This site is public. The exporter refuses to write `data/live.json` if the finished document still contains any of:

- an email address, including a masked `name@domain` shape
- a phone number
- a street address (`123 Name St` and the same suffixes)
- a secret-shaped string (private key, `sk-`, `ghp_`, `AKIA`, `xox`, `api_key=` / `password=` / `token=` assignments)
- a home-directory path (`/Users/`)
- a forbidden object key (`contact_email`, `contact_name`, `brand`, `deal_route`, `margin`, `password`, `access_token`, and the rest in `tools/public_safety.py`)

Sponsor rows never become records in the snapshot. The tracker is reduced to counts: sent, queued, pending approval, replies, deals, needs-a-form, watchlist, skipped, tracked, and the daily cap. Brand names, contact names, inboxes, pitch status per brand, deal terms, and deal prices are not copied. They are also used as private needles: if one of those strings appears in a product title, email subject, clip hook, or other public field, that field or row is dropped. A final scan repeats the check and aborts the write if anything remains.

Legal-hold rows are omitted before the counts. That includes `status=on_hold_legal`, tracker group `H`, and notes that mark a legal hold or gambling. They are not named and they are not included in `tracked`.

Catalog rows with `tribute_merch: true` are omitted. Words that appear only on those rows (and not on the rows that remain) become extra needles, so the same names are dropped from video titles, clips, and email lines. An optional deny file is applied the same way and is never copied:

- `~/.local/share/stinc-ralfy/public-deny.txt`
- or `STINC_PUBLIC_DENY`
- or `stinc-platform/data/public-deny.txt`

One phrase per line. Use it for anything else that must not appear on the public site.

Store contact emails, return addresses, SMTP settings, signatures, and the rest of `config.json` are not read except the integer `daily_cap`.

Email preview PNGs are copied only when the matching HTML file exists and that HTML passes the same scan. The current drafts put a contact email and a street address in the footer, so the exporter withholds the PNGs and says so on the Commerce page. Subjects and preheaders that themselves pass the scan are still listed. Clearing the footer on the Mac and re-running the exporter is what publishes the images.

OAuth tokens, client secrets, and client IDs are not in this repo. The broker below stores them under `~/.local/share/stinc-os/`.

## What is real vs sample

Real when `data/live.json` is present, Ralfy workspace:

| Surface | Real | Still sample |
|---|---|---|
| Overview | YouTube subscribers, Spotify monthly listeners, Instagram followers, store product count, clip-option count, rendered count, sponsors sent, merch-email count | The trend chart and its period comparison. The chart is badged Sample |
| Content studio | Candidate cards with viral score, duration, and the public YouTube URL | The original storyboard cards, badged in the note above them. Scheduling them is still a local demo plan |
| Campaigns | Aggregate counts (sent, queued, clip options, review queue, email drafts) | The campaign cards and their rollout plans |
| Opportunities | The four aggregate counts. Legal-hold rows are not in the total | The archetype table and its dollar ranges, badged Sample. Those ranges are not deals |
| Commerce | Public catalog subset with store prices, plus the 14 email drafts (subject, series, segment, safe preheader) | Order, conversion, and revenue figures when no snapshot is loaded. With a snapshot, those four slots are the catalog counts instead |
| Fans & community | Official public handles and the Ralfy Clips fan-page status. Posting stays off | Owned-fan, email, and SMS totals, and the three sample segments |
| Calendar | — | Every scheduled row |
| Revenue | — | The whole ledger |
| Agent workforce | — | Activity and the four demo agents |
| Artist roster | Clip count for Ralfy when a snapshot is loaded | The emerging-artist slot, and campaign counts |
| Connections | Honest connector states (below) | No live account is connected |

The emerging-artist roster slot stays entirely sample. It is not a real artist.

The committed snapshot was built from the private repo's checked-in files: `platforms.json`, `catalog.json`, `fan_pages.json`, email specs, `tracker.sample.csv` (the masked tracker in git; the live `tracker.csv` is Mac-only), and `dashboard.json` `content.studio` because `~/Projects/content-engine` is not on the machine that produced this commit. `sources.content` is `dashboard-snapshot` until the Mac command below runs against the brand folder. Re-running it on the Mac switches that to `content-engine` and refreshes scores from the candidate files.

Public facts included: YouTube `164K` subscribers, Spotify `383,111` monthly listeners, Instagram `193,835` followers, 37 products on stincteamtgf.com (27 listed here after the private filters), 18 clip options, 1 rendered, 3 sponsor first-touches sent, 5 queued, 0 replies, daily cap 3, 14 merch email drafts. Preview images are withheld.

## OAuth plan

The broker is `tools/oauth_broker.py`. It binds `127.0.0.1:8791` only, beside the portal on `8790`. Client IDs live in `~/.local/share/stinc-os/oauth-clients.json`. Tokens live in `~/.local/share/stinc-os/tokens/<provider>.json` with mode `0600`. State is single-use and expires after 10 minutes. PKCE S256 is required. The authorize URL gets the code challenge, never the verifier. The public site has no broker URL and does not start a login. Connectors stay disabled until a client id is present. Do not connect a real account from this phase.

Example client file, kept off git:

```json
{
  "youtube": {"client_id": ""},
  "shopify": {"client_id": "", "shop": "your-store.myshopify.com"},
  "instagram": {"client_id": ""}
}
```

| Connector | State in the UI | API | What has to happen before it can connect |
|---|---|---|---|
| Spotify for Artists | Coming soon / manual import | No public API. The public Spotify Web API does not expose Spotify for Artists analytics | A partner API, or a manual export Brandon drops on the Mac |
| Apple Music | Coming soon / manual import | Apple Music analytics are not a free public API | Manual catalog/analytics import |
| YouTube Music | Disabled | YouTube Data API OAuth (same Google client as YouTube) | Client ID in the broker file. Read-only scope |
| YouTube | Disabled | YouTube Data API, PKCE, `youtube.readonly` | Same client ID. No uploads in this design |
| Shopify | Disabled | Shopify app OAuth plus Storefront API for public product reads | Client ID and `shop` domain. Orders stay read-only when a later phase turns it on |
| Your website or merch store | Manual import | None | An `https://` URL saved in this browser only. The page does not fetch it |
| Instagram | Disabled | Meta Graph API | Client ID, then Meta app review before insights are real. No login until then |
| TikTok | Coming soon / manual import | Not an open free API; app review | Manual import |
| X | Coming soon / manual import | No free analytics API for this workspace | Manual import. Nothing is posted |
| Clipping channels | Local snapshot when `live.json` has candidates, otherwise not connected | File drop into the content engine, not OAuth | Already local. This site never posts |

Phase 2 turns the broker on for YouTube, Shopify, and Meta after Brandon fills client IDs, and writes connection status (connected boolean and a public handle, never the token) into the next `live.json`. Revenue consolidation is the same phase: replace the sample ledger with Shopify order totals and YouTube/Spotify figures that actually come from those connections. Until then the ledger stays sample on purpose.

## Phases

1. **This change.** Plan, exporter, safety tests, `live.json` on Overview, Content studio, Campaigns, Opportunities, Commerce, and Fans. Sample badges everywhere else. Connections shell with disabled / coming soon / manual states. Broker code ships inert.
2. **OAuth live, still local.** Brandon adds client IDs. Broker can complete PKCE for YouTube, Shopify, and Meta. Tokens stay on the Mac. The exporter adds a connection block with no secrets. Revenue starts using those totals and drops the sample ledger for any source that is actually connected.
3. **Fan CRM and posting, still gated.** Consented fan capture, Shopify order reconciliation, and clip posting only after an explicit approval flag. The public site still does not send or post. Gambling sponsors stay omitted until counsel says otherwise.

## Refresh command

From a checkout of this repo on the Mac (defaults are `$HOME/Projects/stinc-platform` and `$HOME/Projects/content-engine/brands/ralfy-the-plug`, and the script writes into its own repo):

```
python3 ~/Projects/stinc-os-demo/tools/export_live_data.py --platform ~/Projects/stinc-platform --brand ~/Projects/content-engine/brands/ralfy-the-plug
```

That writes `data/live.json`. Commit and push this repo when the snapshot should update GitHub Pages. The command does not send, post, or push.

## Tests

```
python3 -m unittest tests.test_export_live_data tests.test_oauth_broker tests.test_live_public
node tests/qa-runtime.cjs
```

- Exporter fixtures cover a brand folder, the dashboard fallback, withheld preview images, legal-hold omission, and a refuse-to-write path.
- `tests/test_live_public.py` fails if the committed `data/live.json` contains an email, phone number, street address, secret-shaped string, forbidden key, or `/Users/`.
- `tests/qa-runtime.cjs` loads every page and checks the live snapshot path without a network fetch.
