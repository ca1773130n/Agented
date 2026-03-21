# Onboarding UX Research: Production-Level Patterns

> Research compiled from 200+ onboarding flow analyses, deep dives into Linear, Figma, Notion,
> Vercel, Railway, Supabase, Stripe, Canva, Asana, and other best-in-class web applications.

---

## Platform Deep Dives

### Linear (Project Management for Engineering Teams)

Linear's onboarding is widely regarded as one of the best in developer tooling. They reached a $1.25B valuation without running a single A/B test -- built entirely on design craft and user empathy.

**Flow structure (6 steps after signup):**
1. Welcome screen
2. Dark or light mode selection (immediately -- before anything else)
3. Keyboard shortcut teaching (Cmd+K to open command menu)
4. Join team (domain-based, no invites needed)
5. GitHub integration explainer
6. Invite team / subscribe to emails

**What makes it exceptional:**
- **Theme choice first**: Before any setup, users pick dark/light mode. This signals "we care about your comfort" and "you're in control." Most engineers live in dark mode, so this makes everything feel calmer instantly.
- **Keyboard shortcut as onboarding step**: Instead of just telling users about Cmd+K, Linear asks them to actually press it. Big keyboard-style buttons make it feel like muscle memory training. After success, it congratulates and reminds of the shortcut.
- **Frictionless team expansion**: Anyone with the same email domain can join without invites. No "can someone add me?" friction. Growth happens via word-of-mouth as teammates share ticket links.
- **Language and tone**: Soft, calm, gentle copy throughout. "Let's try it out," "Type a command." Feels like a verbal hug, not a corporate wizard.
- **Uncluttered screens**: Each screen has one clear purpose. No multi-column layouts, no competing CTAs.
- **No celebration theater**: No confetti, no "You did it!" modals. The flow is calm and professional. The reward IS the tool being ready.
- **Philosophy**: "Craft over data." Design the whole thing end-to-end with clear user understanding, rather than optimizing each screen in isolation.

### Figma (Collaborative Design Tool)

**What makes it exceptional:**
- **Zero-friction start**: Users can start designing in a browser with zero account creation. Create frames, add shapes, apply styles -- only asked to sign up when they want to save.
- **Opt-in tour**: First modal encourages users to take the tour by highlighting features that differentiate Figma from competitors. Users choose to start the tour -- it's not forced.
- **Animated tooltips**: Almost every tooltip has both concise copy explaining a feature AND an animation illustrating the feature's functionality. Caters to all types of learners.
- **Progressive depth**: Copy in each tooltip is kept brief, but includes links to detailed resources for users who want more context.
- **Competitive positioning in onboarding**: The welcome modal explicitly mentions differences from competitors, giving users motivation to complete the tour.
- **Short tour**: Covers import files, design elements, and team collaboration in a few focused steps.

### Notion (Workspace & Documentation)

**What makes it exceptional:**
- **Empty states as onboarding surfaces**: A blank page doesn't show "No content yet." It shows a warm, human-voiced prompt with the slash-command shortcut, template suggestions, and a single clear action.
- **Self-segmentation**: Asks "How are you planning to use Notion?" (Personal, Team, Enterprise) to tailor the subsequent experience with relevant templates and features.
- **Minimalist pop-ups**: Highlights features exactly when needed, ensuring clarity without interruption.
- **Getting Started checklist**: An interactive checklist inside the workspace that acts as a tutorial. Tasks like "Import data," "Create a page," "Invite teammates."
- **Template-first approach**: Instead of empty workspace, offers curated templates based on the user's self-selected use case.

### Vercel (Deployment Platform)

**What makes it exceptional:**
- **Single-action onboarding**: The entire onboarding converges on one action -- "Deploy." Everything else supports getting to that first deploy.
- **Git-connected wizard**: Step-by-step project creation wizard connects to GitHub/GitLab/Bitbucket, auto-detects framework, suggests deployment settings.
- **Instant feedback**: Build logs stream in real-time. Users see their code deploying within minutes of signing up.
- **Dark UI**: Entire dashboard is dark-themed by default, matching developer expectations.
- **Progressive complexity**: Basic deploy needs zero configuration. Environment variables, domains, and team settings are revealed only when needed.

