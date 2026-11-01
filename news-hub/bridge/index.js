// WhatsApp Channel bridge: the news bot POSTs a poster + caption here, this posts it to your channel.
// UNOFFICIAL (Baileys). Use a separate number that is an admin of the channel.
import express from "express";
import pino from "pino";
import QRCode from "qrcode";
import { MongoClient } from "mongodb";
import makeWASocket, {
  Browsers,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
} from "@whiskeysockets/baileys";
import { useMongoAuthState } from "./mongoAuth.js";

const { MONGODB_URI, BRIDGE_TOKEN, CHANNEL_JID, PORT = 3000 } = process.env;
if (!MONGODB_URI || !BRIDGE_TOKEN) {
  console.error("Set MONGODB_URI and BRIDGE_TOKEN");
  process.exit(1);
}

const logger = pino({ level: "warn" });
let sock = null;
let connected = false;
let lastQR = null;
let auth = null;

async function start() {
  const client = new MongoClient(MONGODB_URI);
  await client.connect();
  const coll = client.db("newshub").collection("wa_auth");
  auth = await useMongoAuthState(coll);
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    logger,
    auth: { creds: auth.state.creds, keys: makeCacheableSignalKeyStore(auth.state.keys, logger) },
    browser: Browsers.ubuntu("Chrome"),
    markOnlineOnConnect: false,
    syncFullHistory: false,
  });

  sock.ev.on("creds.update", auth.saveCreds);
  sock.ev.on("connection.update", async ({ connection, lastDisconnect, qr }) => {
    if (qr) lastQR = qr;
    if (connection === "open") {
      connected = true;
      lastQR = null;
      console.log("WhatsApp connected");
    }
    if (connection === "close") {
      connected = false;
      const code = lastDisconnect?.error?.output?.statusCode;
      console.log("WhatsApp closed, code", code);
      if (code === DisconnectReason.loggedOut) {
        await auth.clear();
        console.log("Logged out: login cleared, scan a new QR at /qr");
      }
      setTimeout(() => start().catch(console.error), 3000);
    }
  });
}

const app = express();
app.use(express.json({ limit: "15mb" }));

const authed = (req, res, next) => {
  const t = (req.headers.authorization || "").replace("Bearer ", "") || req.query.token;
  if (t !== BRIDGE_TOKEN) return res.status(401).json({ error: "unauthorized" });
  next();
};

app.get("/", (_req, res) => res.send("ok"));
app.get("/health", (_req, res) => res.json({ connected }));

app.get("/qr", authed, async (_req, res) => {
  if (connected) return res.send("<h3>Already connected</h3>");
  if (!lastQR) return res.send('<meta http-equiv="refresh" content="3"><h3>Waiting for QR...</h3>');
  const img = await QRCode.toDataURL(lastQR, { width: 320 });
  res.send(`<meta http-equiv="refresh" content="15"><h3>WhatsApp > Linked devices > Link a device</h3><img src="${img}">`);
});

// Turn a channel invite code (the part after whatsapp.com/channel/) into the channel id.
app.get("/channel-id", authed, async (req, res) => {
  try {
    if (!connected) return res.status(503).json({ error: "not connected" });
    const meta = await sock.newsletterMetadata("invite", String(req.query.invite || ""));
    res.json({ id: meta.id, name: meta.name });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

app.post("/send", authed, async (req, res) => {
  try {
    if (!connected) return res.status(503).json({ error: "whatsapp not connected" });
    if (!CHANNEL_JID) return res.status(500).json({ error: "CHANNEL_JID not set" });
    const { caption = "", image_b64 } = req.body || {};
    const content = image_b64
      ? { image: Buffer.from(image_b64, "base64"), caption }
      : { text: caption };
    await sock.sendMessage(CHANNEL_JID, content);
    res.json({ ok: true });
  } catch (e) {
    console.error("send failed", e);
    res.status(500).json({ error: String(e) });
  }
});

app.listen(PORT, () => console.log("bridge listening on", PORT));
start().catch((e) => {
  console.error(e);
  process.exit(1);
});
