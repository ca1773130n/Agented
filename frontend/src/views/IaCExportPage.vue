<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { configExportApi, ApiError } from '../services/api';

const router = useRouter();

type Format = 'terraform' | 'pulumi';
type Environment = 'dev' | 'staging' | 'prod';

const selectedFormat = ref<Format>('terraform');
const selectedEnv = ref<Environment>('prod');
const copyLabel = ref('Copy to Clipboard');

const isLoading = ref(false);
const loadError = ref<string | null>(null);
const exportData = ref<string | null>(null);
const triggerCount = ref(0);

const resources = ref({
  bots: true,
  triggers: true,
  workflows: false,
  teams: false,
  backends: false,
});

const allSelected = computed(() =>
  Object.values(resources.value).every(Boolean),
);

function toggleSelectAll() {
  const next = !allSelected.value;
  resources.value.bots = next;
  resources.value.triggers = next;
  resources.value.workflows = next;
  resources.value.teams = next;
  resources.value.backends = next;
}

async function loadExportData() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const result = await configExportApi.exportAll('json');
    exportData.value = result.data;
    triggerCount.value = result.trigger_count;
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Failed to load export data';
    loadError.value = msg;
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadExportData);

const terraformCode = computed(() => {
  const env = selectedEnv.value;
  const lines: string[] = [];

  lines.push(`terraform {`);
  lines.push(`  required_providers {`);
  lines.push(`    agented = {`);
  lines.push(`      source  = "agented-io/agented"`);
  lines.push(`      version = "~> 1.0"`);
  lines.push(`    }`);
  lines.push(`  }`);
  lines.push(`}`);
  lines.push(``);
  lines.push(`provider "agented" {`);
  lines.push(`  api_url = var.agented_api_url`);
  lines.push(`  token   = var.agented_token`);
  lines.push(`}`);
  lines.push(``);
  lines.push(`variable "agented_api_url" {`);
  lines.push(`  description = "Agented API endpoint"`);
  lines.push(`  type        = string`);
  lines.push(`  default     = "https://api.agented.io"`);
  lines.push(`}`);
  lines.push(``);
  lines.push(`variable "agented_token" {`);
  lines.push(`  description = "Agented API authentication token"`);
  lines.push(`  type        = string`);
  lines.push(`  sensitive   = true`);
  lines.push(`}`);
  lines.push(``);
  lines.push(`variable "ai_provider" {`);
  lines.push(`  description = "AI provider to use for bot executions"`);
  lines.push(`  type        = string`);
  lines.push(`  default     = "claude"`);
  lines.push(`}`);

  if (resources.value.bots) {
    lines.push(``);
    lines.push(`# ── Bots ──────────────────────────────────────────────`);
    lines.push(``);
    lines.push(`resource "agented_bot" "pr_review" {`);
    lines.push(`  name        = "bot-pr-review"`);
    lines.push(`  description = "Automated PR review bot"`);
    lines.push(`  provider    = var.ai_provider`);
    lines.push(`  environment = "${env}"`);
    lines.push(``);
    lines.push(`  prompt_template = <<-EOT`);
    lines.push(`    Review the pull request at {pr_url}.`);
    lines.push(`    Focus on correctness, security, and test coverage.`);
    lines.push(`  EOT`);
    lines.push(``);
    lines.push(`  tags = {`);
    lines.push(`    team      = "platform"`);
    lines.push(`    managed   = "terraform"`);
    lines.push(`    env       = "${env}"`);
    lines.push(`  }`);
    lines.push(`}`);
    lines.push(``);
    lines.push(`resource "agented_bot" "security_audit" {`);
    lines.push(`  name        = "bot-security"`);
    lines.push(`  description = "Weekly security audit bot"`);
    lines.push(`  provider    = var.ai_provider`);
    lines.push(`  environment = "${env}"`);
    lines.push(``);
    lines.push(`  prompt_template = <<-EOT`);
    lines.push(`    Perform a full security audit of the repository.`);
    lines.push(`    Report findings with severity levels.`);
    lines.push(`  EOT`);
    lines.push(``);
    lines.push(`  tags = {`);
    lines.push(`    team      = "security"`);
    lines.push(`    managed   = "terraform"`);
    lines.push(`    env       = "${env}"`);
    lines.push(`  }`);
    lines.push(`}`);
  }

  if (resources.value.triggers) {
    lines.push(``);
    lines.push(`# ── Triggers ──────────────────────────────────────────`);
    lines.push(``);
    lines.push(`resource "agented_trigger" "pr_opened" {`);
    lines.push(`  name    = "github-pr-opened"`);
    lines.push(`  bot_id  = agented_bot.pr_review.id`);
    lines.push(`  type    = "github"`);
    lines.push(``);
    lines.push(`  github_config {`);
    lines.push(`    event      = "pull_request"`);
    lines.push(`    action     = "opened"`);
    lines.push(`    repository = var.github_repo`);
    lines.push(`  }`);
    lines.push(`}`);
    lines.push(``);
    lines.push(`resource "agented_trigger" "weekly_security" {`);
    lines.push(`  name   = "weekly-security-schedule"`);
    lines.push(`  bot_id = agented_bot.security_audit.id`);
    lines.push(`  type   = "schedule"`);
    lines.push(``);
    lines.push(`  schedule_config {`);
    lines.push(`    cron     = "0 9 * * MON"`);
    lines.push(`    timezone = "UTC"`);
    lines.push(`  }`);
    lines.push(`}`);
  }

  if (resources.value.workflows) {
    lines.push(``);
    lines.push(`# ── Workflows ─────────────────────────────────────────`);
    lines.push(``);
    lines.push(`resource "agented_workflow" "ci_pipeline" {`);
    lines.push(`  name        = "ci-pipeline"`);
    lines.push(`  description = "CI/CD automation workflow"`);
    lines.push(`  environment = "${env}"`);
    lines.push(``);
    lines.push(`  step {`);
    lines.push(`    order  = 1`);
    lines.push(`    bot_id = agented_bot.pr_review.id`);
    lines.push(`    name   = "review"`);
    lines.push(`  }`);
    lines.push(``);
    lines.push(`  step {`);
    lines.push(`    order  = 2`);
    lines.push(`    bot_id = agented_bot.security_audit.id`);
    lines.push(`    name   = "security-check"`);
    lines.push(`    when   = "steps.review.status == 'success'"`);
    lines.push(`  }`);
    lines.push(`}`);
  }

  if (resources.value.teams) {
    lines.push(``);
    lines.push(`# ── Teams ─────────────────────────────────────────────`);
    lines.push(``);
    lines.push(`resource "agented_team" "platform" {`);
    lines.push(`  name        = "Platform Engineering"`);
    lines.push(`  description = "Core platform team"`);
    lines.push(`  environment = "${env}"`);
    lines.push(`}`);
    lines.push(``);
    lines.push(`resource "agented_team_member" "platform_bot" {`);
    lines.push(`  team_id = agented_team.platform.id`);
    lines.push(`  bot_id  = agented_bot.pr_review.id`);
    lines.push(`  role    = "executor"`);
    lines.push(`}`);
  }

  if (resources.value.backends) {
    lines.push(``);
    lines.push(`# ── Backends ──────────────────────────────────────────`);
    lines.push(``);
    lines.push(`resource "agented_backend" "primary" {`);
    lines.push(`  name     = "claude-primary"`);
    lines.push(`  provider = "anthropic"`);
    lines.push(`  model    = "claude-opus-4-6"`);
    lines.push(``);
    lines.push(`  config {`);
    lines.push(`    api_key        = var.anthropic_api_key`);
    lines.push(`    max_tokens     = 8192`);
    lines.push(`    temperature    = 0.2`);
    lines.push(`  }`);
    lines.push(`}`);
  }

  lines.push(``);
  lines.push(`# ── Outputs ───────────────────────────────────────────`);
  lines.push(``);
  lines.push(`output "pr_review_bot_id" {`);
  lines.push(`  description = "ID of the PR review bot"`);
  lines.push(`  value       = agented_bot.pr_review.id`);
  lines.push(`}`);

  return lines.join('\n');
});

