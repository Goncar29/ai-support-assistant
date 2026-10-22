# Aurora UI redesign — design

Date: 2026-10-22. Scope: frontend only (`frontend/`). The backend and its SSE contract stay unchanged.

## Goal

Replace the plain chat UI with a modern, clearly "AI" interface that works on phones, tablets and desktops. Users can talk to the assistant by text or by voice. The interface follows the visitor's language (English or Spanish) and lets them switch.

## Decisions

| Topic | Decision |
|---|---|
| Visual direction | **Aurora dark**: a near-black background (`#0b0b14`) with soft violet (`#7c3aed`) and cyan (`#06b6d4`) glows and a pink accent (`#ec4899`). Assistant bubbles are glass: translucent white fill, 1px light border, backdrop blur. User bubbles use a violet→cyan gradient. |
| Cursor effects | **Spotlight + border glow**. A radial violet/cyan halo follows the pointer over the background, and the borders of bubbles, chips and buttons light up where the pointer is. |
| Layout | **Full-screen chat**: a header, a centered conversation and a composer at the bottom. With no messages, a welcome screen shows a large orb, a greeting and suggestion chips. |
| Orb | **Reactive plasma**: three blurred color blobs move inside a sphere, each on its own timing, blended with `mix-blend-mode: screen`. Its speed and color reflect the agent state (see "Orb states"). |
| Voice input | **Web Speech API** (`SpeechRecognition`), free and in the browser. At rest the mic button shows a thin-line SVG mic. While listening it morphs into 5 equalizer bars driven by the real voice level, two green ripples pulse outward, and the orb switches to its green `listening` state. |
| Language | **Bilingual, auto-detected, user-selectable**: an EN/ES toggle in the header. |
| Styling approach | **Plain CSS with custom properties** and small React components. No new runtime dependencies. |

## Orb states

`orbState(streaming, activity, lastReplyText, listening)` is a pure function:

| Condition | State | Look |
|---|---|---|
| `listening` | `listening` | green/cyan/violet blobs; scale and glow follow the voice level |
| `streaming` and (`activity` set, or no reply text yet) | `thinking` | blobs about 3× faster, cyan glow |
| `streaming` and reply text arriving | `speaking` | blobs about 2× faster, a 0.45 s pulse, pink glow |
| otherwise | `idle` | slow blobs, violet glow |

`listening` takes precedence over every other state.

## Components

All components live in `frontend/src/components/`, one per file, and are presentational unless noted otherwise.

- `App`: the container. It wires `useChat`, `useLocale`, `useSpeechInput` and `usePointerGlow`, and shows `Welcome` or `MessageList`.
- `ChatHeader`: a small orb, the name "Support AI", a "demo" badge and the EN/ES toggle.
- `Orb`: props `state` and `size` (`"sm" | "lg"`), plus an optional `level` (0..1) used while listening.
- `Welcome`: a large orb, a greeting and suggestion chips. Clicking a chip sends its text. Chips per locale:
  - EN: "How long does shipping take?", "How do refunds work?", "I forgot my password", "Open a ticket"
  - ES: "¿Cuánto tarda el envío?", "¿Cómo funcionan los reembolsos?", "Olvidé mi contraseña", "Abrir un ticket"
- `MessageList`: the bubbles, plus an activity line under the last message (for example "Searching the FAQ…"). It keeps `aria-live="polite"` and auto-scrolls to the newest message.
- `Composer`: the input, the mic button (hidden when speech is unsupported) and the send button (SVG arrow). Send is disabled while streaming or when the input is empty. Enter sends.
- `MicButton`: the mic SVG ↔ 5 bars morph and the ripples. Each bar height is `level × profile[i] × wobble`, with the profile taller in the middle and a small sine wobble per bar.

## Hooks and modules

