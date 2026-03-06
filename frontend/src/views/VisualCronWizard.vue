<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

// Natural language input
const nlInput = ref('');
const nlParsed = ref<string | null>(null);
const nlHuman = ref<string | null>(null);

function parseNaturalLanguage(text: string): { cron: string; human: string } | null {
  const t = text.toLowerCase().trim();
  // "every hour" / "hourly"
  if (/\bhourly\b|every hour\b/.test(t)) {
    const minMatch = t.match(/(?:at\s+)?:(\d+)/);
    const m = minMatch ? minMatch[1].padStart(2, '0') : '00';
    return { cron: `${m} * * * *`, human: `Every hour at :${m}` };
  }
  // "every N hours"
  const everyNHours = t.match(/every\s+(\d+)\s+hours?/);
  if (everyNHours) {
    const n = everyNHours[1];
    return { cron: `0 */${n} * * *`, human: `Every ${n} hours` };
  }
  // "every N minutes"
  const everyNMin = t.match(/every\s+(\d+)\s+min(?:utes?)?/);
  if (everyNMin) {
    const n = everyNMin[1];
    return { cron: `*/${n} * * * *`, human: `Every ${n} minutes` };
  }
  // Parse time like "9am", "9:30am", "14:00"
  function parseTime(s: string): { h: number; m: number } | null {
    const t12 = s.match(/(\d{1,2})(?::(\d{2}))?\s*(am|pm)/i);
    if (t12) {
      let h = parseInt(t12[1]);
      const m = parseInt(t12[2] || '0');
      const ampm = t12[3].toLowerCase();
      if (ampm === 'pm' && h !== 12) h += 12;
      if (ampm === 'am' && h === 12) h = 0;
      return { h, m };
    }
    const t24 = s.match(/(\d{1,2}):(\d{2})/);
    if (t24) return { h: parseInt(t24[1]), m: parseInt(t24[2]) };
    return null;
  }
  const timeMatch = parseTime(t);
  const h = timeMatch?.h ?? 9;
  const m = timeMatch?.m ?? 0;
  const ms = m.toString().padStart(2, '0');
  // "every weekday" / "monday through friday"
  if (/weekday|mon.*fri|business day/.test(t)) {
    const tz = parseTimezone(t);
    return { cron: `${ms} ${h} * * 1-5`, human: `Every weekday at ${fmt(h, m)}${tz}` };
  }
  // "every weekend"
  if (/weekend/.test(t)) {
    return { cron: `${ms} ${h} * * 0,6`, human: `Every weekend day at ${fmt(h, m)}` };
  }
  // "every monday", "every tuesday", etc.
  const dayNames = ['sunday','monday','tuesday','wednesday','thursday','friday','saturday'];
  for (let i = 0; i < dayNames.length; i++) {
    if (t.includes(dayNames[i])) {
      return { cron: `${ms} ${h} * * ${i}`, human: `Every ${capitalize(dayNames[i])} at ${fmt(h, m)}` };
    }
  }
  // "every day" / "daily"
  if (/\bdaily\b|every day\b/.test(t)) {
    const tz = parseTimezone(t);
    return { cron: `${ms} ${h} * * *`, human: `Every day at ${fmt(h, m)}${tz}` };
  }
  // "every week" / "weekly"
  if (/\bweekly\b|every week\b/.test(t)) {
    return { cron: `${ms} ${h} * * 1`, human: `Every Monday at ${fmt(h, m)}` };
  }
  // "every month" / "monthly" / "on the 1st"
  const monthDay = t.match(/(?:on the\s+)?(\d+)(?:st|nd|rd|th)?\s+(?:of each|of every|each)?\s*month/);
  if (monthDay || /\bmonthly\b/.test(t)) {
    const d = monthDay ? monthDay[1] : '1';
    return { cron: `${ms} ${h} ${d} * *`, human: `On day ${d} of every month at ${fmt(h, m)}` };
  }
  return null;
}

function parseTimezone(text: string): string {
  if (/\bpt\b|pacific/.test(text)) return ' PT';
  if (/\bet\b|eastern/.test(text)) return ' ET';
  if (/\bct\b|central/.test(text)) return ' CT';
  if (/\bmt\b|mountain/.test(text)) return ' MT';
  if (/\butc\b/.test(text)) return ' UTC';
  return '';
}

function fmt(h: number, m: number): string {
  const period = h >= 12 ? 'PM' : 'AM';
  const dh = h === 0 ? 12 : h > 12 ? h - 12 : h;
  return `${dh}:${m.toString().padStart(2, '0')} ${period}`;
}

function capitalize(s: string): string { return s.charAt(0).toUpperCase() + s.slice(1); }

