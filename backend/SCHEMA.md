# Agented Database Schema

*Generated: 2026-02-15 16:19 UTC | Tables: 30*

## agent_conversations

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | TEXT | YES |  | YES |
| agent_id | TEXT | YES |  |  |
| status | TEXT | YES | 'active' |  |
| messages | TEXT | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |
| updated_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `agent_id` -> `agents`.`id`

**Indexes:**

- `idx_agent_conversations_agent_id` (agent_id)
- `idx_agent_conversations_status` (status)
- `sqlite_autoindex_agent_conversations_1` (UNIQUE id)

## agent_sessions

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| account_id | INTEGER | NO |  |  |
| state | TEXT | NO | 'queued' |  |
| stop_reason | TEXT | YES |  |  |
| stop_window_type | TEXT | YES |  |  |
| stop_eta_minutes | REAL | YES |  |  |
| resume_estimate | TEXT | YES |  |  |
| consecutive_safe_polls | INTEGER | YES | 0 |  |
| updated_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Indexes:**

- `idx_agent_sessions_state` (state)
- `sqlite_autoindex_agent_sessions_1` (UNIQUE account_id)

## agents

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | TEXT | YES |  | YES |
| name | TEXT | NO |  |  |
| description | TEXT | YES |  |  |
| role | TEXT | YES |  |  |
| goals | TEXT | YES |  |  |
| context | TEXT | YES |  |  |
| backend_type | TEXT | NO | 'claude' |  |
| enabled | INTEGER | YES | 1 |  |
| skills | TEXT | YES |  |  |
| documents | TEXT | YES |  |  |
| system_prompt | TEXT | YES |  |  |
| creation_conversation_id | TEXT | YES |  |  |
| creation_status | TEXT | YES | 'completed' |  |
| triggers | TEXT | YES |  |  |
| color | TEXT | YES |  |  |
| icon | TEXT | YES |  |  |
| model | TEXT | YES |  |  |
| temperature | REAL | YES |  |  |
| tools | TEXT | YES |  |  |
| autonomous | INTEGER | YES | 0 |  |
| allowed_tools | TEXT | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |
| updated_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Indexes:**

- `idx_agents_created_at` (created_at)
- `idx_agents_enabled` (enabled)
- `sqlite_autoindex_agents_1` (UNIQUE id)

## budget_limits

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| entity_type | TEXT | NO |  |  |
| entity_id | TEXT | NO |  |  |
| period | TEXT | NO | 'monthly' |  |
| soft_limit_usd | REAL | YES |  |  |
| hard_limit_usd | REAL | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |
| updated_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Indexes:**

- `sqlite_autoindex_budget_limits_1` (UNIQUE entity_type, entity_id)

## commands

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| name | TEXT | NO |  |  |
| description | TEXT | YES |  |  |
| content | TEXT | YES |  |  |
| arguments | TEXT | YES |  |  |
| enabled | INTEGER | YES | 1 |  |
| project_id | TEXT | YES |  |  |
| source_path | TEXT | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |
| updated_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `project_id` -> `projects`.`id`

**Indexes:**

- `idx_commands_enabled` (enabled)
- `idx_commands_project` (project_id)

## execution_logs

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| execution_id | TEXT | NO |  |  |
| trigger_id | TEXT | NO |  |  |
| trigger_type | TEXT | NO |  |  |
| started_at | TIMESTAMP | NO |  |  |
| finished_at | TIMESTAMP | YES |  |  |
| duration_ms | INTEGER | YES |  |  |
| prompt | TEXT | YES |  |  |
| backend_type | TEXT | NO |  |  |
| command | TEXT | YES |  |  |
| status | TEXT | NO | 'running' |  |
| exit_code | INTEGER | YES |  |  |
| error_message | TEXT | YES |  |  |
| stdout_log | TEXT | YES |  |  |
| stderr_log | TEXT | YES |  |  |
| trigger_config_snapshot | TEXT | YES |  |  |
| account_id | INTEGER | YES |  |  |
| input_tokens | INTEGER | YES |  |  |
| output_tokens | INTEGER | YES |  |  |
| total_cost_usd | REAL | YES |  |  |

**Foreign Keys:**

- `trigger_id` -> `triggers`.`id`

**Indexes:**

- `idx_execution_logs_status` (status)
- `idx_execution_logs_started_at` (started_at)
- `idx_execution_logs_trigger_id` (trigger_id)
- `sqlite_autoindex_execution_logs_1` (UNIQUE execution_id)

## fallback_chains

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| entity_type | TEXT | NO |  |  |
| entity_id | TEXT | NO |  |  |
| chain_order | INTEGER | NO |  |  |
| backend_type | TEXT | NO |  |  |
| account_id | INTEGER | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Indexes:**

