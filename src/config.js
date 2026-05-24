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
    onlyDirect: String(process.env.ONLY_DIRECT).toLowerCase() === 'true',
    includeFromMe: String(process.env.INCLUDE_FROM_ME).toLowerCase() === 'true',
  },
  dbPath: resolveFromRoot(process.env.DB_PATH, './data/whatsapp.db'),
  sessionPath: resolveFromRoot(process.env.SESSION_PATH, './data/wa-session'),
};

export function bridgeBaseUrl() {
  return `http://${config.bridge.host}:${config.bridge.port}`;
}
