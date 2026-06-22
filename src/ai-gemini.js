import fs from 'node:fs';
import { GoogleGenAI } from '@google/genai';
import { config } from './config.js';

let client = null;
let warnedNoKey = false;

function getClient() {
  if (!config.gemini.apiKey) {
    if (!warnedNoKey) {
      console.warn('[ai/gemini] GEMINI_API_KEY not set; Gemini features disabled.');
      warnedNoKey = true;
    }
    return null;
  }
  if (!client) client = new GoogleGenAI({ apiKey: config.gemini.apiKey });
  return client;
}

function logError(label, err) {
  console.error(`[ai/gemini] ${label} failed: ${err.message}`);
}

function formatContext(recentContext = []) {
  if (!recentContext.length) return '(no prior messages)';
  return recentContext
    .map((m) => {
      const who = m.from_me ? 'me' : m.sender_name || 'them';
      const body = (m.body || '').replace(/\s+/g, ' ').slice(0, 200);
      return `${who}: ${body}`;
    })
    .join('\n');
}

const PRIORITY_SYSTEM = `You triage incoming WhatsApp messages for a busy user.

Classify the new message into exactly one priority:
- "urgent": time-sensitive emergencies, safety issues, or messages that need a response within the hour from someone the user clearly cares about. Be conservative — most messages are NOT urgent.
- "normal": ordinary personal or work messages that the user will want to see soon (questions, requests, planning, meaningful updates).
- "low": small talk, acknowledgements ("ok", "thanks"), forwarded jokes, broadcast/marketing-style content, automated notifications, group chatter that doesn't address the user.

Respond with a JSON object {"priority":"urgent|normal|low","reason":"<10 words"}.`;

const REPLIES_SYSTEM = `You suggest up to 3 short tap-to-send replies to an incoming WhatsApp message.

Rules:
- Each reply is plain text the user could send verbatim, max 80 characters.
- Match the tone of the recent conversation (formal/informal, language).
- Cover meaningfully different responses (e.g., a yes, a no, a clarifying question) — not three paraphrases of the same answer.
- If the message clearly does not need a reply (a thank-you, a goodbye), return an empty list.

Respond with a JSON object {"replies":["...","...","..."]}.`;

const VISION_SYSTEM = `You describe images attached to WhatsApp messages so the recipient can decide whether to open the chat. One sentence, under 200 characters. If the image contains readable text (a receipt, screenshot, sign), include the gist of that text instead of describing the image generically.`;

const BURST_SYSTEM = `You summarize a short burst of WhatsApp group messages into a single notification preview.

Rules:
- summary: 1-2 short sentences, under 240 characters total, covering the GIST and any direct mentions of the recipient, questions to them, decisions, or action items. Skip pure chatter.
- If different senders are saying meaningfully different things, mention who said what.
- priority: "urgent" only for safety/time-critical content; "normal" for substantive discussion or messages the recipient should see; "low" for pure small-talk bursts where nothing important happened.

Respond with a JSON object {"summary":"...","priority":"urgent|normal|low"}.`;

const PRIORITY_SCHEMA = {
  type: 'object',
  properties: {
    priority: { type: 'string', enum: ['urgent', 'normal', 'low'] },
    reason: { type: 'string' },
  },
  required: ['priority', 'reason'],
};

const REPLIES_SCHEMA = {
  type: 'object',
  properties: {
    replies: { type: 'array', items: { type: 'string' } },
  },
  required: ['replies'],
};

const BURST_SCHEMA = {
  type: 'object',
  properties: {
    summary: { type: 'string' },
    priority: { type: 'string', enum: ['urgent', 'normal', 'low'] },
  },
  required: ['summary', 'priority'],
};

function parseJsonSafe(text) {
  if (!text) return null;
  try { return JSON.parse(text); } catch {}
  const match = text.match(/\{[\s\S]*\}/);
  if (match) {
    try { return JSON.parse(match[0]); } catch {}
  }
  return null;
}