### Railway (Cloud Deployment)

**What makes it exceptional:**
- **"Spin up a database before you can dismiss this toast"**: The onboarding is so fast that by the time you notice the welcome message, your service is already provisioning. The team learned that "nothing replaces a really good first-time user experience."
- **Template gallery as onboarding**: Instead of empty dashboard, users can pick from pre-configured templates to deploy immediately.
- **Minimal steps**: GitHub repo connection to live deployment in under 2 minutes. Removes complexity rather than adding features.
- **Visual service graph**: Shows connected services as a visual diagram, making infrastructure tangible.

### Supabase (Backend-as-a-Service)

**What makes it exceptional:**
- **Project creation wizard**: Creates database, auth, storage, and edge functions in one flow. Shows a loading state while provisioning.
- **API keys front and center**: After project creation, immediately shows connection details and API keys with copy buttons.
- **Table editor as onboarding**: The table editor doubles as a learning tool -- users can create their first table visually without writing SQL.
- **Sidebar-driven navigation**: Consistent sidebars in every section (Table view, Auth, SQL Editor) provide always-available context.
- **Transitional key system**: Gracefully migrating from anon keys to publishable/secret keys, showing both during transition with clear explanation.

### Stripe (Payment Infrastructure)

**What makes it exceptional:**
- **Test mode / Live mode separation**: New accounts start in test mode. Users can experiment freely with test card numbers, simulated payments, and webhook testing -- zero risk.
- **Account checklist**: A structured checklist for activation: enable 2FA, set statement descriptor, add bank details, configure payouts. Checkbox state persists in browser cache so users can return anytime.
- **Developers Dashboard**: Collects every API request, shows integration errors, failed requests, webhook events. Turns debugging into a first-class onboarding experience.
- **Documentation-as-product**: Code examples with the user's actual API keys pre-filled. Copy-paste to working integration.
- **Progressive activation**: Start testing immediately. Only need to complete verification steps when ready to go live.

### Canva (Design Platform)

**What makes it exceptional:**
- **Confetti celebration**: After completing the initial account setup survey, Canva pops confetti to acknowledge the effort. Recognizes that setup can feel monotonous.
- **Template-first empty state**: Dashboard immediately shows templates relevant to the user's stated purpose (social media, presentations, etc.).
- **Role-based personalization**: Asks "What will you use Canva for?" and tailors the entire template library and feature suggestions.

### Asana (Project Management)

**What makes it exceptional:**
- **Flying unicorn reward**: Completing tasks triggers a whimsical unicorn animation flying across the screen. Unexpected delight.
- **Gamified leveling system**: Users start as beginners. Completing onboarding tasks advances their level. Progress bar shows remaining tasks to next level.
- **Real-time preview during setup**: When choosing themes and layouts during onboarding, shows a live preview of how the workspace will look.

---

## The 14 Onboarding UX Patterns (from analysis of 200+ flows)

### 1. First Look
Brief intro carousel or video after first login. 2-4 slides highlighting main benefits. Used by Amplitude, Slack, HubSpot.
- **UI**: Carousel/slider modal, embedded video, close button
- **Best for**: Complex SaaS tools, productivity apps

### 2. Product Tour
Step-by-step guided tour with overlays highlighting features in sequence. Used by Google Analytics, Asana, Intercom.
- **UI**: Modal overlays, progress indicators, Next/Skip buttons
- **Best for**: Feature-rich tools, analytics platforms

### 3. Walkthrough Beacons
Small pulsating dots/indicators in the UI. Click to reveal tooltips. Non-blocking. Used by Siimple, website builders.
- **UI**: Pulsating beacon dots, popover tooltips, subtle animations
- **Best for**: Visual editors, website builders, tools where users should explore at their own pace

### 4. Empty State
What users see when there's no content. Illustration + single call to action. Used by Tally, Todoist, Pinterest.
- **UI**: Illustration/icon, prompt/CTA, skeleton screens
- **Best for**: Content-creation apps, user-generated-content platforms