function applyNLSchedule() {
  const result = parseNaturalLanguage(nlInput.value);
  if (!result) {
    nlParsed.value = null;
    nlHuman.value = null;
    showToast('Could not parse schedule. Try "every weekday at 9am" or "daily at 6pm".', 'error');
    return;
  }
  nlParsed.value = result.cron;
  nlHuman.value = result.human;
  // Apply to visual wizard
  customCron.value = result.cron;
  frequency.value = 'custom';
  showToast('Schedule applied from natural language!', 'success');
}

type Frequency = 'hourly' | 'daily' | 'weekly' | 'monthly' | 'custom';

const frequency = ref<Frequency>('daily');
const hour = ref(9);
const minute = ref(0);
const selectedDays = ref<number[]>([1, 2, 3, 4, 5]); // Mon-Fri
const selectedMonthDay = ref(1);
const timezone = ref('UTC');
const customCron = ref('');

const days = [
  { val: 0, label: 'Sun' }, { val: 1, label: 'Mon' }, { val: 2, label: 'Tue' },
  { val: 3, label: 'Wed' }, { val: 4, label: 'Thu' }, { val: 5, label: 'Fri' }, { val: 6, label: 'Sat' },
];

const timezones = ['UTC', 'US/Eastern', 'US/Pacific', 'Europe/London', 'Europe/Berlin', 'Asia/Tokyo'];

const cronExpression = computed(() => {
  const m = minute.value.toString().padStart(2, '0');
  const h = hour.value.toString();
  switch (frequency.value) {
    case 'hourly': return `${m} * * * *`;
    case 'daily': return `${m} ${h} * * *`;
    case 'weekly': return `${m} ${h} * * ${selectedDays.value.join(',')}`;
    case 'monthly': return `${m} ${h} ${selectedMonthDay.value} * *`;
    case 'custom': return customCron.value || '* * * * *';
    default: return '* * * * *';
  }
});

const humanReadable = computed(() => {
  switch (frequency.value) {
    case 'hourly': return `Every hour at :${minute.value.toString().padStart(2, '0')}`;
    case 'daily': return `Every day at ${formatTime(hour.value, minute.value)} ${timezone.value}`;
    case 'weekly': {
      const dayNames = selectedDays.value.map(d => days.find(x => x.val === d)?.label).join(', ');
      return `Every ${dayNames} at ${formatTime(hour.value, minute.value)} ${timezone.value}`;
    }
    case 'monthly': return `On day ${selectedMonthDay.value} of every month at ${formatTime(hour.value, minute.value)} ${timezone.value}`;
    case 'custom': return `Custom: ${customCron.value || 'Enter expression above'}`;
    default: return '';
  }
});

