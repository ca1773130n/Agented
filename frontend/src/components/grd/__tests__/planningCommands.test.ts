import { describe, it, expect } from 'vitest';
import {
  GRD_COMMAND_MANIFEST,
  type GrdCommand,
  type GrdCommandGroup,
} from '../planningCommands';

// The six required groups, keyed by the trailing segment of their labelKey.
const REQUIRED_GROUPS = ['Plan', 'Execute', 'Verify', 'Research', 'Harness', 'Misc'];

// Full supported /grd: command set that the manifest must expose.
const REQUIRED_COMMANDS = [
  'plan-phase',
  'plan-milestone-gaps',
  'autoplan',
  'discuss-phase',
  'execute-phase',
  'autopilot',
  'quick',
  'verify-phase',
  'verify-work',
  'assess-baseline',
  'research',
  'survey',
  'deep-dive',
  'compare-methods',
  'feasibility',
  'harness',
  'settings',
  'sync',
  'map-codebase',
  'progress',
  'help',
];

function allCommands(): GrdCommand[] {
  return GRD_COMMAND_MANIFEST.flatMap((g: GrdCommandGroup) => g.commands);
}

function groupKeyName(g: GrdCommandGroup): string {
  // labelKey looks like 'planningCommandBar.groups.plan' -> 'Plan'
  const seg = g.labelKey.split('.').pop() ?? '';
  return seg.charAt(0).toUpperCase() + seg.slice(1);
}

describe('GRD_COMMAND_MANIFEST', () => {
  it('exports six groups keyed Plan/Execute/Verify/Research/Harness/Misc', () => {
    expect(GRD_COMMAND_MANIFEST).toHaveLength(6);
    const names = GRD_COMMAND_MANIFEST.map(groupKeyName).sort();
    expect(names).toEqual([...REQUIRED_GROUPS].sort());
  });

  it('every group has at least one command', () => {
    for (const g of GRD_COMMAND_MANIFEST) {
      expect(g.commands.length).toBeGreaterThanOrEqual(1);
    }
  });

  it('covers the full supported /grd: command set', () => {
    const names = new Set(allCommands().map((c) => c.name));
    for (const cmd of REQUIRED_COMMANDS) {
      expect(names.has(cmd)).toBe(true);
    }
  });

  it('exposes at least the supported command count', () => {
    expect(allCommands().length).toBeGreaterThanOrEqual(REQUIRED_COMMANDS.length);
  });

  it('every command has non-empty name, labelKey, descKey', () => {
    for (const c of allCommands()) {
      expect(c.name).toBeTruthy();
      expect(c.labelKey).toBeTruthy();
      expect(c.descKey).toBeTruthy();
      expect(c.labelKey).toMatch(/^planningCommandBar\.cmd\./);
      expect(c.descKey).toMatch(/^planningCommandBar\.cmd\./);
    }
  });

  it('marks deprecated commands (evolve) with the deprecated flag', () => {
    const evolve = allCommands().find((c) => c.name === 'evolve');
    expect(evolve).toBeDefined();
    expect(evolve?.deprecated).toBe(true);
  });

  it('has unique command names across the manifest', () => {
    const names = allCommands().map((c) => c.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it('every command carries a group label matching its enclosing group', () => {
    for (const g of GRD_COMMAND_MANIFEST) {
      for (const c of g.commands) {
        expect(c.group).toBe(groupKeyName(g));
      }
    }
  });

  it('every group labelKey is a planningCommandBar.groups.* key', () => {
    for (const g of GRD_COMMAND_MANIFEST) {
      expect(g.labelKey).toMatch(/^planningCommandBar\.groups\./);
    }
  });
});
