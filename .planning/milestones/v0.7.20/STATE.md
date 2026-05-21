# v0.7.20 State

Status: COMPLETE — shipped PR #75 (2026-05-10).

## Shipped

v0.7.18 shipped the AiChatPanel CLI-runner toggle defaulting OFF based
on the original "turned off by default" wording, but the actual intent
(scoping option b) was that all agent-driven flows should use the CLI
runner — sketches, agent chats, super-agent sessions, design
conversations, and project chat are all places where the user wants
agents to actually use tools, not pure-token CLIProxy chat.

## Key files touched

- `backend/app/services/base_conversation_service.py`
- `backend/app/services/cli_agent_runner_service.py`
- `backend/app/services/streaming_helper.py`
- `frontend/src/composables/useConversation.ts`
- `frontend/src/views/ProjectManagementPage.vue`
- `frontend/src/views/SketchChatPage.vue`

## Reference

- PR: #75
- Commit: `bc70bbc1`