### 5. Personalization
Quick preference gathering to adapt the experience. Used by Reddit, Spotify, Netflix.
- **UI**: Questionnaire, selection chips, progress bar, toggles
- **Best for**: Content apps, streaming, social platforms

### 6. Checklists
Task list with checkboxes and progress tracking. Used by Front, Slack, Shopify, QuickBooks.
- **UI**: Checkbox list, progress bar/percentage, completion badge
- **Best for**: Setup-heavy apps, complex onboarding with multiple configurations

### 7. Action-Oriented
Prompts users to DO a specific key action immediately. Used by Slack ("Send your first message"), Copilot, Loom.
- **UI**: Bold CTAs, inline prompts, celebratory micro-animations
- **Best for**: Communication tools, collaboration apps

### 8. Goal Setting
Help users define targets and track progress. Used by Duolingo, fitness apps.
- **UI**: Goal creation screen, progress tracker/dashboard, motivational notifications
- **Best for**: Learning platforms, habit-forming apps

### 9. Social Proof
Show other users, testimonials, or community activity during onboarding.
- **UI**: User counts, testimonials, activity feeds
- **Best for**: Marketplace apps, community platforms

### 10. Demo Content
Prefilled sample data users can play with before creating their own. Used by Figma, Airtable, Frame.
- **UI**: Prefilled templates, editable example fields, switch between "Example" and "My Content"
- **Best for**: Analytics tools, creative software, data-heavy platforms

### 11. Simulation
Interactive demonstration under realistic conditions. Used by Intercom (test chatbot before going live).
- **UI**: Mimics real UX but with guidance overlays
- **Best for**: Complex products requiring customization, customer support tools

### 12. Self-Segmentation
Users pick their role/type to get tailored flow. Used by Notion, HubSpot, Mailchimp.
- **UI**: Segment buttons/cards, short explanations, customized follow-up screens
- **Best for**: Products serving multiple user types

### 13. Contextual Tooltips
Appear only when users hover/interact with specific elements. Non-blocking. Used by Trello, Airtable.
- **UI**: Hover/click-triggered tooltips, dismiss option, subtle animations
- **Best for**: Advanced features, hidden functionality

### 14. Gamification
Progress levels, badges, rewards for completing actions. Used by Duolingo, Asana.
- **UI**: Progress rings, level badges, reward animations, streaks
- **Best for**: Engagement-critical apps, learning platforms

---

## Micro-Interaction Patterns for Onboarding

### Attention & Discovery
- **Pulsating hotspots**: Grammarly uses small flashing beacon icons to draw attention to specific areas. Clicking reveals contextual information.
- **Subtle glow effects**: In dark themes, elements can glow softly to draw attention without harsh spotlight overlays.
- **Hover-over hotspot announcements**: Indicata uses hover-activated hotspots with integrated video to announce new features.

### Progress & Achievement
- **Animated progress bars**: Advance on task completion. Asana shows remaining tasks decreasing with each completion.
- **Level advancement**: Users start as beginners; completing tasks advances their level with visual feedback.
- **Strikethrough animations**: Structured (planning app) provides physical satisfaction of crossing out completed tasks.

### Celebration & Reward
- **Confetti burst**: Canva pops confetti after account setup completion. Brief, delightful, acknowledges effort.
- **Flying character animation**: Asana's unicorn flies across screen on task completion. Unexpected, whimsical.
- **Subtle congratulations**: Linear shows a quiet "Nice work" with a reminder of what was learned. No fireworks.

### Dark Theme Specifics
- **Glow > spotlight**: In dark UIs, subtle glows around highlighted elements feel more native than harsh white overlays.
- **Reduced contrast animations**: Dark themes benefit from animations that use accent colors rather than white flashes.
- **Depth through shadows**: Elements can float above the dark background using subtle box shadows and elevation.
- **Accent color consistency**: Use the app's accent color (not generic blue) for all attention-drawing elements.

---

