<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { triggerApi, ApiError } from '../services/api';
import type { Trigger } from '../services/api';
const { t } = useI18n();
const showToast = useToast();

// Trigger loading
const triggers = ref<Trigger[]>([]);
const scheduledTriggers = computed(() => triggers.value.filter(t => t.trigger_source === 'scheduled'));
const selectedTriggerId = ref('');
const isLoadingTriggers = ref(false);
const triggerLoadError = ref('');

onMounted(async () => {
  await loadTriggers();
});

async function loadTriggers() {
  isLoadingTriggers.value = true;
  triggerLoadError.value = '';
  try {
    const res = await triggerApi.list();
    triggers.value = res.triggers;
    if (scheduledTriggers.value.length > 0) {
      selectedTriggerId.value = scheduledTriggers.value[0].id;
      loadFromTrigger(scheduledTriggers.value[0]);
    }
  } catch (e) {
    triggerLoadError.value = e instanceof ApiError ? e.message : t('visualCronWizard.loadTriggersFailed');
  } finally {
    isLoadingTriggers.value = false;
  }
}

function loadFromTrigger(trigger: Trigger) {
  // Parse schedule_time into the visual builder
  // schedule_type may be extended beyond the TS union; treat unknown types as cron
  const stype = trigger.schedule_type as string | undefined;
  if (stype === 'cron' && trigger.schedule_time) {
    customCron.value = trigger.schedule_time;
    frequency.value = 'custom';
    parseCronToVisual(trigger.schedule_time);
  } else if (stype === 'daily' && trigger.schedule_time) {
    frequency.value = 'daily';
    const parts = trigger.schedule_time.split(':');
    if (parts.length >= 2) {
      hour.value = parseInt(parts[0]) || 9;
      minute.value = parseInt(parts[1]) || 0;
    }
  } else if (stype === 'weekly') {
    frequency.value = 'weekly';
    if (trigger.schedule_day !== undefined) {
      selectedDays.value = [trigger.schedule_day];
    }
  }
  if (trigger.schedule_timezone) {
    timezone.value = trigger.schedule_timezone;
  }
}

function parseCronToVisual(cron: string) {
  const parts = cron.split(/\s+/);
  if (parts.length < 5) return;
  const [min, hr] = parts;
  if (min && !min.includes('*') && !min.includes('/')) minute.value = parseInt(min) || 0;
  if (hr && !hr.includes('*') && !hr.includes('/')) hour.value = parseInt(hr) || 9;
}

function onTriggerSelect() {
  const trigger = triggers.value.find(t => t.id === selectedTriggerId.value);
  if (trigger) loadFromTrigger(trigger);
}

// Natural language input
const nlInput = ref('');
const nlParsed = ref<string | null>(null);
const nlHuman = ref<string | null>(null);

function parseNaturalLanguage(text: string): { cron: string; human: string } | null {
  const txt = text.toLowerCase().trim();
  if (/\bhourly\b|every hour\b/.test(txt)) {
    const minMatch = txt.match(/(?:at\s+)?:(\d+)/);
    const m = minMatch ? minMatch[1].padStart(2, '0') : '00';
    return { cron: `${m} * * * *`, human: t('visualCronWizard.human.hourlyAtMinute', { minute: m }) };
  }
  const everyNHours = txt.match(/every\s+(\d+)\s+hours?/);
  if (everyNHours) {
    const n = everyNHours[1];
    return { cron: `0 */${n} * * *`, human: t('visualCronWizard.human.everyNHours', { count: n }) };
  }
  const everyNMin = txt.match(/every\s+(\d+)\s+min(?:utes?)?/);
  if (everyNMin) {
    const n = everyNMin[1];
    return { cron: `*/${n} * * * *`, human: t('visualCronWizard.human.everyNMinutes', { count: n }) };
  }
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
  const timeMatch = parseTime(txt);
  const h = timeMatch?.h ?? 9;
  const m = timeMatch?.m ?? 0;
  const ms = m.toString().padStart(2, '0');
  if (/weekday|mon.*fri|business day/.test(txt)) {
    const tz = parseTimezoneStr(txt);
    return { cron: `${ms} ${h} * * 1-5`, human: t('visualCronWizard.human.everyWeekday', { time: fmt(h, m) }) + tz };
  }
  if (/weekend/.test(txt)) {
    return { cron: `${ms} ${h} * * 0,6`, human: t('visualCronWizard.human.everyWeekend', { time: fmt(h, m) }) };
  }
  const dayNames = ['sunday','monday','tuesday','wednesday','thursday','friday','saturday'];
  for (let i = 0; i < dayNames.length; i++) {
    if (txt.includes(dayNames[i])) {
      return { cron: `${ms} ${h} * * ${i}`, human: t('visualCronWizard.human.everyDayOfWeek', { day: capitalize(dayNames[i]), time: fmt(h, m) }) };
    }
  }
  if (/\bdaily\b|every day\b/.test(txt)) {
    const tz = parseTimezoneStr(txt);
    return { cron: `${ms} ${h} * * *`, human: t('visualCronWizard.human.everyDay', { time: fmt(h, m) }) + tz };
  }
  if (/\bweekly\b|every week\b/.test(txt)) {
    return { cron: `${ms} ${h} * * 1`, human: t('visualCronWizard.human.everyMonday', { time: fmt(h, m) }) };
  }
  const monthDay = txt.match(/(?:on the\s+)?(\d+)(?:st|nd|rd|th)?\s+(?:of each|of every|each)?\s*month/);
  if (monthDay || /\bmonthly\b/.test(txt)) {
    const d = monthDay ? monthDay[1] : '1';
    return { cron: `${ms} ${h} ${d} * *`, human: t('visualCronWizard.human.onDayOfMonth', { day: d, time: fmt(h, m) }) };
  }
  return null;
}