export async function scoreMessage({ chatName, senderName, body, isGroup, recentContext }) {
  if (!config.ai.priorityEnabled) return null;
  const c = getClient();
  if (!c) return null;
  const userPrompt = `Chat: ${chatName}${isGroup ? ' (group)' : ''}
Sender: ${senderName}

Recent conversation (oldest first):
${formatContext(recentContext)}

NEW message from ${senderName}:
${body || '(no text)'}`;

  try {
    const res = await c.models.generateContent({
      model: config.gemini.modelFast,
      contents: userPrompt,
      config: {
        systemInstruction: PRIORITY_SYSTEM,
        responseMimeType: 'application/json',
        responseSchema: PRIORITY_SCHEMA,
        temperature: 0,
        maxOutputTokens: 80,
      },
    });
    const parsed = parseJsonSafe(res.text);
    if (!parsed || !['urgent', 'normal', 'low'].includes(parsed.priority)) return null;
    return { priority: parsed.priority, reason: String(parsed.reason || '').slice(0, 120) };
  } catch (err) {
    logError('scoreMessage', err);
    return null;
  }
}

export async function suggestReplies({ chatName, senderName, body, recentContext }) {
  if (!config.ai.repliesEnabled) return [];
  const c = getClient();
  if (!c) return [];
  const userPrompt = `Chat: ${chatName}
Sender: ${senderName}

Recent conversation (oldest first):
${formatContext(recentContext)}

NEW message from ${senderName}:
${body || '(no text)'}`;

  try {
    const res = await c.models.generateContent({
      model: config.gemini.modelSmart,
      contents: userPrompt,
      config: {
        systemInstruction: REPLIES_SYSTEM,
        responseMimeType: 'application/json',
        responseSchema: REPLIES_SCHEMA,
        temperature: 0.3,
        maxOutputTokens: 300,
      },
    });
    const parsed = parseJsonSafe(res.text);
    if (!parsed || !Array.isArray(parsed.replies)) return [];
    return parsed.replies
      .map((s) => String(s).trim())
      .filter(Boolean)
      .map((s) => s.slice(0, 80))
      .slice(0, 3);
  } catch (err) {
    logError('suggestReplies', err);
    return [];
  }
}

export async function summarizeBurst({ chatName, messages }) {
  const c = getClient();
  if (!c) return null;
  const lines = messages
    .map((m) => {
      const who = m.from_me ? 'me' : m.sender_name || 'them';
      const body = (m.body || '').replace(/\s+/g, ' ').slice(0, 240);
      return `${who}: ${body}`;
    })
    .join('\n');
  const userPrompt = `Group: ${chatName}
${messages.length} messages in the last burst:

${lines}`;
  try {
    const res = await c.models.generateContent({
      model: config.gemini.modelSmart,
      contents: userPrompt,
      config: {
        systemInstruction: BURST_SYSTEM,
        responseMimeType: 'application/json',
        responseSchema: BURST_SCHEMA,
        temperature: 0.2,
        maxOutputTokens: 250,
      },
    });
    const parsed = parseJsonSafe(res.text);
    if (!parsed || !parsed.summary) return null;
    const priority = ['urgent', 'normal', 'low'].includes(parsed.priority)
      ? parsed.priority
      : 'normal';
    return { summary: String(parsed.summary).slice(0, 280), priority };
  } catch (err) {
    logError('summarizeBurst', err);
    return null;
  }
}

export async function describeImage({ mediaPath, mimetype, caption, senderName }) {
  if (!config.ai.visionEnabled) return null;
  const c = getClient();
  if (!c) return null;
  let data;
  try {
    data = fs.readFileSync(mediaPath).toString('base64');
  } catch (err) {
    console.error('[ai/gemini] read image failed:', err.message);
    return null;
  }
  const userText = `Image sent by ${senderName}${caption ? ` with caption: "${caption}"` : ''}.`;
  try {
    const res = await c.models.generateContent({
      model: config.gemini.modelSmart,
      contents: [
        {
          role: 'user',
          parts: [
            { inlineData: { mimeType: mimetype || 'image/jpeg', data } },
            { text: userText },
          ],
        },
      ],
      config: {
        systemInstruction: VISION_SYSTEM,
        temperature: 0,
        maxOutputTokens: 200,
      },
    });
    const text = (res.text || '').trim();
    return text ? text.slice(0, 240) : null;
  } catch (err) {
    logError('describeImage', err);
    return null;
  }
}
