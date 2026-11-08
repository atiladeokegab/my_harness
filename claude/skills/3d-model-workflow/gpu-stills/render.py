# Frame-stepped capture of Strata: a virtual clock drives requestAnimationFrame and performance.now, so every
# frame is rendered exactly 1/60 s apart however slow the GPU is; JPEG frames pipe into ffmpeg (x264).
import os, sys, subprocess, time, json, pathlib, base64
from playwright.sync_api import sync_playwright

LIVE = os.environ['LIVE']  # the URL under test: a tagged revision or the live service
OUT = pathlib.Path(os.environ.get('OUTDIR', '/out/renders'))
DIST = pathlib.Path(os.environ.get('DIST', '/out/dist'))  # main's build, served in place of the live bundle
FPS, W, H = 60, int(os.environ.get('W', 1920)), int(os.environ.get('H', 1080))
PFX = os.environ.get('PFX', 'live')
LIMIT = float(os.environ.get('LIMIT', 0))  # seconds; 0 = full shot

CLOCK = r"""(() => {
  let now = 0; const t0 = Date.now(); let n = 0; const q = new Map()
  performance.now = () => now
  const D = Date; Date.now = () => t0 + now
  window.requestAnimationFrame = (cb) => { q.set(++n, cb); return n }
  window.cancelAnimationFrame = (i) => q.delete(i)
  window.__vc = { step(ms) { now += ms; const cbs = [...q.values()]; q.clear(); for (const cb of cbs) { try { cb(now) } catch (e) { console.error(e) } } return cbs.length } }
})()"""

# Shot scripts run in the page: they replace the tour's KEYS and TRACKS in place and return the duration.
# Frame: metres, origin deck centre, x east (downstream), y up, z south; az 0 = camera south looking north.
SHOTS = {
  'tour': "() => T.DURATION + 1.0",
  'years': """() => { setScript([
      { t: 0, target: [0, 22, 0], r: 330, az: 292, el: 11 },
      { t: 16, target: [0, 22, 0], r: 315, az: 312, el: 9 }],
    [{ from: 0, to: 0, set: () => { S().setView('orbit'); S().setExploded(false); S().setBascule(0); S().select(null); S().setYear(1886) } },
     { from: 1.5, to: 10.5, set: yearAt(1886, 1894), linear: true },
     { from: 12, to: 14.5, set: yearAt(1894, new Date().getFullYear()) }]); return 16 }""",
  'bascules': """() => { setScript([
      { t: 0, target: [70, 14, 0], r: 280, az: 62, el: 10 },
      { t: 22, target: [40, 14, 0], r: 230, az: 35, el: 8 },
      { t: 40, target: [-20, 14, 0], r: 210, az: 8, el: 7 },
      { t: 56, target: [-90, 14, 0], r: 230, az: -25, el: 9 }],
    [{ from: 0, to: 0, set: () => { S().setView('orbit'); S().setExploded(false); S().setBascule(0); S().select(null); S().setYear(new Date().getFullYear()) } },
     { from: 1.5, to: 6, set: (u) => S().setBascule(u) },
     { from: 50, to: 55, set: (u) => S().setBascule(1 - u) }]); return 56 }""",
  'top': """() => { setScript([
      { t: 0, target: [0, 0, 0], r: 700, az: 240, el: 88 },
      { t: 14, target: [0, 0, 0], r: 480, az: 300, el: 88 }],
    [{ from: 0, to: 0, set: () => { S().setView('top'); S().setExploded(false); S().setBascule(0); S().select(null); S().setYear(new Date().getFullYear()) } }]); return 14 }""",
  'walk': """() => { setScript([
      { t: 0, target: [4, 3, 125], r: 30, az: 0, el: 2 },
      { t: 24, target: [4, 3, -15], r: 30, az: 0, el: 2 }],
    [{ from: 0, to: 0, set: () => { S().setView('orbit'); S().setExploded(false); S().setBascule(0); S().select(null); S().setYear(new Date().getFullYear()) } }]); return 24 }""",
}
PRELUDE = """const T = window.__strata.tour, S = () => window.__strata.useStore.getState();
const yearAt = (a, b) => (u) => S().setYear(Math.round(a + (b - a) * u));
const setScript = (keys, tracks) => { T.KEYS.splice(0, T.KEYS.length, ...keys); T.TRACKS.splice(0, T.TRACKS.length, ...tracks) };"""