- `idx_fallback_chains_entity` (entity_type, entity_id)
- `sqlite_autoindex_fallback_chains_1` (UNIQUE entity_id, chain_order)

## hooks

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| name | TEXT | NO |  |  |
| event | TEXT | NO |  |  |
| description | TEXT | YES |  |  |
| content | TEXT | YES |  |  |
| enabled | INTEGER | YES | 1 |  |
| project_id | TEXT | YES |  |  |
| source_path | TEXT | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |
| updated_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `project_id` -> `projects`.`id`

**Indexes:**

- `idx_hooks_enabled` (enabled)
- `idx_hooks_event` (event)
- `idx_hooks_project` (project_id)

## marketplace_plugins

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | TEXT | YES |  | YES |
| marketplace_id | TEXT | NO |  |  |
| plugin_id | TEXT | YES |  |  |
| remote_name | TEXT | YES |  |  |
| version | TEXT | YES |  |  |
| installed_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `plugin_id` -> `plugins`.`id`
- `marketplace_id` -> `marketplaces`.`id`

**Indexes:**

- `idx_marketplace_plugins_marketplace` (marketplace_id)
- `sqlite_autoindex_marketplace_plugins_1` (UNIQUE id)

## marketplaces

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | TEXT | YES |  | YES |
| name | TEXT | NO |  |  |
| url | TEXT | NO |  |  |
| type | TEXT | YES | 'git' |  |
| is_default | BOOLEAN | YES | FALSE |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Indexes:**

- `idx_marketplaces_name` (name)
- `sqlite_autoindex_marketplaces_1` (UNIQUE id)

## plugin_components

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| plugin_id | TEXT | NO |  |  |
| name | TEXT | NO |  |  |
| type | TEXT | NO |  |  |
| content | TEXT | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |
| updated_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `plugin_id` -> `plugins`.`id`

**Indexes:**

- `idx_plugin_components_type` (type)
- `idx_plugin_components_plugin` (plugin_id)

## plugin_exports

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| plugin_id | TEXT | NO |  |  |
| team_id | TEXT | YES |  |  |
| export_format | TEXT | NO |  |  |
| export_path | TEXT | YES |  |  |
| marketplace_id | TEXT | YES |  |  |
| version | TEXT | YES | '1.0.0' |  |
| status | TEXT | YES | 'draft' |  |
| last_exported_at | TIMESTAMP | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `marketplace_id` -> `marketplaces`.`id`
- `team_id` -> `teams`.`id`
- `plugin_id` -> `plugins`.`id`

**Indexes:**

- `idx_plugin_exports_plugin` (plugin_id)

## plugins

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | TEXT | YES |  | YES |
| name | TEXT | NO |  |  |
| description | TEXT | YES |  |  |
| version | TEXT | YES | '1.0.0' |  |
| status | TEXT | YES | 'draft' |  |
| author | TEXT | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |
| updated_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Indexes:**

- `idx_plugins_status` (status)
- `idx_plugins_name` (name)
- `sqlite_autoindex_plugins_1` (UNIQUE id)

## pr_reviews

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| trigger_id | TEXT | NO | 'bot-pr-review' |  |
| project_name | TEXT | NO |  |  |
| github_repo_url | TEXT | YES |  |  |
| pr_number | INTEGER | NO |  |  |
| pr_url | TEXT | NO |  |  |
| pr_title | TEXT | NO |  |  |
| pr_author | TEXT | YES |  |  |
| pr_status | TEXT | NO | 'open' |  |
| review_status | TEXT | NO | 'pending' |  |
| review_comment | TEXT | YES |  |  |
| fixes_applied | INTEGER | YES | 0 |  |
| fix_comment | TEXT | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |
| updated_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `trigger_id` -> `triggers`.`id`

**Indexes:**

- `idx_pr_reviews_review_status` (review_status)
- `idx_pr_reviews_pr_status` (pr_status)
- `idx_pr_reviews_trigger_id` (trigger_id)

## products

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | TEXT | YES |  | YES |
| name | TEXT | NO |  |  |
| description | TEXT | YES |  |  |
| status | TEXT | YES | 'active' |  |
| owner_team_id | TEXT | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |
| updated_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `owner_team_id` -> `teams`.`id`

**Indexes:**

- `idx_products_status` (status)
- `idx_products_name` (name)
- `sqlite_autoindex_products_1` (UNIQUE id)

## project_installations

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| project_id | TEXT | NO |  |  |
| component_type | TEXT | NO |  |  |
| component_id | TEXT | NO |  |  |
| installed_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Indexes:**

- `idx_project_installations_project` (project_id)
- `sqlite_autoindex_project_installations_1` (UNIQUE project_id, component_type, component_id)

