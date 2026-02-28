"""Database package - re-exports all public functions and constants for backward compatibility.

All public functions and constants are re-exported here so that:
  from app.db import add_trigger, get_trigger  # works
  from app.db import get_connection             # works

For new code, prefer importing from specific sub-modules:
  from app.db.triggers import add_trigger
  from app.db.connection import get_connection
"""

# Infrastructure
# Agents (includes conversations and design conversations)
from .agents import (  # noqa: F401
    # Constants
    VALID_AGENT_STATUSES,
    VALID_CONVERSATION_STATUSES,
    VALID_EFFORT_LEVELS,
    # Agent CRUD
    add_agent,
    count_agents,
    # Agent conversation operations
    create_agent_conversation,
    # Design conversation operations
    create_design_conversation,
    delete_agent,
    delete_agent_conversation,
    delete_old_design_conversations,
    get_active_conversations,
    get_agent,
    get_agent_by_name,
    get_agent_conversation,
    get_all_agents,
    get_design_conversation,
    get_enabled_agents,
    list_design_conversations,
    update_agent,
    update_agent_conversation,
    update_design_conversation,
)

# Backends (fallback chains, accounts, agent sessions)
from .backends import (  # noqa: F401
    _row_to_account,
    # Row-mapping helpers
    _row_to_backend,
    auto_enable_monitoring_for_account,
    check_and_update_backend_installed,
    clear_account_rate_limit,
    create_backend_account,
    delete_agent_session,
    delete_backend_account,
    delete_fallback_chain,
    get_account_rate_limit_state,
    get_account_with_backend,
    # Backend accounts
    get_accounts_for_backend_type,
    # Agent sessions
    get_agent_session,
    get_all_accounts_with_health,
    get_all_agent_sessions,
    # Backend CRUD (used by BackendService)
    get_all_backends,
    get_backend_accounts,
    get_backend_accounts_for_auth,
    get_backend_by_id,
    get_backend_type,
    # Fallback chains
    get_fallback_chain,
    increment_account_executions,
    set_fallback_chain,
    update_account_rate_limit,
    update_backend_account,
    update_backend_last_used,
    update_backend_models,
    upsert_agent_session,
    verify_account_exists,
)

# Budgets (token usage, budget limits, execution token data)
from .budgets import (  # noqa: F401
    # Token usage
    create_token_usage_record,
    delete_budget_limit,
    get_all_budget_limits,
    get_average_output_tokens,
    # Budget limits
    get_budget_limit,
    get_current_period_spend,
    get_token_usage_count,
    get_token_usage_for_execution,
    get_token_usage_summary,
    get_token_usage_total_cost,
    get_usage_aggregated_summary,
    get_usage_by_entity,
    get_window_token_usage,
    set_budget_limit,
    # Execution token data
    update_execution_token_data,
)

# Commands
from .commands import (  # noqa: F401
    add_command,
    count_commands,
    delete_command,
    get_all_commands,
    get_command,
    get_commands_by_project,
    update_command,
)
from .connection import get_connection  # noqa: F401

# GRD (milestones, phases, plans, sessions, sync state)
from .grd import (  # noqa: F401
    add_milestone,
    add_project_phase,
    add_project_plan,
    add_project_session,
    delete_milestone,
    delete_project_phase,
    delete_project_plan,
    delete_project_session,
    delete_project_sync_state,
    get_active_sessions,
    get_milestone,
    get_milestones_by_project,
    get_phases_by_milestone,
    get_plans_by_phase,
    get_project_phase,
    get_project_plan,
    get_project_session,
    get_project_sync_state,
    get_project_sync_states,
    get_sessions_by_project,
    get_sessions_by_status,
    update_milestone,
    update_project_phase,
    update_project_plan,
    update_project_session,
    upsert_project_sync_state,
)

# Hooks
from .hooks import (  # noqa: F401
    add_hook,
    count_hooks,
    delete_hook,
    get_all_hooks,
    get_hook,
    get_hooks_by_event,
    get_hooks_by_project,
    update_hook,
)