const pulumiCode = computed(() => {
  const env = selectedEnv.value;
  const lines: string[] = [];

  lines.push(`import * as pulumi from "@pulumi/pulumi";`);
  lines.push(`import * as agented from "@agented/pulumi-provider";`);
  lines.push(``);
  lines.push(`const config = new pulumi.Config();`);
  lines.push(`const aiProvider = config.get("aiProvider") ?? "claude";`);
  lines.push(`const agentedToken = config.requireSecret("agentedToken");`);
  lines.push(``);
  lines.push(`const provider = new agented.Provider("agented", {`);
  lines.push(`  token: agentedToken,`);
  lines.push(`  apiUrl: "https://api.agented.io",`);
  lines.push(`});`);

  if (resources.value.bots) {
    lines.push(``);
    lines.push(`// ── Bots ──────────────────────────────────────────────`);
    lines.push(``);
    lines.push(`const prReviewBot = new agented.Bot("pr-review", {`);
    lines.push(`  name: "bot-pr-review",`);
    lines.push(`  description: "Automated PR review bot",`);
    lines.push(`  provider: aiProvider,`);
    lines.push(`  environment: "${env}",`);
    lines.push(`  promptTemplate: \``);
    lines.push(`    Review the pull request at {pr_url}.`);
    lines.push(`    Focus on correctness, security, and test coverage.`);
    lines.push(`  \`,`);
    lines.push(`  tags: { team: "platform", managed: "pulumi", env: "${env}" },`);
    lines.push(`}, { provider });`);
    lines.push(``);
    lines.push(`const securityBot = new agented.Bot("security-audit", {`);
    lines.push(`  name: "bot-security",`);
    lines.push(`  description: "Weekly security audit bot",`);
    lines.push(`  provider: aiProvider,`);
    lines.push(`  environment: "${env}",`);
    lines.push(`  promptTemplate: \``);
    lines.push(`    Perform a full security audit of the repository.`);
    lines.push(`    Report findings with severity levels.`);
    lines.push(`  \`,`);
    lines.push(`  tags: { team: "security", managed: "pulumi", env: "${env}" },`);
    lines.push(`}, { provider });`);
  }

  if (resources.value.triggers) {
    lines.push(``);
    lines.push(`// ── Triggers ──────────────────────────────────────────`);
    lines.push(``);
    lines.push(`const prTrigger = new agented.Trigger("pr-opened", {`);
    lines.push(`  name: "github-pr-opened",`);
    lines.push(`  botId: prReviewBot.id,`);
    lines.push(`  type: "github",`);
    lines.push(`  githubConfig: {`);
    lines.push(`    event: "pull_request",`);
    lines.push(`    action: "opened",`);
    lines.push(`  },`);
    lines.push(`}, { provider });`);
    lines.push(``);
    lines.push(`const scheduleTrigger = new agented.Trigger("weekly-security", {`);
    lines.push(`  name: "weekly-security-schedule",`);
    lines.push(`  botId: securityBot.id,`);
    lines.push(`  type: "schedule",`);
    lines.push(`  scheduleConfig: {`);
    lines.push(`    cron: "0 9 * * MON",`);
    lines.push(`    timezone: "UTC",`);
    lines.push(`  },`);
    lines.push(`}, { provider });`);
  }

  if (resources.value.workflows) {
    lines.push(``);
    lines.push(`// ── Workflows ─────────────────────────────────────────`);
    lines.push(``);
    lines.push(`const ciWorkflow = new agented.Workflow("ci-pipeline", {`);
    lines.push(`  name: "ci-pipeline",`);
    lines.push(`  description: "CI/CD automation workflow",`);
    lines.push(`  environment: "${env}",`);
    lines.push(`  steps: [`);
    lines.push(`    { order: 1, botId: prReviewBot.id, name: "review" },`);
    lines.push(`    { order: 2, botId: securityBot.id, name: "security-check",`);
    lines.push(`      when: "steps.review.status == 'success'" },`);
    lines.push(`  ],`);
    lines.push(`}, { provider });`);
  }

  lines.push(``);
  lines.push(`// ── Exports ───────────────────────────────────────────`);
  lines.push(``);
  if (resources.value.bots) {
    lines.push(`export const prReviewBotId = prReviewBot.id;`);
    lines.push(`export const securityBotId = securityBot.id;`);
  }
  if (resources.value.triggers) {
    lines.push(`export const prTriggerId = prTrigger.id;`);
  }

  return lines.join('\n');
});

