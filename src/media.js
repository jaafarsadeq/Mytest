import fs from 'node:fs';
import path from 'node:path';
import mime from 'mime-types';
import { config } from './config.js';

fs.mkdirSync(config.mediaDir, { recursive: true });

const MAX_ATTACH_BYTES = 15 * 1024 * 1024; // ntfy.sh free-tier attachment cap

export async function downloadMedia(message) {
  if (!message.hasMedia) return null;
  let media;
  try {
    media = await message.downloadMedia();
  } catch (err) {
    console.error('[media] downloadMedia failed:', err.message);
    return null;
  }
  if (!media || !media.data) return null;

  const ext = mime.extension(media.mimetype) || 'bin';
  const safeId = String(message.id?._serialized || message.id || Date.now()).replace(/[^\w.-]/g, '_');
  const filename = `${safeId}.${ext}`;
  const fullPath = path.join(config.mediaDir, filename);
  const buf = Buffer.from(media.data, 'base64');
  fs.writeFileSync(fullPath, buf);
  return {
    filename,
    path: fullPath,
    mimetype: media.mimetype,
    sizeBytes: buf.length,
    tooLargeToAttach: buf.length > MAX_ATTACH_BYTES,
    kind: inferKind(media.mimetype),
  };
}

export function inferKind(mimetype = '') {
  if (mimetype.startsWith('image/')) return 'image';
  if (mimetype.startsWith('audio/')) return 'audio';
  if (mimetype.startsWith('video/')) return 'video';
  if (mimetype.startsWith('application/') || mimetype.startsWith('text/')) return 'document';
  return 'other';
}

export function mediaPathFor(filename) {
  return path.join(config.mediaDir, path.basename(filename));
}
