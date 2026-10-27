# Instruction benchmark: D:\Projects\Personal\sanduq-round3 @ bd4a361

## workflow 1.14.0

| file | bytes | linked bytes | instruction bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.workflow.init | 637 | 3570 | 4207 | 2.15 | 0 | 0 | ok |
| speckit.workflow.scope | 592 | 3570 | 4162 | 2.17 | 0 | 0 | ok |
| speckit.workflow.clarify | 635 | 3570 | 4205 | 2.25 | 0 | 0 | ok |
| speckit.workflow.continue | 801 | 4225 | 5026 | 1.92 | 0 | 0 | ok |
| speckit.workflow.finalize | 597 | 3570 | 4167 | 2.3 | 0 | 0 | ok |
| speckit.workflow.status | 598 | 3570 | 4168 | 2.35 | 0 | 0 | has_triggers |
| speckit.workflow.doctor | 615 | 3570 | 4185 | 2.3 | 0 | 0 | ok |
| speckit.workflow.reconcile | 607 | 3570 | 4177 | 2.44 | 0 | 0 | has_triggers |
| speckit.workflow.verify-affected | 499 | 1181 | 1680 | 1.49 | 0 | 0 | ok |
| speckit.workflow.ci-report | 485 | 770 | 1255 | 0.0 | 0 | 0 | has_triggers |
| speckit.workflow.gate-explain | 501 | 1248 | 1749 | 0.0 | 0 | 0 | has_triggers |
| speckit.workflow.worker-brief | 478 | 1393 | 1871 | 0.0 | 0 | 0 | has_triggers |
| speckit.workflow.apply-pending | 516 | 2030 | 2546 | 0.0 | 0 | 0 | ok |
| extensions/workflow/skills/speckit-scope/SKILL.ext.md | 582 | 3570 | 4152 | 1.27 | 0 | 0 | skill; references 0 files, 0 bytes |
| extensions/workflow/skills/speckit-superpowers-bridge/SKILL.ext.md | 930 | 0 | 930 | 1.67 | 0 | 0 | skill; references 0 files, 0 bytes |
| extensions/workflow/skills/workflow/SKILL.ext.md | 3570 | 22980 | 26550 | 1.21 | 1 | 7 | skill; references 35 files, 94167 bytes |

## scope 1.8.1

| file | bytes | linked bytes | instruction bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.scope.run | 938 | 5195 | 6133 | 0.74 | 0 | 0 | ok |
| speckit.scope.guard | 1737 | 2757 | 4494 | 0.81 | 1 | 0 | has_triggers |
| speckit.scope.bind | 1131 | 2757 | 3888 | 1.91 | 1 | 0 | has_triggers |
| speckit.scope.reconcile | 669 | 0 | 669 | 1.06 | 1 | 0 | has_triggers |
| speckit.scope.plan | 517 | 7973 | 8490 | 1.64 | 0 | 0 | has_triggers |
| speckit.scope.after-specify | 1254 | 0 | 1254 | 1.72 | 1 | 0 | has_triggers |
| speckit.scope.plan-guard | 848 | 0 | 848 | 0.81 | 1 | 0 | has_triggers |
| extensions/scope/skills/github-clarification/SKILL.ext.md | 5030 | 7323 | 12353 | 1.34 | 1 | 14 | skill; references 4 files, 7323 bytes |
| extensions/scope/skills/scope-analyst/SKILL.ext.md | 5195 | 10562 | 15757 | 1.13 | 1 | 16 | skill; references 4 files, 5106 bytes |

## assure 2.4.0

| file | bytes | linked bytes | instruction bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.assure.init | 1483 | 1974 | 3457 | 0.5 | 2 | 5 | ok |
| speckit.assure.analyze | 5909 | 8504 | 14413 | 0.93 | 3 | 0 | ok |
| speckit.assure.document | 9458 | 8504 | 17962 | 0.55 | 5 | 6 | ok |
| extensions/assure/skills/assure/SKILL.ext.md | 1974 | 3258 | 5232 | 1.55 | 0 | 7 | skill; references 2 files, 3258 bytes |

## user-manual 1.6.0

| file | bytes | linked bytes | instruction bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.user-manual.init | 2424 | 3807 | 6231 | 1.36 | 1 | 9 | ok |
| speckit.user-manual.analyze | 2588 | 12183 | 14771 | 0.96 | 2 | 8 | ok |
| speckit.user-manual.update | 3921 | 10337 | 14258 | 0.44 | 6 | 10 | ok |
| speckit.user-manual.release | 1582 | 3330 | 4912 | 2.09 | 2 | 7 | ok |
| extensions/user-manual/skills/api-docs/SKILL.ext.md | 1195 | 753 | 1948 | 0.66 | 0 | 6 | skill; references 1 files, 753 bytes |
| extensions/user-manual/skills/preview-publishing/SKILL.ext.md | 1423 | 1018 | 2441 | 1.09 | 0 | 7 | skill; references 1 files, 1018 bytes |
| extensions/user-manual/skills/release-docs/SKILL.ext.md | 946 | 909 | 1855 | 0.93 | 0 | 0 | skill; references 2 files, 909 bytes |
| extensions/user-manual/skills/ui-screenshots/SKILL.ext.md | 1128 | 759 | 1887 | 0.68 | 0 | 0 | skill; references 1 files, 759 bytes |
| extensions/user-manual/skills/user-manual/SKILL.ext.md | 2384 | 11073 | 13457 | 0.73 | 0 | 8 | skill; references 6 files, 6381 bytes |

