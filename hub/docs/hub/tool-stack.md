# Agent Tool Stack

> Hardened tooling specification for hub agents across voice, browser automation, visual auditing, web research, PDF extraction, GPU compute, deployment verification, and UI design. Derived from post-mortems, runbooks, and hackathon retros.
>
> **Core Rule:** No new paid spend without the lead. Every paid service is tagged `[Proposal: Paid]`. Free and local tools are tagged `[Free / Local]`.

---

## 1. Realtime Voice (Interactive Live Voice)

*Interactive, bidirectional speech-to-speech for web, phone, and conversational apps.*

* **Default Tool:** **OpenAI Realtime API (`gpt-realtime-2.1` / `gpt-realtime-2.1-mini`) with voice `marin`**
* **Why:** Delivers single-stream, low-latency (~300 ms) speech-to-speech over WebSockets / WebRTC. Eliminates the compound latency and failure modes of cascading Whisper STT → LLM generation → TTS synthesis. Voice `marin` offers warm, natural, human-grade inflection without robotic cadences.
* **Setup & Invocation:**
  * Env: `OPENAI_API_KEY`
  * Protocol: WebRTC via client-side ephemeral token (`POST https://api.openai.com/v1/realtime/sessions`) or server WebSocket (`wss://api.openai.com/v1/realtime?model=gpt-realtime-2.1`).
  * Session Config:
    ```json
    {
      "model": "gpt-realtime-2.1",
      "voice": "marin",
      "modalities": ["audio", "text"],
      "instructions": "Call phone tools before answering status questions; never guess app state."
    }
    ```
* **Fallback Chain:**
  1. *OpenAI Realtime Mini (`gpt-realtime-2.1-mini`, voice `marin`)*: Lower cost ($0.02–$0.05/min), lower latency.
  2. *Gemini Multimodal Live API (`gemini-2.0-flash-exp` / `gemini-2.5-flash`)*: Bidirectional WebSocket audio/video stream.
  3. *ElevenLabs WebSocket Streaming*: Named fallback only (`eleven_turbo_v2_5`).
  4. *Browser Web Speech API (`SpeechRecognition` + `speechSynthesis`)*: Zero-cost offline fallback.
* **Operational Failure Resolved:**
  * *Murmur OS (7 Nov 2026 Hackathon Retro):* ElevenLabs API returned `500 Internal Server Error`, `401 Unauthorized`, and hit daily character caps right before demo freeze, stalling test runs.
  * *Murmur OS Voice Bleed:* Realtime model answered from hallucinated memory ("I can't see nearby places", "all clear" with unread mail) instead of triggering device tools. Persona prompt must enforce tool calls first.
* **Source & Pricing (Nov 2026):**
  * `[Proposal: Paid]` OpenAI Realtime API: https://platform.openai.com/docs/guides/realtime
  * Audio input: $32.00 / 1M tokens ($0.40 / 1M cached). Audio output: $64.00 / 1M tokens. Mini model: Audio input $10.00 / 1M, output $20.00 / 1M. Estimated $0.06–$0.11 / min (flagship), $0.02–$0.05 / min (mini).

---

## 2. Film & Scripted Voice (Narration & Fixed TTS)

*High-fidelity text-to-speech for product walkthroughs, film scripts, and pre-recorded UI lines.*

* **Default Tool:** **OpenAI Audio Speech API (`tts-1` / `tts-1-hd`) with voice `marin`**
* **Why:** High availability, deterministic pronunciation, generous rate limits, and zero daily lockout risk during rehearsal runs. Voice `marin` provides clean, warm, broadcast-ready narration without the artifacting or drift common under heavy load.
* **Setup & Invocation:**
  * Env: `OPENAI_API_KEY`
  * CLI / cURL:
    ```bash
    curl https://api.openai.com/v1/audio/speech \
      -H "Authorization: Bearer $OPENAI_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{"model": "tts-1", "voice": "marin", "input": "Murmur OS verifies every step on your screen."}' \
      --output narration.mp3
    ```
  * In Node / Browser: Pre-warm fixed lines into a hash-indexed cache (`public/voice/tts-cache.js`).
