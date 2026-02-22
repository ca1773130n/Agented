import { ref } from 'vue';
import type { Ref } from 'vue';
import type { Sketch, Project } from '../services/api/types';
import { sketchApi, projectApi } from '../services/api';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

export function useSketchChat() {
  const sketches: Ref<Sketch[]> = ref([]);
  const currentSketch: Ref<Sketch | null> = ref(null);
  const selectedProjectId: Ref<string | null> = ref(null);
  const projects: Ref<Project[]> = ref([]);
  const isProcessing: Ref<boolean> = ref(false);
  const messages: Ref<ChatMessage[]> = ref([]);
  const error: Ref<string | null> = ref(null);

  async function loadProjects() {
    try {
      const result = await projectApi.list();
      projects.value = result.projects;
    } catch (e: any) {
      error.value = e.message || 'Failed to load projects';
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
    } catch (e: any) {
      error.value = e.message || 'Failed to load sketches';
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
        try {
          const cls = JSON.parse(fetched.classification_json);
          const parts: string[] = [];
          if (cls.phase) parts.push(`Phase: ${cls.phase}`);
          if (cls.domains && cls.domains.length) parts.push(`Domains: ${cls.domains.join(', ')}`);
          if (cls.complexity) parts.push(`Complexity: ${cls.complexity}`);
          if (cls.confidence != null) parts.push(`Confidence: ${Math.round(cls.confidence * 100)}%`);
          if (parts.length) classificationSummary = parts.join(' | ');
        } catch {
          // classification_json parse error, use default summary
        }
      }

      messages.value.push({
        role: 'assistant',
        content: classificationSummary,
        timestamp: new Date().toISOString(),
      });

      currentSketch.value = fetched;
      await loadSketches();
    } catch (e: any) {
      const errMsg = e.message || 'Failed to create or classify sketch';
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
        try {
          const rt = JSON.parse(fetched.routing_json);
          const parts: string[] = [];
          if (rt.target_type) parts.push(`Target: ${rt.target_type}`);
          if (rt.target_id) parts.push(`ID: ${rt.target_id}`);
          if (rt.reason) parts.push(`Reason: ${rt.reason}`);
          if (parts.length) routingSummary = parts.join(' | ');
        } catch {
          // routing_json parse error
        }
      }

      messages.value.push({
        role: 'assistant',
        content: routingSummary,
        timestamp: new Date().toISOString(),
      });

      await loadSketches();
    } catch (e: any) {
      const errMsg = e.message || 'Failed to route sketch';
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
      try {
        const cls = JSON.parse(sketch.classification_json);
        const parts: string[] = [];
        if (cls.phase) parts.push(`Phase: ${cls.phase}`);
        if (cls.domains && cls.domains.length) parts.push(`Domains: ${cls.domains.join(', ')}`);
        if (cls.complexity) parts.push(`Complexity: ${cls.complexity}`);
        if (cls.confidence != null) parts.push(`Confidence: ${Math.round(cls.confidence * 100)}%`);
        if (parts.length) {
          messages.value.push({
            role: 'assistant',
            content: parts.join(' | '),
            timestamp: sketch.updated_at || new Date().toISOString(),
          });
        }
      } catch {
        // ignore parse error
      }
    }

    if (sketch.routing_json) {
      try {
        const rt = JSON.parse(sketch.routing_json);
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
      } catch {
        // ignore parse error
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
