# Adeel Raja News Hub bot (free)

Every 30 minutes: collect news -> Gemini scores and picks the best story -> writes an Urdu + English
headline and caption -> draws a branded poster -> posts it to your Facebook page and WhatsApp channel.
Breaking stories go out immediately. Max 24 posts a day, quiet 1-6 AM PKT.

## Setup
1. Create a **public** GitHub repo and upload everything (keep `.github`, `assets`, `posters`).
2. Settings > Secrets and variables > Actions, add:
   - `GEMINI_API_KEY` (free, aistudio.google.com)
   - `FB_PAGE_ID`, `FB_PAGE_TOKEN` (long-lived Page token with pages_manage_posts)
   - `WHATSAPP_BRIDGE_URL`, `WHATSAPP_BRIDGE_TOKEN` (after you set up the `bridge/` folder, see bridge/README.md)
3. Actions > news-hub > Run workflow with **dry_run ON**. When it finishes, download the
   `posters` artifact and check the posters.
4. Run again with dry_run OFF, or let the 30-minute schedule take over.

Posters from the last 3 days are saved in `posters/` (open them on your phone to post by hand
to YouTube Community, which has no API).

Options (env): MAX_PER_RUN (1), MAX_BREAKING (3), MAX_PER_DAY (24), MIN_SCORE (6),
QUIET_HOURS ("1-6"), HANDLE ("@adeelrajaviews").
Edit `sources.py` to change sources, `poster.py` to change the design.
