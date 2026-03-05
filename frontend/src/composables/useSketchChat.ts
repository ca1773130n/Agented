import { ref } from 'vue';
import type { Ref } from 'vue';
import type { Sketch, Project, ConversationMessage } from '../services/api/types';
import { sketchApi, projectApi } from '../services/api';

/**
 * Parse a JSON block from a string (e.g. a JSON field value).
 * Returns the parsed value on success, or null on parse failure.
 */
function parseJsonBlock(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export function useSketchChat() {
  const sketches: Ref<Sketch[]> = ref([]);
  const currentSketch: Ref<Sketch | null> = ref(null);
  const selectedProjectId: Ref<string | null> = ref(null);
  const projects: Ref<Project[]> = ref([]);
  const isProcessing: Ref<boolean> = ref(false);
  const messages: Ref<ConversationMessage[]> = ref([]);
  const error: Ref<string | null> = ref(null);

  async function loadProjects() {
    try {
      const result = await projectApi.list();
      projects.value = result.projects;
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to load projects';
    }
  }

  async function loadSketches() {
    try {
      const params: { project_id?: string } = {};
      if (selectedProjectId.value) {
        params.project_id = selectedProjectId.value;
      }
      const result = await sketchApi.list(params);
      sketches.value = result.sketches;
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to load sketches';
    }
  }

  async function submitSketch(text: string) {
    isProcessing.value = true;
    error.value = null;

    messages.value.push({
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    });

    try {
      const createResult = await sketchApi.create({
        title: text.slice(0, 100),
        content: text,
        project_id: selectedProjectId.value ?? undefined,
      });

      const sketchId = createResult.sketch_id;

      await sketchApi.classify(sketchId);

      const fetched = await sketchApi.get(sketchId);

      let classificationSummary = 'Sketch created and classified.';
      if (fetched.classification_json) {
        const cls = parseJsonBlock(fetched.classification_json) as Record<string, unknown> | null;
        if (cls) {
          const parts: string[] = [];
          if (cls.phase) parts.push(`Phase: ${cls.phase}`);
          if (cls.domains && (cls.domains as unknown[]).length) parts.push(`Domains: ${(cls.domains as string[]).join(', ')}`);
          if (cls.complexity) parts.push(`Complexity: ${cls.complexity}`);
          if (cls.confidence != null) parts.push(`Confidence: ${Math.round((cls.confidence as number) * 100)}%`);
          if (parts.length) classificationSummary = parts.join(' | ');
        }
      }

      messages.value.push({
        role: 'assistant',
        content: classificationSummary,
        timestamp: new Date().toISOString(),
      });

      currentSketch.value = fetched;
      await loadSketches();
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : 'Failed to create or classify sketch';
      error.value = errMsg;
      messages.value.push({
        role: 'assistant',
        content: `Error: ${errMsg}`,
        timestamp: new Date().toISOString(),
      });
    } finally {
      isProcessing.value = false;
    }
  }

  async function routeSketch(sketchId: string) {
    isProcessing.value = true;
    error.value = null;

    try {
      await sketchApi.route(sketchId);
      const fetched = await sketchApi.get(sketchId);
      currentSketch.value = fetched;

      let routingSummary = 'Sketch routed successfully.';
      if (fetched.routing_json) {
        const rt = parseJsonBlock(fetched.routing_json) as Record<string, unknown> | null;
        if (rt) {
          const parts: string[] = [];
          if (rt.target_type) parts.push(`Target: ${rt.target_type}`);
          if (rt.target_id) parts.push(`ID: ${rt.target_id}`);
          if (rt.reason) parts.push(`Reason: ${rt.reason}`);
          if (parts.length) routingSummary = parts.join(' | ');
        }
      }

      messages.value.push({
        role: 'assistant',
        content: routingSummary,
        timestamp: new Date().toISOString(),
      });

      await loadSketches();
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : 'Failed to route sketch';
      error.value = errMsg;
      messages.value.push({
        role: 'assistant',
        content: `Error: ${errMsg}`,
        timestamp: new Date().toISOString(),
      });
    } finally {
      isProcessing.value = false;
    }
  }

  function selectSketch(sketch: Sketch) {
    currentSketch.value = sketch;
    messages.value = [];

    // Rebuild messages from sketch data
    messages.value.push({
      role: 'user',
      content: sketch.content || sketch.title,
      timestamp: sketch.created_at || new Date().toISOString(),
    });

    if (sketch.classification_json) {
      const cls = parseJsonBlock(sketch.classification_json) as Record<string, unknown> | null;
      if (cls) {
        const parts: string[] = [];
        if (cls.phase) parts.push(`Phase: ${cls.phase}`);
        if (cls.domains && (cls.domains as unknown[]).length) parts.push(`Domains: ${(cls.domains as string[]).join(', ')}`);
        if (cls.complexity) parts.push(`Complexity: ${cls.complexity}`);
        if (cls.confidence != null) parts.push(`Confidence: ${Math.round((cls.confidence as number) * 100)}%`);
        if (parts.length) {
          messages.value.push({
            role: 'assistant',
            content: parts.join(' | '),
            timestamp: sketch.updated_at || new Date().toISOString(),
          });
        }
      }
    }

    if (sketch.routing_json) {
      const rt = parseJsonBlock(sketch.routing_json) as Record<string, unknown> | null;
      if (rt) {
        const parts: string[] = [];
        if (rt.target_type) parts.push(`Target: ${rt.target_type}`);
        if (rt.target_id) parts.push(`ID: ${rt.target_id}`);
        if (rt.reason) parts.push(`Reason: ${rt.reason}`);
        if (parts.length) {
          messages.value.push({
            role: 'assistant',
            content: parts.join(' | '),
            timestamp: sketch.updated_at || new Date().toISOString(),
          });
        }
      }
    }
  }

  function clearChat() {
    currentSketch.value = null;
    messages.value = [];
    error.value = null;
  }

  return {
    sketches,
    currentSketch,
    selectedProjectId,
    projects,
    isProcessing,
    messages,
    error,
    loadProjects,
    loadSketches,
    submitSketch,
    routeSketch,
    selectSketch,
    clearChat,
  };
}
