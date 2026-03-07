/**
 * Backward-compatible barrel file.
 * All types have been split into domain-specific files under ./types/.
 * This file re-exports everything so existing imports continue to work.
 */

export * from './types/index';