# ID generators and constants
from .ids import (  # noqa: F401
    AGENT_ID_LENGTH,
    AGENT_ID_PREFIX,
    CONVERSATION_ID_LENGTH,
    CONVERSATION_ID_PREFIX,
    MCP_SERVER_ID_LENGTH,
    MCP_SERVER_ID_PREFIX,
    MESSAGE_ID_LENGTH,
    MESSAGE_ID_PREFIX,
    MILESTONE_ID_LENGTH,
    # New v0.4.0 ID generators
    MILESTONE_ID_PREFIX,
    PHASE_ID_LENGTH,
    PHASE_ID_PREFIX,
    PLAN_ID_LENGTH,
    PLAN_ID_PREFIX,
    PLUGIN_ID_LENGTH,
    PLUGIN_ID_PREFIX,
    PRODUCT_DECISION_ID_LENGTH,
    PRODUCT_DECISION_ID_PREFIX,
    PRODUCT_ID_LENGTH,
    PRODUCT_ID_PREFIX,
    PRODUCT_MILESTONE_ID_LENGTH,
    PRODUCT_MILESTONE_ID_PREFIX,
    PROJECT_ID_LENGTH,
    PROJECT_ID_PREFIX,
    PROJECT_SESSION_ID_LENGTH,
    PROJECT_SESSION_ID_PREFIX,
    ROTATION_EVENT_ID_LENGTH,
    ROTATION_EVENT_ID_PREFIX,
    SESSION_ID_LENGTH,
    SESSION_ID_PREFIX,
    SKETCH_ID_LENGTH,
    SKETCH_ID_PREFIX,
    SUPER_AGENT_ID_LENGTH,
    # New v0.3.0 ID generators
    SUPER_AGENT_ID_PREFIX,
    TEAM_ID_LENGTH,
    TEAM_ID_PREFIX,
    TRIGGER_ID_LENGTH,
    TRIGGER_ID_PREFIX,
    WORKFLOW_EXECUTION_ID_LENGTH,
    WORKFLOW_EXECUTION_ID_PREFIX,
    WORKFLOW_ID_LENGTH,
    WORKFLOW_ID_PREFIX,
    _generate_short_id,
    _get_unique_agent_id,
    _get_unique_conversation_id,
    _get_unique_mcp_server_id,
    _get_unique_message_id,
    _get_unique_milestone_id,
    _get_unique_phase_id,
    _get_unique_plan_id,
    _get_unique_plugin_id,
    _get_unique_product_decision_id,
    _get_unique_product_id,
    _get_unique_product_milestone_id,
    _get_unique_project_id,
    _get_unique_project_session_id,
    _get_unique_rotation_event_id,
    _get_unique_session_id,
    _get_unique_sketch_id,
    _get_unique_super_agent_id,
    _get_unique_team_id,
    _get_unique_trigger_id,
    _get_unique_workflow_execution_id,
    _get_unique_workflow_id,
    generate_agent_id,
    generate_conversation_id,
    generate_execution_id,
    generate_mcp_server_id,
    generate_message_id,
    generate_milestone_id,
    generate_phase_id,
    generate_plan_id,
    generate_plugin_id,
    generate_product_decision_id,
    generate_product_id,
    generate_product_milestone_id,
    generate_project_id,
    generate_project_session_id,
    generate_rotation_event_id,
    generate_session_id,
    generate_sketch_id,
    generate_super_agent_id,
    generate_team_id,
    generate_trigger_id,
    generate_workflow_execution_id,
    generate_workflow_id,
)

# MCP servers and execution type handlers
from .mcp_servers import (  # noqa: F401
    add_execution_type_handler,
    add_mcp_server,
    assign_mcp_to_project,
    count_mcp_servers,
    delete_execution_type_handler,
    delete_mcp_server,
    get_all_execution_type_handlers,
    get_all_mcp_servers,
    get_handlers_for_type,
    get_mcp_server,
    get_project_mcp_servers,
    unassign_mcp_from_project,
    update_execution_type_handler,
    update_mcp_server,
    update_project_mcp_assignment,
)

# Messages (agent_messages)
from .messages import (  # noqa: F401
    add_agent_message,
    batch_add_broadcast_messages,
    expire_stale_messages,
    get_inbox_messages,
    get_outbox_messages,
    get_pending_messages,
    update_message_status,
)

# Schema and migrations
from .migrations import init_db  # noqa: F401

