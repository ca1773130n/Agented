/**
 * Declarative manifest for the GRD planning command bar.
 *
 * Single source of truth for the full supported `/grd:` command set, grouped
 * into six functional groups (Plan / Execute / Verify / Research / Harness /
 * Misc). PlanningCommandBar.vue renders straight from this manifest and the
 * planning page routes `invoke` per group:
 *   - Research-group commands -> research-start surface (20-03)
 *   - Harness-group commands  -> /harness panel deep-link (20-04)
 *   - everything else         -> grd_chat planning session
 *
 * Every command's label/desc resolves through `planningCommandBar.cmd.*`
 * i18n keys (key-identical across en/ko/ja/zh); group headers through
 * `planningCommandBar.groups.*`.
 */

export interface GrdCommand {
  /** The `/grd:<name>` command name (unique across the manifest). */
  name: string;
  /** i18n key for the button label (planningCommandBar.cmd.*). */
  labelKey: string;
  /** i18n key for the tooltip/description (planningCommandBar.cmd.*). */
  descKey: string;
  /** Marks superseded commands (e.g. evolve) — rendered but non-default. */
  deprecated?: boolean;
  /** Capitalized group key this command belongs to (Plan, Research, ...). */
  group?: string;
}

export interface GrdCommandGroup {
  /** i18n key for the group header (planningCommandBar.groups.*). */
  labelKey: string;
  commands: GrdCommand[];
}

/** Capitalized group names used for group-aware invoke routing. */
export const GRD_GROUP = {
  PLAN: 'Plan',
  EXECUTE: 'Execute',
  VERIFY: 'Verify',
  RESEARCH: 'Research',
  HARNESS: 'Harness',
  MISC: 'Misc',
} as const;

function cmd(
  name: string,
  i18nKey: string,
  group: string,
  deprecated = false
): GrdCommand {
  return {
    name,
    labelKey: `planningCommandBar.cmd.${i18nKey}.label`,
    descKey: `planningCommandBar.cmd.${i18nKey}.desc`,
    group,
    ...(deprecated ? { deprecated: true } : {}),
  };
}

export const GRD_COMMAND_MANIFEST: GrdCommandGroup[] = [
  {
    labelKey: 'planningCommandBar.groups.plan',
    commands: [
      cmd('plan-phase', 'planPhase', GRD_GROUP.PLAN),
      cmd('plan-milestone-gaps', 'planGaps', GRD_GROUP.PLAN),
      cmd('autoplan', 'autoplan', GRD_GROUP.PLAN),
      cmd('discuss-phase', 'discussPhase', GRD_GROUP.PLAN),
    ],
  },
  {
    labelKey: 'planningCommandBar.groups.execute',
    commands: [
      cmd('execute-phase', 'executePhase', GRD_GROUP.EXECUTE),
      cmd('autopilot', 'autopilot', GRD_GROUP.EXECUTE),
      cmd('quick', 'quick', GRD_GROUP.EXECUTE),
    ],
  },
  {
    labelKey: 'planningCommandBar.groups.verify',
    commands: [
      cmd('verify-phase', 'verifyPhase', GRD_GROUP.VERIFY),
      cmd('verify-work', 'verifyWork', GRD_GROUP.VERIFY),
      cmd('assess-baseline', 'assessBaseline', GRD_GROUP.VERIFY),
    ],
  },
  {
    labelKey: 'planningCommandBar.groups.research',
    commands: [
      cmd('research', 'research', GRD_GROUP.RESEARCH),
      cmd('survey', 'survey', GRD_GROUP.RESEARCH),
      cmd('deep-dive', 'deepDive', GRD_GROUP.RESEARCH),
      cmd('compare-methods', 'compareMethods', GRD_GROUP.RESEARCH),
      cmd('feasibility', 'feasibility', GRD_GROUP.RESEARCH),
    ],
  },
  {
    labelKey: 'planningCommandBar.groups.harness',
    commands: [
      cmd('harness', 'harness', GRD_GROUP.HARNESS),
      cmd('evolve', 'evolve', GRD_GROUP.HARNESS, /* deprecated */ true),
    ],
  },
  {
    labelKey: 'planningCommandBar.groups.misc',
    commands: [
      cmd('settings', 'settings', GRD_GROUP.MISC),
      cmd('sync', 'sync', GRD_GROUP.MISC),
      cmd('map-codebase', 'mapCodebase', GRD_GROUP.MISC),
      cmd('progress', 'progress', GRD_GROUP.MISC),
      cmd('help', 'help', GRD_GROUP.MISC),
    ],
  },
];

/** Flat lookup: command name -> its group name (for invoke routing). */
export const GRD_COMMAND_GROUP_BY_NAME: Record<string, string> = Object.fromEntries(
  GRD_COMMAND_MANIFEST.flatMap((g) =>
    g.commands.map((c) => [c.name, c.group ?? GRD_GROUP.MISC])
  )
);
