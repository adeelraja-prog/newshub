# Adeel Raja News Hub — Facebook Posters Only

This repository workflow collects fresh news from configured sources, applies editorial checks, writes Urdu/English poster copy, renders a branded Adeel Raja news poster, and publishes the image to the Facebook Page feed.

## Current scope
- Facebook Page photo posts only.
- One fixed premium poster design; content changes, design does not.
- Urdu headline first, English context, source credit, Adeel Raja branding.
- Scheduled collection and publishing; one due poster per run, subject to editorial quality and spacing rules.
- No YouTube discovery/download/promotion.
- No Reels or video rendering.
- No WhatsApp bridge or WhatsApp publishing.
- No Google image generation dependency.

## Required GitHub Actions secrets
- `GEMINI_API_KEY` (editorial copy/analysis)
- `FB_PAGE_ID`
- `FB_PAGE_TOKEN` (Page token with photo publishing permissions)

## Run
Open **Actions → news-hub → Run workflow**. Keep dry-run enabled to generate preview posters without publishing. Turn dry-run off only when ready for Facebook publishing.

Poster previews and the run report are uploaded as a workflow artifact.