# Monitoring (rate limit snapshots, monitoring config, setup executions)
from .monitoring import (  # noqa: F401
    # Setup executions
    create_setup_execution,
    delete_old_snapshots,
    # Pending rate-limit retries
    delete_pending_retry,
    get_all_pending_retries,
    get_latest_snapshots,
    # Monitoring config
    get_monitoring_config,
    get_pending_retries_due,
    get_rate_limit_stats_by_period,
    get_setup_execution,
    get_setup_executions_for_project,
    get_snapshot_history,
    # Rate limit snapshots
    insert_rate_limit_snapshot,
    save_monitoring_config,
    update_setup_execution,
    upsert_pending_retry,
)

# Plugins (includes components, marketplaces, sync state, exports)
from .plugins import (  # noqa: F401
    # Marketplaces
    add_marketplace,
    add_marketplace_plugin,
    add_plugin,
    add_plugin_component,
    # Plugin exports
    add_plugin_export,
    # Sync state
    add_sync_state,
    count_plugins,
    delete_marketplace,
    delete_marketplace_plugin,
    delete_plugin,
    delete_plugin_component,
    delete_plugin_export,
    delete_sync_states_for_plugin,
    get_all_marketplaces,
    get_all_plugins,
    get_marketplace,
    get_marketplace_plugins,
    get_plugin,
    # Plugin components
    get_plugin_component_by_name,
    get_plugin_components,
    get_plugin_detail,
    get_plugin_export,
    get_plugin_exports_for_plugin,
    get_sync_state,
    get_sync_states_for_plugin,
    update_marketplace,
    update_plugin,
    update_plugin_component,
    update_plugin_export,
    update_sync_state,
)

# Products
from .products import (  # noqa: F401
    add_product,
    count_products,
    delete_product,
    get_all_products,
    get_product,
    get_product_detail,
    update_product,
)

# Projects (includes skills, installations, team assignments)
from .projects import (  # noqa: F401
    add_project,
    # Project installations
    add_project_installation,
    # Project skills
    add_project_skill,
    # Project team edges (org chart)
    add_project_team_edge,
    # Project team assignments
    assign_team_to_project,
    clear_project_skills,
    count_projects,
    delete_project,
    delete_project_installation,
    delete_project_skill,
    delete_project_skill_by_id,
    delete_project_team_edge,
    delete_project_team_edges_by_project,
    get_all_projects,
    get_project,
    get_project_detail,
    get_project_installation,
    get_project_installations,
    get_project_skills,
    get_project_team_edges,
    get_project_teams,
    get_projects_with_github_repo,
    unassign_team_from_project,
    update_project,
    update_project_clone_status,
    update_project_team_topology_config,
)

# Rotations and organizational (rotation events, product decisions, product milestones, team connections)
from .rotations import (  # noqa: F401
    add_milestone_project,
    add_product_decision,
    add_product_milestone,
    add_rotation_event,
    add_team_connection,
    delete_milestone_project,
    delete_product_decision,
    delete_product_milestone,
    delete_team_connection,
    get_all_rotation_events,
    get_decisions_by_product,
    get_milestones_by_product,
    get_product_decision,
    get_product_milestone,
    get_projects_for_milestone,
    get_rotation_event,
    get_rotation_events_by_execution,
    get_team_connections,
    update_product_decision,
    update_product_milestone,
    update_rotation_event,
)

# Rules
from .rules import (  # noqa: F401
    add_rule,
    count_rules,
    delete_rule,
    get_all_rules,
    get_rule,
    get_rules_by_project,
    get_rules_by_type,
    update_rule,
)
from .seeds import (  # noqa: F401
    auto_register_project_root,
    migrate_existing_paths,
    seed_predefined_triggers,
    seed_preset_mcp_servers,
)

# Settings
from .settings import (  # noqa: F401
    delete_setting,
    get_all_settings,
    get_setting,
    set_setting,
)

# Sketches
from .sketches import (  # noqa: F401
    add_sketch,
    delete_sketch,
    get_all_sketches,
    get_recent_classified_sketches,
    get_sketch,
    update_sketch,
)

# Skills (user_skills)
from .skills import (  # noqa: F401
    add_user_skill,
    delete_user_skill,
    get_all_user_skills,
    get_enabled_user_skills,
    get_harness_skills,
    get_user_skill,
    get_user_skill_by_name,
    toggle_skill_harness,
    update_user_skill,
)

