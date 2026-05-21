# v0.7.78 State

Status: COMPLETE — shipped PR #121 (2026-05-17).

## Shipped

The wizard previously kept its chat history in a process-local
``SkillConversationService._conversations`` dict only. Refreshing
the page or restarting the backend silently wiped every in-flight
conversation — the operator had to start over.

## Key files touched

- `backend/app/db/__init__.py`
- `backend/app/db/migrations/v07_features.py`
- `backend/app/db/skill_conversations.py`
- `backend/app/services/skill_conversation_service.py`
- `frontend/src/services/api/skills.ts`
- `frontend/src/views/SkillCreateWizard.vue`

## Reference

- PR: #121
- Commit: `ee9eb90b`
