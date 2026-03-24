# Agented Platform — User Scenario Test Plan

## Core Workflows (Must Work End-to-End)

### 1. Project Management
- [ ] Create a new project with name, description, github_repo
- [ ] View project dashboard with all sections populated
- [ ] Edit project settings (name, description, status)
- [ ] Assign a team to a project
- [ ] Remove a team from a project
- [ ] Set project local_path for worktree creation
- [ ] View project instances after team assignment

### 2. SuperAgent Chat (Primary Use Case)
- [ ] Open SA playground from SuperAgents list
- [ ] Create a new session
- [ ] Send a message and receive streaming response
- [ ] Switch between Management and Work mode
- [ ] Select a previous session from Sessions tab
- [ ] URL updates with ?session= when selecting session
- [ ] Refresh page preserves selected session
- [ ] View conversation history with proper timestamps
- [ ] End a session
- [ ] Resume a completed/paused session by sending a message

### 3. Project-Scoped SA Instances
- [ ] View instances on project dashboard (Active Agents section)
- [ ] Click Chat on an instance → opens instance playground
- [ ] Instance playground shows SA name and project context
- [ ] Send message in instance playground
- [ ] Click Chat on a session → navigates to correct playground with session
- [ ] Sessions grouped by SA on project dashboard

### 4. Team Management
- [ ] View teams list
- [ ] Create a new team
- [ ] View team dashboard with members
- [ ] Add/remove team members
- [ ] View team topology canvas on project dashboard

### 5. Agent Management
- [ ] View agents list
- [ ] Create a new agent
- [ ] Edit agent details
- [ ] Delete an agent

### 6. Token Usage Dashboard
- [ ] View cost chart with continuous data (no gaps)
- [ ] Switch between 7d/30d/month/custom periods
- [ ] View entity breakdown by bot/team/agent
- [ ] Budget limits display and creation
- [ ] Collect sessions button works

### 7. Sidebar Navigation
- [ ] Every sidebar item navigates to a working page (no 404)
- [ ] Projects section shows project list with expand
- [ ] Instance sub-items under projects
- [ ] Active route highlights correctly
- [ ] Breadcrumbs show correct path for every page

### 8. Triggers & Executions
- [ ] View triggers list
- [ ] View trigger dashboard
- [ ] Run a trigger manually
- [ ] View execution history
- [ ] View execution search

### 9. Skills, Commands, Hooks, Rules, Plugins
- [ ] View list page for each entity type
- [ ] Create new entity
- [ ] Edit entity
- [ ] Delete entity
- [ ] Design/playground pages work

### 10. Settings & System
- [ ] Settings page loads
- [ ] AI Backends page shows registered backends
- [ ] API Keys management
- [ ] Audit log page shows entries
