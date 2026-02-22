import { describe, it, expect, beforeEach } from 'vitest'
import {
  registerInManifest,
  deregisterFromManifest,
  getManifest,
  isRegistered,
  clearRegistry,
} from '../tool-registry'

describe('tool-registry', () => {
  beforeEach(() => {
    clearRegistry()
  })

  describe('registerInManifest', () => {
    it('adds an entry that appears in getManifest', () => {
      registerInManifest('test_tool', 'A test tool', 'TestPage')
      const manifest = getManifest()
      expect(manifest).toHaveLength(1)
      expect(manifest[0]).toEqual({
        name: 'test_tool',
        description: 'A test tool',
        page: 'TestPage',
      })
    })

    it('registers multiple tools and returns correct count', () => {
      registerInManifest('tool_a', 'Tool A', 'PageA')
      registerInManifest('tool_b', 'Tool B', 'PageB')
      registerInManifest('tool_c', 'Tool C', 'PageC')
      const manifest = getManifest()
      expect(manifest).toHaveLength(3)
      expect(manifest.map((e) => e.name)).toEqual(['tool_a', 'tool_b', 'tool_c'])
    })
  })

  describe('deregisterFromManifest', () => {
    it('removes an entry so getManifest no longer includes it', () => {
      registerInManifest('to_remove', 'Will be removed', 'TestPage')
      expect(isRegistered('to_remove')).toBe(true)
      deregisterFromManifest('to_remove')
      expect(isRegistered('to_remove')).toBe(false)
      expect(getManifest()).toHaveLength(0)
    })

    it('is a no-op when deregistering a non-existent name', () => {
      registerInManifest('existing', 'Existing tool', 'TestPage')
      // Should not throw
      deregisterFromManifest('non_existent')
      expect(getManifest()).toHaveLength(1)
    })
  })

  describe('isRegistered', () => {
    it('returns true for registered tools', () => {
      registerInManifest('present_tool', 'Present', 'TestPage')
      expect(isRegistered('present_tool')).toBe(true)
    })

    it('returns false for unregistered tools', () => {
      expect(isRegistered('absent_tool')).toBe(false)
    })
  })

  describe('getManifest', () => {
    it('returns a fresh array copy, not a reference to internal state', () => {
      registerInManifest('copy_test', 'Copy test', 'TestPage')
      const manifest1 = getManifest()
      const manifest2 = getManifest()
      expect(manifest1).toEqual(manifest2)
      expect(manifest1).not.toBe(manifest2) // Different array instances
    })

    it('returns empty array when nothing is registered', () => {
      expect(getManifest()).toEqual([])
    })
  })

  describe('clearRegistry', () => {
    it('removes all entries', () => {
      registerInManifest('a', 'A', 'Page')
      registerInManifest('b', 'B', 'Page')
      clearRegistry()
      expect(getManifest()).toEqual([])
      expect(isRegistered('a')).toBe(false)
      expect(isRegistered('b')).toBe(false)
    })
  })
})
