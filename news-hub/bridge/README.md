# WhatsApp Channel bridge (free, unofficial)

Receives a poster + caption from the news bot and posts it to your WhatsApp Channel.

## Before you start
- WhatsApp has no official API for Channels. This uses an unofficial library, so the number can be banned.
- Use a SEPARATE number, and make it an admin of your channel (Channel > Admins > add).

## Setup
1. **MongoDB Atlas** (free M0 cluster, no card): create a cluster, a database user, and under
   Network Access allow 0.0.0.0/0. Copy the connection string (`mongodb+srv://...`).
2. **Deploy on Render** (free Web Service, no card): new Web Service from this folder/repo,
   Runtime = Docker. Environment variables:
   - `MONGODB_URI`  your Atlas string
   - `BRIDGE_TOKEN` a long random password you choose
   - `CHANNEL_JID`  (leave empty for now)
3. **Link the number:** open `https://YOUR-APP.onrender.com/qr?token=BRIDGE_TOKEN`, then on the
   separate phone: WhatsApp > Linked devices > Link a device > scan.
4. **Find the channel id:** open your channel link `whatsapp.com/channel/XXXXXXXX`, copy the code
   after /channel/, then open
   `https://YOUR-APP.onrender.com/channel-id?token=BRIDGE_TOKEN&invite=XXXXXXXX`.
   Put the returned id (ends with `@newsletter`) into `CHANNEL_JID` on Render and redeploy.
5. **Keep it awake:** free cron-job.org (or UptimeRobot): ping `https://YOUR-APP.onrender.com/health`
   every 10 minutes.
6. In the GitHub repo secrets of the news bot add `WHATSAPP_BRIDGE_URL` (the Render URL, no trailing
   slash) and `WHATSAPP_BRIDGE_TOKEN`.

If WhatsApp logs the number out, the bridge clears the login: open /qr and scan again.