## pr 4.3.0

| file | bytes | linked bytes | instruction bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.pr.generate | 11058 | 12582 | 23640 | 0.95 | 10 | 19 | ok |
| speckit.pr.review-feedback | 5518 | 0 | 5518 | 0.38 | 11 | 14 | ok |

## project 2.3.0

| file | bytes | linked bytes | instruction bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.project.init | 2279 | 0 | 2279 | 0.35 | 4 | 5 | ok |
| speckit.project.sync | 1323 | 0 | 1323 | 0.47 | 2 | 3 | ok |

## illustrate 2.5.0

| file | bytes | linked bytes | instruction bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.illustrate.generate | 1526 | 11837 | 13363 | 0.49 | 0 | 5 | ok |
| speckit.illustrate.export | 1506 | 10180 | 11686 | 1.46 | 0 | 6 | ok |
| speckit.illustrate.theme | 920 | 8097 | 9017 | 0.0 | 0 | 5 | ok |
| speckit.illustrate.import | 2204 | 58937 | 61141 | 2.32 | 0 | 8 | ok |
| extensions/illustrate/skill/SKILL.md | 11730 | 283977 | 295707 | 0.68 | 4 | 15 | skill; references 74 files, 726423 bytes |

## memory 2.3.0

| file | bytes | linked bytes | instruction bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.memory.init | 1715 | 0 | 1715 | 0.93 | 0 | 0 | ok |
| speckit.memory.prepare | 1723 | 0 | 1723 | 1.77 | 1 | 6 | ok |
| speckit.memory.run | 4620 | 16975 | 21595 | 1.78 | 1 | 10 | ok |
| speckit.memory.session | 2176 | 2145 | 4321 | 1.97 | 1 | 0 | ok |
| speckit.memory.enable | 1252 | 0 | 1252 | 0.59 | 2 | 0 | ok |
| speckit.memory.impact | 2573 | 0 | 2573 | 0.8 | 2 | 4 | ok |
| speckit.memory.status | 691 | 2145 | 2836 | 1.11 | 1 | 0 | ok |

## progress 1.3.0

| file | bytes | linked bytes | instruction bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.progress.init | 496 | 2154 | 2650 | 1.47 | 1 | 0 | ok |
| speckit.progress.refresh | 427 | 0 | 427 | 1.72 | 1 | 0 | ok |
| speckit.progress.status | 355 | 0 | 355 | 0.0 | 1 | 0 | ok |
| speckit.progress.theme | 416 | 0 | 416 | 0.0 | 1 | 0 | ok |
| speckit.progress.export | 344 | 0 | 344 | 0.0 | 1 | 0 | ok |
| extensions/progress/skills/progress/SKILL.ext.md | 2154 | 5003 | 7157 | 1.39 | 1 | 4 | skill; references 1 files, 5003 bytes |

## Summary

| extension | version | instruction bytes | tokens | words | proh/100w | script calls | prose steps | descriptions failing | catalog entries | catalog chars |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| workflow | 1.14.0 | 42900 | 10725 | 5698 | 1.28 | 10 | 7 | 5/13 | 13 | 3241 |
| scope | 1.8.1 | 45934 | 11483 | 6243 | 1.22 | 11 | 45 | 6/7 | 7 | 1638 |
| assure | 2.4.0 | 28612 | 7153 | 3720 | 0.62 | 10 | 18 | 0/3 | 3 | 427 |
| user-manual | 1.6.0 | 33941 | 8485 | 4106 | 0.63 | 11 | 55 | 0/4 | 4 | 532 |
| pr | 4.3.0 | 29158 | 7289 | 4065 | 0.69 | 27 | 38 | 0/2 | 2 | 276 |
| project | 2.3.0 | 3602 | 900 | 495 | 0.4 | 6 | 8 | 0/2 | 2 | 280 |
| illustrate | 2.5.0 | 301863 | 75465 | 39315 | 0.46 | 53 | 170 | 0/4 | 4 | 549 |
| memory | 2.3.0 | 31725 | 7931 | 4282 | 1.17 | 11 | 27 | 0/7 | 7 | 983 |
| progress | 1.3.0 | 9195 | 2298 | 1387 | 1.08 | 6 | 4 | 0/5 | 5 | 678 |
| all | | 526930 | 131729 | 69311 | 0.68 | 145 | 372 | 11/47 | 47 | 8604 |

## Duplicates (top 25 of 4)

| paragraph | words | files |
| --- | ---: | --- |
| when generating a new diagram, keep these intact in the template: - the two cdn  | 131 | extensions/illustrate/skill/references/technical-color-architecture.md, extensions/illustrate/skill/references/technical-color-process-flow.md |
| every diagram ships with a single unobtrusive ⋯ toggle in the header. click it t | 91 | extensions/illustrate/skill/references/technical-color-architecture.md, extensions/illustrate/skill/references/technical-color-process-flow.md |
| caveats: clipboard api needs a user gesture and a secure context (https/file/loc | 36 | extensions/illustrate/skill/references/technical-color-architecture.md, extensions/illustrate/skill/references/technical-color-process-flow.md |
| set --format, --size, --detail, and --audience from [output-spec.md](output-spec | 36 | extensions/illustrate/skill/references/import-excalidraw.md, extensions/illustrate/skill/references/import-mermaid.md |