const previewCode = computed(() =>
  selectedFormat.value === 'terraform' ? terraformCode.value : pulumiCode.value,
);

const fileName = computed(() => {
  const ext = selectedFormat.value === 'terraform' ? 'tf' : 'ts';
  const base = selectedFormat.value === 'terraform' ? 'main' : 'index';
  return `agented-${selectedEnv.value}.${base}.${ext}`;
});

async function copyToClipboard() {
  try {
    await navigator.clipboard.writeText(previewCode.value);
    copyLabel.value = 'Copied!';
    setTimeout(() => (copyLabel.value = 'Copy to Clipboard'), 2000);
  } catch {
    copyLabel.value = 'Copy failed';
    setTimeout(() => (copyLabel.value = 'Copy to Clipboard'), 2000);
  }
}

function downloadFile() {
  const blob = new Blob([previewCode.value], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName.value;
  a.click();
  URL.revokeObjectURL(url);
}

const lineCount = computed(() => previewCode.value.split('\n').length);
const charCount = computed(() => previewCode.value.length);
</script>

<template>
  <div class="iac-export">
    <AppBreadcrumb
      :items="[
        { label: 'Settings', action: () => router.push({ name: 'settings' }) },
        { label: 'IaC Export' },
      ]"
    />

    <PageHeader
      title="Infrastructure-as-Code Export"
      subtitle="Export platform configurations as Terraform or Pulumi definitions for version-controlled, reproducible deployments."
    />

    <!-- Format + Environment selectors -->
    <div class="controls-row">
      <!-- Format selector -->
      <div class="card selector-card">
        <div class="selector-label">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
            <polyline points="16 18 22 12 16 6"/>
            <polyline points="8 6 2 12 8 18"/>
          </svg>
          Output Format
        </div>
        <div class="btn-group">
          <button
            class="btn btn-format"
            :class="{ active: selectedFormat === 'terraform' }"
            @click="selectedFormat = 'terraform'"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
            Terraform HCL
          </button>
          <button
            class="btn btn-format"
            :class="{ active: selectedFormat === 'pulumi' }"
            @click="selectedFormat = 'pulumi'"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
            Pulumi TypeScript
          </button>
        </div>
      </div>

      <!-- Environment selector -->
      <div class="card selector-card">
        <div class="selector-label">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>
          </svg>
          Environment
        </div>
        <div class="btn-group">
          <button
            class="btn btn-env"
            :class="{ active: selectedEnv === 'dev' }"
            @click="selectedEnv = 'dev'"
          >dev</button>
          <button
            class="btn btn-env"
            :class="{ active: selectedEnv === 'staging' }"
            @click="selectedEnv = 'staging'"
          >staging</button>
          <button
            class="btn btn-env"
            :class="{ active: selectedEnv === 'prod' }"
            @click="selectedEnv = 'prod'"
          >prod</button>
        </div>
      </div>
    </div>

    <!-- Loading / Error -->
    <div v-if="isLoading" class="card" style="padding: 32px; text-align: center; color: var(--text-tertiary);">
      Loading export configuration...
    </div>
    <div v-else-if="loadError" class="card" style="padding: 32px; text-align: center; color: #ef4444;">
      {{ loadError }}
      <button class="btn btn-ghost" style="margin-top: 12px;" @click="loadExportData">Retry</button>
    </div>

    <!-- Export data summary -->
    <div v-if="exportData && !isLoading" class="card" style="padding: 16px 24px;">
      <div style="font-size: 0.82rem; color: var(--text-secondary);">
        Backend export contains <strong>{{ triggerCount }}</strong> trigger configuration(s).
      </div>
    </div>

    <div class="main-grid">
      <!-- Resource checkboxes -->
      <div class="card resources-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
              <line x1="8" y1="21" x2="16" y2="21"/>
              <line x1="12" y1="17" x2="12" y2="21"/>
            </svg>
            Resources
          </h3>
        </div>
        <div class="resource-list">
          <label class="resource-row select-all-row">
            <input
              type="checkbox"
              :checked="allSelected"
              :indeterminate="!allSelected && Object.values(resources).some(Boolean)"
              @change="toggleSelectAll"
            />
            <span class="resource-name">Select All</span>
          </label>
          <div class="resource-divider" />
          <label class="resource-row">
            <input v-model="resources.bots" type="checkbox" />
            <span class="resource-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="13" height="13">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
              </svg>
            </span>
            <span class="resource-name">Bots</span>
            <span class="resource-count">2</span>
          </label>
          <label class="resource-row">
            <input v-model="resources.triggers" type="checkbox" />
            <span class="resource-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="13" height="13">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
              </svg>
            </span>
            <span class="resource-name">Triggers</span>
            <span class="resource-count">{{ triggerCount }}</span>
          </label>
          <label class="resource-row">
            <input v-model="resources.workflows" type="checkbox" />
            <span class="resource-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="13" height="13">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
            </span>
            <span class="resource-name">Workflows</span>
            <span class="resource-count">1</span>
          </label>
          <label class="resource-row">
            <input v-model="resources.teams" type="checkbox" />
            <span class="resource-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="13" height="13">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                <circle cx="9" cy="7" r="4"/>
                <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
              </svg>
            </span>
            <span class="resource-name">Teams</span>
            <span class="resource-count">3</span>
          </label>
          <label class="resource-row">
            <input v-model="resources.backends" type="checkbox" />
            <span class="resource-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="13" height="13">
                <ellipse cx="12" cy="5" rx="9" ry="3"/>
                <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
                <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
              </svg>
            </span>
            <span class="resource-name">Backends</span>
            <span class="resource-count">2</span>
          </label>
        </div>
      </div>

      <!-- Code preview -->
      <div class="card preview-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <polyline points="16 18 22 12 16 6"/>
              <polyline points="8 6 2 12 8 18"/>
            </svg>
            Preview
            <span class="file-badge">{{ fileName }}</span>
          </h3>
          <div class="preview-meta">
            <span class="meta-stat">{{ lineCount }} lines</span>
            <span class="meta-sep">·</span>
            <span class="meta-stat">{{ charCount }} chars</span>
          </div>
        </div>
        <div class="code-wrapper">
          <div class="line-numbers" aria-hidden="true">
            <span v-for="n in lineCount" :key="n">{{ n }}</span>
          </div>
          <pre class="code-content"><code>{{ previewCode }}</code></pre>
        </div>
        <div class="preview-actions">
          <button class="btn btn-ghost" @click="copyToClipboard">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
            </svg>
            {{ copyLabel }}
          </button>
          <button class="btn btn-primary" @click="downloadFile">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            Download as File
          </button>
        </div>
      </div>
    </div>

    <!-- Usage instructions -->
    <div class="card usage-card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          Usage Instructions
        </h3>
      </div>
      <div class="usage-body">
        <div class="usage-section" v-if="selectedFormat === 'terraform'">
          <h4>Getting started with Terraform</h4>
          <ol class="usage-steps">
            <li>Download the generated <code>{{ fileName }}</code> file into your Terraform project directory.</li>
            <li>Install the Agented provider: run <code>terraform init</code> to fetch the <code>agented-io/agented</code> provider.</li>
            <li>Set required variables via a <code>terraform.tfvars</code> file or environment variables:<br/>
              <code>TF_VAR_agented_token=&lt;your-token&gt;</code>
            </li>
            <li>Preview changes: <code>terraform plan</code></li>
            <li>Apply: <code>terraform apply</code></li>
          </ol>
        </div>
        <div class="usage-section" v-else>
          <h4>Getting started with Pulumi</h4>
          <ol class="usage-steps">
            <li>Download the generated <code>{{ fileName }}</code> file into your Pulumi project.</li>
            <li>Install the Agented SDK: <code>npm install @agented/pulumi-provider</code></li>
            <li>Configure the stack secret: <code>pulumi config set --secret agentedToken &lt;your-token&gt;</code></li>
            <li>Preview changes: <code>pulumi preview</code></li>
            <li>Deploy: <code>pulumi up</code></li>
          </ol>
        </div>
        <div class="usage-tips">
          <div class="tip">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            Never commit API tokens to version control. Use secret management tools like HashiCorp Vault or AWS Secrets Manager.
          </div>
          <div class="tip">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
            Generated configurations reflect your current platform state. Re-export after significant changes to keep IaC definitions in sync.
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.iac-export {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ── Cards ──────────────────────────────────────────────── */
.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

/* ── Controls row ───────────────────────────────────────── */
.controls-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.selector-card {
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.selector-label {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.selector-label svg { color: var(--accent-cyan); }

.btn-group {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* ── Buttons ────────────────────────────────────────────── */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s;
  white-space: nowrap;
}

.btn-primary {
  background: var(--accent-cyan);
  color: #000;
  border-color: var(--accent-cyan);
}
.btn-primary:hover { opacity: 0.85; }

.btn-ghost {
  background: transparent;
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}
.btn-ghost:hover {
  border-color: var(--accent-cyan);
  color: var(--text-primary);
}

.btn-format {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}
.btn-format:hover {
  border-color: var(--accent-cyan);
  color: var(--text-primary);
}
.btn-format.active {
  background: rgba(34, 211, 238, 0.12);
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

.btn-env {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
  padding: 6px 14px;
}
.btn-env:hover {
  border-color: var(--accent-cyan);
  color: var(--text-primary);
}
.btn-env.active {
  background: rgba(34, 211, 238, 0.12);
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

/* ── Main grid ──────────────────────────────────────────── */
.main-grid {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 16px;
  align-items: start;
}

/* ── Resources card ─────────────────────────────────────── */
.resources-card { overflow: visible; }

.resource-list {
  display: flex;
  flex-direction: column;
  padding: 8px 0;
}

.resource-row {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 20px;
  cursor: pointer;
  transition: background 0.1s;
  user-select: none;
}
.resource-row:hover { background: var(--bg-tertiary); }

.select-all-row {
  font-weight: 600;
  font-size: 0.82rem;
  color: var(--text-secondary);
}

.resource-divider {
  height: 1px;
  background: var(--border-subtle);
  margin: 4px 0;
}

.resource-icon { color: var(--text-tertiary); display: flex; }

.resource-name {
  flex: 1;
  font-size: 0.875rem;
  color: var(--text-primary);
}

.resource-count {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 2px 7px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  color: var(--text-muted);
}

input[type="checkbox"] {
  accent-color: var(--accent-cyan);
  width: 14px;
  height: 14px;
  cursor: pointer;
  flex-shrink: 0;
}

/* ── Preview card ───────────────────────────────────────── */
.preview-card {
  display: flex;
  flex-direction: column;
}

.file-badge {
  font-size: 0.7rem;
  font-weight: 500;
  font-family: 'Geist Mono', monospace;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  color: var(--text-tertiary);
  margin-left: 4px;
}

.preview-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.meta-stat { color: var(--text-muted); }
.meta-sep { opacity: 0.4; }

.code-wrapper {
  display: flex;
  overflow: auto;
  max-height: 520px;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
}

.line-numbers {
  display: flex;
  flex-direction: column;
  padding: 20px 12px 20px 16px;
  text-align: right;
  font-family: 'Geist Mono', monospace;
  font-size: 0.75rem;
  line-height: 1.6;
  color: var(--text-muted);
  opacity: 0.4;
  user-select: none;
  flex-shrink: 0;
  border-right: 1px solid var(--border-subtle);
  min-width: 40px;
}

.line-numbers span { display: block; }

.code-content {
  flex: 1;
  margin: 0;
  padding: 20px 24px;
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre;
  overflow: visible;
}

.code-content code {
  font-family: inherit;
  color: inherit;
}

.preview-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 20px;
  justify-content: flex-end;
}

/* ── Usage card ─────────────────────────────────────────── */
.usage-body {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.usage-section h4 {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px;
}

.usage-steps {
  margin: 0;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 0.875rem;
  line-height: 1.6;
}

.usage-steps code {
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  padding: 1px 6px;
  border-radius: 4px;
  color: var(--accent-cyan);
}

.usage-tips {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 4px;
  border-top: 1px solid var(--border-subtle);
}

.tip {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  font-size: 0.82rem;
  color: var(--text-tertiary);
  line-height: 1.5;
}

.tip svg {
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--accent-cyan);
  opacity: 0.7;
}

/* ── Responsive ─────────────────────────────────────────── */
@media (max-width: 768px) {
  .controls-row {
    grid-template-columns: 1fr;
  }
  .main-grid {
    grid-template-columns: 1fr;
  }
}
</style>
