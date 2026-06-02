import fs from 'node:fs';
import path from 'node:path';
import express from 'express';
import qrcode from 'qrcode-terminal';
import pkg from 'whatsapp-web.js';
import { config, priorityRank } from './config.js';
import {
  saveMessage,
  upsertChat,
  listChats,
  getRecentMessages,
  searchMessages,
  getChatContext,
  updateMessageAi,
  getMessageById,
} from './db.js';
import { sendNtfy } from './ntfy.js';
import { downloadMedia, mediaPathFor } from './media.js';
import { scoreMessage, suggestReplies, describeImage, summarizeBurst } from './ai.js';

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
      if (row.is_group && config.ai.burstEnabled) {
        bufferForBurst(row, message);
      } else {
        await enrichAndPush(row, message);
      }
    }
  } catch (err) {
    console.error('[wa] handleIncoming failed:', err.message);
  }
}

const groupBuffers = new Map();

function bufferForBurst(row, message) {
  let buf = groupBuffers.get(row.chat_id);
  if (!buf) {
    buf = { entries: [], timer: null };
    groupBuffers.set(row.chat_id, buf);
    buf.timer = setTimeout(() => flushBurst(row.chat_id), config.ai.burstWindowMs);
  }
  buf.entries.push({ row, message });
  if (buf.entries.length >= config.ai.burstMaxBuffer) {
    clearTimeout(buf.timer);
    flushBurst(row.chat_id);
  }
}

