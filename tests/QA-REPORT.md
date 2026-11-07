# Independent QA report

Date: November 7, 2026

Public deployment: https://grandpajackai.github.io/stinc-os-demo/

## Result

13 independent application-runtime checks pass using `node tests/qa-runtime.cjs`. The harness runs the actual application JavaScript in a Node VM with controlled DOM, local-storage, form, and hash-navigation event adapters. It verifies application logic; it is not a substitute for a rendered browser test.

Verified behaviors:

- All 11 page render functions execute.
- All six campaign types produce distinct, relevant plans.
- Campaign creation, activation, completion, and persisted data work.
- Campaign creation from Overview retains its review dialog after the hash-navigation event.
- Adding a source creates three candidate records for the current artist.
- Clip edits persist, scheduling appears in the calendar, and moving back to review works.
- Pitch drafts and pipeline status save correctly.
- Artist campaign and content filtering works.
- Saved fan-capture offers reopen selected.
- Fan briefs and opportunities are scoped to the current artist.
- Paused agents cannot execute; resumed agents can.
- User-authored campaign markup is escaped in rendered HTML.
- Campaign and content status filters return the expected records.

## Public deployment checks

Independently requested the public HTML, JavaScript, stylesheet, portrait PNG, merchandise JPEG, and SVG brand mark. All returned HTTP 200, nonempty bodies, and the expected content types. The deployed JavaScript includes type-specific `campaignPlans`, artist-scoped opportunity filtering, and the campaign navigation regression fix.

Public URLs with `#campaigns`, `#content`, `#calendar`, and `#opportunities` return the application HTML successfully. These are client-side fragment routes; their rendered behavior is covered by application runtime checks, not by HTTP fragment requests.

## Defects found and verified fixed

1. Creating a campaign from Overview initially opened the review dialog before a queued route event closed it. Verified the corrected pending-campaign flow retains the dialog.
2. A saved fan offer initially reset to the first option when reopened. Verified the saved offer is now selected.
3. Fan briefs and opportunities initially shared data across artist workspaces. Verified artist-scoped storage and filtering.

## Browser verification limitation

This independent QA agent could enumerate the user's Chrome browser, but documented tab creation/binding failed with a tool-level timeout-options error. The in-app browser available to the root agent was not exposed to this QA agent. Consequently, this report makes no independent screenshot, mobile-layout, keyboard, or real-browser interaction claims. The root agent is responsible for the separate rendered-browser review.

The application intentionally uses sample performance, finance, opportunity archetypes, storyboard clips, and simulated agent activity. Live publishing, real clipping, outreach delivery, connected revenue, authentication, and a shared database are not implemented by this public static demo.
