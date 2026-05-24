import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { bridgeBaseUrl } from './config.js';

const BRIDGE = bridgeBaseUrl();

async function bridgeGet(pathname, params = {}) {
  const url = new URL(BRIDGE + pathname);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
  }
  const res = await fetch(url);
  if (!res.ok) throw new Error(`bridge ${pathname} -> HTTP ${res.status}`);
  return res.json();
}

async function bridgePost(pathname, body) {
  const res = await fetch(BRIDGE + pathname, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `bridge ${pathname} -> HTTP ${res.status}`);
  return data;
}

const tools = [
  {
    name: 'wa_health',
    description: 'Check whether the WhatsApp bridge is running and the WhatsApp Web client is connected.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'wa_list_chats',
    description: 'List recent WhatsApp chats, ordered by most recent activity. Optionally filter by name substring.',
    inputSchema: {
      type: 'object',
      properties: {
        search: { type: 'string', description: 'Optional case-insensitive substring of chat name.' },
        limit: { type: 'number', description: 'Max chats to return (default 50, max 500).' },
      },
      additionalProperties: false,
    },
  },
  {
    name: 'wa_recent_messages',
    description: 'Return recent messages. If chatId is given, returns messages from that chat; otherwise across all chats.',
    inputSchema: {
      type: 'object',
      properties: {
        chatId: { type: 'string', description: 'WhatsApp chat id (e.g. "12025550100@c.us" or "...@g.us").' },
        limit: { type: 'number', description: 'Max messages to return (default 20, max 500).' },
      },
      additionalProperties: false,
    },
  },
  {
    name: 'wa_search_messages',
    description: 'Full-text-ish search across stored message bodies (SQL LIKE).',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Substring to search for.' },
        limit: { type: 'number', description: 'Max results (default 50, max 500).' },
      },
      required: ['query'],
      additionalProperties: false,
    },
  },
  {
    name: 'wa_send_message',
    description: 'Send a WhatsApp message to a chat id or phone number (digits only, e.g. "12025550100").',
    inputSchema: {
      type: 'object',
      properties: {
        to: { type: 'string', description: 'Chat id (e.g. "...@c.us") or phone number digits.' },
        message: { type: 'string', description: 'Text to send.' },
      },
      required: ['to', 'message'],
      additionalProperties: false,
    },
  },
];

const server = new Server(
  { name: 'whatsapp-mcp', version: '1.0.0' },
  { capabilities: { tools: {} } },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools }));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args = {} } = req.params;
  try {
    const result = await dispatch(name, args);
    return {
      content: [{ type: 'text', text: JSON.stringify(result, null, 2) }],
    };
  } catch (err) {
    return {
      isError: true,
      content: [{ type: 'text', text: `Error: ${err.message}` }],
    };
  }
});

async function dispatch(name, args) {
  switch (name) {
    case 'wa_health':
      return bridgeGet('/health');
    case 'wa_list_chats':
      return bridgeGet('/chats', { search: args.search, limit: args.limit });
    case 'wa_recent_messages':
      return bridgeGet('/messages', { chatId: args.chatId, limit: args.limit });
    case 'wa_search_messages':
      return bridgeGet('/messages/search', { q: args.query, limit: args.limit });
    case 'wa_send_message':
      return bridgePost('/send', { to: args.to, message: args.message });
    default:
      throw new Error(`unknown tool: ${name}`);
  }
}

const transport = new StdioServerTransport();
await server.connect(transport);
console.error('[mcp] whatsapp-mcp server connected over stdio.');