ATTEMPTS = [
  ['--use-angle=vulkan', '--enable-features=Vulkan,VulkanFromANGLE,DefaultANGLEVulkan', '--disable-vulkan-surface'],
  ['--use-gl=angle', '--use-angle=gl-egl'],
  ['--use-gl=egl'],
  [],
]
BASE = ['--headless=new', '--ignore-gpu-blocklist', '--enable-gpu', '--enable-gpu-rasterization', '--no-sandbox',
        '--disable-dev-shm-usage', '--hide-scrollbars', '--mute-audio', '--disable-background-timer-throttling',
        '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows']

RENDERER = """() => { const c = document.createElement('canvas'); const g = c.getContext('webgl2') || c.getContext('webgl');
  if (!g) return 'no webgl'; const e = g.getExtension('WEBGL_debug_renderer_info'); return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : g.getParameter(g.RENDERER) }"""

def launch(p):
    want_gpu = os.environ.get('CPU') != '1'
    for extra in (ATTEMPTS if want_gpu else [[]]):
        b = p.chromium.launch(headless=False, args=BASE + extra)
        pg = b.new_page()
        pg.goto('about:blank')
        r = pg.evaluate(RENDERER)
        print('renderer with', extra, '->', r, flush=True)
        pg.close()
        if not want_gpu or 'NVIDIA' in r.upper():
            return b, r
        b.close()
    if os.environ.get('REQUIRE_GPU') == '1':
        sys.exit('no NVIDIA renderer')
    return p.chromium.launch(headless=False, args=BASE), 'fallback'

def serve_dist(route):
    url = route.request.url
    path = url[len(LIVE):].split('?')[0].split('#')[0]
    if path.startswith('/api/'):
        return route.continue_()
    f = DIST / (path.lstrip('/') or 'index.html')
    if DIST.exists() and f.is_file():
        return route.fulfill(path=str(f))
    return route.continue_()

def open_app(p, logs=None, query='?capture=1', phone=False, enter=True, size=None, clock=True):
    b, renderer = launch(p)
    ctx = (b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=3, is_mobile=True, has_touch=True)
           if phone else b.new_context(viewport={'width': (size or (W, H))[0], 'height': (size or (W, H))[1]}, device_scale_factor=1))
    if clock: ctx.add_init_script(CLOCK)
    pg = ctx.new_page()
    def on_console(m):
        if m.type in ('error', 'warning') or '[strata]' in m.text:
            print('console:', m.type, m.text[:300], flush=True)
            if logs is not None: logs.append(f'{m.type}: {m.text}')
    pg.on('console', on_console)
    pg.on('pageerror', lambda e: logs is not None and logs.append(f'pageerror: {e}'))
    pg.route(LIVE + '/**', serve_dist)
    if os.environ.get('REFERER'):  # Google tiles key is referrer-restricted to the live host
        ref = os.environ['REFERER']
        pg.route(lambda u: 'googleapis.com' in u, lambda r: r.continue_(headers={**r.request.headers, 'referer': ref}))
    pg.on('response', lambda r: r.status >= 400 and logs is not None and logs.append(f'http {r.status}: {r.url[:160]}'))
    pg.goto(LIVE + '/' + query, wait_until='load', timeout=120000)
    if enter: enter_bridge(pg)
    return b, renderer, ctx, pg

def enter_bridge(pg):
    # Leave the museum landing: a DOM click (Playwright's own click waits on rAF, which the virtual clock owns).
    t0 = time.time()
    while time.time() - t0 < 45:
        pg.evaluate('window.__vc && window.__vc.step(1000/60)')
        hit = pg.evaluate("(() => { const b = [...document.querySelectorAll('button,a,[role=button]')].find((e) => /Enter Tower Bridge/i.test(e.textContent)); if (b) { b.click(); return true } return false })()")
        if hit:
            print('entered Tower Bridge', flush=True)
            break
        time.sleep(0.1)

def landing(pg, secs=10):
    for _ in range(int(secs * 30)):
        pg.evaluate('window.__vc && window.__vc.step(1000/60)'); time.sleep(1 / 30)

def warm(pg, secs=15):
    # Warm up in real time until the place and its textures are in, so nothing pops during the shot.
    t0 = time.time()
    while time.time() - t0 < 90:
        pg.evaluate('window.__vc && window.__vc.step(1000/60)')
        time.sleep(1 / 60)
        if time.time() - t0 > secs and pg.evaluate('!!(window.__strata && window.__strata.useStore.getState().place)'): break
    for _ in range(240):
        pg.evaluate('window.__vc.step(1000/60)')