function parseTimezoneStr(text: string): string {
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
    showToast(t('visualCronWizard.toast.parseFailed'), 'error');
    return;
  }
  nlParsed.value = result.cron;
  nlHuman.value = result.human;
  customCron.value = result.cron;
  frequency.value = 'custom';
  showToast(t('visualCronWizard.toast.applied'), 'success');
}

type Frequency = 'hourly' | 'daily' | 'weekly' | 'monthly' | 'custom';

const frequency = ref<Frequency>('daily');
const hour = ref(9);
const minute = ref(0);
const selectedDays = ref<number[]>([1, 2, 3, 4, 5]);
const selectedMonthDay = ref(1);
const timezone = ref('UTC');
const customCron = ref('');

const days = computed(() => [
  { val: 0, label: t('visualCronWizard.days.sun') }, { val: 1, label: t('visualCronWizard.days.mon') }, { val: 2, label: t('visualCronWizard.days.tue') },
  { val: 3, label: t('visualCronWizard.days.wed') }, { val: 4, label: t('visualCronWizard.days.thu') }, { val: 5, label: t('visualCronWizard.days.fri') }, { val: 6, label: t('visualCronWizard.days.sat') },
]);

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
    case 'hourly': return t('visualCronWizard.human.hourlyAtMinute', { minute: minute.value.toString().padStart(2, '0') });
    case 'daily': return t('visualCronWizard.human.everyDayTz', { time: formatTime(hour.value, minute.value), tz: timezone.value });
    case 'weekly': {
      const dayNames = selectedDays.value.map(d => days.value.find(x => x.val === d)?.label).join(', ');
      return t('visualCronWizard.human.everyDaysTz', { days: dayNames, time: formatTime(hour.value, minute.value), tz: timezone.value });
    }
    case 'monthly': return t('visualCronWizard.human.onDayOfMonthTz', { day: selectedMonthDay.value, time: formatTime(hour.value, minute.value), tz: timezone.value });
    case 'custom': return t('visualCronWizard.human.custom', { cron: customCron.value || t('visualCronWizard.enterExpressionAbove') });
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
  if (!selectedTriggerId.value) {
    showToast(t('visualCronWizard.toast.selectTrigger'), 'info');
    return;
  }
  isSaving.value = true;
  try {
    await triggerApi.update(selectedTriggerId.value, {
      trigger_source: 'scheduled',
    });

    showToast(t('visualCronWizard.toast.saved', { cron: cronExpression.value }), 'success');
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : t('visualCronWizard.toast.saveFailed'), 'error');
  } finally {
    isSaving.value = false;
  }
}
</script>