## project_paths

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| trigger_id | TEXT | NO |  |  |
| local_project_path | TEXT | NO |  |  |
| symlink_name | TEXT | YES |  |  |
| path_type | TEXT | NO | 'local' |  |
| github_repo_url | TEXT | YES |  |  |
| project_id | TEXT | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `trigger_id` -> `triggers`.`id`
- `project_id` -> `projects`.`id`

**Indexes:**

- `sqlite_autoindex_project_paths_1` (UNIQUE trigger_id, local_project_path)

## project_skills

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| project_id | TEXT | NO |  |  |
| skill_name | TEXT | NO |  |  |
| skill_path | TEXT | YES |  |  |
| source | TEXT | YES | 'manual' |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `project_id` -> `projects`.`id`

**Indexes:**

- `idx_project_skills_project` (project_id)
- `sqlite_autoindex_project_skills_1` (UNIQUE project_id, skill_name)

## project_teams

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| project_id | TEXT | NO |  |  |
| team_id | TEXT | NO |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `team_id` -> `teams`.`id`
- `project_id` -> `projects`.`id`

**Indexes:**

- `idx_project_teams_team` (team_id)
- `idx_project_teams_project` (project_id)
- `sqlite_autoindex_project_teams_1` (UNIQUE project_id, team_id)

## projects

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | TEXT | YES |  | YES |
| name | TEXT | NO |  |  |
| description | TEXT | YES |  |  |
| status | TEXT | YES | 'active' |  |
| product_id | TEXT | YES |  |  |
| github_repo | TEXT | YES |  |  |
| owner_team_id | TEXT | YES |  |  |
| local_path | TEXT | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |
| updated_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `owner_team_id` -> `teams`.`id`
- `product_id` -> `products`.`id`

**Indexes:**

- `idx_projects_product` (product_id)
- `idx_projects_status` (status)
- `idx_projects_name` (name)
- `sqlite_autoindex_projects_1` (UNIQUE id)

## rate_limit_snapshots

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| account_id | INTEGER | NO |  |  |
| backend_type | TEXT | NO |  |  |
| window_type | TEXT | NO |  |  |
| tokens_used | INTEGER | YES | 0 |  |
| tokens_limit | INTEGER | YES | 0 |  |
| percentage | REAL | YES | 0.0 |  |
| threshold_level | TEXT | YES | 'normal' |  |
| resets_at | TIMESTAMP | YES |  |  |
| recorded_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `account_id` -> `backend_accounts`.`id`

**Indexes:**

- `idx_snapshots_time` (recorded_at)
- `idx_snapshots_account_time` (account_id, recorded_at)

## rules

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| name | TEXT | NO |  |  |
| description | TEXT | YES |  |  |
| rule_type | TEXT | NO | 'validation' |  |
| condition | TEXT | YES |  |  |
| action | TEXT | YES |  |  |
| enabled | INTEGER | YES | 1 |  |
| project_id | TEXT | YES |  |  |
| source_path | TEXT | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |
| updated_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `project_id` -> `projects`.`id`

**Indexes:**

- `idx_rules_enabled` (enabled)
- `idx_rules_type` (rule_type)
- `idx_rules_project` (project_id)

## setup_executions

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | TEXT | YES |  | YES |
| project_id | TEXT | NO |  |  |
| command | TEXT | NO |  |  |
| status | TEXT | NO | 'running' |  |
| started_at | TEXT | NO |  |  |
| finished_at | TEXT | YES |  |  |
| exit_code | INTEGER | YES |  |  |
| error_message | TEXT | YES |  |  |

**Foreign Keys:**

- `project_id` -> `projects`.`id`

**Indexes:**

- `sqlite_autoindex_setup_executions_1` (UNIQUE id)

## sync_state

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| plugin_id | TEXT | NO |  |  |
| entity_type | TEXT | NO |  |  |
| entity_id | TEXT | NO |  |  |
| file_path | TEXT | NO |  |  |
| content_hash | TEXT | YES |  |  |
| last_synced_at | TIMESTAMP | YES |  |  |
| sync_direction | TEXT | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `plugin_id` -> `plugins`.`id`

**Indexes:**

- `idx_sync_state_plugin` (plugin_id)
- `sqlite_autoindex_sync_state_1` (UNIQUE plugin_id, entity_type, entity_id)

## team_agent_assignments

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| team_id | TEXT | NO |  |  |
| agent_id | TEXT | NO |  |  |
| entity_type | TEXT | NO |  |  |
| entity_id | TEXT | NO |  |  |
| entity_name | TEXT | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `agent_id` -> `agents`.`id`
- `team_id` -> `teams`.`id`

**Indexes:**

