import 'dotenv/config';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(here, '..');

function resolveFromRoot(p, fallback) {
  const value = p ?? fallback;
  return path.isAbsolute(value) ? value : path.resolve(projectRoot, value);
}

function parseList(value) {
  if (!value) return [];
  return value.split(',').map((s) => s.trim()).filter(Boolean);
}

function bool(value, fallback = false) {
  if (value === undefined) return fallback;
  return String(value).toLowerCase() === 'true';
}

export const config = {
  projectRoot,
  ntfy: {
    server: (process.env.NTFY_SERVER || 'https://ntfy.sh').replace(/\/$/, ''),
    topic: process.env.NTFY_TOPIC || '',
    token: process.env.NTFY_TOKEN || '',
  },
  bridge: {
    port: Number(process.env.BRIDGE_PORT || 3037),
    host: process.env.BRIDGE_HOST || '127.0.0.1',
    token: process.env.BRIDGE_TOKEN || '',
  },
  filters: {
    muteChats: parseList(process.env.MUTE_CHATS),
    onlyDirect: bool(process.env.ONLY_DIRECT),
    includeFromMe: bool(process.env.INCLUDE_FROM_ME),
  },
  ai: {
    apiKey: process.env.ANTHROPIC_API_KEY || '',
    modelFast: process.env.ANTHROPIC_MODEL_FAST || 'claude-haiku-4-5-20251001',
    modelSmart: process.env.ANTHROPIC_MODEL_SMART || 'claude-sonnet-4-6',
    priorityEnabled: bool(process.env.AI_PRIORITY_ENABLED, true),
    repliesEnabled: bool(process.env.AI_REPLIES_ENABLED, true),
    visionEnabled: bool(process.env.AI_VISION_ENABLED, true),
    priorityFloor: (process.env.AI_PRIORITY_FLOOR || 'low').toLowerCase(),
    repliesInGroups: bool(process.env.AI_REPLIES_IN_GROUPS),
  },
  actionToken: process.env.ACTION_TOKEN || '',
  publicBridgeUrl: (process.env.PUBLIC_BRIDGE_URL || '').replace(/\/$/, ''),
  dbPath: resolveFromRoot(process.env.DB_PATH, './data/whatsapp.db'),
  sessionPath: resolveFromRoot(process.env.SESSION_PATH, './data/wa-session'),
  mediaDir: resolveFromRoot(process.env.MEDIA_DIR, './data/media'),
};

export const PRIORITY_RANK = { low: 0, normal: 1, urgent: 2 };

export function priorityRank(p) {
  return PRIORITY_RANK[p] ?? PRIORITY_RANK.normal;
}

export function bridgeBaseUrl() {
  return `http://${config.bridge.host}:${config.bridge.port}`;
}
