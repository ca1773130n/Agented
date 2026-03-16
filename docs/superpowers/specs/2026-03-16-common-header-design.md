# Common Header Design

## Overview

Add a full-width top bar with logo, breadcrumb navigation, and action icons (search, theme toggle, notifications, profile). The header sits above the sidebar+content row, replacing the current sidebar-only layout.

## Layout Change

Current:
```
[Sidebar (240px)] [Content (flex:1)]
```

New:
```
[Full-width Header (48px)]
[Sidebar (240px)] [Content (flex:1)]
```

- `App.vue` root `.app-container` changes to `flex-direction: column`
- New inner wrapper (`.app-body`) holds sidebar + content as a horizontal flex row
- Header is `position: sticky; top: 0; z-index: 1001`
- Logo/branding removed from `AppSidebar.vue` header section — moves into the top bar
- Sidebar retains nav sections but loses its top branding area

### Header contents (left to right)

1. Logo icon — reuse existing sidebar logo mark (gradient background SVG from App.vue) at 28x28px + "Agented" text
2. Separator (`1px` vertical divider, 20px height, `var(--border-subtle)`)
3. Breadcrumb: `Home / Organization / Products / My Product`
4. Spacer (`flex: 1`)
5. Search icon (opens command palette)
6. Theme toggle icon (moon — dark only for now)
7. Notification bell icon (dropdown)
8. Profile avatar (dropdown)

All vertically centered (`align-items: center`), consistent icon sizing (18x18px).

## Components

### `AppHeader.vue` (`src/components/layout/AppHeader.vue`)

- **Props**: none — derives breadcrumb from `useRoute()`
- **Emits**: `toggleSidebar` (mobile hamburger, reuses existing pattern)
- **Contains**: logo, breadcrumb, action icons, dropdown states (notifications, profile)
- Breadcrumb computed from route matched records
- Icon buttons use `<button>` with `aria-label` for accessibility

### `CommandPalette.vue` (`src/components/layout/CommandPalette.vue`)

- Teleported to `<body>` via `<Teleport>`
- Opens via prop or global `Cmd+K` / `Ctrl+K` shortcut
- `z-index: 2000` (above header at 1001, below toasts at 10000)
- `role="dialog"`, `aria-modal="true"`, focus trapped inside while open
- Text input at top, filtered results below
- Searches by **name only** across: products, projects, teams, agents, bots, plugins (existing API list endpoints)
- Results show entity type badge + name; click navigates
- **Empty state**: "No results found" message
- **Error state**: "Search failed" with retry option
- **Loading state**: spinner while API calls are in flight
- Closes on `Escape`, click outside, or navigation

### Dropdowns (inline in AppHeader)

Notification and profile dropdowns are `v-show` toggled `<div>`s inside `AppHeader.vue`. Click-outside closes them. `z-index: 1002` (just above header).

**Profile dropdown items:**
- User display name (static "User" for now — no auth system)
- Divider
- "Settings" (navigates to settings page if exists, or no-op)
- "Sign Out" (no-op for now, placeholder)

**Notification dropdown:**
- Empty state: bell icon + "No notifications" text + "You're all caught up" subtitle

## Breadcrumb Logic

### Route-to-breadcrumb mapping

A lookup object maps route names to breadcrumb segment arrays. Each segment is either a static label or a dynamic `{param}` placeholder resolved at runtime.

```
'products'           → [Home, Organization, Products]
'product-dashboard'  → [Home, Organization, Products, {product.name}]
'product-settings'   → [Home, Organization, Products, {product.name}, Settings]
'agents'             → [Home, Organization, Agents]
'agent-detail'       → [Home, Organization, Agents, {agent.name}]
'dashboards'         → [Home, Dashboards]
'security-dashboard' → [Home, Dashboards, Security]
'bots'               → [Home, System, Bots]
'sketch-chat'        → [Home, Sketch]
```

This table is extended to cover all routes in the app. Routes not in the lookup table fall back to auto-generating from `route.name` — split on `-`, title-case each word (e.g., `token-usage` → `Home / Token Usage`).

### Entity name resolution

For dynamic segments like `{product.name}`, AppHeader fetches the entity name using the entity ID from route params via the existing API client (e.g., `productApi.get(productId)`). Results are cached in a reactive `Map<string, string>` keyed by `entityType:entityId` to avoid refetching on repeated navigation.

**Loading state**: Show the entity ID as placeholder text while the name loads (e.g., `prod-abc123`), replace with name when resolved.

### Navigation targets

Each breadcrumb segment except the last is a clickable `<router-link>`. Targets:
- "Home" → `{ name: 'dashboards' }`
- "Organization" → not clickable (section label only)
- "Products" → `{ name: 'products' }`
- Entity names → their dashboard route (e.g., `{ name: 'product-dashboard', params: { productId } }`)

### Overflow handling

When breadcrumb is too wide for available space:
- Desktop: middle segments collapse to `...` (show first, last 2 segments), full path in tooltip on hover
- Mobile (< 768px): show only last 2 segments

### Existing AppBreadcrumb removal

Remove `AppBreadcrumb` usage from individual pages — header handles it globally.

## Styling

### Header
- Background: `var(--bg-secondary)` (#12121a)
- Bottom border: `1px solid var(--border-subtle)`
- Height: 48px
- `position: sticky; top: 0; z-index: 1001`
- Padding: `0 16px`

### Action icons
- Inline SVGs (existing pattern, no icon library)
- `<button>` elements with `aria-label` attributes
- Size: 18x18px
- Color: `var(--text-secondary)`, hover: `var(--text-primary)`
- Gap: 8px between icons
- Profile avatar: 28x28px circle, `background: var(--accent-violet)`, white initial letter

### Dropdowns (notification & profile)
- `position: absolute`, anchored below trigger, aligned right
- `right: 0` to prevent right-edge overflow
- Background: `var(--bg-elevated)`
- Border: `var(--border-default)`, `border-radius: 8px`
- `box-shadow: 0 4px 12px rgba(0,0,0,0.3)`
- Close on click outside
- Min-width: 200px

### Command palette
- Centered modal with backdrop (`rgba(0,0,0,0.5)`)
- Max width: 560px, `border-radius: 12px`
- Input at top with search icon, results list below (max-height with scroll)
- Keyboard nav: arrows to move, Enter to select, Escape to close
- Results grouped by entity type with type badges

### Theme toggle
- Moon icon, static appearance (no state change on click)
- Click shows toast: "Light theme coming soon"
- Uses existing `showToast` via `inject`

### Mobile (< 768px)
- Header stays full width, height stays 48px
- Breadcrumb shows last 2 segments only
- Hamburger icon appears before logo (reuses existing mobile toggle)
- "Agented" text hidden, logo icon only

## Z-Index Layering

```
Toasts:          10000 (existing)
Command Palette: 2000
Dropdowns:       1002
Header:          1001
Sidebar:         1000 (existing)
```

## Files Modified

- `App.vue` — layout restructure (flex-direction, new `.app-body` wrapper), header CSS
- `AppSidebar.vue` — remove logo/branding header section
- Individual page views — remove per-page `AppBreadcrumb` usage

## Files Created

- `src/components/layout/AppHeader.vue`
- `src/components/layout/CommandPalette.vue`