def shoot(cdp, path):
    path.write_bytes(base64.b64decode(cdp.send('Page.captureScreenshot', {'format': 'png'})['data']))

def tourstills(p, times=(3, 15, 22, 30, 37, 42, 50, 57)):
    logs = []
    b, renderer, ctx, pg = open_app(p, logs)
    warm(pg, 30)
    cdp = ctx.new_cdp_session(pg)
    d = OUT / 'stills'; d.mkdir(parents=True, exist_ok=True)
    pg.evaluate('window.__strata.tour.startTour()')
    frame = 0
    for t in times:
        while frame < t * FPS:
            pg.evaluate('window.__vc.step(1000/60)'); frame += 1
            if frame % 30 == 0: time.sleep(0.05)  # let fetches (docent answer) land in real time too
        time.sleep(1.5)  # real time for network-driven UI (docent card) before the shot
        pg.evaluate('window.__vc.step(1000/60)'); frame += 1
        shoot(cdp, d / f'{PFX}-tour-{t:02d}s.png')
        print('tour still', t, flush=True)
    (d / f'{PFX}-tour-console.txt').write_text(f'renderer: {renderer}\n' + '\n'.join(logs) + '\n')
    b.close()

def phone(p):
    logs = []
    b, renderer, ctx, pg = open_app(p, logs, query='?capture=1&lite=1', phone=True, enter=False)
    cdp = ctx.new_cdp_session(pg)
    d = OUT / 'stills'; d.mkdir(parents=True, exist_ok=True)
    landing(pg)
    shoot(cdp, d / f'{PFX}-phone-home-390x844.png')
    enter_bridge(pg)
    warm(pg, 30)
    if os.environ.get('PHONE_YEAR'):
        pg.evaluate(f"window.__strata.tour.stopTour(); window.__strata.useStore.getState().setYear({int(os.environ['PHONE_YEAR'])})")
        steps(pg, 360)
    shoot(cdp, d / f'{PFX}-phone-lite-390x844.png')
    (d / f'{PFX}-phone-console.txt').write_text(f'renderer: {renderer}\n' + '\n'.join(logs) + '\n')
    print('phone still', flush=True)
    b.close()

def home(p):
    logs = []
    b, renderer, ctx, pg = open_app(p, logs, enter=False, size=(1280, 720))
    cdp = ctx.new_cdp_session(pg)
    d = OUT / 'stills'; d.mkdir(parents=True, exist_ok=True)
    landing(pg)
    shoot(cdp, d / f'{PFX}-home-1280x720.png')
    (d / f'{PFX}-home-console.txt').write_text(f'renderer: {renderer}\n' + '\n'.join(logs) + '\n')
    print('home still', flush=True)
    b.close()

