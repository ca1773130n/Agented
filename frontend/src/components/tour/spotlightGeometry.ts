/**
 * Spotlight geometry helper (Plan 02-01, OB-11).
 *
 * Maps a tour target element to the padding + border-radius the
 * `TourSpotlight` should render around it. Padding varies by element type
 * so the spotlight visually matches the shape of inputs (tight),
 * buttons (medium), and cards/sections (loose). Elements can override via
 * `data-tour-padding` or `data-tour-radius` attributes.
 */

export interface SpotlightGeometry {
  /** Pixels of padding to add around the target rect on every side. */
  padding: number
  /** CSS border-radius value for the spotlight (string, may be `12px`,
   *  `9999px`, etc.; falls back to a default for elements with no radius). */
  borderRadius: string
}

const PADDING_BY_TAG: Record<string, number> = {
  input: 4,
  textarea: 4,
  select: 4,
  button: 6,
  a: 6,
}

const DEFAULT_PADDING = 12
const DEFAULT_BORDER_RADIUS = '8px'

/**
 * Compute spotlight padding + border-radius for a target element. Pure
 * function over the element's tag, role attribute, dataset overrides, and
 * computed border-radius.
 *
 * Caller passes the element. When `null`, returns sensible defaults so
 * TourSpotlight can render without flickering during step transitions.
 */
export function computeSpotlightGeometry(
  target: Element | null,
  /** Optional injection seam for tests. */
  computedStyle: (el: Element) => CSSStyleDeclaration = window.getComputedStyle,
): SpotlightGeometry {
  if (!target) {
    return { padding: DEFAULT_PADDING, borderRadius: DEFAULT_BORDER_RADIUS }
  }

  const dataset = (target as HTMLElement).dataset ?? {}
  const overridePadding = parsePxOverride(dataset.tourPadding)
  const overrideRadius = dataset.tourRadius

  const tag = target.tagName.toLowerCase()
  const role = (target.getAttribute('role') ?? '').toLowerCase()

  let padding: number
  if (overridePadding != null) {
    padding = overridePadding
  } else if (tag in PADDING_BY_TAG) {
    padding = PADDING_BY_TAG[tag]
  } else if (role === 'button') {
    padding = PADDING_BY_TAG.button
  } else {
    padding = DEFAULT_PADDING
  }

  let borderRadius: string
  if (overrideRadius) {
    borderRadius = overrideRadius
  } else {
    try {
      const computed = computedStyle(target).borderRadius
      borderRadius = computed && computed !== '0px' ? computed : DEFAULT_BORDER_RADIUS
    } catch {
      borderRadius = DEFAULT_BORDER_RADIUS
    }
  }

  return { padding, borderRadius }
}

function parsePxOverride(raw: string | undefined): number | null {
  if (raw == null || raw === '') return null
  const n = Number.parseFloat(raw)
  return Number.isFinite(n) ? n : null
}
