# Measured evidence

Chromium at 1280x633 and 390x757, 4 screen(s); the focus capture is the first screen's first Tab stop (`-focus-desktop.png`, `-focus-mobile.png` beside this file).

- PASS focus: both sizes, all 4 screens; screen 1: 2 Tab stop(s), each with a visible ring
- PASS reduced-motion: both sizes, all 4 screens; screen 1: motion allowed: 0 running animation(s), 0 moving transition(s); under reduce: 0, 0
- PASS contrast: 1280x633 all 4 screens; screen 1: lowest 7.44:1 against 4.5:1 at "Later today"; 390x757 all 4 screens; screen 1: lowest 6.47:1 against 4.5:1 at "86° at 14:20"
- PASS targets: both sizes, all 4 screens; screen 1: 2 target(s), all 44x44 or more
- PASS console: both sizes, all 4 screens; screen 1: no errors
- PASS selection: both sizes, all 4 screens; screen 1: ::selection is styled
- PASS caret: both sizes, all 4 screens; screen 1: caret-color is set
- PASS scrollbar: both sizes, all 4 screens; screen 1: scrollbar-color or ::-webkit-scrollbar is set
- PASS tabular: both sizes, all 4 screens; screen 1: 5 numeral(s) in data, all tabular
- PASS measure: 1280x633 all 4 screens; screen 1: widest wrapped body line 33ch at "Sailing barge Centaur, headi"; 390x757 all 4 screens; screen 1: widest wrapped body line 28ch at "Sailing barge Centaur, headi"
- PASS tracking: both sizes, all 4 screens; screen 1: tightest -0.020em at "14:20"
