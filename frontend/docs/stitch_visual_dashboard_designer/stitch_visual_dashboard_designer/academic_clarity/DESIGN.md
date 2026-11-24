---
name: Academic Clarity
colors:
  surface: '#f8f9fa'
  surface-dim: '#d9dadb'
  surface-bright: '#f8f9fa'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f4f5'
  surface-container: '#edeeef'
  surface-container-high: '#e7e8e9'
  surface-container-highest: '#e1e3e4'
  on-surface: '#191c1d'
  on-surface-variant: '#424936'
  inverse-surface: '#2e3132'
  inverse-on-surface: '#f0f1f2'
  outline: '#727a64'
  outline-variant: '#c1cab0'
  surface-tint: '#416900'
  primary: '#416900'
  on-primary: '#ffffff'
  primary-container: '#84cc16'
  on-primary-container: '#315200'
  inverse-primary: '#91db2a'
  secondary: '#1f6c3a'
  on-secondary: '#ffffff'
  secondary-container: '#a4f1b2'
  on-secondary-container: '#24703e'
  tertiary: '#735c00'
  on-tertiary: '#ffffff'
  tertiary-container: '#deb400'
  on-tertiary-container: '#594700'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#acf847'
  primary-fixed-dim: '#91db2a'
  on-primary-fixed: '#102000'
  on-primary-fixed-variant: '#304f00'
  secondary-fixed: '#a6f4b5'
  secondary-fixed-dim: '#8bd79b'
  on-secondary-fixed: '#00210b'
  on-secondary-fixed-variant: '#005226'
  tertiary-fixed: '#ffe083'
  tertiary-fixed-dim: '#eec200'
  on-tertiary-fixed: '#231b00'
  on-tertiary-fixed-variant: '#574500'
  background: '#f8f9fa'
  on-background: '#191c1d'
  surface-variant: '#e1e3e4'
  card-background: '#ffffff'
  text-primary: '#111827'
  text-secondary: '#6b7280'
  border-subtle: '#e5e7eb'
  error-red: '#ef4444'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-md-mobile:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  title-sm:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  body-base:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-caps:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
  metadata:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 4px
  gutter: 24px
  margin-page: 32px
  card-padding: 20px
  stack-gap: 16px
---

## Brand & Style

The design system is engineered to foster focus and reduce cognitive load for students. It balances a **professional academic** foundation with a **friendly, modern** AI-first aesthetic. The goal is to evoke a sense of organized calm—transforming the potentially stressful experience of studying into a streamlined, encouraging workflow.

The visual style is **Modern Minimalist with Tactile accents**. It leverages generous whitespace, high-contrast surface separation, and soft geometry to create a "breathable" environment. By using white cards against a tinted off-white background, the system achieves depth through tonal layering rather than heavy shadows, maintaining a lightweight and clean feel suitable for long study sessions.

## Colors

The palette is optimized for readability and emotional "freshness."

- **Primary (#84cc16):** A vibrant Lime Green used for essential actions, progress indicators, and focus states. It signifies growth and active learning.
- **Surface & Background:** The main application utilizes an off-white mint tint (#f9fafb) to reduce screen glare. Interaction happens on pure white (#ffffff) cards to create clear containment.
- **Success & Warning:** Dark green (#166534) is reserved for completion states, while Light Yellow (#facc15) highlights urgent deadlines or "late" markers.
- **Typography:** Deep charcoal (#111827) provides maximum legibility for body text, while mid-range grays handle metadata and secondary descriptions.

## Typography

This design system uses **Inter** exclusively to ensure a clean, utilitarian, and highly legible experience across all Vietnamese diacritics.

- **Hierarchy:** Use `Display LG` for personalized welcomes (e.g., "Chào mừng, Hải Dương!"). `Headline MD` is used for primary section titles like "Môn học của tôi".
- **Functional Text:** `Body Base` is optimized for AI chat responses and long-form reading. `Label Caps` should be used sparingly for category tags or small uppercase headers.
- **Mobile Scaling:** Headlines scale down on mobile to prevent excessive line-breaking, ensuring titles remain readable on narrower viewports.

## Layout & Spacing

The layout philosophy follows a **Fluid Grid** with fixed maximum widths for content containers to maintain line-length readability.

- **Dashboard:** Uses a 12-column grid. On desktop, the primary workspace (Today's Tasks/Focus) spans 8 columns, while the sidebar/stats panel spans 4 columns.
- **The "Workspace" View:** Inspired by high-productivity research tools, this view uses a fixed 3-column split (20% Sources | 50% Chat | 30% Studio) to facilitate multi-tasking without switching tabs.
- **Rhythm:** A consistent 24px gutter creates "Thoáng" (breathable) spacing. Vertical stacks of cards should use a 16px gap to maintain a clear relationship between items.

## Elevation & Depth

Hierarchy is established through **Tonal Layering** rather than traditional shadows.

- **Level 0 (Background):** The muted #f9fafb surface.
- **Level 1 (Cards):** Pure white surfaces with a very subtle `0px 2px 4px rgba(0,0,0,0.04)` shadow and a 1px `border-subtle` outline. This makes cards appear to rest gently on the background.
- **Level 2 (Interactive/Active):** On hover, cards may transition to a light primary tint background or increase shadow density slightly to indicate interactivity.
- **Modals:** Use a 40% opacity dark overlay to dim the background, pushing the modal surface to the highest visual plane.

## Shapes

The design system utilizes **Rounded (0.5rem / 8px - 12px)** geometry to maintain a friendly, approachable feel.

- **Standard Cards:** Use a 12px radius (`rounded-lg` in this system) to encapsulate content comfortably.
- **Action Buttons:** Use a full "Pill" shape (32px+) to distinguish them clearly from layout containers and cards.
- **Input Fields:** Use 8px corners to balance the structure of the text within.
- **Decorative Elements:** Progress bars and tags should always be fully rounded (pill-shaped).

## Components

### Buttons
- **Primary:** Pill-shaped, #84cc16 background with white text. High contrast and bold.
- **Secondary:** White background with a 1px #e5e7eb border and text-secondary.
- **Ghost:** No border or background, used for low-priority actions like "Xem thêm" (See more).

### Cards
- Every distinct piece of information (a course, a task, an AI suggestion) must be wrapped in a white card. 
- **Empty State Cards:** Use a dashed border and centered "plus" icon to encourage user action (e.g., "Thêm môn học").

### Input Fields & Search
- Inputs should have a subtle gray border that turns Primary Green on focus.
- Search bars in the navigation should include a "Kính lúp" (magnifying glass) icon and placeholder text like "Tìm kiếm tài liệu...".

### Progress Indicators
- Use circular "ring" charts for subject mastery percentages.
- Use horizontal bars for task completion within a course. Both should utilize the primary lime green for the "filled" state.

### AI Studio Components
- **Flashcards:** Specialized small cards with a "flip" metaphor.
- **Chat Bubbles:** AI responses should have a very light gray background to distinguish them from user prompts, which are plain text or right-aligned.