- `hooks/usePointerGlow.ts`: listens to `pointermove` on the page and writes `--x`/`--y` (page) and `--ex`/`--ey` (per `.glow` element) in a `requestAnimationFrame`. It never triggers React re-renders. It is active only when `(hover: hover)` matches and `prefers-reduced-motion` does not.
- `hooks/useSpeechInput.ts`:
  - Returns `{ supported, listening, level, transcript, error, start, stop }`.
  - It wraps `SpeechRecognition` (or `webkitSpeechRecognition`) with `interimResults = true` and `lang` taken from the locale (`en-US` / `es-ES`).
  - The level comes from `getUserMedia({ audio: true })` and an `AnalyserNode` (RMS of the time-domain data, clamped to 0..1).
  - On end, the final transcript stays in the input for review; nothing is sent automatically.
  - Every track, audio context and recognition is stopped on `stop`, on end and on unmount.
  - A denied microphone permission sets `error`, which the UI shows as a short dismissible notice.
- `i18n/messages.ts`:
  - `en` and `es` dictionaries with the same keys: placeholder, send/mic/stop labels, welcome greeting, chips, tool activity labels, the generic error, the incomplete-stream error, the rate-limit message (singular and plural seconds), the mic-permission error and the speech-privacy tooltip.
- `i18n/useLocale.ts`:
  - Locale resolution order: the stored choice in `localStorage` (`ui-locale`), then `navigator.language` starting with `es`, then `en`.
  - Returns `{ locale, setLocale, t }`.
  - Updates `<html lang>`.
  - `localStorage` access is wrapped in try/catch.
- Existing modules:
  - `useChat` and `chatStream` stop hard-coding English strings. `useChat` exposes the raw tool name; the UI translates it.
  - The rate-limit error keeps its seconds value so the UI formats the message per locale.

## Styles

- `styles/theme.css`: design tokens on `:root` (colors, glow colors, radii, spacing, font stack `Inter, system-ui, sans-serif`) and the base page background with two fixed aurora blobs.
- `styles/effects.css`: the spotlight layer, the `.glow` border mask, orb keyframes and states, mic ripples and bars.
- `styles/layout.css`: header, conversation column, composer, welcome and chips.
- The current `App.css` is removed.

## Responsive

- Mobile first.
- The conversation column is at most 760px wide on desktop. On phones it is full width with 16px side gutters.
- The page height uses `100dvh`, so the mobile keyboard does not break the layout. The composer sticks to the bottom with `padding-bottom: env(safe-area-inset-bottom)`.
- The chip row scrolls horizontally on narrow screens. Nothing causes horizontal page scroll.
- Tap targets are at least 44px.
- Verified in a real browser (ego-browser) at 375px, 768px and 1280px widths.

## Accessibility

- `prefers-reduced-motion: reduce`:
  - The orb shows a static gradient.
  - The ripples, bar wobble and spotlight are off.
  - The border glow stays static.
- The pointer effects run only on `(hover: hover)` devices. Touch devices get the same layout without them.
- Every icon button has a localized `aria-label`. The mic button exposes `aria-pressed` while listening.
- Focus is visible (a violet outline). Text meets WCAG AA contrast on the dark background.

## Error handling

- Chat errors (network, rate limit, incomplete stream) appear as a localized alert above the composer, as they do today.
- Speech unsupported: no mic button.
- Microphone permission denied: a localized notice, and the orb returns to `idle`.
- Recognition error mid-session: stop listening and keep any partial transcript in the input.

## Testing

Vitest with jsdom, plus the existing tests:

- `orbState`: each of the 4 states, and `listening` taking precedence.
- `useLocale`: a stored choice beats `navigator.language`; `es-AR` resolves to `es`; an unknown language falls back to `en`; `setLocale` persists and updates `<html lang>`; a throwing `localStorage` falls back without crashing.
- `useSpeechInput`: with a fake `SpeechRecognition`:
  - Interim results update `transcript`.
  - `stop`/end leaves the final transcript.
  - `supported` is false without the API.
  - A permission error sets `error`.
  - Unmount stops recognition.
- `useChat` / `chatStream`: the existing tests, updated so they assert tool names and error data instead of English strings.
- `Composer`: Enter sends; send is disabled while streaming or when the input is empty; the mic button is hidden when speech is unsupported.
- E2E on the deployed demo with ego-browser: welcome and chips, an FAQ answer, ticket creation, the EN/ES toggle, and layout at the three widths.

## Out of scope

- Backend changes.
- Text-to-speech (the assistant speaking).
- A light theme.
- Conversation history persistence.
