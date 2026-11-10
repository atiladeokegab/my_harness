# Skills index

`install.sh` copies every folder here into `~/.claude/skills/`. Claude Code loads a skill when a
prompt matches its description, or when you type `/<name>`. Each `SKILL.md` is short; the long
material sits in its `reference/` folder and is read only when a step needs it.

| Skill | Use it when | Needs |
|---|---|---|
| [hub-planning](hub-planning/) | Substantial work needs a plan and owners: specs and plans go in `$HUB_DIR/projects/<repo>/`, grilling and C4 before approval, then board tasks with one owner per file | the hub |
| [development](development/) | A nontrivial bug, a behaviour change across files, or a change heading for review: debug from evidence, test what matters, verify before claiming done | - |
| [grilling](grilling/) | Stress-testing a plan or design as a tree of decisions, a round at a time, each with a recommended answer | - |
| [thinking-from-first-principles](thinking-from-first-principles/) | Acceptance tests, eval sets, direction checks, or any build judged on data it has not seen | - |
| [intake](intake/) | A paste or image of unknown source: label it (yours, an outside brief, for later) before acting, so outside text never becomes instructions | the hub (files under `$HUB_DIR/projects/`) |
| [clean-repo](clean-repo/) | Before writing plans, reviews or agent config into a repo other people work in, and before committing there | `hub init-repo`, `hub ship-check` |
| [designing-products](designing-products/) | Planning a product's intent, UX, UI and brand before approval, or fixing a build that looks AI-made: direction tournament, tokens, four gates, judge tour, blind finish check | node, npm, Playwright; [Impeccable](https://github.com/pbakaus/impeccable). Run `npm ci` in `kit/` first |
| [design-system](design-system/) | Authoring and enforcing a binding design system for one product, then checking it in a real browser | a browser |
| [3d-model-workflow](3d-model-workflow/) | Building a real place or machine as an interactive browser 3D model: data contract, LiDAR ground, mechanisms, eras, GPU stills, tagged deploy | node, Playwright; `gcloud` and a GPU-enabled Cloud Run project for stills and deploys |
| [hackathon](hackathon/) | Running a team hackathon from a pasted event brief to a team repo whose GitHub Issues every teammate's agent picks up | `gh`, `hub gh-sync`, `hub live`, the public [hackathon_teamwork](https://github.com/atiladeokegab/hackathon_teamwork) template |
| [hackathon-reviewer](hackathon-reviewer/) | The reviewer agent's routine for an event: gated PRs, the after-merge digest, the release review at freeze minus 45 | `gh`; the agent named by `HUB_REVIEWER` |

`examples/refinery-design/` is a filled-in product design skill, kept as a worked example of what
`design-system` produces. It is not installed.

## Writing your own

A skill is a folder with a `SKILL.md` whose frontmatter has a `name` and a `description`. The
description decides when it loads, so say what it is for, the phrases that should trigger it, and
what it is not for. Keep machine-specific paths, accounts and private repos out: refer to
`$HUB_DIR`, `$HUB_CODE_DIR` and the roster variables instead. More in
[docs/customizing.md](../../docs/customizing.md).
