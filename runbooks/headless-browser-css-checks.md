# Checking CSS and layout without a browser you can drive

**Symptom.** You need to know what a page actually looks like — is it overflowing, is
content hidden, where does an anchor land — and every measurement you take disagrees with
what the user sees. On Refinery this produced three separate wrong conclusions in one
session, including telling the user two components were broken when they were already
fixed and live.

## What works

Windows Chrome, from WSL, at `/mnt/c/Program Files/Google/Chrome/Application/chrome.exe`:

```bash
"$CHROME" --headless=new --disable-gpu --force-device-scale-factor=1 \
  --virtual-time-budget=12000 --screenshot="C:\\Windows\\Temp\\x.png" "$URL"
"$CHROME" --headless=new --virtual-time-budget=12000 --dump-dom "$URL"   # DOM after JS
```

**To measure rather than eyeball, serve a probe from the site's own origin.** Put an HTML
file in `website/public/`, load it from the same host, and iframe the site inside it. Same
origin means you can scroll the iframe and read `getBoundingClientRect` and
`getComputedStyle`. A `file://` wrapper cannot: cross-origin blocks `contentDocument`.
Report results by setting `document.title` and reading it back with `--dump-dom`. Delete
the probe before committing.

## Five traps, each of which produced a wrong answer

1. **Minimum window width.** `--window-size=390` still gives a ~500px layout viewport, so a
   390px screenshot is a crop of a 500px layout and everything looks falsely cut off at the
   right. Use a 390px-wide **iframe** inside a wider wrapper instead. Check
   `documentElement.clientWidth` before believing any narrow-viewport result.
2. **`requestAnimationFrame` never fires** under `--virtual-time-budget`. A probe that
   awaits a frame hangs and produces no output at all, and any rAF-driven value reads as
   its initial value — which is why every parallax measurement came back `0.00px`. Use
   `setTimeout`, which does advance.
3. **Smooth scrolling never completes.** `scrollTo` and `scrollIntoView` silently do
   nothing while `scroll-behavior: smooth` is set. Set
   `documentElement.style.scrollBehavior = 'auto'` before measuring.
4. **CSS transitions do not advance**, so `getComputedStyle(el).opacity` can report `0` on
   content that screenshots perfectly. Trust pixels over computed style, or wait and
   screenshot.
5. **`100svh` resizes with the capture window.** A tall screenshot inflates every
   viewport-height section, so you cannot measure a realistic viewport and see past one
   screen in the same render. Use the same-origin probe and scroll instead.

Also: Windows Chrome cannot reach a WSL `127.0.0.1`. Serve on the WSL IP from
`ip route get 1 | awk '{print $7}'`. CDP on `--remote-debugging-port` was not reachable
from WSL at all — the firewall blocks it — so the same-origin probe is the tool, not CDP.

## Cost when missed

Hours, twice. Once reporting live components as broken on WeasyPrint evidence after
Prometheus had explicitly warned that WeasyPrint does not resolve Tailwind's screen media
queries; once nearly reporting a site-wide horizontal overflow that was the window-width
clamp.
