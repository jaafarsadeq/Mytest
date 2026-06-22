import { config } from './config.js';

export async function sendNtfy({
  title,
  message,
  tags = [],
  priority = 'default',
  clickUrl,
  attachUrl,
  actions = [],
}) {
  if (!config.ntfy.topic) {
    console.warn('[ntfy] NTFY_TOPIC not set; skipping push.');
    return { skipped: true };
  }
  const url = `${config.ntfy.server}/${encodeURIComponent(config.ntfy.topic)}`;
  const headers = {
    'Content-Type': 'text/plain; charset=utf-8',
    Title: encodeHeader(title),
    Priority: priority,
  };
  if (tags.length) headers.Tags = tags.join(',');
  if (clickUrl) headers.Click = clickUrl;
  if (attachUrl) headers.Attach = attachUrl;
  if (actions.length) headers.Actions = encodeActions(actions);
  if (config.ntfy.token) headers.Authorization = `Bearer ${config.ntfy.token}`;

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers,
      body: message ?? '',
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      console.error(`[ntfy] HTTP ${res.status}: ${text}`);
      return { ok: false, status: res.status };
    }
    return { ok: true };
  } catch (err) {
    console.error('[ntfy] request failed:', err.message);
    return { ok: false, error: err.message };
  }
}

function encodeHeader(value = '') {
  // ntfy headers must be ASCII; encode non-ASCII as RFC 2047 UTF-8 base64.
  // eslint-disable-next-line no-control-regex
  if (/^[\x00-\x7F]*$/.test(value)) return value;
  const b64 = Buffer.from(value, 'utf-8').toString('base64');
  return `=?UTF-8?B?${b64}?=`;
}

function escapeActionPart(value) {
  return String(value).replace(/[\\,;"]/g, (c) => `\\${c}`);
}

function encodeActions(actions) {
  return actions
    .map((a) => {
      const parts = [
        a.type || 'http',
        escapeActionPart(a.label || ''),
        escapeActionPart(a.url || ''),
        `method=${a.method || 'POST'}`,
        'clear=true',
      ];
      if (a.bodyJson) {
        const body = JSON.stringify(a.bodyJson);
        parts.push(`body=${escapeActionPart(body)}`);
        parts.push('headers.Content-Type=application/json');
      }
      if (a.headers) {
        for (const [k, v] of Object.entries(a.headers)) {
          parts.push(`headers.${k}=${escapeActionPart(v)}`);
        }
      }
      return parts.join(', ');
    })
    .join('; ');
}
