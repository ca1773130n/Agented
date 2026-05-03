# v0.5.9 — finish path-Y + cleanup tail

Two-part milestone:

1. Migrate the last 2 chat-bearing pages (AIBackendsPage,
   SuperAgentPlayground) to upstream's self-managed `AiChatPanel`.
2. Delete the now-redundant Agented local components + type shims
   (~2080 LoC). The upstream is canonical; Agented consumes as a
   library user.

After v0.5.9: path Y is closed. v0.5.10+ owns E (production hardening).
