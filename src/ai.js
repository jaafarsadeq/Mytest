import fs from 'node:fs';
import Anthropic from '@anthropic-ai/sdk';
import { config } from './config.js';

let client = null;
let warnedNoKey = false;

function getClient() {
  if (!config.ai.apiKey) {
    if (!warnedNoKey) {
      console.warn('[ai] ANTHROPIC_API_KEY not set; AI features disabled.');
      warnedNoKey = true;
    }
    return null;
  }
  if (!client) client = new Anthropic({ apiKey: config.ai.apiKey });
  return client;
}

function logError(label, err) {
  if (err instanceof Anthropic.APIError) {
    console.error(`[ai] ${label} HTTP ${err.status}: ${err.message}`);
  } else {
    console.error(`[ai] ${label} failed: ${err.message}`);
  }
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

Respond ONLY with a compact JSON object: {"priority":"urgent|normal|low","reason":"<10 words"}. No prose, no markdown.`;

const REPLIES_SYSTEM = `You suggest up to 3 short tap-to-send replies to an incoming WhatsApp message.

Rules:
- Each reply is plain text the user could send verbatim, max 80 characters.
- Match the tone of the recent conversation (formal/informal, language).
- Cover meaningfully different responses (e.g., a yes, a no, a clarifying question) — not three paraphrases of the same answer.
- If the message clearly does not need a reply (a thank-you, a goodbye), return an empty list.

Respond ONLY with a compact JSON object: {"replies":["...","...","..."]}. No prose.`;

const VISION_SYSTEM = `You describe images attached to WhatsApp messages so the recipient can decide whether to open the chat. One sentence, under 200 characters. If the image contains readable text (a receipt, screenshot, sign), include the gist of that text instead of describing the image generically.`;

const BURST_SYSTEM = `You summarize a short burst of WhatsApp group messages into a single notification preview.

Rules:
- Output a JSON object {"summary":"...","priority":"urgent|normal|low"}.
- summary: 1-2 short sentences, under 240 characters total, covering the GIST and any direct mentions of the recipient, questions to them, decisions, or action items. Skip pure chatter.
- If different senders are saying meaningfully different things, mention who said what.
- priority: "urgent" only for safety/time-critical content; "normal" for substantive discussion or messages the recipient should see; "low" for pure small-talk bursts where nothing important happened.

Respond ONLY with the JSON object. No prose.`;

function extractText(message) {
  return message.content
    .filter((b) => b.type === 'text')
    .map((b) => b.text)
    .join('')
    .trim();
}

function parseJson(text) {
  if (!text) return null;
  const cleaned = text.replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/, '');
  try {
    return JSON.parse(cleaned);
  } catch {
    const match = cleaned.match(/\{[\s\S]*\}/);
    if (match) {
      try { return JSON.parse(match[0]); } catch {}
    }
    return null;
  }
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
    const res = await c.messages.create({
      model: config.ai.modelFast,
      max_tokens: 80,
      system: [
        { type: 'text', text: PRIORITY_SYSTEM, cache_control: { type: 'ephemeral' } },
      ],
      messages: [{ role: 'user', content: userPrompt }],
    });
    const parsed = parseJson(extractText(res));
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
    const res = await c.messages.create({
      model: config.ai.modelSmart,
      max_tokens: 300,
      system: [
        { type: 'text', text: REPLIES_SYSTEM, cache_control: { type: 'ephemeral' } },
      ],
      messages: [{ role: 'user', content: userPrompt }],
    });
    const parsed = parseJson(extractText(res));
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
    const res = await c.messages.create({
      model: config.ai.modelSmart,
      max_tokens: 250,
      system: [
        { type: 'text', text: BURST_SYSTEM, cache_control: { type: 'ephemeral' } },
      ],
      messages: [{ role: 'user', content: userPrompt }],
    });
    const parsed = parseJson(extractText(res));
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
    console.error('[ai] read image failed:', err.message);
    return null;
  }
  const userParts = [
    {
      type: 'image',
      source: { type: 'base64', media_type: mimetype || 'image/jpeg', data },
    },
    {
      type: 'text',
      text: `Image sent by ${senderName}${caption ? ` with caption: "${caption}"` : ''}.`,
    },
  ];
  try {
    const res = await c.messages.create({
      model: config.ai.modelSmart,
      max_tokens: 200,
      system: [
        { type: 'text', text: VISION_SYSTEM, cache_control: { type: 'ephemeral' } },
      ],
      messages: [{ role: 'user', content: userParts }],
    });
    const text = extractText(res);
    return text ? text.slice(0, 240) : null;
  } catch (err) {
    logError('describeImage', err);
    return null;
  }
}
