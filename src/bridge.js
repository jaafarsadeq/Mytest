import fs from 'node:fs';
import path from 'node:path';
import express from 'express';
import qrcode from 'qrcode-terminal';
import pkg from 'whatsapp-web.js';
import { config } from './config.js';
import { saveMessage, upsertChat, listChats, getRecentMessages, searchMessages } from './db.js';
import { sendNtfy } from './ntfy.js';

const { Client, LocalAuth } = pkg;

fs.mkdirSync(config.sessionPath, { recursive: true });

const puppeteerOpts = {
  headless: true,
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
};
if (process.env.PUPPETEER_EXECUTABLE_PATH) {
  puppeteerOpts.executablePath = process.env.PUPPETEER_EXECUTABLE_PATH;
}

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: config.sessionPath }),
  puppeteer: puppeteerOpts,
});

let clientReady = false;

client.on('qr', (qr) => {
  console.log('\n=== Scan this QR with WhatsApp on your phone ===');
  console.log('WhatsApp → Settings → Linked Devices → Link a Device\n');
  qrcode.generate(qr, { small: true });
});

client.on('authenticated', () => console.log('[wa] authenticated.'));
client.on('auth_failure', (m) => console.error('[wa] auth failure:', m));
client.on('disconnected', (reason) => {
  console.error('[wa] disconnected:', reason);
  clientReady = false;
});

client.on('ready', async () => {
  clientReady = true;
  console.log('[wa] client ready.');
  try {
    const chats = await client.getChats();
    for (const chat of chats) {
      upsertChat({
        id: chat.id._serialized,
        name: chat.name || chat.id.user,
        is_group: chat.isGroup,
        last_message_ts: chat.timestamp ? chat.timestamp * 1000 : 0,
        unread_count: chat.unreadCount,
      });
    }
    console.log(`[wa] indexed ${chats.length} chats.`);
  } catch (err) {
    console.error('[wa] failed to index chats:', err.message);
  }
});

async function handleIncoming(message) {
  try {
    const chat = await message.getChat();
    const contact = await message.getContact();
    const isGroup = chat.isGroup;
    const chatName = chat.name || contact.pushname || contact.number || 'Unknown';
    const senderName = contact.pushname || contact.name || contact.number || 'Unknown';
    const fromMe = !!message.fromMe;

    const row = {
      id: message.id._serialized,
      chat_id: chat.id._serialized,
      chat_name: chatName,
      is_group: isGroup ? 1 : 0,
      sender_id: message.author || message.from || '',
      sender_name: senderName,
      from_me: fromMe ? 1 : 0,
      body: message.body || '',
      type: message.type || 'chat',
      has_media: message.hasMedia ? 1 : 0,
      timestamp: (message.timestamp || Math.floor(Date.now() / 1000)) * 1000,
    };
    saveMessage(row);

    if (shouldNotify(row)) {
      await pushToPhone(row);
    }
  } catch (err) {
    console.error('[wa] handleIncoming failed:', err.message);
  }
}

function shouldNotify(row) {
  if (row.from_me && !config.filters.includeFromMe) return false;
  if (config.filters.onlyDirect && row.is_group) return false;
  const muted = config.filters.muteChats;
  if (muted.length) {
    if (muted.includes(row.chat_id) || muted.includes(row.chat_name)) return false;
  }
  if (!row.body && !row.has_media) return false;
  return true;
}

async function pushToPhone(row) {
  const isGroup = !!row.is_group;
  const title = isGroup
    ? `${row.chat_name} — ${row.sender_name}`
    : row.sender_name || row.chat_name;
  let body = row.body || '';
  if (!body && row.has_media) body = `[${row.type || 'media'}]`;
  if (body.length > 400) body = `${body.slice(0, 397)}...`;

  const tags = ['speech_balloon'];
  if (isGroup) tags.push('busts_in_silhouette');
  if (row.has_media) tags.push('frame_with_picture');

  await sendNtfy({ title, message: body, tags, priority: 'default' });
}

client.on('message', handleIncoming);
client.on('message_create', (m) => {
  if (m.fromMe) handleIncoming(m);
});

const app = express();
app.use(express.json({ limit: '256kb' }));

app.get('/health', (_req, res) => {
  res.json({ ok: true, ready: clientReady });
});

app.get('/chats', (req, res) => {
  const limit = Math.min(Number(req.query.limit) || 50, 500);
  const search = String(req.query.search || '');
  res.json({ chats: listChats({ limit, search }) });
});

app.get('/messages', (req, res) => {
  const limit = Math.min(Number(req.query.limit) || 20, 500);
  const chatId = req.query.chatId ? String(req.query.chatId) : undefined;
  res.json({ messages: getRecentMessages({ chatId, limit }) });
});

app.get('/messages/search', (req, res) => {
  const q = String(req.query.q || '');
  const limit = Math.min(Number(req.query.limit) || 50, 500);
  if (!q) return res.status(400).json({ error: 'q is required' });
  res.json({ messages: searchMessages({ query: q, limit }) });
});

app.post('/send', async (req, res) => {
  if (!clientReady) return res.status(503).json({ error: 'wa client not ready' });
  const { chatId, to, message } = req.body || {};
  const target = chatId || to;
  if (!target || !message) {
    return res.status(400).json({ error: 'chatId/to and message are required' });
  }
  try {
    const normalized = normalizeChatId(target);
    const sent = await client.sendMessage(normalized, String(message));
    res.json({ ok: true, id: sent.id?._serialized });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

function normalizeChatId(input) {
  const s = String(input).trim();
  if (s.includes('@')) return s;
  const digits = s.replace(/\D/g, '');
  if (!digits) throw new Error(`invalid chat id: ${input}`);
  return `${digits}@c.us`;
}

if (config.bridge.token) {
  app.use((req, res, next) => {
    if (req.path === '/health') return next();
    const auth = req.headers.authorization || '';
    if (auth !== `Bearer ${config.bridge.token}`) {
      return res.status(401).json({ error: 'unauthorized' });
    }
    next();
  });
}

app.listen(config.bridge.port, config.bridge.host, () => {
  console.log(`[bridge] HTTP API listening on http://${config.bridge.host}:${config.bridge.port}`);
});

console.log('[wa] starting WhatsApp Web client...');
client.initialize();

const shutdown = async (signal) => {
  console.log(`[bridge] received ${signal}, shutting down...`);
  try { await client.destroy(); } catch {}
  process.exit(0);
};
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
