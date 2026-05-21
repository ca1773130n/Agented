# v0.7.77 State

Status: COMPLETE — shipped 2026-05-17.

## Shipped

The skills wizard now produces real Anthropic-format Skill packages — SKILL.md with YAML frontmatter, plus optional `scripts/` (chmod 755 helpers claude invokes via Bash), `references/` (long-form docs claude loads on demand), `assets/` (static files). A slide-over preview drawer renders the full file tree before commit so operators see exactly what will land on disk.

## Key files touched

- `backend/app/services/skill_conversation_service.py`
- `docs/superpowers/specs/2026-05-17-full-skill-package-creation-design.md`
- `frontend/src/components/skills/SkillCreatePreviewDrawer.vue`
- `frontend/src/composables/useConversation.ts`
- `frontend/src/services/api/skills.ts`
- `frontend/src/views/SkillCreateWizard.vue`

## Reference

- Commit: `1deb9a60`