async function flushBurst(chatId) {
  const buf = groupBuffers.get(chatId);
  if (!buf) return;
  groupBuffers.delete(chatId);
  const entries = buf.entries;

  if (entries.length === 1) {
    const { row, message } = entries[0];
    try { await enrichAndPush(row, message); }
    catch (err) { console.error('[wa] enrichAndPush failed:', err.message); }
    return;
  }

  const first = entries[0].row;
  const summarized = await summarizeBurst({
    chatName: first.chat_name,
    messages: entries.map(({ row }) => ({
      sender_name: row.sender_name,
      from_me: row.from_me,
      body: row.body,
    })),
  });

  if (!summarized) {
    // Claude failed — fall back to pushing each message individually.
    for (const { row, message } of entries) {
      try { await enrichAndPush(row, message); }
      catch (err) { console.error('[wa] fallback push failed:', err.message); }
    }
    return;
  }

  for (const { row } of entries) {
    updateMessageAi({ id: row.id, priority: summarized.priority });
  }

  if (priorityRank(summarized.priority) < priorityRank(config.ai.priorityFloor)) {
    return;
  }

  await sendNtfy({
    title: `${first.chat_name} — ${entries.length} new messages`,
    message: summarized.summary,
    tags: ['speech_balloon', 'busts_in_silhouette', ...(summarized.priority === 'urgent' ? ['rotating_light'] : [])],
    priority: NTFY_PRIORITY[summarized.priority] || 'default',
  });
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

async function enrichAndPush(row, message) {
  let mediaInfo = null;
  let bodyForPush = row.body || '';

  if (row.has_media) {
    mediaInfo = await downloadMedia(message);
    if (mediaInfo) {
      updateMessageAi({ id: row.id, media_path: mediaInfo.filename });
      if (mediaInfo.kind === 'image') {
        const summary = await describeImage({
          mediaPath: mediaInfo.path,
          mimetype: mediaInfo.mimetype,
          caption: row.body,
          senderName: row.sender_name,
        });
        if (summary) {
          updateMessageAi({ id: row.id, ai_summary: summary });
          if (!bodyForPush) bodyForPush = summary;
        }
      }
      if (!bodyForPush) {
        bodyForPush = mediaPlaceholder(mediaInfo.kind);
      }
    } else if (!bodyForPush) {
      bodyForPush = `[${row.type || 'media'}]`;
    }
  }

  const context = getChatContext({
    chatId: row.chat_id,
    limit: 10,
    beforeTs: row.timestamp,
  });

  const scored = await scoreMessage({
    chatName: row.chat_name,
    senderName: row.sender_name,
    body: bodyForPush,
    isGroup: !!row.is_group,
    recentContext: context,
  });
  const priority = scored?.priority || 'normal';
  updateMessageAi({ id: row.id, priority });

  if (priorityRank(priority) < priorityRank(config.ai.priorityFloor)) {
    return;
  }

  let replies = [];
  const repliesAllowedHere = !row.is_group || config.ai.repliesInGroups;
  if (repliesAllowedHere) {
    replies = await suggestReplies({
      chatName: row.chat_name,
      senderName: row.sender_name,
      body: bodyForPush,
      recentContext: context,
    });
  }

  await pushToPhone({ row, bodyForPush, priority, mediaInfo, replies });
}

function mediaPlaceholder(kind) {
  switch (kind) {
    case 'image': return '[image]';
    case 'audio': return '[voice note]';
    case 'video': return '[video]';
    case 'document': return '[document]';
    default: return '[media]';
  }
}

const NTFY_PRIORITY = { low: 'low', normal: 'default', urgent: 'max' };

async function pushToPhone({ row, bodyForPush, priority, mediaInfo, replies }) {
  const isGroup = !!row.is_group;
  const title = isGroup
    ? `${row.chat_name} — ${row.sender_name}`
    : row.sender_name || row.chat_name;

  let body = bodyForPush || '';
  if (body.length > 400) body = `${body.slice(0, 397)}...`;

  const tags = ['speech_balloon'];
  if (isGroup) tags.push('busts_in_silhouette');
  if (mediaInfo?.kind === 'image') tags.push('frame_with_picture');
  if (mediaInfo?.kind === 'audio') tags.push('studio_microphone');
  if (priority === 'urgent') tags.push('rotating_light');

  let attachUrl;
  if (mediaInfo && mediaInfo.kind === 'image' && !mediaInfo.tooLargeToAttach && publicMediaUrl(mediaInfo)) {
    attachUrl = publicMediaUrl(mediaInfo);
  } else if (mediaInfo?.tooLargeToAttach) {
    console.warn(`[bridge] media too large to attach (${mediaInfo.sizeBytes} bytes)`);
  }

  const actions = buildReplyActions(row, replies);

  await sendNtfy({
    title,
    message: body,
    tags,
    priority: NTFY_PRIORITY[priority] || 'default',
    attachUrl,
    actions,
  });
}

function publicMediaUrl(mediaInfo) {
  if (!config.publicBridgeUrl || !config.actionToken) return null;
  const t = encodeURIComponent(config.actionToken);
  return `${config.publicBridgeUrl}/media/${encodeURIComponent(mediaInfo.filename)}?t=${t}`;
}

function buildReplyActions(row, replies) {
  if (!replies?.length) return [];
  if (!config.publicBridgeUrl || !config.actionToken) return [];
  const url = `${config.publicBridgeUrl}/reply-action`;
  return replies.slice(0, 3).map((text) => ({
    type: 'http',
    label: text.length > 30 ? `${text.slice(0, 27)}...` : text,
    url,
    method: 'POST',
    bodyJson: { chatId: row.chat_id, text, token: config.actionToken },
  }));
}

client.on('message', handleIncoming);
client.on('message_create', (m) => {
  if (m.fromMe) handleIncoming(m);
});

const app = express();
app.use(express.json({ limit: '256kb' }));

function requireBridgeAuth(req, res, next) {
  if (!config.bridge.token) return next();
  const auth = req.headers.authorization || '';
  if (auth === `Bearer ${config.bridge.token}`) return next();
  return res.status(401).json({ error: 'unauthorized' });
}

app.get('/health', (_req, res) => {
  res.json({ ok: true, ready: clientReady });
});

app.post('/reply-action', async (req, res) => {
  const token = req.body?.token || req.query?.t || '';
  if (!config.actionToken || token !== config.actionToken) {
    return res.status(401).json({ error: 'unauthorized' });
  }
  if (!clientReady) return res.status(503).json({ error: 'wa client not ready' });
  const { chatId, text } = req.body || {};
  if (!chatId || !text) {
    return res.status(400).json({ error: 'chatId and text are required' });
  }
  try {
    const sent = await client.sendMessage(String(chatId), String(text));
    res.json({ ok: true, id: sent.id?._serialized });
  } catch (err) {
    console.error('[bridge] reply-action failed:', err.message);
    res.status(500).json({ error: err.message });
  }
});

app.get('/media/:filename', (req, res) => {
  const token = String(req.query.t || '');
  if (!config.actionToken || token !== config.actionToken) {
    return res.status(401).end();
  }
  const safe = path.basename(String(req.params.filename));
  const fullPath = mediaPathFor(safe);
  if (!fs.existsSync(fullPath)) return res.status(404).end();
  res.sendFile(fullPath);
});

app.use(requireBridgeAuth);

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

app.get('/messages/by-id', (req, res) => {
  const id = String(req.query.id || '');
  if (!id) return res.status(400).json({ error: 'id is required' });
  const message = getMessageById(id);
  if (!message) return res.status(404).json({ error: 'not found' });
  res.json({ message });
});

app.post('/ai/suggest-replies', async (req, res) => {
  const chatId = String(req.body?.chatId || '');
  if (!chatId) return res.status(400).json({ error: 'chatId is required' });
  const recent = getRecentMessages({ chatId, limit: 1 });
  if (!recent.length) return res.status(404).json({ error: 'no messages in chat' });
  const latest = recent[0];
  const context = getChatContext({ chatId, limit: 10, beforeTs: latest.timestamp });
  const replies = await suggestReplies({
    chatName: latest.chat_name,
    senderName: latest.sender_name,
    body: latest.body || latest.ai_summary || '',
    recentContext: context,
  });
  res.json({ replies, message: latest });
});

app.post('/ai/describe-media', async (req, res) => {
  const id = String(req.body?.messageId || '');
  if (!id) return res.status(400).json({ error: 'messageId is required' });
  const message = getMessageById(id);
  if (!message) return res.status(404).json({ error: 'not found' });
  if (message.ai_summary) return res.json({ summary: message.ai_summary, cached: true });
  if (!message.media_path) return res.status(400).json({ error: 'message has no media' });
  const fullPath = mediaPathFor(message.media_path);
  if (!fs.existsSync(fullPath)) return res.status(410).json({ error: 'media file missing' });
  const summary = await describeImage({
    mediaPath: fullPath,
    mimetype: guessMimeFromName(message.media_path),
    caption: message.body,
    senderName: message.sender_name,
  });
  if (summary) updateMessageAi({ id, ai_summary: summary });
  res.json({ summary, cached: false });
});

function guessMimeFromName(name) {
  const ext = (name.split('.').pop() || '').toLowerCase();
  if (['jpg', 'jpeg'].includes(ext)) return 'image/jpeg';
  if (ext === 'png') return 'image/png';
  if (ext === 'webp') return 'image/webp';
  if (ext === 'gif') return 'image/gif';
  return 'image/jpeg';
}

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

app.listen(config.bridge.port, config.bridge.host, () => {
  console.log(`[bridge] HTTP API listening on http://${config.bridge.host}:${config.bridge.port}`);
});

console.log('[wa] starting WhatsApp Web client...');
client.initialize().catch((err) => {
  console.error('[wa] initialize failed:', err.message);
  console.error('[wa] HTTP API stays up for /health and DB queries; WA features unavailable until restart.');
});

process.on('unhandledRejection', (err) => {
  console.error('[wa] unhandled rejection:', err?.message || err);
});

const shutdown = async (signal) => {
  console.log(`[bridge] received ${signal}, shutting down...`);
  try { await client.destroy(); } catch {}
  process.exit(0);
};
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