* **Fallback Chain:**
  1. *OpenAI `tts-1` with voice `alloy` / `nova`*: Secondary voice options within the same endpoint.
  2. *ElevenLabs API (`eleven_multilingual_v2`, voice `Rachel` / `Adam`)*: Named fallback when OpenAI TTS is unavailable.
  3. *Edge-TTS (`edge-tts` CLI)*: `[Free / Local]` Zero-cost Microsoft Azure neural TTS runner with no API keys (`edge-tts --voice en-US-ChristopherNeural --text "..." --write-media out.mp3`).
  4. *Web Speech Synthesis (`window.speechSynthesis`)*: Client-side local engine.
* **Operational Failure Resolved:**
  * *Murmur OS (7 Nov 2026):* `test/sound.test.js` had to catch repeated ElevenLabs `500` and `429` errors; character quota exhaustion blocked narration builds.
  * *Demo Film (26 Oct 2026, T-793):* Voice tone drifted between takes, creating mismatched audio splices across scene cuts.
* **Source & Pricing (Nov 2026):**
  * `[Proposal: Paid]` OpenAI Audio API: https://platform.openai.com/docs/guides/text-to-speech
  * `tts-1`: $15.00 / 1M characters ($0.000015 / character). `tts-1-hd`: $30.00 / 1M characters.
  * `[Free / Local]` Edge-TTS: https://github.com/rany2/edge-tts (Free, zero API key, MIT license).

---

## 3. Browser Automation & Headless Web Testing

*Automated end-to-end testing, responsive viewport verification, WebAudio validation, and UI interaction.*

* **Default Tool:** **Playwright (`@playwright/test` / `playwright` core)**
* **Why:** Complete control over mobile viewports, high-DPI scaling, browser context isolation, and DevTools protocol. Unlike raw headless Chrome flags, Playwright advances `requestAnimationFrame`, handles `scroll-behavior: auto`, triggers WebAudio gesture unlocks, and waits on network idle and DOM stability.
* **Setup & Invocation:**
  * Pinned install: `~/.npm/_npx/e41f203b7505f1fb/node_modules/playwright`
  * Execution:
    ```javascript
    import { chromium } from 'playwright';
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({
      viewport: { width: 390, height: 844 }, // Mobile test standard
      deviceScaleFactor: 2
    });
    ```
* **Fallback Chain:**
  1. *Puppeteer Core (`puppeteer-core` with system Chromium)*: Direct CDP driver.
  2. *Same-origin iframe probe via Headless Chromium*: As documented in `runbooks/headless-browser-css-checks.md`.
* **Operational Failure Resolved:**
  * *`runbooks/headless-browser-css-checks.md`:* Raw `chrome --headless=new --window-size=390` clamped to 500px min layout viewport, falsely reporting horizontal overflow. `--virtual-time-budget` never advanced `requestAnimationFrame`, reporting parallax as `0.00px`. Smooth scrolling silently hung `scrollIntoView`.
  * *WeasyPrint Failure:* WeasyPrint reported components broken because it does not resolve Tailwind screen media queries (`@media (min-width: ...)`).
* **Source & Pricing (Nov 2026):**
  * `[Free / Local]` Playwright: https://playwright.dev / https://github.com/microsoft/playwright (Apache 2.0, open source, free).

---

## 4. Screenshots & Visual Auditing

*Pixel-accurate full-page and element image captures, design-rubric scoring, and dark/light mode checks.*

