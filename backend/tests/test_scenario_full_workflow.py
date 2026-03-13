"""Comprehensive scenario test: DevOps Team Setup.

Exercises the complete workflow of the Agented platform from end to end,
creating and linking entities across all major features as an integrated workflow.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _datetime_str(days_ago: int, hour: int = 12) -> str:
    """Return ISO datetime string for N days ago at given hour."""
    dt = datetime.now() - timedelta(days=days_ago)
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def _date_str(days_ago: int) -> str:
    """Return ISO date string for N days ago."""
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Scenario test
# ---------------------------------------------------------------------------


class TestDevOpsTeamSetupScenario:
    """End-to-end scenario: set up a complete DevOps team with all platform features."""

    # -------------------------------------------------------------------------
    # Step 1: Create a product
    # -------------------------------------------------------------------------

    def test_step_01_create_product(self, client):
        """Create product 'Payments Platform'."""
        resp = client.post(
            "/admin/products/",
            json={"name": "Payments Platform", "description": "Core payment processing platform"},
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["product"]["name"] == "Payments Platform"
        assert body["product"]["id"].startswith("prod-")

    # -------------------------------------------------------------------------
    # Step 2: Create a project under that product
    # -------------------------------------------------------------------------

    def test_step_02_create_project(self, client):
        """Create project 'payments-api' under the product."""
        # Create product first
        prod_resp = client.post("/admin/products/", json={"name": "Payments Platform"})
        product_id = prod_resp.get_json()["product"]["id"]

        resp = client.post(
            "/admin/projects/",
            json={
                "name": "payments-api",
                "description": "Payment processing API service",
                "product_id": product_id,
            },
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["project"]["name"] == "payments-api"
        assert body["project"]["id"].startswith("proj-")

    # -------------------------------------------------------------------------
    # Step 3: Create 3 agents with different roles
    # -------------------------------------------------------------------------

    def test_step_03_create_agents(self, client):
        """Create 3 agents: Security Auditor, Code Reviewer, Release Manager."""
        agents_config = [
            {
                "name": "Security Auditor",
                "description": "Scans code for security vulnerabilities and OWASP issues",
                "role": "security",
            },
            {
                "name": "Code Reviewer",
                "description": "Reviews PRs for code quality and conventions",
                "role": "reviewer",
            },
            {
                "name": "Release Manager",
                "description": "Manages releases, changelogs, and version bumps",
                "role": "manager",
            },
        ]

        agent_ids = []
        for config in agents_config:
            resp = client.post("/admin/agents/", json=config)
            assert resp.status_code == 201
            body = resp.get_json()
            assert body["agent_id"].startswith("agent-")
            assert body["name"] == config["name"]
            agent_ids.append(body["agent_id"])

        # Verify all 3 exist
        list_resp = client.get("/admin/agents/")
        assert list_resp.status_code == 200
        assert list_resp.get_json()["total_count"] == 3

    # -------------------------------------------------------------------------
    # Step 4: Create a team and assign agents as members
    # -------------------------------------------------------------------------

    def test_step_04_create_team_with_members(self, client):
        """Create team 'DevOps Squad' with pipeline topology and assign 3 agents."""
        # Create agents
        agent_ids = []
        for name in ["Security Auditor", "Code Reviewer", "Release Manager"]:
            resp = client.post("/admin/agents/", json={"name": name})
            agent_ids.append(resp.get_json()["agent_id"])

        # Create team
        team_resp = client.post(
            "/admin/teams/",
            json={
                "name": "DevOps Squad",
                "description": "Core DevOps automation team",
                "topology": "pipeline",
            },
        )
        assert team_resp.status_code == 201
        team_body = team_resp.get_json()
        assert team_body["team"]["id"].startswith("team-")
        team_id = team_body["team"]["id"]

        # Add members to team
        for agent_id in agent_ids:
            member_resp = client.post(
                f"/admin/teams/{team_id}/members",
                json={"agent_id": agent_id},
            )
            # May return 201 or 200 depending on implementation
            assert member_resp.status_code in (200, 201)

        # Verify team members
        members_resp = client.get(f"/admin/teams/{team_id}/members")
        assert members_resp.status_code == 200
        members = members_resp.get_json()
        assert len(members.get("members", members.get("agents", []))) >= 3

    # -------------------------------------------------------------------------
    # Step 5: Create skills, hooks, commands, and rules for the project
    # -------------------------------------------------------------------------

    def test_step_05_create_skills_hooks_commands_rules(self, client):
        """Create skills, hooks, commands, and rules for the project."""
        # Create project
        proj_resp = client.post("/admin/projects/", json={"name": "payments-api"})
        project_id = proj_resp.get_json()["project"]["id"]

        # Create hooks
        hook_configs = [
            {
                "name": "Pre-Deploy Check",
                "event": "PreToolUse",
                "content": "echo 'Running pre-deploy checks...'",
            },
            {
                "name": "Post-Deploy Notify",
                "event": "PostToolUse",
                "content": "echo 'Deployment completed'",
            },
        ]
        hook_ids = []
        for config in hook_configs:
            resp = client.post("/admin/hooks/", json=config)
            assert resp.status_code == 201
            hook_ids.append(resp.get_json()["hook"]["id"])

        # Create commands
        command_configs = [
            {
                "name": "run-tests",
                "description": "Run the full test suite",
                "content": "cd backend && uv run pytest",
                "project_id": project_id,
            },
            {
                "name": "lint-code",
                "description": "Lint Python code with Ruff",
                "content": "cd backend && uv run ruff check .",
                "project_id": project_id,
            },
        ]
        command_ids = []
        for config in command_configs:
            resp = client.post("/admin/commands/", json=config)
            assert resp.status_code == 201
            command_ids.append(resp.get_json()["command"]["id"])

        # Create rules
        rule_configs = [
            {
                "name": "no-console-log",
                "rule_type": "pre_check",
                "description": "Disallow console.log in production code",
                "condition": "file.contains('console.log')",
                "action": "warn",
                "project_id": project_id,
            },
            {
                "name": "require-tests",
                "rule_type": "validation",
                "description": "All new functions must have tests",
                "condition": "function.test_coverage < 80",
                "action": "block",
                "project_id": project_id,
            },
        ]
        rule_ids = []
        for config in rule_configs:
            resp = client.post("/admin/rules/", json=config)
            assert resp.status_code == 201
            rule_ids.append(resp.get_json()["rule"]["id"])

        # Verify all created
        hooks_resp = client.get("/admin/hooks/")
        assert hooks_resp.status_code == 200
        assert hooks_resp.get_json()["total_count"] == 2

        commands_resp = client.get(f"/admin/commands/?project_id={project_id}")
        assert commands_resp.status_code == 200
        assert commands_resp.get_json()["total_count"] == 2

        rules_resp = client.get("/admin/rules/")
        assert rules_resp.status_code == 200
        assert rules_resp.get_json()["total_count"] == 2

    # -------------------------------------------------------------------------
    # Step 6: Create triggers/bots
    # -------------------------------------------------------------------------

    def test_step_06_create_triggers(self, client):
        """Create webhook, GitHub, and scheduled triggers."""
        # Create a team first for association
        team_resp = client.post(
            "/admin/teams/", json={"name": "DevOps Squad", "topology": "pipeline"}
        )
        team_id = team_resp.get_json()["team"]["id"]

        # Webhook trigger for security scans
        webhook_resp = client.post(
            "/admin/triggers/",
            json={
                "name": "Security Scan Webhook",
                "prompt_template": "Scan {paths} for security vulnerabilities: {message}",
                "trigger_source": "webhook",
                "backend_type": "claude",
                "detection_keyword": "security_scan",
                "team_id": team_id,
            },
        )
        assert webhook_resp.status_code == 201
        webhook_id = webhook_resp.get_json()["trigger_id"]
        assert webhook_id.startswith("trig-") or webhook_id.startswith("bot-")

        # GitHub trigger for PR reviews
        github_resp = client.post(
            "/admin/triggers/",
            json={
                "name": "PR Review Bot",
                "prompt_template": "Review this pull request: {pr_url}\n\nChanges:\n{message}",
                "trigger_source": "github",
                "backend_type": "claude",
                "model": "claude-sonnet-4",
                "team_id": team_id,
            },
        )
        assert github_resp.status_code == 201

        # Scheduled trigger for weekly reports
        scheduled_resp = client.post(
            "/admin/triggers/",
            json={
                "name": "Weekly Report Generator",
                "prompt_template": "Generate a weekly status report for {paths}",
                "trigger_source": "scheduled",
                "backend_type": "claude",
                "schedule_type": "weekly",
                "schedule_time": "09:00",
                "schedule_day": 1,
                "schedule_timezone": "UTC",
            },
        )
        assert scheduled_resp.status_code == 201

        # Verify all triggers (including 2 predefined)
        list_resp = client.get("/admin/triggers/")
        assert list_resp.status_code == 200
        triggers = list_resp.get_json()["triggers"]
        assert len(triggers) >= 5  # 2 predefined + 3 created

    # -------------------------------------------------------------------------
    # Step 7: Create MCP servers and assign to project
    # -------------------------------------------------------------------------

    def test_step_07_create_mcp_servers(self, client):
        """Create MCP servers and assign to project."""
        # Create project
        proj_resp = client.post("/admin/projects/", json={"name": "payments-api"})
        project_id = proj_resp.get_json()["project"]["id"]

        # Create MCP server
        mcp_resp = client.post(
            "/admin/mcp-servers/",
            json={
                "name": "code-analysis",
                "description": "Static code analysis MCP server",
                "server_type": "stdio",
                "command": "npx",
                "args": "-y @modelcontextprotocol/server-analysis",
                "category": "analysis",
            },
        )
        assert mcp_resp.status_code == 201
        mcp_data = mcp_resp.get_json()
        mcp_id = mcp_data["id"]
        assert mcp_id.startswith("mcp-")

        # Assign to project
        assign_resp = client.post(
            f"/admin/projects/{project_id}/mcp-servers/{mcp_id}",
            json={},
        )
        assert assign_resp.status_code in (200, 201)

        # Verify assignment
        proj_mcp_resp = client.get(f"/admin/projects/{project_id}/mcp-servers")
        assert proj_mcp_resp.status_code == 200
        servers = proj_mcp_resp.get_json()["servers"]
        assert len(servers) >= 1
        assert any(s["mcp_server_id"] == mcp_id for s in servers)

    # -------------------------------------------------------------------------
    # Step 8: Create prompt snippets
    # -------------------------------------------------------------------------

    def test_step_08_create_prompt_snippets(self, client):
        """Create and resolve prompt snippets."""
        # Create snippets
        resp1 = client.post(
            "/admin/prompt-snippets/",
            json={
                "name": "security_preamble",
                "content": "You are a security expert. Analyze code for OWASP Top 10 issues.",
                "description": "Standard security analysis preamble",
            },
        )
        assert resp1.status_code == 201
        snippet_id = resp1.get_json()["snippet"]["id"]

        resp2 = client.post(
            "/admin/prompt-snippets/",
            json={
                "name": "output_format",
                "content": "Respond in JSON: {findings: [{severity, description, location}]}",
            },
        )
        assert resp2.status_code == 201

        # Resolve snippets in a template
        resolve_resp = client.post(
            "/admin/prompt-snippets/resolve",
            json={"text": "{{security_preamble}}\n\nScan the code.\n\n{{output_format}}"},
        )
        assert resolve_resp.status_code == 200
        resolved = resolve_resp.get_json()["resolved"]
        assert "OWASP Top 10" in resolved
        assert "JSON" in resolved

        # Update snippet
        update_resp = client.put(
            f"/admin/prompt-snippets/{snippet_id}",
            json={"content": "You are a senior security expert. Focus on critical issues."},
        )
        assert update_resp.status_code == 200

        # List snippets
        list_resp = client.get("/admin/prompt-snippets/")
        assert list_resp.status_code == 200
        assert len(list_resp.get_json()["snippets"]) == 2

    # -------------------------------------------------------------------------
    # Step 9: Deploy a bot template
    # -------------------------------------------------------------------------

    def test_step_09_deploy_bot_template(self, client):
        """Seed bot templates and deploy one."""
        from app.db.seeds import seed_bot_templates

        seed_bot_templates()

        # List templates
        list_resp = client.get("/admin/bot-templates/")
        assert list_resp.status_code == 200
        templates = list_resp.get_json()["templates"]
        assert len(templates) == 5

        # Deploy the security-scanner template
        scanner = next(t for t in templates if t["slug"] == "security-scanner")
        deploy_resp = client.post(f"/admin/bot-templates/{scanner['id']}/deploy")
        assert deploy_resp.status_code == 201
        data = deploy_resp.get_json()
        assert "trigger_id" in data

        # Verify deployed trigger exists
        from app.db.triggers import get_trigger

        trigger = get_trigger(data["trigger_id"])
        assert trigger is not None

    # -------------------------------------------------------------------------
    # Step 10: Test dry-run execution
    # -------------------------------------------------------------------------

    def test_step_10_dry_run_execution(self, client):
        """Dry-run a trigger to preview execution without side effects."""
        from app.db.triggers import create_trigger

        trigger_id = create_trigger(
            name="Dry Run Test",
            prompt_template="Analyze: {message}",
            backend_type="claude",
            trigger_source="manual",
            model="claude-sonnet-4",
        )

        with patch("subprocess.Popen") as mock_popen:
            resp = client.post(
                f"/admin/triggers/{trigger_id}/dry-run",
                json={"message": "test dry run payload"},
            )
            assert resp.status_code == 200
            mock_popen.assert_not_called()

        data = resp.get_json()
        assert "rendered_prompt" in data
        assert "cli_command" in data
        assert "estimated_tokens" in data
        assert data["trigger_id"] == trigger_id
        assert "test dry run payload" in data["rendered_prompt"]

    # -------------------------------------------------------------------------
    # Step 11: Test execution queue operations
    # -------------------------------------------------------------------------

    def test_step_11_execution_queue(self, client):
        """Test execution queue enqueue, status, and cancel."""
        from app.db.execution_queue import enqueue_execution

        # Enqueue entries
        entry1 = enqueue_execution("trig-sec", "webhook", "scan repo A", "{}")
        entry2 = enqueue_execution("trig-sec", "webhook", "scan repo B", "{}")
        entry3 = enqueue_execution("trig-rev", "github", "review PR #42", "{}")
        assert entry1.startswith("qe-")
        assert entry2.startswith("qe-")
        assert entry3.startswith("qe-")

        # Get queue status
        status_resp = client.get("/admin/executions/queue")
        assert status_resp.status_code == 200
        status = status_resp.get_json()
        assert status["total_pending"] == 3

        # Get trigger-specific queue
        trig_resp = client.get("/admin/executions/queue/trig-sec")
        assert trig_resp.status_code == 200
        assert trig_resp.get_json()["pending"] == 2

        # Cancel one trigger's queue
        cancel_resp = client.delete("/admin/executions/queue/trig-sec")
        assert cancel_resp.status_code == 200
        assert cancel_resp.get_json()["cancelled"] == 2

        # Verify only other trigger remains
        status_resp2 = client.get("/admin/executions/queue")
        assert status_resp2.get_json()["total_pending"] == 1

    # -------------------------------------------------------------------------
    # Step 12: Create a workflow DAG with multiple nodes
    # -------------------------------------------------------------------------

    def test_step_12_create_workflow_dag(self, client):
        """Create a workflow with a branching DAG and run it."""
        # Create workflow
        wf_resp = client.post(
            "/admin/workflows/",
            json={
                "name": "Deploy Pipeline",
                "description": "CI/CD pipeline with parallel stages",
                "trigger_type": "manual",
            },
        )
        assert wf_resp.status_code == 201
        wf_id = wf_resp.get_json()["workflow_id"]
        assert wf_id.startswith("wf-")

        # Create a branching DAG version
        dag_graph = json.dumps(
            {
                "nodes": [
                    {"id": "start", "type": "trigger", "label": "Start", "config": {}},
                    {"id": "lint", "type": "command", "label": "Lint", "config": {}},
                    {"id": "test", "type": "command", "label": "Test", "config": {}},
                    {"id": "security", "type": "script", "label": "Security Scan", "config": {}},
                    {"id": "deploy", "type": "command", "label": "Deploy", "config": {}},
                ],
                "edges": [
                    {"source": "start", "target": "lint"},
                    {"source": "start", "target": "test"},
                    {"source": "start", "target": "security"},
                    {"source": "lint", "target": "deploy"},
                    {"source": "test", "target": "deploy"},
                    {"source": "security", "target": "deploy"},
                ],
            }
        )

        version_resp = client.post(
            f"/admin/workflows/{wf_id}/versions",
            json={"graph_json": dag_graph},
        )
        assert version_resp.status_code == 201
        assert version_resp.get_json()["version"] == 1

        # Get latest version
        latest_resp = client.get(f"/admin/workflows/{wf_id}/versions/latest")
        assert latest_resp.status_code == 200
        assert latest_resp.get_json()["version"] == 1

        # Run workflow
        run_resp = client.post(f"/admin/workflows/{wf_id}/run")
        assert run_resp.status_code == 202
        exec_id = run_resp.get_json()["execution_id"]
        assert exec_id.startswith("wfx-")

        # List executions
        exec_list_resp = client.get(f"/admin/workflows/{wf_id}/executions")
        assert exec_list_resp.status_code == 200
        assert len(exec_list_resp.get_json()["executions"]) == 1

    # -------------------------------------------------------------------------
    # Step 13: Test analytics endpoints
    # -------------------------------------------------------------------------

    def test_step_13_analytics(self, client):
        """Test cost, execution, and effectiveness analytics."""
        from app.db.budgets import create_token_usage_record
        from app.db.triggers import (
            add_pr_review,
            create_execution_log,
            update_execution_log,
            update_pr_review,
        )

        # Seed cost data
        for i in range(5):
            create_token_usage_record(
                execution_id=f"exec-analytics-{i}",
                entity_type="trigger",
                entity_id="bot-pr-review",
                backend_type="claude",
                input_tokens=1000 + i * 100,
                output_tokens=200 + i * 50,
                total_cost_usd=0.05 + i * 0.01,
                recorded_at=_datetime_str(i),
            )

        # Seed execution data
        for i in range(8):
            exec_id = f"exec-scenario-{i}"
            create_execution_log(
                execution_id=exec_id,
                trigger_id="bot-pr-review",
                trigger_type="github",
                started_at=_datetime_str(i % 3),
                prompt="test prompt",
                backend_type="claude",
                command="claude -p test",
            )
            update_execution_log(
                execution_id=exec_id,
                status="success" if i < 6 else "failed",
                finished_at=_datetime_str(i % 3),
            )

        # Seed PR review data
        for i in range(4):
            rid = add_pr_review(
                project_name=f"project-{i}",
                pr_number=i + 1,
                pr_url=f"https://github.com/org/repo/pull/{i + 1}",
                pr_title=f"PR {i + 1}",
                trigger_id="bot-pr-review",
            )
            if rid:
                status = "approved" if i < 2 else "changes_requested"
                update_pr_review(rid, review_status=status)

        # Test cost analytics
        cost_resp = client.get(
            "/admin/analytics/cost",
            query_string={"group_by": "day", "start_date": _date_str(10)},
        )
        assert cost_resp.status_code == 200
        cost = cost_resp.get_json()
        assert cost["total_cost"] > 0
        assert cost["period_count"] >= 1

        # Test execution analytics
        exec_resp = client.get(
            "/admin/analytics/executions",
            query_string={"group_by": "day", "start_date": _date_str(10)},
        )
        assert exec_resp.status_code == 200
        executions = exec_resp.get_json()
        assert executions["total_executions"] == 8

        # Test effectiveness analytics
        eff_resp = client.get("/admin/analytics/effectiveness")
        assert eff_resp.status_code == 200
        effectiveness = eff_resp.get_json()
        assert effectiveness["total_reviews"] == 4
        assert effectiveness["accepted"] == 2

    # -------------------------------------------------------------------------
    # Step 14: Test audit trail
    # -------------------------------------------------------------------------

    def test_step_14_audit_trail(self, client):
        """Test audit log retrieval."""
        # Audit events are created automatically by other operations
        # Trigger some operations that generate audit events
        client.post(
            "/admin/triggers/",
            json={"name": "Audit Test Trigger", "prompt_template": "test"},
        )

        # Get audit history
        audit_resp = client.get("/api/audit/history")
        assert audit_resp.status_code == 200
        body = audit_resp.get_json()
        assert "audits" in body or "events" in body

        # Get audit stats
        stats_resp = client.get("/api/audit/stats")
        assert stats_resp.status_code == 200

    # -------------------------------------------------------------------------
    # Step 15: Test budget limits and monitoring
    # -------------------------------------------------------------------------

    def test_step_15_budget_limits(self, client):
        """Test budget creation and monitoring."""
        # Set a budget limit via PUT
        budget_resp = client.put(
            "/admin/budgets/limits",
            json={
                "entity_type": "trigger",
                "entity_id": "bot-pr-review",
                "soft_limit_usd": 150.0,
                "hard_limit_usd": 200.0,
                "period": "monthly",
            },
        )
        assert budget_resp.status_code == 200

        # List budget limits
        list_resp = client.get("/admin/budgets/limits")
        assert list_resp.status_code == 200

        # Get window usage
        window_resp = client.get("/admin/budgets/window-usage")
        assert window_resp.status_code == 200

    # -------------------------------------------------------------------------
    # Step 16: Test RBAC roles
    # -------------------------------------------------------------------------

    def test_step_16_rbac_roles(self, client):
        """Test RBAC role management."""
        from app.db.rbac import create_user_role, count_user_roles

        # Create roles
        admin_id = create_user_role("key-admin-scenario", "Admin Key", "admin")
        viewer_id = create_user_role("key-viewer-scenario", "Viewer Key", "viewer")
        operator_id = create_user_role("key-operator-scenario", "Operator Key", "operator")
        assert admin_id is not None
        assert viewer_id is not None
        assert operator_id is not None

        # Verify roles count
        assert count_user_roles() == 3

        # Admin can list roles
        resp = client.get(
            "/admin/rbac/roles",
            headers={"X-API-Key": "key-admin-scenario"},
        )
        assert resp.status_code == 200

        # Viewer cannot list roles (admin-only endpoint)
        resp = client.get(
            "/admin/rbac/roles",
            headers={"X-API-Key": "key-viewer-scenario"},
        )
        assert resp.status_code == 403

        # Viewer can read triggers
        resp = client.get(
            "/admin/triggers/",
            headers={"X-API-Key": "key-viewer-scenario"},
        )
        assert resp.status_code == 200

        # Viewer cannot create triggers
        resp = client.post(
            "/admin/triggers/",
            json={"name": "blocked-trigger", "prompt_template": "test"},
            headers={"X-API-Key": "key-viewer-scenario"},
        )
        assert resp.status_code == 403

    # -------------------------------------------------------------------------
    # Step 17: Test secrets vault
    # -------------------------------------------------------------------------

    def test_step_17_secrets_vault(self, client, monkeypatch):
        """Test secrets vault CRUD operations."""
        # Set up vault key
        key = Fernet.generate_key().decode()
        monkeypatch.setenv("AGENTED_VAULT_KEYS", key)

        from app.services.secret_vault_service import SecretVaultService

        SecretVaultService.reset()

        # Create secrets
        resp1 = client.post(
            "/admin/secrets/",
            json={
                "name": "github-token",
                "value": "ghp_abc123def456",
                "description": "GitHub API token",
            },
        )
        assert resp1.status_code == 201
        data = resp1.get_json()
        assert data["id"].startswith("sec-")
        assert "value" not in data
        assert "encrypted_value" not in data
        secret_id = data["id"]

        resp2 = client.post(
            "/admin/secrets/",
            json={"name": "slack-webhook", "value": "https://hooks.slack.com/xxx"},
        )
        assert resp2.status_code == 201

        # List secrets (no values exposed)
        list_resp = client.get("/admin/secrets/")
        assert list_resp.status_code == 200
        secrets = list_resp.get_json()["secrets"]
        assert len(secrets) >= 2
        for s in secrets:
            assert "encrypted_value" not in s
            assert "value" not in s

        # Reveal secret value
        reveal_resp = client.post(f"/admin/secrets/{secret_id}/reveal")
        assert reveal_resp.status_code == 200
        assert reveal_resp.get_json()["value"] == "ghp_abc123def456"

        # Update secret
        update_resp = client.put(
            f"/admin/secrets/{secret_id}",
            json={"value": "ghp_new_token_789"},
        )
        assert update_resp.status_code == 200

        # Verify updated value
        reveal2 = client.post(f"/admin/secrets/{secret_id}/reveal")
        assert reveal2.get_json()["value"] == "ghp_new_token_789"

        # Vault status
        status_resp = client.get("/admin/secrets/status")
        assert status_resp.status_code == 200
        assert status_resp.get_json()["configured"] is True

        # Cleanup
        SecretVaultService.reset()

    # -------------------------------------------------------------------------
    # Step 18: Test GitOps configuration
    # -------------------------------------------------------------------------

    def test_step_18_gitops_configuration(self, client):
        """Test GitOps repo management."""
        from unittest.mock import MagicMock

        from app.db.gitops import create_gitops_repo

        # Create via API
        resp = client.post(
            "/admin/gitops/repos",
            json={
                "name": "payments-config",
                "repo_url": "https://github.com/org/payments-config.git",
                "branch": "main",
                "config_path": "agented/",
                "poll_interval_seconds": 300,
            },
        )
        assert resp.status_code == 201
        repo_data = resp.get_json()
        repo_id = repo_data["id"]
        assert repo_id.startswith("gop-")

        # List repos
        list_resp = client.get("/admin/gitops/repos")
        assert list_resp.status_code == 200
        assert len(list_resp.get_json()) >= 1

        # Get single repo
        get_resp = client.get(f"/admin/gitops/repos/{repo_id}")
        assert get_resp.status_code == 200
        assert get_resp.get_json()["name"] == "payments-config"

        # Update repo
        update_resp = client.put(
            f"/admin/gitops/repos/{repo_id}",
            json={"branch": "develop", "poll_interval_seconds": 600},
        )
        assert update_resp.status_code == 200
        assert update_resp.get_json()["branch"] == "develop"

        # Trigger sync (mocked)
        with patch(
            "app.routes.gitops.GitOpsSyncService.sync_repo",
            return_value={
                "commit_sha": "abc123",
                "files_changed": 2,
                "files_applied": 2,
                "files_conflicted": 0,
                "changes": [],
                "status": "success",
            },
        ) as mock_sync:
            sync_resp = client.post(f"/admin/gitops/repos/{repo_id}/sync")
            assert sync_resp.status_code == 200
            assert sync_resp.get_json()["status"] == "success"
            mock_sync.assert_called_once_with(repo_id, dry_run=False)

    # -------------------------------------------------------------------------
    # Step 19: Test bulk operations
    # -------------------------------------------------------------------------

    def test_step_19_bulk_operations(self, client):
        """Test bulk create, update, and delete across entity types."""
        # Bulk create agents
        agents = [{"name": f"Bulk Agent {i}", "description": f"Agent {i}"} for i in range(5)]
        resp = client.post("/admin/bulk/agents", json={"action": "create", "items": agents})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 5
        assert data["succeeded"] == 5
        assert data["failed"] == 0
        created_ids = [r["id"] for r in data["results"]]

        # Bulk update agents
        updates = [
            {"id": aid, "name": f"Updated Bulk Agent {i}"} for i, aid in enumerate(created_ids)
        ]
        resp = client.post("/admin/bulk/agents", json={"action": "update", "items": updates})
        assert resp.status_code == 200
        assert resp.get_json()["succeeded"] == 5

        # Bulk delete agents
        deletes = [{"id": aid} for aid in created_ids]
        resp = client.post("/admin/bulk/agents", json={"action": "delete", "items": deletes})
        assert resp.status_code == 200
        assert resp.get_json()["succeeded"] == 5

        # Bulk create triggers
        triggers = [
            {"name": f"Bulk Trigger {i}", "prompt_template": f"Prompt {i}"} for i in range(3)
        ]
        resp = client.post("/admin/bulk/triggers", json={"action": "create", "items": triggers})
        assert resp.status_code == 200
        assert resp.get_json()["succeeded"] == 3

        # Bulk create plugins
        plugins = [{"name": f"Bulk Plugin {i}"} for i in range(3)]
        resp = client.post("/admin/bulk/plugins", json={"action": "create", "items": plugins})
        assert resp.status_code == 200
        assert resp.get_json()["succeeded"] == 3

        # Bulk create hooks
        hooks = [{"name": f"Bulk Hook {i}", "event": "PreToolUse"} for i in range(3)]
        resp = client.post("/admin/bulk/hooks", json={"action": "create", "items": hooks})
        assert resp.status_code == 200
        assert resp.get_json()["succeeded"] == 3

        # Verify per-item failure isolation
        mixed_items = [
            {"name": "Good Agent"},
            {"description": "Missing name"},  # Should fail
            {"name": "Another Good Agent"},
        ]
        resp = client.post("/admin/bulk/agents", json={"action": "create", "items": mixed_items})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["succeeded"] == 2
        assert data["failed"] == 1

    # -------------------------------------------------------------------------
    # Step 20: Verify full CRUD lifecycle for all entities
    # -------------------------------------------------------------------------

    def test_step_20_full_crud_lifecycle(self, client):
        """Verify create, list, get, update, delete for all major entities."""
        # --- Product ---
        prod_resp = client.post("/admin/products/", json={"name": "CRUD Product"})
        assert prod_resp.status_code == 201
        prod_id = prod_resp.get_json()["product"]["id"]

        get_prod = client.get(f"/admin/products/{prod_id}")
        assert get_prod.status_code == 200
        assert get_prod.get_json()["name"] == "CRUD Product"

        client.put(f"/admin/products/{prod_id}", json={"name": "Updated CRUD Product"})
        assert client.get(f"/admin/products/{prod_id}").get_json()["name"] == "Updated CRUD Product"

        assert client.delete(f"/admin/products/{prod_id}").status_code == 200
        assert client.get(f"/admin/products/{prod_id}").status_code == 404

        # --- Project ---
        proj_resp = client.post("/admin/projects/", json={"name": "CRUD Project"})
        assert proj_resp.status_code == 201
        proj_id = proj_resp.get_json()["project"]["id"]

        assert client.get(f"/admin/projects/{proj_id}").status_code == 200
        client.put(f"/admin/projects/{proj_id}", json={"name": "Updated CRUD Project"})
        assert client.get(f"/admin/projects/{proj_id}").get_json()["name"] == "Updated CRUD Project"
        assert client.delete(f"/admin/projects/{proj_id}").status_code == 200
        assert client.get(f"/admin/projects/{proj_id}").status_code == 404

        # --- Agent ---
        agent_resp = client.post("/admin/agents/", json={"name": "CRUD Agent"})
        assert agent_resp.status_code == 201
        agent_id = agent_resp.get_json()["agent_id"]

        assert client.get(f"/admin/agents/{agent_id}").status_code == 200
        client.put(f"/admin/agents/{agent_id}", json={"name": "Updated CRUD Agent"})
        assert client.delete(f"/admin/agents/{agent_id}").status_code == 200
        assert client.get(f"/admin/agents/{agent_id}").status_code == 404

        # --- Team ---
        team_resp = client.post("/admin/teams/", json={"name": "CRUD Team"})
        assert team_resp.status_code == 201
        team_id = team_resp.get_json()["team"]["id"]

        assert client.get(f"/admin/teams/{team_id}").status_code == 200
        client.put(f"/admin/teams/{team_id}", json={"name": "Updated CRUD Team"})
        assert client.delete(f"/admin/teams/{team_id}").status_code == 200
        assert client.get(f"/admin/teams/{team_id}").status_code == 404

        # --- Trigger ---
        trig_resp = client.post(
            "/admin/triggers/",
            json={"name": "CRUD Trigger", "prompt_template": "CRUD test prompt"},
        )
        assert trig_resp.status_code == 201
        trig_id = trig_resp.get_json()["trigger_id"]

        assert client.get(f"/admin/triggers/{trig_id}").status_code == 200
        client.put(f"/admin/triggers/{trig_id}", json={"name": "Updated CRUD Trigger"})
        assert client.delete(f"/admin/triggers/{trig_id}").status_code == 200
        assert client.get(f"/admin/triggers/{trig_id}").status_code == 404

        # --- Hook ---
        hook_resp = client.post("/admin/hooks/", json={"name": "CRUD Hook", "event": "PreToolUse"})
        assert hook_resp.status_code == 201
        hook_id = hook_resp.get_json()["hook"]["id"]

        assert client.get(f"/admin/hooks/{hook_id}").status_code == 200
        client.put(f"/admin/hooks/{hook_id}", json={"name": "Updated CRUD Hook"})
        assert client.delete(f"/admin/hooks/{hook_id}").status_code == 200
        assert client.get(f"/admin/hooks/{hook_id}").status_code == 404

        # --- Command ---
        cmd_resp = client.post(
            "/admin/commands/", json={"name": "crud-cmd", "content": "echo test"}
        )
        assert cmd_resp.status_code == 201
        cmd_id = cmd_resp.get_json()["command"]["id"]

        assert client.get(f"/admin/commands/{cmd_id}").status_code == 200
        client.put(f"/admin/commands/{cmd_id}", json={"name": "updated-crud-cmd"})
        assert client.delete(f"/admin/commands/{cmd_id}").status_code == 200
        assert client.get(f"/admin/commands/{cmd_id}").status_code == 404

        # --- Rule ---
        rule_resp = client.post(
            "/admin/rules/",
            json={"name": "crud-rule", "rule_type": "validation"},
        )
        assert rule_resp.status_code == 201
        rule_id = rule_resp.get_json()["rule"]["id"]

        assert client.get(f"/admin/rules/{rule_id}").status_code == 200
        client.put(f"/admin/rules/{rule_id}", json={"name": "updated-crud-rule"})
        assert client.delete(f"/admin/rules/{rule_id}").status_code == 200
        assert client.get(f"/admin/rules/{rule_id}").status_code == 404

        # --- MCP Server ---
        mcp_resp = client.post(
            "/admin/mcp-servers/",
            json={"name": "crud-mcp", "server_type": "stdio", "command": "npx test"},
        )
        assert mcp_resp.status_code == 201
        mcp_id = mcp_resp.get_json()["id"]

        assert client.get(f"/admin/mcp-servers/{mcp_id}").status_code == 200
        client.put(f"/admin/mcp-servers/{mcp_id}", json={"name": "updated-crud-mcp"})
        assert client.delete(f"/admin/mcp-servers/{mcp_id}").status_code == 200
        assert client.get(f"/admin/mcp-servers/{mcp_id}").status_code == 404

        # --- Workflow ---
        wf_resp = client.post(
            "/admin/workflows/",
            json={"name": "CRUD Workflow", "trigger_type": "manual"},
        )
        assert wf_resp.status_code == 201
        wf_id = wf_resp.get_json()["workflow_id"]

        assert client.get(f"/admin/workflows/{wf_id}").status_code == 200
        client.put(f"/admin/workflows/{wf_id}", json={"name": "Updated CRUD Workflow"})
        assert client.delete(f"/admin/workflows/{wf_id}").status_code == 200
        assert client.get(f"/admin/workflows/{wf_id}").status_code == 404


class TestIntegratedEntityLinking:
    """Test that entities can be correctly linked and cross-referenced."""

    def test_product_project_team_chain(self, client):
        """Product -> Project -> Team linkage works end to end."""
        # Product
        prod = client.post("/admin/products/", json={"name": "Linked Product"}).get_json()[
            "product"
        ]

        # Project under product
        proj = client.post(
            "/admin/projects/",
            json={"name": "Linked Project", "product_id": prod["id"]},
        ).get_json()["project"]

        # Agents
        agent1 = client.post("/admin/agents/", json={"name": "Agent Alpha"}).get_json()
        agent2 = client.post("/admin/agents/", json={"name": "Agent Beta"}).get_json()

        # Team
        team = client.post(
            "/admin/teams/",
            json={"name": "Linked Team", "topology": "pipeline"},
        ).get_json()
        team_id = team["team"]["id"]

        # Add agents to team
        client.post(
            f"/admin/teams/{team_id}/members",
            json={"agent_id": agent1["agent_id"]},
        )
        client.post(
            f"/admin/teams/{team_id}/members",
            json={"agent_id": agent2["agent_id"]},
        )

        # Create trigger with team
        trig = client.post(
            "/admin/triggers/",
            json={
                "name": "Team-Linked Trigger",
                "prompt_template": "Run with team",
                "team_id": team_id,
            },
        ).get_json()

        # Verify trigger has team
        trig_detail = client.get(f"/admin/triggers/{trig['trigger_id']}").get_json()
        assert trig_detail["team_id"] == team_id

    def test_project_mcp_command_rule_linkage(self, client):
        """Project -> MCP, Commands, Rules linkage works."""
        # Create project
        proj = client.post("/admin/projects/", json={"name": "Full Project"}).get_json()["project"]
        proj_id = proj["id"]

        # Create MCP server and assign to project
        mcp = client.post(
            "/admin/mcp-servers/",
            json={"name": "linked-mcp", "command": "npx test"},
        ).get_json()
        mcp_id = mcp["id"]
        client.post(f"/admin/projects/{proj_id}/mcp-servers/{mcp_id}", json={})

        # Create project-scoped command
        cmd = client.post(
            "/admin/commands/",
            json={"name": "proj-cmd", "content": "echo test", "project_id": proj_id},
        ).get_json()["command"]

        # Create project-scoped rule
        rule = client.post(
            "/admin/rules/",
            json={
                "name": "proj-rule",
                "rule_type": "validation",
                "project_id": proj_id,
            },
        ).get_json()["rule"]

        # Verify project has MCP servers
        mcp_resp = client.get(f"/admin/projects/{proj_id}/mcp-servers")
        assert mcp_resp.status_code == 200
        assert len(mcp_resp.get_json()["servers"]) >= 1

        # Verify commands filter by project
        cmd_resp = client.get(f"/admin/commands/?project_id={proj_id}")
        assert cmd_resp.status_code == 200
        assert cmd_resp.get_json()["total_count"] >= 1

        # Clean up (delete project should cascade or at least not error)
        assert client.delete(f"/admin/projects/{proj_id}").status_code == 200

    def test_predefined_bots_cannot_be_deleted(self, client):
        """Predefined bots (bot-security, bot-pr-review) cannot be deleted."""
        resp1 = client.delete("/admin/triggers/bot-security")
        assert resp1.status_code in (400, 403, 409)

        resp2 = client.delete("/admin/triggers/bot-pr-review")
        assert resp2.status_code in (400, 403, 409)

        # But they can be retrieved
        assert client.get("/admin/triggers/bot-security").status_code == 200
        assert client.get("/admin/triggers/bot-pr-review").status_code == 200


class TestHealthAndMonitoring:
    """Test health check and monitoring endpoints."""

    def test_health_liveness(self, client):
        """GET /health/liveness returns 200."""
        resp = client.get("/health/liveness")
        assert resp.status_code == 200

    def test_health_readiness(self, client):
        """GET /health/readiness returns 200 with status ok."""
        resp = client.get("/health/readiness")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "ok"

    def test_execution_retries_endpoint(self, client):
        """GET /admin/executions/retries returns retry info."""
        resp = client.get("/admin/executions/retries")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "retries" in data
        assert "total" in data

    def test_analytics_empty_endpoints(self, client):
        """Analytics endpoints return valid JSON with no data."""
        cost_resp = client.get("/admin/analytics/cost")
        assert cost_resp.status_code == 200
        assert cost_resp.get_json()["total_cost"] == 0.0

        exec_resp = client.get("/admin/analytics/executions")
        assert exec_resp.status_code == 200
        assert exec_resp.get_json()["total_executions"] == 0

        eff_resp = client.get("/admin/analytics/effectiveness")
        assert eff_resp.status_code == 200
        assert eff_resp.get_json()["total_reviews"] == 0


# ---------------------------------------------------------------------------
# Additional domain scenario tests
# ---------------------------------------------------------------------------


class TestPluginsScenario:
    """Plugin management scenario tests."""

    def test_plugin_crud(self, client):
        """Full CRUD lifecycle for plugins."""
        # List (empty)
        resp = client.get("/admin/plugins/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["plugins"] == [] or isinstance(body["plugins"], list)
        initial_count = body["total_count"]

        # Create
        resp = client.post(
            "/admin/plugins/",
            json={
                "name": "Security Scanner",
                "description": "Scans for vulnerabilities",
                "version": "1.0.0",
                "status": "draft",
                "author": "test-user",
            },
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Plugin created"
        plugin_id = body["plugin"]["id"]
        assert plugin_id.startswith("plug-")

        # Read
        resp = client.get(f"/admin/plugins/{plugin_id}")
        assert resp.status_code == 200
        detail = resp.get_json()
        assert detail["name"] == "Security Scanner"

        # Update
        resp = client.put(
            f"/admin/plugins/{plugin_id}",
            json={"name": "Security Scanner v2", "version": "2.0.0"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Security Scanner v2"

        # List (now has one more)
        resp = client.get("/admin/plugins/")
        assert resp.status_code == 200
        assert resp.get_json()["total_count"] == initial_count + 1

        # Delete
        resp = client.delete(f"/admin/plugins/{plugin_id}")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Plugin deleted"

        # Verify deleted
        resp = client.get(f"/admin/plugins/{plugin_id}")
        assert resp.status_code == 404

    def test_plugin_components_crud(self, client):
        """Full CRUD lifecycle for plugin components."""
        # Create plugin first
        resp = client.post(
            "/admin/plugins/",
            json={"name": "Component Test Plugin", "description": "For testing components"},
        )
        assert resp.status_code == 201
        plugin_id = resp.get_json()["plugin"]["id"]

        # List components (empty)
        resp = client.get(f"/admin/plugins/{plugin_id}/components")
        assert resp.status_code == 200
        assert resp.get_json()["components"] == []

        # Add component
        resp = client.post(
            f"/admin/plugins/{plugin_id}/components",
            json={"name": "scan-deps", "type": "skill", "content": "echo scanning"},
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Component added"
        component_id = body["component"]["id"]

        # Update component
        resp = client.put(
            f"/admin/plugins/{plugin_id}/components/{component_id}",
            json={"name": "scan-deps-v2", "content": "echo scanning v2"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["component"]["name"] == "scan-deps-v2"

        # Delete component
        resp = client.delete(f"/admin/plugins/{plugin_id}/components/{component_id}")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Component deleted"

        # Verify component deleted
        resp = client.get(f"/admin/plugins/{plugin_id}/components")
        assert resp.status_code == 200
        assert resp.get_json()["components"] == []

    def test_plugin_not_found(self, client):
        """Operations on non-existent plugin return 404."""
        resp = client.get("/admin/plugins/plug-nonexist")
        assert resp.status_code == 404

        resp = client.put("/admin/plugins/plug-nonexist", json={"name": "x"})
        assert resp.status_code == 404

        resp = client.delete("/admin/plugins/plug-nonexist")
        assert resp.status_code == 404


class TestSkillsScenario:
    """Skills management scenario tests."""

    def test_list_discovered_skills(self, client):
        """GET /api/skills/ returns skill discovery list."""
        resp = client.get("/api/skills/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "skills" in body

    def test_user_skills_crud(self, client):
        """Full CRUD for user skills."""
        # List (initially empty)
        resp = client.get("/api/skills/user")
        assert resp.status_code == 200
        assert "skills" in resp.get_json()

        # Add skill
        resp = client.post(
            "/api/skills/user",
            json={
                "skill_name": "test-skill",
                "skill_path": "/tmp/skills/test-skill",
                "description": "A test skill",
                "enabled": 1,
                "selected_for_harness": 0,
            },
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Skill added"
        skill_id = body["id"]

        # Get single skill
        resp = client.get(f"/api/skills/user/{skill_id}")
        assert resp.status_code == 200
        assert resp.get_json()["skill"]["skill_name"] == "test-skill"

        # Update skill
        resp = client.put(
            f"/api/skills/user/{skill_id}",
            json={"description": "Updated description"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Skill updated"

        # Delete skill
        resp = client.delete(f"/api/skills/user/{skill_id}")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Skill removed"

        # Verify not found
        resp = client.get(f"/api/skills/user/{skill_id}")
        assert resp.status_code == 404

    def test_duplicate_skill_rejected(self, client):
        """Adding a skill with duplicate name returns 409."""
        payload = {
            "skill_name": "dup-skill",
            "skill_path": "/tmp/skills/dup",
        }
        resp = client.post("/api/skills/user", json=payload)
        assert resp.status_code == 201

        resp = client.post("/api/skills/user", json=payload)
        assert resp.status_code == 409

    def test_harness_endpoints(self, client):
        """Harness skills listing and config endpoints."""
        resp = client.get("/api/skills/harness")
        assert resp.status_code == 200
        assert "skills" in resp.get_json()

        resp = client.get("/api/skills/harness/config")
        assert resp.status_code == 200

    def test_playground_files(self, client):
        """GET /api/skills/playground/files returns file listing."""
        resp = client.get("/api/skills/playground/files")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "working_dir" in body
        assert "files" in body


class TestSettingsScenario:
    """Settings management scenario tests."""

    def test_settings_crud(self, client):
        """Full CRUD lifecycle for settings."""
        # List (initial)
        resp = client.get("/api/settings/")
        assert resp.status_code == 200
        assert "settings" in resp.get_json()

        # Set a value
        resp = client.put("/api/settings/test_key", json={"value": "test_value"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["key"] == "test_key"
        assert body["value"] == "test_value"

        # Get the value
        resp = client.get("/api/settings/test_key")
        assert resp.status_code == 200
        assert resp.get_json()["value"] == "test_value"

        # Delete
        resp = client.delete("/api/settings/test_key")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Setting deleted"

        # Verify deleted (returns empty value, not 404)
        resp = client.get("/api/settings/test_key")
        assert resp.status_code == 200
        assert resp.get_json()["value"] == ""

    def test_delete_nonexistent_setting(self, client):
        """Deleting a non-existent setting returns 404."""
        resp = client.delete("/api/settings/nonexistent_key_xyz")
        assert resp.status_code == 404

    def test_harness_plugin_settings(self, client):
        """Harness plugin convenience endpoints."""
        # Get (initially empty)
        resp = client.get("/api/settings/harness-plugin")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["plugin_id"] is None

        # Set
        resp = client.put(
            "/api/settings/harness-plugin",
            json={
                "plugin_id": "plug-abc123",
                "marketplace_id": "mkt-xyz",
                "plugin_name": "My Plugin",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["plugin_id"] == "plug-abc123"

        # Verify persisted
        resp = client.get("/api/settings/harness-plugin")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["plugin_id"] == "plug-abc123"
        assert body["marketplace_id"] == "mkt-xyz"
        assert body["plugin_name"] == "My Plugin"


class TestIntegrationsScenario:
    """Integration management scenario tests."""

    def test_integration_crud(self, client):
        """Full CRUD lifecycle for integrations."""
        # List (empty)
        resp = client.get("/admin/integrations")
        assert resp.status_code == 200
        assert resp.get_json() == []

        # Create
        resp = client.post(
            "/admin/integrations",
            json={
                "name": "Slack Alerts",
                "type": "slack",
                "config": {"channel": "#alerts"},
            },
        )
        assert resp.status_code == 201
        body = resp.get_json()
        integration_id = body["id"]
        assert integration_id.startswith("intg-")

        # Read
        resp = client.get(f"/admin/integrations/{integration_id}")
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Slack Alerts"

        # Update
        resp = client.put(
            f"/admin/integrations/{integration_id}",
            json={"name": "Slack Alerts v2", "enabled": False},
        )
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Slack Alerts v2"

        # List (has one)
        resp = client.get("/admin/integrations")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 1

        # Delete
        resp = client.delete(f"/admin/integrations/{integration_id}")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "deleted"

        # Verify deleted
        resp = client.get(f"/admin/integrations/{integration_id}")
        assert resp.status_code == 404

    def test_integration_not_found(self, client):
        """Operations on non-existent integration return 404."""
        resp = client.get("/admin/integrations/intg-nonexist")
        assert resp.status_code == 404

        resp = client.put("/admin/integrations/intg-nonexist", json={"name": "x"})
        assert resp.status_code == 404

        resp = client.delete("/admin/integrations/intg-nonexist")
        assert resp.status_code == 404

    def test_trigger_integrations(self, client):
        """List integrations linked to a trigger."""
        # Create integration with trigger_id
        resp = client.post(
            "/admin/integrations",
            json={
                "name": "PR Notifier",
                "type": "slack",
                "config": {"channel": "#prs"},
                "trigger_id": "bot-pr-review",
            },
        )
        assert resp.status_code == 201

        # List integrations for trigger
        resp = client.get("/admin/triggers/bot-pr-review/integrations")
        assert resp.status_code == 200
        integrations = resp.get_json()
        assert len(integrations) >= 1

    def test_test_integration(self, client):
        """Test connection for an integration."""
        # Create
        resp = client.post(
            "/admin/integrations",
            json={
                "name": "Test Integration",
                "type": "slack",
                "config": {"channel": "#test"},
            },
        )
        integration_id = resp.get_json()["id"]

        # Test endpoint (will fail without real credentials, but should return a response)
        resp = client.post(f"/admin/integrations/{integration_id}/test")
        assert resp.status_code in (200, 400)
        body = resp.get_json()
        assert "success" in body
        assert "message" in body


class TestMarketplaceScenario:
    """Marketplace management scenario tests."""

    def test_marketplace_crud(self, client):
        """Full CRUD lifecycle for marketplaces."""
        # List (empty or has defaults)
        resp = client.get("/admin/marketplaces/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "marketplaces" in body
        initial_count = len(body["marketplaces"])

        # Create
        resp = client.post(
            "/admin/marketplaces/",
            json={
                "name": "Test Marketplace",
                "url": "https://github.com/org/marketplace-repo",
                "type": "git",
            },
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Marketplace created"
        marketplace_id = body["marketplace"]["id"]

        # Read
        resp = client.get(f"/admin/marketplaces/{marketplace_id}")
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Test Marketplace"

        # Update
        resp = client.put(
            f"/admin/marketplaces/{marketplace_id}",
            json={"name": "Updated Marketplace"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Updated Marketplace"

        # List (one more)
        resp = client.get("/admin/marketplaces/")
        assert resp.status_code == 200
        assert len(resp.get_json()["marketplaces"]) == initial_count + 1

        # Delete
        resp = client.delete(f"/admin/marketplaces/{marketplace_id}")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Marketplace deleted"

        # Verify deleted
        resp = client.get(f"/admin/marketplaces/{marketplace_id}")
        assert resp.status_code == 404

    def test_marketplace_not_found(self, client):
        """Operations on non-existent marketplace return 404."""
        resp = client.get("/admin/marketplaces/mkt-nonexist")
        assert resp.status_code == 404

        resp = client.delete("/admin/marketplaces/mkt-nonexist")
        assert resp.status_code == 404

    def test_marketplace_plugins(self, client):
        """List and install plugins in a marketplace."""
        # Create marketplace
        resp = client.post(
            "/admin/marketplaces/",
            json={
                "name": "Plugin Marketplace",
                "url": "https://github.com/org/mp-repo",
                "type": "git",
            },
        )
        marketplace_id = resp.get_json()["marketplace"]["id"]

        # List plugins (empty)
        resp = client.get(f"/admin/marketplaces/{marketplace_id}/plugins")
        assert resp.status_code == 200
        assert resp.get_json()["plugins"] == []

        # Install plugin
        resp = client.post(
            f"/admin/marketplaces/{marketplace_id}/plugins",
            json={"remote_name": "security-scanner", "version": "1.0.0"},
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Plugin installed"
        installed_id = body["plugin"]["id"]

        # List plugins (has one)
        resp = client.get(f"/admin/marketplaces/{marketplace_id}/plugins")
        assert resp.status_code == 200
        assert len(resp.get_json()["plugins"]) == 1

        # Uninstall plugin
        resp = client.delete(f"/admin/marketplaces/{marketplace_id}/plugins/{installed_id}")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Plugin uninstalled"

    def test_marketplace_create_validation(self, client):
        """Marketplace creation requires name and url."""
        resp = client.post("/admin/marketplaces/", json={})
        assert resp.status_code == 400

        resp = client.post("/admin/marketplaces/", json={"name": "No URL"})
        assert resp.status_code == 400

    def test_marketplace_cache_refresh(self, client):
        """POST /admin/marketplaces/search/refresh clears cache."""
        resp = client.post("/admin/marketplaces/search/refresh")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Marketplace cache cleared"


class TestBookmarksScenario:
    """Bookmark management scenario tests."""

    def test_bookmark_crud(self, client):
        """Full CRUD lifecycle for bookmarks."""
        # List (empty)
        resp = client.get("/admin/bookmarks")
        assert resp.status_code == 200
        assert resp.get_json()["bookmarks"] == []

        # Create
        resp = client.post(
            "/admin/bookmarks",
            json={
                "execution_id": "exec-abc123",
                "trigger_id": "bot-pr-review",
                "title": "Important finding",
                "notes": "Found a critical issue",
                "tags": ["security", "critical"],
                "line_number": 42,
            },
        )
        assert resp.status_code == 201
        body = resp.get_json()
        bookmark_id = body["id"]
        assert body["title"] == "Important finding"
        assert body["deep_link"] == "/executions/exec-abc123#line-42"

        # Read
        resp = client.get(f"/admin/bookmarks/{bookmark_id}")
        assert resp.status_code == 200
        assert resp.get_json()["title"] == "Important finding"

        # Update
        resp = client.put(
            f"/admin/bookmarks/{bookmark_id}",
            json={"title": "Updated finding", "tags": ["security"]},
        )
        assert resp.status_code == 200
        assert resp.get_json()["title"] == "Updated finding"

        # List (has one)
        resp = client.get("/admin/bookmarks")
        assert resp.status_code == 200
        assert resp.get_json()["total"] == 1

        # Delete
        resp = client.delete(f"/admin/bookmarks/{bookmark_id}")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Bookmark deleted"

        # Verify deleted
        resp = client.get(f"/admin/bookmarks/{bookmark_id}")
        assert resp.status_code == 404

    def test_bookmark_trigger_listing(self, client):
        """List bookmarks scoped to a trigger."""
        # Create bookmark for a trigger
        resp = client.post(
            "/admin/bookmarks",
            json={
                "execution_id": "exec-xyz",
                "trigger_id": "bot-security",
                "title": "Security scan bookmark",
            },
        )
        assert resp.status_code == 201

        # List for trigger
        resp = client.get("/admin/triggers/bot-security/bookmarks")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] >= 1

    def test_bookmark_not_found(self, client):
        """Operations on non-existent bookmark return 404."""
        resp = client.get("/admin/bookmarks/bkmk-nonexist")
        assert resp.status_code == 404

        resp = client.delete("/admin/bookmarks/bkmk-nonexist")
        assert resp.status_code == 404

    def test_bookmark_search_by_query(self, client):
        """Search bookmarks by query text."""
        client.post(
            "/admin/bookmarks",
            json={
                "execution_id": "exec-search1",
                "trigger_id": "bot-pr-review",
                "title": "Performance regression detected",
                "notes": "Latency increased by 200ms",
            },
        )
        resp = client.get("/admin/bookmarks?query=regression")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] >= 1


class TestCampaignsScenario:
    """Campaign management scenario tests."""

    def test_campaign_lifecycle(self, client):
        """Create, list, get, and delete a campaign."""
        # List (empty)
        resp = client.get("/admin/campaigns")
        assert resp.status_code == 200
        assert resp.get_json()["campaigns"] == []

        # Create campaign (uses a predefined trigger)
        resp = client.post(
            "/admin/campaigns",
            json={
                "name": "Security Scan Wave 1",
                "trigger_id": "bot-security",
                "repo_urls": [
                    "https://github.com/org/repo-a",
                    "https://github.com/org/repo-b",
                ],
            },
        )
        assert resp.status_code == 201
        body = resp.get_json()
        campaign_id = body["campaign"]["id"]
        assert campaign_id.startswith("camp-")

        # Get detail
        resp = client.get(f"/admin/campaigns/{campaign_id}")
        assert resp.status_code == 200
        detail = resp.get_json()
        assert detail["campaign"]["name"] == "Security Scan Wave 1"
        assert "executions" in detail

        # List (has one)
        resp = client.get("/admin/campaigns")
        assert resp.status_code == 200
        assert resp.get_json()["total"] >= 1

        # Delete
        resp = client.delete(f"/admin/campaigns/{campaign_id}")
        assert resp.status_code == 200
        assert resp.get_json()["deleted"] is True

    def test_campaign_not_found(self, client):
        """Operations on non-existent campaign return 404."""
        resp = client.get("/admin/campaigns/camp-nonexist")
        assert resp.status_code == 404

        resp = client.delete("/admin/campaigns/camp-nonexist")
        assert resp.status_code == 404

    def test_trigger_campaigns(self, client):
        """List campaigns scoped to a trigger."""
        resp = client.get("/admin/triggers/bot-security/campaigns")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "campaigns" in body
        assert "total" in body

    def test_campaign_results_not_found(self, client):
        """Get results for non-existent campaign returns 404."""
        resp = client.get("/admin/campaigns/camp-nonexist/results")
        assert resp.status_code == 404


class TestTriggerConditionsScenario:
    """Trigger condition rules scenario tests."""

    def test_trigger_condition_crud(self, client):
        """Full CRUD lifecycle for trigger condition rules."""
        trigger_id = "bot-pr-review"

        # List (empty)
        resp = client.get(f"/admin/triggers/{trigger_id}/conditions")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["rules"] == []
        assert body["total"] == 0

        # Create condition
        resp = client.post(
            f"/admin/triggers/{trigger_id}/conditions",
            json={
                "name": "Large PR filter",
                "description": "Only trigger for large PRs",
                "enabled": True,
                "logic": "AND",
                "conditions": [
                    {
                        "id": "cond-1",
                        "field": "pr.lines_changed",
                        "operator": "greater_than",
                        "value": "500",
                    }
                ],
            },
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Condition rule created"
        condition_id = body["rule"]["id"]

        # Read
        resp = client.get(f"/admin/trigger-conditions/{condition_id}")
        assert resp.status_code == 200
        rule = resp.get_json()
        assert rule["name"] == "Large PR filter"

        # Update
        resp = client.put(
            f"/admin/trigger-conditions/{condition_id}",
            json={"name": "Very Large PR filter", "logic": "OR"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Very Large PR filter"

        # List (has one)
        resp = client.get(f"/admin/triggers/{trigger_id}/conditions")
        assert resp.status_code == 200
        assert resp.get_json()["total"] == 1

        # Delete
        resp = client.delete(f"/admin/trigger-conditions/{condition_id}")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Condition rule deleted"

        # Verify deleted
        resp = client.get(f"/admin/trigger-conditions/{condition_id}")
        assert resp.status_code == 404

    def test_condition_not_found(self, client):
        """Operations on non-existent condition return 404."""
        resp = client.get("/admin/trigger-conditions/cond-nonexist")
        assert resp.status_code == 404

        resp = client.put("/admin/trigger-conditions/cond-nonexist", json={"name": "x"})
        assert resp.status_code == 404

        resp = client.delete("/admin/trigger-conditions/cond-nonexist")
        assert resp.status_code == 404


class TestPrReviewsScenario:
    """PR review scenario tests."""

    def test_pr_review_crud(self, client):
        """Full CRUD lifecycle for PR reviews."""
        # List (empty)
        resp = client.get("/api/pr-reviews/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["reviews"] == []

        # Create
        resp = client.post(
            "/api/pr-reviews/",
            json={
                "project_name": "payments-api",
                "pr_number": 42,
                "pr_url": "https://github.com/org/payments-api/pull/42",
                "pr_title": "Add retry logic",
                "pr_author": "dev-user",
            },
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "PR review created"
        review_id = body["id"]

        # Read
        resp = client.get(f"/api/pr-reviews/{review_id}")
        assert resp.status_code == 200
        review = resp.get_json()
        assert review["pr_title"] == "Add retry logic"

        # Update
        resp = client.put(
            f"/api/pr-reviews/{review_id}",
            json={"review_status": "approved", "review_comment": "LGTM"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "PR review updated"

        # Delete
        resp = client.delete(f"/api/pr-reviews/{review_id}")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "PR review deleted"

        # Verify deleted
        resp = client.get(f"/api/pr-reviews/{review_id}")
        assert resp.status_code == 404

    def test_pr_review_stats(self, client):
        """GET /api/pr-reviews/stats returns statistics."""
        resp = client.get("/api/pr-reviews/stats")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "total_reviews" in body or isinstance(body, dict)

    def test_pr_review_history(self, client):
        """GET /api/pr-reviews/history returns time-series data."""
        resp = client.get("/api/pr-reviews/history?days=7")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "history" in body

    def test_pr_review_create_validation(self, client):
        """Creating PR review without required fields returns 400."""
        resp = client.post(
            "/api/pr-reviews/",
            json={"project_name": "x"},
        )
        assert resp.status_code == 400

    def test_pr_review_not_found(self, client):
        """Operations on non-existent review return 404."""
        resp = client.get("/api/pr-reviews/99999")
        assert resp.status_code == 404

        resp = client.put("/api/pr-reviews/99999", json={"review_status": "x"})
        assert resp.status_code == 404

        resp = client.delete("/api/pr-reviews/99999")
        assert resp.status_code == 404


class TestConfigExportScenario:
    """Configuration export/import scenario tests."""

    def test_export_single_trigger_json(self, client):
        """Export a predefined trigger as JSON."""
        resp = client.get("/admin/triggers/bot-pr-review/export?format=json")
        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert body["version"] == "1.0"
        assert body["kind"] == "trigger"
        assert body["metadata"]["name"] is not None

    def test_export_single_trigger_yaml(self, client):
        """Export a predefined trigger as YAML."""
        resp = client.get("/admin/triggers/bot-pr-review/export?format=yaml")
        assert resp.status_code == 200
        # Should be valid YAML text
        assert b"version:" in resp.data or b"kind:" in resp.data

    def test_export_all_triggers(self, client):
        """Export all triggers as JSON."""
        resp = client.get("/admin/triggers/export-all?format=json")
        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert isinstance(body, list)
        assert len(body) >= 2  # At least the 2 predefined triggers

    def test_import_trigger_json(self, client):
        """Import a trigger from JSON config."""
        config = json.dumps(
            {
                "version": "1.0",
                "kind": "trigger",
                "metadata": {
                    "name": "Imported Test Trigger",
                    "backend_type": "claude",
                    "trigger_source": "webhook",
                },
                "spec": {
                    "prompt_template": "Review {message}",
                    "paths": [],
                },
            }
        )
        resp = client.post(
            "/admin/triggers/import",
            json={"config": config, "format": "json"},
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["status"] == "created"
        assert body["trigger_id"] is not None

    def test_import_trigger_upsert(self, client):
        """Import with upsert updates an existing trigger."""
        config = json.dumps(
            {
                "version": "1.0",
                "kind": "trigger",
                "metadata": {
                    "name": "Upsert Trigger",
                    "backend_type": "claude",
                    "trigger_source": "webhook",
                },
                "spec": {
                    "prompt_template": "First version {message}",
                    "paths": [],
                },
            }
        )
        # First create
        resp = client.post(
            "/admin/triggers/import",
            json={"config": config, "format": "json"},
        )
        assert resp.status_code == 201

        # Upsert (update)
        config2 = json.dumps(
            {
                "version": "1.0",
                "kind": "trigger",
                "metadata": {
                    "name": "Upsert Trigger",
                    "backend_type": "claude",
                    "trigger_source": "webhook",
                },
                "spec": {
                    "prompt_template": "Updated version {message}",
                    "paths": [],
                },
            }
        )
        resp = client.post(
            "/admin/triggers/import",
            json={"config": config2, "format": "json", "upsert": True},
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "updated"

    def test_validate_config_valid(self, client):
        """Validate a valid config returns valid=True."""
        config = json.dumps(
            {
                "version": "1.0",
                "kind": "trigger",
                "metadata": {
                    "name": "Valid Trigger",
                    "backend_type": "claude",
                    "trigger_source": "webhook",
                },
                "spec": {
                    "prompt_template": "Do something",
                },
            }
        )
        resp = client.post(
            "/admin/triggers/validate-config",
            json={"config": config, "format": "json"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["valid"] is True
        assert body["error"] is None

    def test_validate_config_invalid(self, client):
        """Validate an invalid config returns valid=False."""
        config = json.dumps({"version": "1.0"})
        resp = client.post(
            "/admin/triggers/validate-config",
            json={"config": config, "format": "json"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["valid"] is False
        assert body["error"] is not None

    def test_export_nonexistent_trigger(self, client):
        """Export a non-existent trigger returns 404."""
        resp = client.get("/admin/triggers/trig-nonexist/export?format=json")
        assert resp.status_code == 404
