import { config } from './config.js';
import * as anthropic from './ai-anthropic.js';
import * as gemini from './ai-gemini.js';

const providers = { anthropic, gemini };

function pick(feature) {
  const override = config.ai.providers[feature];
  const chosen = override || config.ai.providers.default;
  return providers[chosen] || providers.anthropic;
}

export function scoreMessage(args) {
  return pick('priority').scoreMessage(args);
}

export function suggestReplies(args) {
  return pick('replies').suggestReplies(args);
}

export function summarizeBurst(args) {
  return pick('burst').summarizeBurst(args);
}

export function describeImage(args) {
  return pick('vision').describeImage(args);
}