# SuperAgents (super_agents + documents + sessions)
from .super_agents import (  # noqa: F401
    VALID_DOC_TYPES,
    add_super_agent,
    add_super_agent_document,
    add_super_agent_session,
    count_active_sessions,
    delete_super_agent,
    delete_super_agent_document,
    delete_super_agent_session,
    get_active_sessions_list,
    get_all_super_agents,
    get_super_agent,
    get_super_agent_document,
    get_super_agent_documents,
    get_super_agent_session,
    get_super_agent_sessions,
    update_super_agent,
    update_super_agent_document,
    update_super_agent_session,
)

# Teams (includes members, agent assignments, and edges)
from .teams import (  # noqa: F401
    # Team edge operations (directed graph)
    VALID_EDGE_TYPES,
    VALID_ENTITY_TYPES,
    add_team,
    # Team agent assignment operations
    add_team_agent_assignment,
    add_team_edge,
    # Team member operations
    add_team_member,
    count_teams,
    delete_team,
    delete_team_agent_assignment,
    delete_team_agent_assignments_bulk,
    delete_team_edge,
    delete_team_edges_by_team,
    get_all_teams,
    get_team,
    get_team_agent_assignments,
    get_team_by_name,
    get_team_detail,
    get_team_edges,
    get_team_hierarchy,
    get_team_members,
    get_teams_by_trigger_source,
    get_webhook_teams,
    remove_team_member,
    update_team,
    update_team_member,
)

# Triggers (includes paths, symlinks, execution logs, PR reviews)
from .triggers import (  # noqa: F401
    PREDEFINED_TRIGGER,
    PREDEFINED_TRIGGER_ID,
    PREDEFINED_TRIGGER_IDS,
    PREDEFINED_TRIGGERS,
    # Constants
    VALID_BACKENDS,
    VALID_SCHEDULE_TYPES,
    VALID_TRIGGER_SOURCES,
    _create_symlink,
    # Symlink helpers
    _ensure_symlink_dir,
    _generate_symlink_name,
    _remove_symlink,
    _sanitize_name,
    add_github_repo,
    # PR review operations
    add_pr_review,
    # Project path operations
    add_project_path,
    add_project_to_trigger,
    # Trigger CRUD
    add_trigger,
    # Execution log operations
    count_all_execution_logs,
    count_execution_logs_for_trigger,
    create_execution_log,
    delete_old_execution_logs,
    delete_pr_review,
    delete_trigger,
    get_active_execution_count,
    get_all_execution_logs,
    get_all_pr_reviews,
    get_all_triggers,
    get_execution_log,
    get_execution_logs_for_trigger,
    get_latest_execution_for_trigger,
    get_paths_for_trigger,
    get_paths_for_trigger_detailed,
    get_pr_review,
    get_pr_review_history,
    get_pr_review_stats,
    get_pr_reviews_count,
    get_pr_reviews_for_trigger,
    get_prompt_template_history,
    get_running_execution_for_trigger,
    get_symlink_paths_for_trigger,
    get_trigger,
    get_trigger_by_name,
    get_triggers_by_trigger_source,
    get_webhook_triggers,
    list_paths_for_trigger,
    log_prompt_template_change,
    mark_stale_executions_interrupted,
    remove_github_repo,
    remove_project_from_trigger,
    remove_project_path,
    update_execution_log,
    update_execution_status_cas,
    update_pr_review,
    update_trigger,
    update_trigger_auto_resolve,
    update_trigger_last_run,
    update_trigger_next_run,
)

# Workflows (workflows, versions, executions, node executions)
from .workflows import (  # noqa: F401
    add_workflow,
    add_workflow_execution,
    add_workflow_node_execution,
    add_workflow_version,
    add_workflow_version_raw,
    delete_workflow,
    get_all_workflows,
    get_latest_workflow_version,
    get_running_workflow_executions,
    get_workflow,
    get_workflow_execution,
    get_workflow_executions,
    get_workflow_node_executions,
    get_workflow_versions,
    publish_workflow_version,
    update_workflow,
    update_workflow_execution,
    update_workflow_node_execution,
    validate_workflow_graph,
)
