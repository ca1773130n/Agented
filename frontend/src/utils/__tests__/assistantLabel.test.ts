import { describe, it, expect } from 'vitest';
import { backendDisplayName, modelDisplayName, authorName } from '../assistantLabel';

describe('assistantLabel', () => {
  describe('backendDisplayName', () => {
    it('maps known backends to their display name', () => {
      expect(backendDisplayName('claude')).toBe('Claude');
      expect(backendDisplayName('codex')).toBe('Codex');
      expect(backendDisplayName('gemini')).toBe('Gemini');
      expect(backendDisplayName('opencode')).toBe('OpenCode');
    });

    it('title-cases unknown backends', () => {
      expect(backendDisplayName('mistral')).toBe('Mistral');
    });

    it("returns '' for missing or unresolved ('auto') backends", () => {
      expect(backendDisplayName(undefined)).toBe('');
      expect(backendDisplayName(null)).toBe('');
      expect(backendDisplayName('')).toBe('');
      expect(backendDisplayName('auto')).toBe('');
    });
  });

  describe('modelDisplayName', () => {
    it('prettifies known short model ids', () => {
      expect(modelDisplayName('opus')).toBe('Opus');
      expect(modelDisplayName('sonnet')).toBe('Sonnet');
      expect(modelDisplayName('haiku')).toBe('Haiku');
    });

    it('passes through full model ids unchanged', () => {
      expect(modelDisplayName('gpt-5.1')).toBe('gpt-5.1');
      expect(modelDisplayName('claude-opus-4-8')).toBe('claude-opus-4-8');
    });

    it("returns '' for a missing model", () => {
      expect(modelDisplayName(undefined)).toBe('');
      expect(modelDisplayName(null)).toBe('');
      expect(modelDisplayName('')).toBe('');
    });
  });

  describe('authorName', () => {
    it("labels users as 'You'", () => {
      expect(authorName('user', 'claude')).toBe('You');
    });

    it('labels assistants by their backend', () => {
      expect(authorName('assistant', 'claude')).toBe('Claude');
    });

    it("falls back to 'Assistant' (never 'AI') when the backend is unknown", () => {
      expect(authorName('assistant', undefined)).toBe('Assistant');
      expect(authorName('assistant', 'auto')).toBe('Assistant');
    });

    it('passes other roles through', () => {
      expect(authorName('system')).toBe('system');
    });
  });
});
