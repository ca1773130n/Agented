import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SketchChatPage from '../SketchChatPage.vue'
import SketchClassification from '../../components/sketches/SketchClassification.vue'
import SketchRouting from '../../components/sketches/SketchRouting.vue'
import SketchStatusTracker from '../../components/sketches/SketchStatusTracker.vue'
import { router } from '../../router/index'

vi.mock('../../services/api', () => ({
  sketchApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    classify: vi.fn(),
    route: vi.fn(),
  },
  projectApi: {
    list: vi.fn(),
  },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  },
}))

describe('SketchChatPage', () => {
  const mockShowToast = vi.fn()

  function mountPage() {
    return mount(SketchChatPage, {
      global: {
        provide: {
          showToast: mockShowToast,
        },
        stubs: {
          teleport: true,
        },
      },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { sketchApi, projectApi } = await import('../../services/api')
    vi.mocked(sketchApi.list).mockResolvedValue({ sketches: [] })
    vi.mocked(projectApi.list).mockResolvedValue({
      projects: [
        { id: 'proj-abc', name: 'Test Project', status: 'active', team_count: 0 },
      ],
    })
  })

  it('renders sketch chat page with title', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('Sketch Ideation')
  })

  it('renders project selector', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const select = wrapper.find('.project-selector')
    expect(select.exists()).toBe(true)
    expect(wrapper.text()).toContain('All Projects')
  })

  it('renders AiChatPanel component', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const chatPanel = wrapper.findComponent({ name: 'AiChatPanel' })
    expect(chatPanel.exists()).toBe(true)
  })
})

describe('SketchClassification', () => {
  it('shows placeholder when classification is null', () => {
    const wrapper = mount(SketchClassification, {
      props: { classification: null },
    })

    expect(wrapper.text()).toContain('Not yet classified')
  })

  it('displays classification data', () => {
    const wrapper = mount(SketchClassification, {
      props: {
        classification: {
          phase: 'execution',
          domains: ['backend', 'database'],
          complexity: 'high',
          confidence: 0.85,
          source: 'llm',
        },
      },
    })

    expect(wrapper.text()).toContain('execution')
    expect(wrapper.text()).toContain('backend')
    expect(wrapper.text()).toContain('database')
    expect(wrapper.text()).toContain('high')
    expect(wrapper.text()).toContain('85%')
  })
})

describe('SketchRouting', () => {
  it('shows placeholder when routing is null', () => {
    const wrapper = mount(SketchRouting, {
      props: { routing: null },
    })

    expect(wrapper.text()).toContain('Not yet routed')
  })

  it('displays routing data', () => {
    const wrapper = mount(SketchRouting, {
      props: {
        routing: {
          target_type: 'super_agent',
          target_id: 'sa-abc123',
          reason: 'Best match for backend work',
        },
      },
    })

    expect(wrapper.text()).toContain('SuperAgent')
    expect(wrapper.text()).toContain('sa-abc123')
    expect(wrapper.text()).toContain('Best match for backend work')
  })
})

describe('SketchStatusTracker', () => {
  it('renders all 5 status steps', () => {
    const wrapper = mount(SketchStatusTracker, {
      props: { status: 'draft' },
    })

    expect(wrapper.text()).toContain('Draft')
    expect(wrapper.text()).toContain('Classified')
    expect(wrapper.text()).toContain('Routed')
    expect(wrapper.text()).toContain('In Progress')
    expect(wrapper.text()).toContain('Completed')
  })

  it('highlights current step for classified status', () => {
    const wrapper = mount(SketchStatusTracker, {
      props: { status: 'classified' },
    })

    const steps = wrapper.findAll('.pipeline-step')
    expect(steps.length).toBe(5)
    // draft (index 0) should be completed
    expect(steps[0].classes()).toContain('step-completed')
    // classified (index 1) should be current
    expect(steps[1].classes()).toContain('step-current')
    // routed (index 2) should be future
    expect(steps[2].classes()).toContain('step-future')
  })
})

describe('Route registration', () => {
  it('router has sketch-chat route', () => {
    const route = router.resolve({ name: 'sketch-chat' })
    expect(route).toBeDefined()
    expect(route.name).toBe('sketch-chat')
  })

  it('sketch-chat route maps to /sketches path', () => {
    const route = router.resolve({ name: 'sketch-chat' })
    expect(route.path).toBe('/sketches')
  })

  it('/sketches path resolves to sketch-chat route', () => {
    const route = router.resolve('/sketches')
    expect(route.name).toBe('sketch-chat')
  })
})
