/**
 * Orchestrates applying an AI-generated team config (team + topology + agents +
 * members + skill/entity assignments) against the backend.
 *
 * Extracted from TeamsPage so the multi-step apply — and crucially its
 * partial-failure accounting — is unit-testable without driving the DOM.
 *
 * The previous in-component version swallowed every per-step failure and then
 * unconditionally reported success as long as the (cheap) team shell was
 * created, so a config where every agent/member/assignment failed still told
 * the operator "team created from generated config". This returns a structured
 * outcome instead, letting the caller report honestly.
 *
 * Duplicate-ish failures on member/assignment add (HTTP 409 — "already exists")
 * are intentionally NOT counted as issues: the original code skipped them on
 * purpose, and re-adding an existing member is a no-op, not a real failure.
 */
import { teamApi, agentApi, userSkillsApi, ApiError } from '../services/api';
import type { GeneratedTeamConfig } from '../services/api';

export type ApplyIssueKind = 'topology' | 'agent' | 'member' | 'skill' | 'assignment';

export interface ApplyIssue {
  kind: ApplyIssueKind;
  /** Human-readable subject (agent name, entity name) when available. */
  name?: string;
}

export interface ApplyOutcome {
  /** `null` when the team itself could not be created (nothing else attempted). */
  teamId: string | null;
  /** Empty when the whole config applied cleanly. */
  issues: ApplyIssue[];
  membersAdded: number;
  assignmentsAdded: number;
}

export interface ApplyDeps {
  /** Description to stamp on agents auto-created for the team (caller supplies i18n). */
  autoAgentDescription: (teamName: string) => string;
}

/** A duplicate / already-exists conflict is benign — the original flow skipped it. */
function isBenignConflict(e: unknown): boolean {
  return e instanceof ApiError && e.status === 409;
}

export async function applyGeneratedConfig(
  config: GeneratedTeamConfig,
  deps: ApplyDeps,
): Promise<ApplyOutcome> {
  const issues: ApplyIssue[] = [];
  let membersAdded = 0;
  let assignmentsAdded = 0;

  // 1. Create the team shell. A failure here throws to the caller (full failure).
  const result = await teamApi.create({
    name: config.name,
    description: config.description || undefined,
    color: config.color || undefined,
  });

  const teamId = result.team?.id ?? null;
  if (!teamId) {
    return { teamId: null, issues, membersAdded, assignmentsAdded };
  }

  // 2. Topology (optional).
  if (config.topology) {
    try {
      await teamApi.updateTopology(teamId, {
        topology: config.topology,
        topology_config: JSON.stringify(config.topology_config || {}),
      });
    } catch {
      issues.push({ kind: 'topology' });
    }
  }

  // 3. Agents → members → assignments.
  for (const agentCfg of config.agents) {
    let agentId = agentCfg.agent_id ?? undefined;

    // Auto-create the agent when the AI suggested a brand-new one.
    if (!agentId) {
      try {
        const agentResult = await agentApi.create({
          name: agentCfg.name,
          role: agentCfg.role || 'member',
          description: deps.autoAgentDescription(config.name),
        });
        agentId = agentResult.agent_id;
      } catch {
        issues.push({ kind: 'agent', name: agentCfg.name });
        continue;
      }
    }

    // Add as a team member (409 = already a member, benign).
    try {
      await teamApi.addMember(teamId, {
        name: agentCfg.name,
        role: agentCfg.role || 'member',
        agent_id: agentId,
      });
      membersAdded++;
    } catch (e) {
      if (!isBenignConflict(e)) issues.push({ kind: 'member', name: agentCfg.name });
    }

    // Skill/entity assignments for this agent.
    for (const assignment of agentCfg.assignments) {
      if (assignment.valid === false) continue;

      if (assignment.needs_creation && assignment.entity_type === 'skill') {
        try {
          await userSkillsApi.add({
            skill_name: assignment.entity_id,
            skill_path: `generated/${assignment.entity_id}`,
            description: assignment.entity_name || assignment.entity_id,
          });
        } catch {
          // Still attempt the assignment in case the skill already exists,
          // but record that creation failed.
          issues.push({ kind: 'skill', name: assignment.entity_name || assignment.entity_id });
        }
      }

      try {
        await teamApi.addAssignment(teamId, agentId, {
          entity_type: assignment.entity_type,
          entity_id: assignment.entity_id,
          entity_name: assignment.entity_name || undefined,
        });
        assignmentsAdded++;
      } catch (e) {
        if (!isBenignConflict(e)) {
          issues.push({ kind: 'assignment', name: assignment.entity_name || assignment.entity_id });
        }
      }
    }
  }

  return { teamId, issues, membersAdded, assignmentsAdded };
}
