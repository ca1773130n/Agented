<!--
  Reusable execution-driver selector (phase 19, REQ-13).

  A thin <select> over the three execution drivers the backend's
  ``resolve_execution_driver`` precedence resolves to —
  ``cliproxy`` | ``cli_agent`` | ``grd`` — defaulting to ``grd`` (the
  phase-19 default driver). Used on both project settings
  (persisted to ``projects.default_driver``) and the super-agent
  settings surface (persisted to ``config_json.driver``).

  v-model contract: ``modelValue`` in, ``update:modelValue`` out, so
  parents bind with ``v-model``. Labels come from the ``driver.*``
  i18n namespace; the enum literals themselves are never translated.
-->
<script setup lang="ts">
import { useI18n } from 'vue-i18n';

export type ExecutionDriver = 'cliproxy' | 'cli_agent' | 'grd';

const DRIVERS: ExecutionDriver[] = ['grd', 'cli_agent', 'cliproxy'];

const props = withDefaults(
  defineProps<{
    modelValue?: ExecutionDriver | null;
    disabled?: boolean;
  }>(),
  { modelValue: 'grd', disabled: false },
);

const emit = defineEmits<{
  (e: 'update:modelValue', value: ExecutionDriver): void;
}>();

const { t } = useI18n();

// NULL / undefined means "inherit / unset" on the backend — surface it
// as the default ``grd`` so the control is never blank.
function current(): ExecutionDriver {
  return (props.modelValue as ExecutionDriver) || 'grd';
}

function onChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value as ExecutionDriver;
  emit('update:modelValue', value);
}

function label(driver: ExecutionDriver): string {
  return t(`driver.options.${driver}`);
}
</script>

<template>
  <div class="driver-select-wrapper">
    <select
      class="driver-select"
      :value="current()"
      :disabled="disabled"
      data-testid="driver-selector"
      :aria-label="t('driver.selectorTitle')"
      @change="onChange"
    >
      <option
        v-for="d in DRIVERS"
        :key="d"
        :value="d"
        :data-driver="d"
      >
        {{ label(d) }}
      </option>
    </select>
    <svg class="select-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M6 9l6 6 6-6" />
    </svg>
  </div>
</template>

<style scoped>
.driver-select-wrapper {
  position: relative;
  display: inline-block;
  min-width: 300px;
}

.driver-select {
  width: 100%;
  padding: 12px 40px 12px 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.9rem;
  cursor: pointer;
  appearance: none;
  transition: border-color 0.2s;
}

.driver-select:hover,
.driver-select:focus {
  border-color: var(--accent-cyan);
  outline: none;
}

.driver-select:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.select-arrow {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  color: var(--text-tertiary);
  pointer-events: none;
}
</style>
