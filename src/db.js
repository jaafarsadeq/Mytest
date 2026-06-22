import fs from 'node:fs';
import path from 'node:path';
import Database from 'better-sqlite3';
import { config } from './config.js';

fs.mkdirSync(path.dirname(config.dbPath), { recursive: true });

export const db = new Database(config.dbPath);
db.pragma('journal_mode = WAL');

db.exec(`
  CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL,
    chat_name TEXT,
    is_group INTEGER NOT NULL DEFAULT 0,
    sender_id TEXT,
    sender_name TEXT,
    from_me INTEGER NOT NULL DEFAULT 0,
    body TEXT,
    type TEXT,
    has_media INTEGER NOT NULL DEFAULT 0,
    timestamp INTEGER NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);
  CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp DESC);

  CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    name TEXT,
    is_group INTEGER NOT NULL DEFAULT 0,
    last_message_ts INTEGER,
    unread_count INTEGER DEFAULT 0
  );
`);

function ensureColumn(table, column, ddl) {
  const cols = db.prepare(`PRAGMA table_info(${table})`).all();
  if (!cols.some((c) => c.name === column)) {
    db.exec(`ALTER TABLE ${table} ADD COLUMN ${column} ${ddl}`);
  }
}

ensureColumn('messages', 'priority', 'TEXT');
ensureColumn('messages', 'ai_summary', 'TEXT');
ensureColumn('messages', 'media_path', 'TEXT');

const insertMessageStmt = db.prepare(`
  INSERT OR REPLACE INTO messages
    (id, chat_id, chat_name, is_group, sender_id, sender_name, from_me, body, type, has_media, timestamp)
  VALUES
    (@id, @chat_id, @chat_name, @is_group, @sender_id, @sender_name, @from_me, @body, @type, @has_media, @timestamp)
`);

const upsertChatStmt = db.prepare(`
  INSERT INTO chats (id, name, is_group, last_message_ts, unread_count)
  VALUES (@id, @name, @is_group, @last_message_ts, @unread_count)
  ON CONFLICT(id) DO UPDATE SET
    name = excluded.name,
    is_group = excluded.is_group,
    last_message_ts = MAX(IFNULL(chats.last_message_ts, 0), excluded.last_message_ts),
    unread_count = excluded.unread_count
`);

export function saveMessage(msg) {
  insertMessageStmt.run(msg);
  upsertChatStmt.run({
    id: msg.chat_id,
    name: msg.chat_name,
    is_group: msg.is_group,
    last_message_ts: msg.timestamp,
    unread_count: 0,
  });
}

export function upsertChat(chat) {
  upsertChatStmt.run({
    id: chat.id,
    name: chat.name,
    is_group: chat.is_group ? 1 : 0,
    last_message_ts: chat.last_message_ts || 0,
    unread_count: chat.unread_count || 0,
  });
}

export function listChats({ limit = 50, search = '' } = {}) {
  if (search) {
    return db
      .prepare(
        `SELECT * FROM chats WHERE name LIKE ? ORDER BY last_message_ts DESC LIMIT ?`,
      )
      .all(`%${search}%`, limit);
  }
  return db
    .prepare(`SELECT * FROM chats ORDER BY last_message_ts DESC LIMIT ?`)
    .all(limit);
}

export function getRecentMessages({ chatId, limit = 20 } = {}) {
  if (chatId) {
    return db
      .prepare(
        `SELECT * FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?`,
      )
      .all(chatId, limit);
  }
  return db
    .prepare(`SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?`)
    .all(limit);
}

export function searchMessages({ query, limit = 50 }) {
  return db
    .prepare(
      `SELECT * FROM messages WHERE body LIKE ? ORDER BY timestamp DESC LIMIT ?`,
    )
    .all(`%${query}%`, limit);
}

export function getMessageById(id) {
  return db.prepare(`SELECT * FROM messages WHERE id = ?`).get(id);
}

export function getChatContext({ chatId, limit = 10, beforeTs }) {
  if (beforeTs) {
    return db
      .prepare(
        `SELECT sender_name, from_me, body, timestamp
           FROM messages
          WHERE chat_id = ? AND timestamp < ?
          ORDER BY timestamp DESC LIMIT ?`,
      )
      .all(chatId, beforeTs, limit)
      .reverse();
  }
  return db
    .prepare(
      `SELECT sender_name, from_me, body, timestamp
         FROM messages
        WHERE chat_id = ?
        ORDER BY timestamp DESC LIMIT ?`,
    )
    .all(chatId, limit)
    .reverse();
}

const updateAiStmt = db.prepare(`
  UPDATE messages
     SET priority = COALESCE(@priority, priority),
         ai_summary = COALESCE(@ai_summary, ai_summary),
         media_path = COALESCE(@media_path, media_path)
   WHERE id = @id
`);

export function updateMessageAi(fields) {
  updateAiStmt.run({
    id: fields.id,
    priority: fields.priority ?? null,
    ai_summary: fields.ai_summary ?? null,
    media_path: fields.media_path ?? null,
  });
}