const nextRuns = computed(() => {
  const runs: string[] = [];
  const now = new Date();
  for (let i = 0; i < 5; i++) {
    const d = new Date(now);
    if (frequency.value === 'hourly') d.setHours(d.getHours() + i + 1, minute.value, 0, 0);
    else if (frequency.value === 'daily') { d.setDate(d.getDate() + i); d.setHours(hour.value, minute.value, 0, 0); }
    else if (frequency.value === 'weekly') { d.setDate(d.getDate() + (i + 1) * 7); d.setHours(hour.value, minute.value, 0, 0); }
    else { d.setMonth(d.getMonth() + i); d.setDate(selectedMonthDay.value); d.setHours(hour.value, minute.value, 0, 0); }
    runs.push(d.toLocaleString('en-US', { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' }));
  }
  return runs;
});

function toggleDay(d: number) {
  const i = selectedDays.value.indexOf(d);
  if (i === -1) selectedDays.value.push(d);
  else selectedDays.value.splice(i, 1);
}

function formatTime(h: number, m: number) {
  const period = h >= 12 ? 'PM' : 'AM';
  const displayH = h === 0 ? 12 : h > 12 ? h - 12 : h;
  return `${displayH}:${m.toString().padStart(2, '0')} ${period}`;
}

const isSaving = ref(false);
async function handleSave() {
  isSaving.value = true;
  try {
    await new Promise(r => setTimeout(r, 700));
    showToast(`Schedule saved: ${cronExpression.value}`, 'success');
  } finally {
    isSaving.value = false;
  }
}
</script>

<template>
  <div class="cron-wizard">
    <AppBreadcrumb :items="[
      { label: 'Scheduling', action: () => router.push({ name: 'scheduling-dashboard' }) },
      { label: 'Schedule Wizard' },
    ]" />

    <PageHeader
      title="Natural Language Schedule Builder"
      subtitle="Type a schedule in plain English or use the visual builder — generates a valid cron expression with a human-readable preview."
    />

    <!-- Natural language input -->
    <div class="card nl-card">
      <div class="nl-header">
        <span class="nl-icon">✦</span>
        <span class="nl-title">Natural Language Input</span>
        <span class="nl-hint">e.g. "every weekday at 9am PT", "daily at 6pm", "every Monday at 10:30am"</span>
      </div>
      <div class="nl-body">
        <div class="nl-input-row">
          <input
            v-model="nlInput"
            class="nl-input"
            placeholder="every weekday at 9am PT"
            @keyup.enter="applyNLSchedule"
          />
          <button class="btn btn-primary" @click="applyNLSchedule">Parse Schedule</button>
        </div>
        <div v-if="nlParsed" class="nl-result">
          <div class="nl-result-human">{{ nlHuman }}</div>
          <code class="nl-result-cron">{{ nlParsed }}</code>
          <span class="nl-applied-badge">Applied to visual builder</span>
        </div>
      </div>
    </div>

    <div class="section-divider">— or configure visually —</div>

    <div class="layout">
      <div class="wizard-col">
        <!-- Frequency selector -->
        <div class="card freq-card">
          <div class="card-header">Frequency</div>
          <div class="freq-pills">
            <button
              v-for="f in (['hourly', 'daily', 'weekly', 'monthly', 'custom'] as Frequency[])"
              :key="f"
              :class="['freq-pill', { active: frequency === f }]"
              @click="frequency = f"
            >{{ f }}</button>
          </div>
        </div>

        <!-- Time picker -->
        <div v-if="frequency !== 'hourly' && frequency !== 'custom'" class="card time-card">
          <div class="card-header">Time</div>
          <div class="time-body">
            <div class="time-inputs">
              <div class="time-field">
                <label class="field-label">Hour</label>
                <input type="number" v-model.number="hour" min="0" max="23" class="num-input" />
              </div>
              <span class="time-sep">:</span>
              <div class="time-field">
                <label class="field-label">Minute</label>
                <input type="number" v-model.number="minute" min="0" max="59" class="num-input" />
              </div>
            </div>
            <div class="time-field tz-field">
              <label class="field-label">Timezone</label>
              <select v-model="timezone" class="select-input">
                <option v-for="tz in timezones" :key="tz" :value="tz">{{ tz }}</option>
              </select>
            </div>
          </div>
        </div>

        <!-- Weekly day picker -->
        <div v-if="frequency === 'weekly'" class="card days-card">
          <div class="card-header">Days of Week</div>
          <div class="days-body">
            <button
              v-for="d in days"
              :key="d.val"
              :class="['day-btn', { active: selectedDays.includes(d.val) }]"
              @click="toggleDay(d.val)"
            >{{ d.label }}</button>
          </div>
        </div>

        <!-- Monthly day picker -->
        <div v-if="frequency === 'monthly'" class="card">
          <div class="card-header">Day of Month</div>
          <div class="month-body">
            <input type="number" v-model.number="selectedMonthDay" min="1" max="31" class="num-input" />
          </div>
        </div>

        <!-- Custom cron -->
        <div v-if="frequency === 'custom'" class="card">
          <div class="card-header">Custom Cron Expression</div>
          <div class="custom-body">
            <input v-model="customCron" class="cron-input" placeholder="0 9 * * 1-5" />
            <div class="cron-help">Format: minute hour day-of-month month day-of-week</div>
          </div>
        </div>

        <div class="actions">
          <button class="btn btn-primary" :disabled="isSaving" @click="handleSave">
            {{ isSaving ? 'Saving...' : 'Save Schedule' }}
          </button>
        </div>
      </div>

      <!-- Preview panel -->
      <div class="preview-col">
        <div class="card preview-card">
          <div class="card-header">Schedule Preview</div>
          <div class="preview-body">
            <div class="human-readable">{{ humanReadable }}</div>
            <div class="cron-expr">
              <span class="cron-label">Cron:</span>
              <code class="cron-code">{{ cronExpression }}</code>
            </div>
          </div>
        </div>

        <div class="card next-runs-card">
          <div class="card-header">Next 5 Runs</div>
          <div class="next-runs-list">
            <div v-for="(run, i) in nextRuns" :key="i" class="next-run-item">
              <span class="run-num">{{ i + 1 }}</span>
              <span class="run-time">{{ run }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cron-wizard { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.layout { display: grid; grid-template-columns: 1fr 320px; gap: 20px; align-items: start; }
.wizard-col { display: flex; flex-direction: column; gap: 14px; }
.preview-col { display: flex; flex-direction: column; gap: 14px; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }
.card-header { padding: 12px 18px; border-bottom: 1px solid var(--border-default); font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); }

.freq-pills { display: flex; gap: 8px; padding: 14px 18px; flex-wrap: wrap; }
.freq-pill { padding: 7px 16px; border-radius: 20px; font-size: 0.82rem; font-weight: 500; border: 1px solid var(--border-default); background: var(--bg-tertiary); color: var(--text-secondary); cursor: pointer; text-transform: capitalize; transition: all 0.15s; }
.freq-pill.active { background: var(--accent-cyan); color: #000; border-color: var(--accent-cyan); }
.freq-pill:hover:not(.active) { border-color: var(--accent-cyan); color: var(--accent-cyan); }

.time-body { padding: 16px 18px; display: flex; flex-direction: column; gap: 14px; }
.time-inputs { display: flex; align-items: flex-end; gap: 8px; }
.time-field { display: flex; flex-direction: column; gap: 4px; }
.tz-field { flex: 1; }
.field-label { font-size: 0.72rem; color: var(--text-tertiary); font-weight: 500; }
.time-sep { font-size: 1.2rem; color: var(--text-secondary); margin-bottom: 6px; }
.num-input { width: 70px; padding: 8px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 1rem; text-align: center; }
.num-input:focus { outline: none; border-color: var(--accent-cyan); }
.select-input { padding: 7px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.82rem; width: 100%; }

.days-body { display: flex; gap: 8px; padding: 16px 18px; flex-wrap: wrap; }
.day-btn { width: 40px; height: 40px; border-radius: 50%; border: 1px solid var(--border-default); background: var(--bg-tertiary); color: var(--text-secondary); font-size: 0.75rem; font-weight: 600; cursor: pointer; transition: all 0.15s; }
.day-btn.active { background: var(--accent-cyan); color: #000; border-color: var(--accent-cyan); }
.day-btn:hover:not(.active) { border-color: var(--accent-cyan); }

.month-body { padding: 16px 18px; }
.custom-body { padding: 16px 18px; display: flex; flex-direction: column; gap: 8px; }
.cron-input { padding: 10px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-family: monospace; font-size: 1rem; width: 100%; box-sizing: border-box; }
.cron-input:focus { outline: none; border-color: var(--accent-cyan); }
.cron-help { font-size: 0.72rem; color: var(--text-muted); }

.actions { display: flex; justify-content: flex-end; }
.btn { padding: 8px 20px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.preview-body { padding: 20px 18px; display: flex; flex-direction: column; gap: 16px; }
.human-readable { font-size: 1rem; font-weight: 600; color: var(--text-primary); line-height: 1.4; }
.cron-expr { display: flex; align-items: center; gap: 8px; }
.cron-label { font-size: 0.72rem; color: var(--text-tertiary); }
.cron-code { font-family: monospace; font-size: 0.88rem; color: var(--accent-cyan); background: var(--bg-tertiary); padding: 4px 10px; border-radius: 4px; }

.next-runs-list { display: flex; flex-direction: column; }
.next-run-item { display: flex; align-items: center; gap: 12px; padding: 10px 18px; border-bottom: 1px solid var(--border-subtle); }
.next-run-item:last-child { border-bottom: none; }
.run-num { width: 22px; height: 22px; border-radius: 50%; background: rgba(6,182,212,0.1); color: var(--accent-cyan); font-size: 0.72rem; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.run-time { font-size: 0.78rem; color: var(--text-secondary); }

.nl-card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }
.nl-header { display: flex; align-items: center; gap: 10px; padding: 14px 20px; border-bottom: 1px solid var(--border-default); }
.nl-icon { color: var(--accent-cyan); font-size: 1rem; }
.nl-title { font-size: 0.88rem; font-weight: 700; color: var(--text-primary); }
.nl-hint { font-size: 0.75rem; color: var(--text-muted); margin-left: 8px; }
.nl-body { padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; }
.nl-input-row { display: flex; gap: 10px; }
.nl-input { flex: 1; padding: 10px 14px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 8px; color: var(--text-primary); font-size: 0.9rem; font-style: italic; }
.nl-input:focus { outline: none; border-color: var(--accent-cyan); font-style: normal; }
.nl-result { display: flex; align-items: center; gap: 14px; padding: 10px 14px; background: rgba(6,182,212,0.06); border-radius: 8px; border: 1px solid rgba(6,182,212,0.2); flex-wrap: wrap; }
.nl-result-human { font-size: 0.88rem; font-weight: 600; color: var(--text-primary); }
.nl-result-cron { font-family: monospace; font-size: 0.82rem; color: var(--accent-cyan); background: var(--bg-tertiary); padding: 3px 8px; border-radius: 4px; }
.nl-applied-badge { font-size: 0.72rem; color: #34d399; font-weight: 600; margin-left: auto; }

.section-divider { text-align: center; font-size: 0.75rem; color: var(--text-muted); letter-spacing: 0.08em; padding: 4px 0; }

@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } .nl-input-row { flex-direction: column; } .nl-hint { display: none; } }
</style>