* **Default Tool:** **Playwright Screenshot Engine with sRGB Enforcement (`--force-color-profile=srgb`)**
* **Why:** Prevents Display P3 wide-gamut hex shifts on macOS/retina displays, automatically awaits `document.fonts.ready`, supports `animations: 'disabled'` to eliminate halfway-faded opacity bugs, and captures full-length mobile views without viewport inflation.
* **Setup & Invocation:**
  * CLI helper: `shot-scraper` (Simon Willison's tool, wrapping Playwright):
    ```bash
    shot-scraper http://localhost:3000 -w 390 -h 844 --retina -o mobile.png --wait 500
    ```
  * Playwright script:
    ```javascript
    await page.screenshot({
      path: 'screenshot.png',
      fullPage: true,
      animations: 'disabled'
    });
    ```
* **Fallback Chain:**
  1. *`shot-scraper` CLI*: Fast, zero-boilerplate terminal CLI for quick URL/selector captures.
  2. *Headless Chromium CLI*: `"$CHROME" --headless=new --disable-gpu --force-device-scale-factor=1 --force-color-profile=srgb --screenshot=out.png "$URL"`.
* **Operational Failure Resolved:**
  * *`runbooks/screenshot-colour-p3-shift.md`:* Hex colors sampled from screenshots drifted by up to 8% in channel values due to uncalibrated Display P3 profile conversion.
  * *`runbooks/website-content-invisible.md`:* Screenshots captured blank sections because elements with scroll-triggered fade animations (`opacity: 0`) were captured before scroll events fired.
* **Source & Pricing (Nov 2026):**
  * `[Free / Local]` shot-scraper: https://github.com/simonw/shot-scraper (Apache 2.0, open source, free).
  * `[Free / Local]` Playwright Screenshot API: https://playwright.dev/docs/screenshots (Free).

---

## 5. Web Search & Documentation Fetch

*Extracting current API documentation, error diagnoses, and real-time facts without hallucination.*

* **Default Tool:** **Google Search API / Antigravity Native Search + Jina Reader (`r.jina.ai`) for Markdown Fetch**
* **Why:** Bypasses LLM training cutoff dates. Jina Reader transforms arbitrary documentation URLs into clean, token-efficient Markdown without HTML boilerplate, cookie banners, or navigation scripts.
* **Setup & Invocation:**
  * Search: Native agent search tool or Tavily API (`TAVILY_API_KEY`).
  * Direct URL Fetch to Markdown: Prepend `https://r.jina.ai/` with standard `curl`:
    ```bash
    curl -sL --max-time 15 "https://r.jina.ai/https://docs.anthropic.com/en/docs/skills" > doc.md
    ```
* **Fallback Chain:**
  1. *`trafilatura` CLI*: Local Python text/content extraction library (`uvx trafilatura -u "$URL"`).
  2. *`curl -sL --max-time 15 "$URL"` piped to `pandoc -f html -t markdown`*: Local standard tool.
  3. *Brave Search API*: Privacy-first web search API fallback.
* **Operational Failure Resolved:**
  * *`runbooks/hubfetch-agent-hung.md`:* Unbounded HTTP fetches hung agent subshells when network drops occurred.
  * *DevDay & Murmur API Mismatches:* Outdated assumptions on API payloads (e.g. enum arrays vs objects, Node 24 read-only properties) caused runtime 400s; verified fresh documentation eliminates spec guesswork.
* **Source & Pricing (Nov 2026):**
  * `[Free / Local]` Jina Reader: https://jina.ai/reader (Free tier: 20 RPM without key; 10M free tokens at 500 RPM with free key).
  * `[Free / Local]` Trafilatura: https://trafilatura.readthedocs.io (GPL 3.0, free local Python).
  * `[Proposal: Paid]` Tavily Search API: https://tavily.com (1,000 free searches/month; paid tiers for heavy search).

---

## 6. PDF Inspection & Document Extraction

*Extracting tables, rules, and research papers from judge packs and design guides.*

* **Default Tool:** **`pdftotext -layout` (Poppler) for text/tables; Gemini Multimodal (`gemini-2.5-flash`) for slides/diagrams**
* **Why:** `pdftotext -layout` retains spatial indentation and multi-column alignment without Python library overhead. Gemini Multimodal reads complex visual PDFs (charts, slide decks, architectural diagrams) with optical and structural understanding.
* **Setup & Invocation:**
  * Text/Tables CLI:
    ```bash
    pdftotext -layout input.pdf - | head -n 100
    ```
  * Python structured extraction: `pdfplumber` (`uvx --with pdfplumber python -c 'import pdfplumber; ...'`).
* **Fallback Chain:**
  1. *`pdfplumber`*: Detailed bounding-box and table-grid extractor.
  2. *PyMuPDF (`fitz`)*: High-speed PDF rendering and text parsing.
  3. *`pypdf`*: Lightweight metadata and raw text dump.
* **Operational Failure Resolved:**
  * *Biocomputing & Hackathon Briefs:* Naive stream extractors merged multi-column judging rubrics into unreadable interleaved sentences, obscuring scoring criteria.
* **Source & Pricing (Nov 2026):**
  * `[Free / Local]` Poppler Utils: https://poppler.freedesktop.org (GPL, standard Linux package `poppler-utils`).
  * `[Free / Local]` pdfplumber: https://github.com/jsvine/pdfplumber (MIT, free open source).

---

## 7. GPU Rendering & 3D Workflows

*Hardware-accelerated 3D tile rendering, Gaussian splat processing, and high-performance WebGL builds.*

* **Default Tool:** **GCP Cloud GPU Worker (NVIDIA L4 / T4) or Serverless GPU (Modal / RunPod)**
* **Why:** Software OpenGL (SwiftShader / Mesa) on CPU VMs cannot render complex WebGL / 3D tiles, producing black frames or severe lag. Dedicated cloud GPUs provide deterministic rendering benchmarks and hardware video encoding.
* **Setup & Invocation:**
  * Long-running GPU commands must execute detached with explicit status polling in bounded 9-minute slices (avoiding background hang bugs):
    ```bash
    setsid nohup bash -c 'render-job > render.log 2>&1; echo $? > render.exit' >/dev/null 2>&1 &
    # Foreground poll loop:
    timeout 540 bash -c 'until [ -e render.exit ]; do sleep 15; done'; cat render.exit
    ```
* **Fallback Chain:**
  1. *Modal Labs Serverless GPU (`modal run ...`)*: Instant serverless containerized GPU runs.
  2. *RunPod Serverless*: On-demand container GPU instances.
  3. *Headless Chrome SwiftShader (`--use-gl=swiftshader`)*: Strict geometry smoke tests ONLY; never for visual sign-off.
* **Operational Failure Resolved:**
  * *Strata Hackathon (1 Nov 2026, Lesson 27 & 36):* Software GL rendered black/stale frames (15 min lost). 20 builders on 8-core CPU VM pushed load to 17, swinging render timings from 5s to 33s. Timings must be measured on GPU.
  * *`runbooks/subagent-misses-background-notice.md`:* `build-gpu` sub-agent launched a background job and sat idle for 2.5 hours waiting for a completion notice that arrived only after turn end.
* **Source & Pricing (Nov 2026):**
  * `[Proposal: Paid]` GCP Compute Engine L4: ~$0.70 / hour (spot/preemptible ~$0.30/hr).
  * `[Proposal: Paid]` Modal Labs: https://modal.com ($0.00022/sec for T4, ~$0.80/hr for L4).

---

## 8. Deploy Checks & Health Probes

*Validating live host availability, API keys, provider mode, and author attribution before handoff.*

* **Default Tool:** **Automated Post-Deploy Probe (`curl` + `jq` on `/health`) + `hub ship-check`**
* **Why:** Guarantees that production is live, not falling back to offline demo mocks, and that git author configuration conforms to repository standards.
* **Setup & Invocation:**
  * Probe command:
    ```bash
    curl -fsS --retry 3 --retry-delay 2 "https://$HOST/health" | \
      jq -e '.status == "ok" && .provider == "live"' >/dev/null || \
      { echo "Deploy verification failed: provider is not live"; exit 1; }
    ```
  * Pre-ship check: `hub ship-check`
* **Fallback Chain:**
  1. *Playwright Headless Smoke Test*: Load production URL and assert zero console/page errors.
  2. *Direct HTTP Status Check*: `curl -I -sS "https://$HOST" | head -n 1`.
* **Operational Failure Resolved:**
  * *Murmur OS (7 Nov 2026):* New worktrees deployed without `.env`, silently booting on offline demo providers with audio disabled. Deploy scripts must refuse when `/health` fails to report `"provider": "live"`.
  * *`runbooks/vercel-deploy-blocked.md`:* Vercel silently blocked deployments for months because git-author identity was not linked to the team organization.
  * *Strata (Lesson 34):* Subshell pipes masked non-zero exit codes during builds (`set -eo pipefail` required).
* **Source & Pricing (Nov 2026):**
  * `[Free / Local]` Built-in `curl`, `jq`, and hub CLI.

---

## 9. Design References, UI Inspiration & Design System Linting

*Ensuring clean typography, cohesive palette harmony, accessible contrast, and eliminating the generic "AI template" look.*

* **Default Tool:** **Impeccable CLI (`impeccable detect` / `impeccable doctor`) + Refactoring UI Design Rules**
* **Why:** Programmatically enforces 4px/8px spacing grids, optical hierarchy, single-accent color rules, and WCAG AA contrast. Replaces arbitrary CSS styling with tested design system tokens.
* **Setup & Invocation:**
  * Pinned binary: `~/.local/share/impeccable/0.1.18/impeccable`
  * Execution:
    ```bash
    ~/.local/share/impeccable/0.1.18/impeccable detect
    ~/.local/share/impeccable/0.1.18/impeccable doctor
    ```
  * Primitives: Unstyled Radix UI / Headless UI primitives paired with Tailwind CSS.
* **Fallback Chain:**
  1. *Lighthouse CLI*: Automated accessibility and contrast audit (`lighthouse --chrome-flags="--headless" --output=json`).
  2. *Manual contrast verification*: `getComputedStyle` luminance ratio calculation script.
* **Operational Failure Resolved:**
  * *Hackathon Retros (Night Shift Lesson 1, DevDay Lesson 25):* "We lose on the story, not the build. The demo had no sparkle." "Judges really want something that looks pretty... make it pretty first, then go from there."
  * *`runbooks/tailwind-layer-order.md`:* Unlayered CSS classes overriding Tailwind utility classes.
* **Source & Pricing (Nov 2026):**
  * `[Free / Local]` Impeccable: https://github.com/pbakaus/impeccable (Open source, pinned binary 0.1.18).
  * `[Free / Local]` Lighthouse CLI: https://github.com/GoogleChrome/lighthouse (Apache 2.0).

---

## 10. Out-of-Band Team Alerting & WhatsApp

*Direct push messaging to the lead's mobile device for critical blockers, deployments, and hackathon milestones.*

* **Default Tool:** **`hubwa send` (Wassist WhatsApp Bridge)**
* **Why:** Reaches the lead immediately on their phone lockscreen during live events without requiring them to watch terminal multiplexers. Features a durable persistent queue that auto-delivers once 24-hour interaction windows re-arm.
* **Setup & Invocation:**
  * CLI: `hubwa send "T-1047 deployed to live host; all 193 smoke tests green."`
  * Secrets: `~/.config/hub/wassist.key`, `~/.config/hub/wassist.agent`
* **Fallback Chain:**
  1. *`hubmsg Zeus "<message>"`*: Internal hub durable inbox messaging.
  2. *System Notification*: `notify-send` / terminal bell.
  3. *Email / Webhook trigger*: Standard curl POST to alerting webhook.
* **Operational Failure Resolved:**
  * *Murmur OS (7 Nov 2026):* 13 deploy rounds took ~4 minutes each with the lead constantly asking "is it deployed yet". Automated WhatsApp alerts keep the lead informed in real time.
  * *`runbooks/whatsapp-send-fails.md`:* Handling 24-hour session window closures gracefully via persistent held queues.
* **Source & Pricing (Nov 2026):**
  * `[Proposal: Paid]` Wassist: https://wassist.app (WhatsApp API provider).

---

## 11. Command Execution & Subshell Sandboxing

*Safe, deterministic execution of long-running, noisy commands without terminal buffer overflow or silent hanging.*

* **Default Tool:** **`hub sh -- <command>`**
* **Why:** Automatically truncates output to the last 20 lines on-screen while piping the complete output to a persistent disk log (`~/hub/logs/sh/<agent>/...`). Guarantees exit code propagation and prevents terminal buffer flooding.
* **Setup & Invocation:**
  * CLI:
    ```bash
    hub sh -- npm test
    hub sh -- timeout 300 make check
    ```
* **Fallback Chain:**
  1. *`tee` with pipefail*: `set -o pipefail; command 2>&1 | tee output.log`.
* **Operational Failure Resolved:**
  * *Strata (Lesson 34):* Silent failure hiding in multi-command pipelines.
  * *`runbooks/pytest-looks-hung-cobc-compiles.md`:* Agents killing compiling tasks under the mistaken assumption that 0% CPU meant deadlocks.
* **Source & Pricing (Nov 2026):**
  * `[Free / Local]` Hub CLI built-in.

---

## Tool Stack Summary Matrix

| Need | Default Tool | Cost / License | Fallback | Primary Resolved Failure |
|---|---|---|---|---|
| **Realtime Voice** | OpenAI Realtime (`gpt-realtime-2.1`, voice `marin`) | `[Proposal: Paid]` ($0.06–$0.11/min) | Gemini Live / ElevenLabs WebSocket | Murmur OS ElevenLabs 500/401 downtime |
| **Scripted Voice / TTS** | OpenAI Audio Speech (`tts-1`, voice `marin`) | `[Proposal: Paid]` ($15/1M chars) | Edge-TTS (Free) / ElevenLabs | Quota exhaustion during film rehearsal |
| **Browser Automation** | Playwright (`chromium`) | `[Free / Local]` (Apache 2.0) | Chrome same-origin probe | Headless Chrome rAF / viewport clamp |
| **Screenshots & Audits** | Playwright + sRGB (`shot-scraper`) | `[Free / Local]` (Apache 2.0) | Headless Chrome CLI | P3 hex shift & opacity:0 reveal bugs |
| **Web Search & Fetch** | Google Search + Jina Reader (`r.jina.ai`) | `[Free / Local]` (Free tier) | Trafilatura / Brave Search | Unbounded fetch hangs & stale API cuts |
| **PDF Extraction** | `pdftotext -layout` + Gemini Multimodal | `[Free / Local]` (GPL) | `pdfplumber` / PyMuPDF | Scrambled multi-column judge rubrics |
| **GPU Rendering** | Cloud GPU (NVIDIA L4 / T4, Modal/RunPod) | `[Proposal: Paid]` (~$0.30–$0.80/hr) | Headless Chrome SwiftShader | CPU VM load 17 & black WebGL renders |
| **Deploy & Health** | `curl` `/health` probe + `hub ship-check` | `[Free / Local]` | Playwright smoke test | Murmur OS silent offline demo fallbacks |
| **UI Design & Lint** | Impeccable CLI + Refactoring UI tokens | `[Free / Local]` | Lighthouse CLI | Generic AI clip-art & low visual polish |
| **Team Alerting** | `hubwa send` (Wassist WhatsApp) | `[Proposal: Paid]` | `hubmsg` internal queue | 13 deploy blind-spots during hackathons |
| **Command Execution** | `hub sh -- <cmd>` | `[Free / Local]` | `tee` with pipefail | Hidden subshell exit codes & log spam |