<template>
  <div class="cron-wizard">

    <PageHeader
      :title="t('visualCronWizard.title')"
      :subtitle="t('visualCronWizard.subtitle')"
    />

    <!-- Trigger selector -->
    <div v-if="isLoadingTriggers" class="loading-msg">{{ t('visualCronWizard.loadingTriggers') }}</div>
    <div v-else-if="triggerLoadError" class="error-msg">{{ triggerLoadError }}</div>
    <div v-else class="trigger-selector">
      <label class="selector-label">{{ t('visualCronWizard.triggerLabel') }}</label>
      <select v-model="selectedTriggerId" class="trigger-select-input" @change="onTriggerSelect">
        <option value="">{{ t('visualCronWizard.selectTrigger') }}</option>
        <option v-for="trig in triggers" :key="trig.id" :value="trig.id">
          {{ trig.name }} ({{ trig.trigger_source }})
        </option>
      </select>
      <span v-if="scheduledTriggers.length > 0" class="scheduled-count">
        {{ t('visualCronWizard.scheduledTriggerCount', { count: scheduledTriggers.length }) }}
      </span>
    </div>

    <!-- Natural language input -->
    <div class="card nl-card">
      <div class="nl-header">
        <span class="nl-icon">*</span>
        <span class="nl-title">{{ t('visualCronWizard.nlTitle') }}</span>
        <span class="nl-hint">{{ t('visualCronWizard.nlHint') }}</span>
      </div>
      <div class="nl-body">
        <div class="nl-input-row">
          <input
            v-model="nlInput"
            class="nl-input"
            :placeholder="t('visualCronWizard.nlPlaceholder')"
            @keyup.enter="applyNLSchedule"
          />
          <button class="btn btn-primary" @click="applyNLSchedule">{{ t('visualCronWizard.parseSchedule') }}</button>
        </div>
        <div v-if="nlParsed" class="nl-result">
          <div class="nl-result-human">{{ nlHuman }}</div>
          <code class="nl-result-cron">{{ nlParsed }}</code>
          <span class="nl-applied-badge">{{ t('visualCronWizard.appliedBadge') }}</span>
        </div>
      </div>
    </div>

    <div class="section-divider">{{ t('visualCronWizard.orConfigureVisually') }}</div>

    <div class="layout">
      <div class="wizard-col">
        <!-- Frequency selector -->
        <div class="card freq-card">
          <div class="card-header">{{ t('visualCronWizard.frequency') }}</div>
          <div class="freq-pills">
            <button
              v-for="f in (['hourly', 'daily', 'weekly', 'monthly', 'custom'] as Frequency[])"
              :key="f"
              :class="['freq-pill', { active: frequency === f }]"
              @click="frequency = f"
            >{{ t('visualCronWizard.freq.' + f) }}</button>
          </div>
        </div>

        <!-- Time picker -->
        <div v-if="frequency !== 'hourly' && frequency !== 'custom'" class="card time-card">
          <div class="card-header">{{ t('visualCronWizard.time') }}</div>
          <div class="time-body">
            <div class="time-inputs">
              <div class="time-field">
                <label class="field-label">{{ t('visualCronWizard.hour') }}</label>
                <input type="number" v-model.number="hour" min="0" max="23" class="num-input" />
              </div>
              <span class="time-sep">:</span>
              <div class="time-field">
                <label class="field-label">{{ t('visualCronWizard.minute') }}</label>
                <input type="number" v-model.number="minute" min="0" max="59" class="num-input" />
              </div>
            </div>
            <div class="time-field tz-field">
              <label class="field-label">{{ t('visualCronWizard.timezone') }}</label>
              <select v-model="timezone" class="select-input">
                <option v-for="tz in timezones" :key="tz" :value="tz">{{ tz }}</option>
              </select>
            </div>
          </div>
        </div>

        <!-- Weekly day picker -->
        <div v-if="frequency === 'weekly'" class="card days-card">
          <div class="card-header">{{ t('visualCronWizard.daysOfWeek') }}</div>
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
          <div class="card-header">{{ t('visualCronWizard.dayOfMonth') }}</div>
          <div class="month-body">
            <input type="number" v-model.number="selectedMonthDay" min="1" max="31" class="num-input" />
          </div>
        </div>

        <!-- Custom cron -->
        <div v-if="frequency === 'custom'" class="card">
          <div class="card-header">{{ t('visualCronWizard.customCronExpression') }}</div>
          <div class="custom-body">
            <input v-model="customCron" class="cron-input" placeholder="0 9 * * 1-5" />
            <div class="cron-help">{{ t('visualCronWizard.cronFormatHelp') }}</div>
          </div>
        </div>

        <div class="actions">
          <button class="btn btn-primary" :disabled="isSaving || !selectedTriggerId" @click="handleSave">
            {{ isSaving ? t('visualCronWizard.saving') : t('visualCronWizard.saveSchedule') }}
          </button>
        </div>
      </div>

      <!-- Preview panel -->
      <div class="preview-col">
        <div class="card preview-card">
          <div class="card-header">{{ t('visualCronWizard.schedulePreview') }}</div>
          <div class="preview-body">
            <div class="human-readable">{{ humanReadable }}</div>
            <div class="cron-expr">
              <span class="cron-label">{{ t('visualCronWizard.cronLabel') }}</span>
              <code class="cron-code">{{ cronExpression }}</code>
            </div>
          </div>
        </div>

        <div class="card next-runs-card">
          <div class="card-header">{{ t('visualCronWizard.next5Runs') }}</div>
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

.loading-msg { font-size: 0.82rem; color: var(--text-tertiary); padding: 12px 0; }
.error-msg { font-size: 0.82rem; color: #ef4444; padding: 12px 0; }

.trigger-selector { display: flex; align-items: center; gap: 12px; }
.selector-label { font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }
.trigger-select-input { flex: 1; max-width: 400px; padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.82rem; }
.scheduled-count { font-size: 0.72rem; color: var(--text-muted); }

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