def ttff(p):
    # Phone time to first frame, real clock, cold cache: unthrottled, then Lighthouse mobile (150 ms RTT, 1.6 Mbps, 4x CPU).
    # shortcut: the L4 is far faster than a phone GPU, so the GPU share of these times is optimistic.
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'pillow'], check=False)
    from PIL import Image, ImageStat
    import io
    d = OUT / 'stills'; d.mkdir(parents=True, exist_ok=True)
    lines = []
    for label, net, cpu in (('unthrottled', None, 1), ('slow-4g-4xcpu', (150, 1.6e6 / 8, 750e3 / 8), 4)):
        logs = []
        b, renderer, ctx, pg = open_app(p, logs, query='?capture=1&lite=1', phone=True, enter=False, clock=False)
        cdp = ctx.new_cdp_session(pg)
        if net:
            cdp.send('Network.enable')
            cdp.send('Network.emulateNetworkConditions', {'offline': False, 'latency': net[0], 'downloadThroughput': net[1], 'uploadThroughput': net[2]})
        cdp.send('Emulation.setCPUThrottlingRate', {'rate': cpu})
        pg.goto('about:blank')
        t0 = time.time(); marks = {}
        pg.goto(LIVE + '/?capture=1&lite=1', wait_until='commit', timeout=180000)
        enter = pg.locator('button,a,[role=button]', has_text='Enter Tower Bridge').first
        enter.wait_for(timeout=240000); marks['home_enter_button'] = time.time() - t0
        shoot(cdp, d / f'{PFX}-ttff-{label}-home.png')
        enter.click(); t1 = time.time(); marks['click_enter'] = t1 - t0
        prev, first, lit = None, None, None
        while time.time() - t1 < 240:
            im = Image.open(io.BytesIO(base64.b64decode(cdp.send('Page.captureScreenshot', {'format': 'jpeg', 'quality': 40})['data']))).convert('L')
            scene = im.crop((0, int(im.height * 0.30), im.width, int(im.height * 0.66)))  # the 3D band between the controls and the sheet
            sd = ImageStat.Stat(scene).stddev[0]
            black = sum(scene.histogram()[:12]) / (scene.width * scene.height)  # an unlit bridge renders as a black silhouette
            if first is None and sd > 15 and not enter.is_visible():
                first = time.time() - t1; marks['first_scene_frame_after_enter'] = first
                im.save(d / f'{PFX}-ttff-{label}-first.png')
            if first is not None and lit is None and black < 0.05:
                lit = time.time() - t1; marks['first_lit_frame_after_enter'] = lit
                im.save(d / f'{PFX}-ttff-{label}-lit.png')
            if lit is not None and prev is not None and sum(abs(a - b) for a, b in zip(im.resize((48, 104)).getdata(), prev.resize((48, 104)).getdata())) / (48 * 104) < 2:
                marks['visually_settled_after_enter'] = time.time() - t1
                im.save(d / f'{PFX}-ttff-{label}-settled.png'); break
            prev = im
        if lit is None: marks['no_lit_frame_within_s'] = time.time() - t1; im.save(d / f'{PFX}-ttff-{label}-last.png')
        lines.append(f"{label}: " + ', '.join(f"{k} {v:.1f}s" for k, v in marks.items()))
        print(lines[-1], flush=True)
        lines += [f'  {l}' for l in logs if 'ReadPixels' not in l]
        b.close()
    (d / f'{PFX}-ttff.txt').write_text(f'renderer: {renderer}\n' + '\n'.join(lines) + '\n')

def render(p, shot):
    if shot == 'ttff': return ttff(p)
    if shot == 'home': return home(p)
    if shot == 'stills': return stills(p)
    if shot == 'tourstills': return tourstills(p)
    if shot == 'phone': return phone(p)
    b, renderer, ctx, pg = open_app(p)
    warm(pg, 30)
    dur = pg.evaluate(f'({SHOTS[shot]})()'.replace('() => {', '() => {' + PRELUDE, 1) if shot != 'tour' else f'(() => {{ {PRELUDE} return ({SHOTS[shot]})() }})()')
    if LIMIT: dur = min(dur, LIMIT)
    pg.evaluate('window.__strata.tour.startTour()')
    n = int(round(dur * FPS))
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f'strata-{shot}.mp4'
    tmp = pathlib.Path('/work') / out.name if pathlib.Path('/work').exists() else out.with_suffix('.part.mp4')
    ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', str(FPS), '-c:v', 'mjpeg', '-i', '-',
                           '-vf', f'scale={W}:{H}:flags=lanczos', '-c:v', 'libx264', '-preset', 'medium', '-crf', '15', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(tmp)],
                          stdin=subprocess.PIPE)
    cdp = ctx.new_cdp_session(pg)
    import base64
    t1 = time.time()
    for i in range(n):
        pg.evaluate('window.__vc.step(1000/60)')
        img = cdp.send('Page.captureScreenshot', {'format': 'jpeg', 'quality': 93})['data']
        raw = base64.b64decode(img)
        if i == 0: print('first frame', raw[:4].hex(), len(raw), flush=True); (OUT / f'strata-{shot}-first.jpg').write_bytes(raw)
        ff.stdin.write(raw)
        if i % 300 == 0:
            print(f'{shot} frame {i}/{n} {time.time()-t1:.0f}s', flush=True)
    ff.stdin.close(); ff.wait()
    if tmp != out:
        subprocess.run(['cp', str(tmp), str(out)], check=True)
    print(json.dumps({'shot': shot, 'frames': n, 'seconds': n / FPS, 'renderer': renderer, 'wall': round(time.time() - t1)}), flush=True)
    (OUT / f'strata-{shot}.json').write_text(json.dumps({'frames': n, 'seconds': n / FPS, 'renderer': renderer}))
    b.close()