- `idx_taa_agent` (team_id, agent_id)
- `idx_taa_team` (team_id)
- `sqlite_autoindex_team_agent_assignments_1` (UNIQUE team_id, agent_id, entity_type, entity_id)

## team_members

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| team_id | TEXT | NO |  |  |
| name | TEXT | NO |  |  |
| email | TEXT | YES |  |  |
| role | TEXT | YES | 'member' |  |
| layer | TEXT | YES | 'backend' |  |
| description | TEXT | YES |  |  |
| agent_id | TEXT | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `agent_id` -> `agents`.`id`
- `team_id` -> `teams`.`id`

**Indexes:**

- `idx_team_members_team` (team_id)
- `sqlite_autoindex_team_members_1` (UNIQUE team_id, name)

## teams

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | TEXT | YES |  | YES |
| name | TEXT | NO |  |  |
| description | TEXT | YES |  |  |
| color | TEXT | YES | '#00d4ff' |  |
| leader_id | TEXT | YES |  |  |
| source | TEXT | YES | 'ui_created' |  |
| topology | TEXT | YES | NULL |  |
| topology_config | TEXT | YES | NULL |  |
| trigger_source | TEXT | YES | NULL |  |
| trigger_config | TEXT | YES | NULL |  |
| enabled | INTEGER | YES | 1 |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |
| updated_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `leader_id` -> `agents`.`id`

**Indexes:**

- `idx_teams_name` (name)
- `sqlite_autoindex_teams_1` (UNIQUE id)

## token_usage

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| execution_id | TEXT | NO |  |  |
| entity_type | TEXT | NO |  |  |
| entity_id | TEXT | NO |  |  |
| backend_type | TEXT | NO |  |  |
| account_id | INTEGER | YES |  |  |
| input_tokens | INTEGER | YES | 0 |  |
| output_tokens | INTEGER | YES | 0 |  |
| cache_read_tokens | INTEGER | YES | 0 |  |
| cache_creation_tokens | INTEGER | YES | 0 |  |
| total_cost_usd | REAL | YES | 0 |  |
| num_turns | INTEGER | YES | 0 |  |
| duration_api_ms | INTEGER | YES | 0 |  |
| session_id | TEXT | YES |  |  |
| recorded_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Indexes:**

- `idx_token_usage_execution` (execution_id)
- `idx_token_usage_recorded` (recorded_at)
- `idx_token_usage_entity` (entity_type, entity_id)

## triggers

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | TEXT | YES |  | YES |
| name | TEXT | NO |  |  |
| group_id | INTEGER | NO | 0 |  |
| detection_keyword | TEXT | NO | '' |  |
| prompt_template | TEXT | NO |  |  |
| backend_type | TEXT | NO | 'claude' |  |
| trigger_source | TEXT | NO | 'webhook' |  |
| match_field_path | TEXT | YES |  |  |
| match_field_value | TEXT | YES |  |  |
| text_field_path | TEXT | YES | 'text' |  |
| is_predefined | INTEGER | YES | 0 |  |
| enabled | INTEGER | YES | 1 |  |
| auto_resolve | INTEGER | YES | 0 |  |
| schedule_type | TEXT | YES |  |  |
| schedule_time | TEXT | YES |  |  |
| schedule_day | INTEGER | YES |  |  |
| schedule_timezone | TEXT | YES | 'Asia/Seoul' |  |
| next_run_at | TIMESTAMP | YES |  |  |
| last_run_at | TIMESTAMP | YES |  |  |
| skill_command | TEXT | YES |  |  |
| model | TEXT | YES |  |  |
| execution_mode | TEXT | YES | 'direct' |  |
| team_id | TEXT | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Foreign Keys:**

- `team_id` -> `teams`.`id`

**Indexes:**

- `sqlite_autoindex_triggers_1` (UNIQUE id)

## user_skills

| Column | Type | Nullable | Default | PK |
|--------|------|----------|---------|-----|
| id | INTEGER | YES |  | YES |
| skill_name | TEXT | NO |  |  |
| skill_path | TEXT | NO |  |  |
| description | TEXT | YES |  |  |
| enabled | INTEGER | YES | 1 |  |
| selected_for_harness | INTEGER | YES | 0 |  |
| metadata | TEXT | YES |  |  |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |
| updated_at | TIMESTAMP | YES | CURRENT_TIMESTAMP |  |

**Indexes:**

- `idx_user_skills_harness` (selected_for_harness)
- `idx_user_skills_enabled` (enabled)
- `sqlite_autoindex_user_skills_1` (UNIQUE skill_name)

---
*Note: 4 additional tables (settings, ai_backends, backend_accounts, design_conversations) exist only in migration code and are not created in the fresh-schema path. They will appear in production databases that have been migrated.*