## Table Stakes Features

*Every good onboarding has these. Missing any of these is a noticeable gap.*

### 1. Skip / Defer / Exit
- Every tour step must have a visible Skip button
- Users can exit at any time and resume later
- Progress is saved if they leave mid-flow
- Skip should never be punitive (no "Are you sure?" guilt modals)

### 2. Progress Indication
- Show "Step 2 of 5" or a progress bar
- Users need to know how long this will take before committing
- Progress should be visible but not dominant

### 3. Single-Purpose Screens
- Each onboarding screen does one thing
- No multi-column layouts with competing information
- Clear visual hierarchy: headline, supporting text, action

### 4. Dark/Light Mode Respect
- If the app supports dark mode, onboarding must also support it
- Ideally, let users choose theme early (Linear does this first)
- Never show a blinding white onboarding in a dark-themed app

### 5. Keyboard Accessibility
- All onboarding steps navigable via keyboard
- Enter to proceed, Escape to skip/close
- For developer tools: teach keyboard shortcuts during onboarding (Linear's approach)

### 6. Empty State Design
- When users land in the app with no data, show them what to do
- Illustration + single CTA + brief explanation
- Avoid "Nothing here yet" without actionable guidance

### 7. Fast Time to Value
- Users should accomplish something meaningful within 2-3 minutes
- The first "win" should be tangible (deployed app, created issue, sent message)
- Front-load value, defer configuration

### 8. Contextual Help
- Help content appears where and when relevant
- Tooltips on complex fields (API keys, configuration options)
- Links to deeper documentation for power users

### 9. Responsive & Performant
- Onboarding must not feel sluggish
- Transitions should be smooth (200-300ms)
- No loading spinners during the tour itself

### 10. Persistence
- Completed steps stay completed across sessions
- Users returning after days should see their progress
- Don't re-show dismissed onboarding elements

---

## Differentiators

*These are what separate great onboarding from merely adequate onboarding.*

### 1. Personality-First Welcome (Linear Model)
Instead of starting with "Enter your company name," start with something that shows you understand the user. Linear asks about dark/light mode first -- a choice that says "we care about your comfort." This is a deliberate craft decision, not a product requirement.

### 2. Learn-by-Doing, Not Learn-by-Reading
- Linear: "Press Cmd+K" with big keyboard buttons, then congratulates
- Figma: Animated tooltips show AND tell
- Intercom: Simulate your chatbot before going live
- The best onboarding makes users DO the thing, not read about the thing

### 3. Calm, Warm Language
- Linear: "Let's try it out" instead of "COMPLETE THIS STEP"
- Notion: Human-voiced empty states instead of "No content"
- Avoid corporate jargon, technical language, or overly enthusiastic copy
- The tone should match the product's personality

### 4. Smart Defaults & Auto-Detection
- Vercel auto-detects framework from repo
- Supabase pre-configures database settings
- Railway provisions services before user finishes reading the welcome toast
- Don't ask users to configure what you can infer

### 5. Frictionless Team Growth
- Linear: Domain-based auto-join, no invite flow needed
- Slack: Invite via link, no admin approval required for basic access
- Remove every possible barrier to team adoption

### 6. Test Mode / Sandbox
- Stripe: Full test mode with simulated data, switch to live when ready
- Supabase: Projects start with development credentials
- Let users experiment without consequences before committing

### 7. Celebratory Micro-Moments (Used Sparingly)
- Canva: Confetti after setup completion (acknowledges effort)
- Asana: Flying unicorn on first task completion (unexpected delight)
- Linear: Quiet "Nice work" (matches calm brand)
- Match the celebration to the brand. Not every app needs confetti.

### 8. Everboarding (Continuous Onboarding)
- New features get contextual introduction when users first encounter them
- Advanced capabilities revealed when usage patterns suggest readiness
- Onboarding is never "done" -- it's a living system
- "We noticed you haven't tried X yet" nudges after appropriate time

### 9. Demo Content / Prefilled State
- Show the product populated with realistic example data
- Let users edit/play with examples before creating their own
- Figma: Example design file. Airtable: Example base. Frame: Example project.
- Prevents the "blank canvas paralysis" problem

### 10. Documentation Pre-Filled with User Context
- Stripe: Code examples contain the user's actual API keys
- Supabase: Connection strings pre-populated with project details
- Copy-paste to working integration, zero manual substitution

---

## Anti-Features

*Things to deliberately NOT do. These are common patterns that feel productive but actively harm the user experience.*

### 1. DO NOT: Force a Full Tour Before Access
Users who are forced through a mandatory, unskippable tour before they can use the product will resent the experience. Always provide Skip/Exit. Let power users jump straight in. A forced 12-step tour is a 12-step path to closing the tab.

### 2. DO NOT: Ask for Everything Upfront
Long signup forms asking for company size, role, use case, phone number, and billing info before the user has seen the product. Progressive profiling (ask over time) beats front-loaded interrogation. Keep signup to name + email + password maximum.

### 3. DO NOT: Use Generic Tooltip Tours
Six tooltips on one screen pointing at every button saying "This is the Settings button" teaches nothing. Tooltips should explain WHY and WHEN, not label what's already labeled. If the UI needs tooltips to be understood, the UI needs redesigning.

### 4. DO NOT: Over-Celebrate
Confetti on every completed step. "AMAZING JOB!" after entering your name. Patronizing celebrations erode trust with professional users. Reserve celebration for genuinely meaningful moments (first deployment, first payment processed, project completion).

### 5. DO NOT: Show Onboarding on Every Visit
If a user has completed or dismissed onboarding, it must never reappear uninvited. Persistent "Have you tried our new feature?" banners that can't be permanently dismissed are hostile UX. Store completion state server-side, not just in browser cache.

### 6. DO NOT: Use Jargon in Onboarding Copy
"Configure your webhook endpoint for event-driven architecture" means nothing to a new user. Use plain language: "Tell us where to send notifications when things happen." Save technical language for documentation.

### 7. DO NOT: Block the UI During Tours
Full-screen overlays that prevent interaction with the actual product. The user should be able to poke around, click things, and explore -- even during a guided tour. The tour should enhance exploration, not replace it.

### 8. DO NOT: Ignore Return Visitors
Users who leave mid-onboarding and return should see their progress preserved, not be forced to restart. Users who completed onboarding months ago should not see the tour again. Users who skipped onboarding should have an easy way to access it later (Help menu, settings).

### 9. DO NOT: Use Video-Only Tutorials
Long video walkthroughs as the sole onboarding method. Videos can't be searched, skimmed, or referenced later. They become outdated quickly. Use video as a supplement to interactive onboarding, never as a replacement.

### 10. DO NOT: Onboard Features the User Doesn't Have Access To
Don't tour premium features to free users (feels like an upsell pitch). Don't show admin features to regular users. Segment onboarding by plan and role. Every step should be immediately actionable by the current user.

### 11. DO NOT: Use Carousels as the Primary Onboarding
Auto-advancing carousels with feature screenshots are the "banner blindness" of onboarding. Users swipe through without reading. If you must use a carousel, make it interactive (not just screenshots) and keep it to 3 slides maximum.

### 12. DO NOT: Forget Mobile Responsiveness
If users might sign up on mobile, the onboarding must work on mobile. Cramped tooltip overlays, tiny close buttons, and horizontal carousels that don't swipe properly are immediate abandonment triggers.

---

## Patterns Specifically Relevant to Agented

Given that Agented is a bot automation platform managing CLI tools, webhooks, GitHub events, schedules, and integrations, these patterns are most relevant:

### High-Priority Patterns for Agented

1. **Self-Segmentation** (Pattern #12): Ask users their primary use case -- CI/CD automation, code review bots, security scanning, custom workflows. Tailor the subsequent setup flow.

2. **Checklist with Progress** (Pattern #6): Multiple setup steps (create first bot, configure backend CLI, set up webhook, connect GitHub). Checklist gives structure and saves progress.

3. **Action-Oriented First Win** (Pattern #7): Get users to their first successful bot execution within 3 minutes. "Run your first bot" should be the single north-star CTA.

4. **Test/Sandbox Mode** (Stripe model): Let users trigger bot executions in a test mode before connecting to real repositories or webhooks.

5. **Theme Selection First** (Linear model): Dark-themed developer tool should confirm dark mode preference immediately. Signals craft.

6. **Keyboard Shortcut Teaching** (Linear model): If there are keyboard shortcuts, teach them interactively during onboarding.

7. **Empty State as Onboarding** (Notion model): Bot list, execution log, and conversation views should have instructive empty states with clear CTAs when no data exists.

8. **Smart Defaults** (Vercel/Railway model): Auto-detect installed CLI tools, pre-fill configuration based on detected environment, minimize manual entry.

9. **API Key / CLI Setup Guidance** (Stripe model): Show actual connection strings and CLI install commands with copy buttons. Pre-fill with the user's specific project context.

10. **Contextual Tooltips for Complex Config** (Pattern #13): Webhook URLs, cron expressions, environment variables, and GitHub event types all benefit from in-context explanation tooltips.

### Suggested Agented Onboarding Flow

```
Step 0: Welcome + Theme Selection (dark/light)
Step 1: "What do you want to automate?" (self-segmentation cards)
         - Code Review    - Security Scanning
         - CI/CD Tasks    - Custom Workflows
Step 2: Backend Detection (auto-detect installed CLIs, show status)
Step 3: Create First Bot (pre-filled based on Step 1 selection)
Step 4: First Execution (trigger a test run, show live SSE log)
Step 5: "You're set up!" (quiet celebration, next steps suggestions)
```

Each step: single purpose, Skip button, progress indicator, calm language.

---

## Sources

- [The onboarding Linear built without any AB Testing](https://www.growthdives.com/p/the-onboarding-linear-built-without) -- Deep dive into Linear's $1.25B onboarding philosophy
- [The 14 Types of Onboarding UX/UI Used by Top Apps](https://designerup.co/blog/the-14-types-of-onboarding-ux-ui-used-by-top-apps-and-how-to-copy-them/) -- Analysis of 200+ onboarding flows
- [SaaS Onboarding UX: Best Practices, Patterns & Examples (2026)](https://www.designstudiouiux.com/blog/saas-onboarding-ux/) -- Comprehensive SaaS onboarding guide
- [15 Onboarding Micro-Interactions to Inspire Your Design](https://userguiding.com/blog/onboarding-microinteractions) -- Micro-interaction patterns from Canva, Asana, Grammarly
- [Figma's animated onboarding flow](https://goodux.appcues.com/blog/figmas-animated-onboarding-flow) -- Figma tooltip and tour analysis
- [SaaS Onboarding Flows That Actually Convert in 2026](https://www.saasui.design/blog/saas-onboarding-flows-that-actually-convert-2026) -- Everboarding and progressive profiling patterns
- [Common user onboarding mistakes to avoid](https://productfruits.com/blog/common-user-onboarding-mistakes) -- Anti-patterns and mistakes
- [7 User Onboarding Mistakes and How to Avoid Them](https://medium.com/@userpilot/7-user-onboarding-mistakes-and-how-to-avoid-them-4a6b5328779c) -- Forced tours, long forms, missing skip buttons
- [Linear Start Guide](https://linear.app/docs/start-guide) -- Official Linear onboarding documentation
- [Vercel Getting Started](https://vercel.com/docs/getting-started-with-vercel) -- Vercel project wizard and deploy flow
- [Stripe Account Checklist](https://docs.stripe.com/get-started/account/checklist) -- Stripe progressive activation model
- [SuperSplat User Guide](https://github.com/playcanvas/supersplat/wiki/User-Guide) -- SuperSplat editor documentation
- [Railway Quick Start](https://docs.railway.com/quick-start) -- Railway's fast-deploy onboarding
- [UX Patterns for CLI Tools](https://www.lucasfcosta.com/blog/ux-patterns-cli-tools) -- CLI-specific UX patterns