POSES = {  # name: (year or None, key or None, lidar)
  'orbit-default-2026': (2026, None, False),
  '400m-45deg-2026': (2026, {'t': 0, 'target': [0, 0, 0], 'r': 566, 'az': 300, 'el': 45}, False),
  'low-25m-north-tower-2026': (2026, {'t': 0, 'target': [0, 30, -35], 'r': 90, 'az': 25, 'el': -3}, False),
  'top-1200m-2026': (2026, {'t': 0, 'target': [0, 0, 0], 'r': 1200, 'az': 270, 'el': 89}, False),
  'hero-1890': (1890, {'t': 0, 'target': [0, 22, 0], 'r': 330, 'az': 300, 'el': 10}, False),
  'hero-lidar-on-2026': (2026, {'t': 0, 'target': [0, 22, 0], 'r': 330, 'az': 300, 'el': 10}, True),
  'north-end-out-2026': (2026, {'t': 0, 'target': [0, 3, -320], 'r': 110, 'az': 0, 'el': 1}, False),
  'north-end-back-2026': (2026, {'t': 0, 'target': [0, 2, -140], 'r': 90, 'az': 180, 'el': 2}, False),
  'south-end-out-2026': (2026, {'t': 0, 'target': [0, 3, 320], 'r': 110, 'az': 180, 'el': 1}, False),
  'south-end-back-2026': (2026, {'t': 0, 'target': [0, 2, 140], 'r': 90, 'az': 0, 'el': 2}, False),
  'north-end-out-1890': (1890, {'t': 0, 'target': [0, 3, -320], 'r': 110, 'az': 0, 'el': 1}, False),
  'north-end-back-1890': (1890, {'t': 0, 'target': [0, 2, -140], 'r': 90, 'az': 180, 'el': 2}, False),
  'south-end-out-1890': (1890, {'t': 0, 'target': [0, 3, 320], 'r': 110, 'az': 180, 'el': 1}, False),
  'south-end-back-1890': (1890, {'t': 0, 'target': [0, 2, 140], 'r': 90, 'az': 0, 'el': 2}, False),
}

def steps(pg, n):
    for _ in range(n):
        pg.evaluate('window.__vc.step(1000/60)'); time.sleep(1 / 120)

def stills(p):
    logs = []
    b, renderer, ctx, pg = open_app(p, logs)
    pg.evaluate("window.__strata.tour.stopTour(); window.__strata.useStore.getState().setYear(2026)")
    warm(pg, 30)
    cdp = ctx.new_cdp_session(pg)
    d = OUT / 'stills'; d.mkdir(parents=True, exist_ok=True)
    lidar_on = False
    only = os.environ.get('POSES_ONLY')
    for name, (year, key, lidar) in POSES.items():
        if only and name not in only.split(','): continue
        pg.evaluate(f"window.__strata.useStore.getState().setYear({year})")
        if lidar != lidar_on:
            pg.evaluate("(() => { const b = [...document.querySelectorAll('button')].find((e) => /lidar/i.test(e.textContent)); b && b.click(); return !!b })()")
            lidar_on = lidar
        if key:
            pg.evaluate(f"(() => {{ const T = window.__strata.tour; T.KEYS.splice(0, T.KEYS.length, {json.dumps(key)}); T.TRACKS.splice(0, T.TRACKS.length); T.startTour() }})()")
        steps(pg, 360)  # 6 s for tiles and period imagery to swap in
        (d / f'{PFX}-{name}.png').write_bytes(base64.b64decode(cdp.send('Page.captureScreenshot', {'format': 'png'})['data']))
        pg.evaluate('window.__vc.step(1000/60)')  # the next frame, to diff for flicker
        (d / f'{PFX}-{name}-next.png').write_bytes(base64.b64decode(cdp.send('Page.captureScreenshot', {'format': 'png'})['data']))
        print('still', name, flush=True)
    (d / f'{PFX}-console.txt').write_text(f'renderer: {renderer}\n' + '\n'.join(logs) + '\n')
    print('console lines', len(logs), flush=True)
    b.close()

if __name__ == '__main__':
    order = os.environ.get('ORDER', 'tour,years,bascules,top,walk').split(',')
    shot = sys.argv[1] if len(sys.argv) > 1 else 'auto'
    shots = [order[int(os.environ.get('CLOUD_RUN_TASK_INDEX', 0))]] if shot == 'auto' else shot.split(',')
    with sync_playwright() as p:
        for s in shots:
            render(p, s)
