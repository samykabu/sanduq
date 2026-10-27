# Instruction benchmark: D:\Projects\Personal\sanduq-round3-base @ 7ad9135

## workflow 1.14.0

| file | bytes | linked bytes | instruction bytes | conditional bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.workflow.init | 637 | 3570 | 4207 | 0 | 2.15 | 0 | 0 | ok |
| speckit.workflow.scope | 592 | 3570 | 4162 | 0 | 2.17 | 0 | 0 | ok |
| speckit.workflow.clarify | 635 | 3570 | 4205 | 0 | 2.25 | 0 | 0 | ok |
| speckit.workflow.continue | 801 | 3570 | 4371 | 655 | 1.92 | 0 | 0 | ok |
| speckit.workflow.finalize | 597 | 3570 | 4167 | 0 | 2.3 | 0 | 0 | ok |
| speckit.workflow.status | 598 | 3570 | 4168 | 0 | 2.35 | 0 | 0 | has_triggers |
| speckit.workflow.doctor | 615 | 3570 | 4185 | 0 | 2.3 | 0 | 0 | ok |
| speckit.workflow.reconcile | 607 | 3570 | 4177 | 0 | 2.44 | 0 | 0 | has_triggers |
| speckit.workflow.verify-affected | 499 | 1181 | 1680 | 0 | 1.49 | 0 | 0 | ok |
| speckit.workflow.ci-report | 485 | 770 | 1255 | 0 | 0.0 | 0 | 0 | has_triggers |
| speckit.workflow.gate-explain | 501 | 1248 | 1749 | 0 | 0.0 | 0 | 0 | has_triggers |
| speckit.workflow.worker-brief | 478 | 1393 | 1871 | 0 | 0.0 | 0 | 0 | has_triggers |
| speckit.workflow.apply-pending | 516 | 2030 | 2546 | 0 | 0.0 | 0 | 0 | ok |
| extensions/workflow/skills/speckit-scope/SKILL.ext.md | 582 | 3570 | 4152 | 0 | 1.27 | 0 | 0 | skill; references 0 files, 0 bytes |
| extensions/workflow/skills/speckit-superpowers-bridge/SKILL.ext.md | 930 | 0 | 930 | 0 | 1.67 | 0 | 0 | skill; references 0 files, 0 bytes |
| extensions/workflow/skills/workflow/SKILL.ext.md | 3570 | 16293 | 19863 | 6687 | 1.21 | 1 | 7 | skill; references 35 files, 94167 bytes |

## scope 1.8.1

| file | bytes | linked bytes | instruction bytes | conditional bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.scope.run | 938 | 5195 | 6133 | 0 | 0.74 | 0 | 0 | ok |
| speckit.scope.guard | 1737 | 2757 | 4494 | 0 | 0.81 | 1 | 0 | has_triggers |
| speckit.scope.bind | 1131 | 2757 | 3888 | 0 | 1.91 | 1 | 0 | has_triggers |
| speckit.scope.reconcile | 669 | 0 | 669 | 0 | 1.06 | 1 | 0 | has_triggers |
| speckit.scope.plan | 517 | 7973 | 8490 | 0 | 1.64 | 0 | 0 | has_triggers |
| speckit.scope.after-specify | 1254 | 0 | 1254 | 0 | 1.72 | 1 | 0 | has_triggers |
| speckit.scope.plan-guard | 848 | 0 | 848 | 0 | 0.81 | 1 | 0 | has_triggers |
| extensions/scope/skills/github-clarification/SKILL.ext.md | 5030 | 5469 | 10499 | 0 | 1.34 | 1 | 14 | skill; references 4 files, 7323 bytes |
| extensions/scope/skills/scope-analyst/SKILL.ext.md | 5195 | 10075 | 15270 | 0 | 1.13 | 1 | 16 | skill; references 4 files, 5106 bytes |

## assure 2.4.0

| file | bytes | linked bytes | instruction bytes | conditional bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.assure.init | 1483 | 1974 | 3457 | 0 | 0.5 | 2 | 5 | ok |
| speckit.assure.analyze | 5909 | 1974 | 7883 | 6530 | 0.93 | 3 | 0 | ok |
| speckit.assure.document | 9458 | 1974 | 11432 | 6530 | 0.55 | 5 | 6 | ok |
| extensions/assure/skills/assure/SKILL.ext.md | 1974 | 3258 | 5232 | 0 | 1.55 | 0 | 7 | skill; references 2 files, 3258 bytes |

## user-manual 1.6.0

| file | bytes | linked bytes | instruction bytes | conditional bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.user-manual.init | 2424 | 2384 | 4808 | 1423 | 1.36 | 1 | 9 | ok |
| speckit.user-manual.analyze | 2588 | 5653 | 8241 | 6530 | 0.96 | 2 | 8 | ok |
| speckit.user-manual.update | 3921 | 2384 | 6305 | 7953 | 0.44 | 6 | 10 | ok |
| speckit.user-manual.release | 1582 | 3330 | 4912 | 0 | 2.09 | 2 | 7 | ok |
| extensions/user-manual/skills/api-docs/SKILL.ext.md | 1195 | 753 | 1948 | 0 | 0.66 | 0 | 6 | skill; references 1 files, 753 bytes |
| extensions/user-manual/skills/preview-publishing/SKILL.ext.md | 1423 | 1018 | 2441 | 0 | 1.09 | 0 | 7 | skill; references 1 files, 1018 bytes |
| extensions/user-manual/skills/release-docs/SKILL.ext.md | 946 | 318 | 1264 | 591 | 0.93 | 0 | 0 | skill; references 2 files, 909 bytes |
| extensions/user-manual/skills/ui-screenshots/SKILL.ext.md | 1128 | 759 | 1887 | 0 | 0.68 | 0 | 0 | skill; references 1 files, 759 bytes |
| extensions/user-manual/skills/user-manual/SKILL.ext.md | 2384 | 11073 | 13457 | 0 | 0.73 | 0 | 8 | skill; references 6 files, 6381 bytes |

## pr 4.3.0

| file | bytes | linked bytes | instruction bytes | conditional bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.pr.generate | 11058 | 7381 | 18439 | 5201 | 0.95 | 10 | 19 | ok |
| speckit.pr.review-feedback | 5518 | 0 | 5518 | 0 | 0.38 | 11 | 14 | ok |

## project 2.3.0

| file | bytes | linked bytes | instruction bytes | conditional bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.project.init | 2279 | 0 | 2279 | 0 | 0.35 | 4 | 5 | ok |
| speckit.project.sync | 1323 | 0 | 1323 | 0 | 0.47 | 2 | 3 | ok |

## illustrate 2.5.0

| file | bytes | linked bytes | instruction bytes | conditional bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.illustrate.generate | 1526 | 11837 | 13363 | 0 | 0.49 | 0 | 5 | ok |
| speckit.illustrate.export | 1506 | 10180 | 11686 | 0 | 1.46 | 0 | 6 | ok |
| speckit.illustrate.theme | 920 | 8097 | 9017 | 0 | 0.0 | 0 | 5 | ok |
| speckit.illustrate.import | 2204 | 29620 | 31824 | 7990 | 2.32 | 0 | 8 | ok; one of 3 |
| extensions/illustrate/skill/SKILL.md | 11730 | 221602 | 233332 | 41048 | 0.68 | 4 | 15 | skill; references 74 files, 726423 bytes |

## memory 2.3.0

| file | bytes | linked bytes | instruction bytes | conditional bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.memory.init | 1715 | 0 | 1715 | 0 | 0.93 | 0 | 0 | ok |
| speckit.memory.prepare | 1723 | 0 | 1723 | 0 | 1.77 | 1 | 6 | ok |
| speckit.memory.run | 4620 | 12822 | 17442 | 4153 | 1.78 | 1 | 10 | ok |
| speckit.memory.session | 2176 | 2145 | 4321 | 0 | 1.97 | 1 | 0 | ok |
| speckit.memory.enable | 1252 | 0 | 1252 | 0 | 0.59 | 2 | 0 | ok |
| speckit.memory.impact | 2573 | 0 | 2573 | 0 | 0.8 | 2 | 4 | ok |
| speckit.memory.status | 691 | 2145 | 2836 | 0 | 1.11 | 1 | 0 | ok |

## progress 1.3.0

| file | bytes | linked bytes | instruction bytes | conditional bytes | proh/100w | script calls | prose steps | description |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| speckit.progress.init | 496 | 2154 | 2650 | 0 | 1.47 | 1 | 0 | ok |
| speckit.progress.refresh | 427 | 0 | 427 | 0 | 1.72 | 1 | 0 | ok |
| speckit.progress.status | 355 | 0 | 355 | 0 | 0.0 | 1 | 0 | ok |
| speckit.progress.theme | 416 | 0 | 416 | 0 | 0.0 | 1 | 0 | ok |
| speckit.progress.export | 344 | 0 | 344 | 0 | 0.0 | 1 | 0 | ok |
| extensions/progress/skills/progress/SKILL.ext.md | 2154 | 5003 | 7157 | 0 | 1.39 | 1 | 4 | skill; references 1 files, 5003 bytes |

## Summary

| extension | version | instruction bytes | tokens | conditional bytes | command bytes | words | proh/100w | script calls | prose steps | descriptions failing | catalog entries | catalog chars |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| workflow | 1.14.0 | 35558 | 8889 | 7342 | 42743 | 4736 | 1.33 | 10 | 7 | 5/13 | 13 | 3241 |
| scope | 1.8.1 | 43593 | 10898 | 2341 | 25776 | 5917 | 1.13 | 11 | 45 | 6/7 | 7 | 1638 |
| assure | 2.4.0 | 22082 | 5520 | 6530 | 22772 | 3019 | 0.76 | 10 | 18 | 0/3 | 3 | 427 |
| user-manual | 1.6.0 | 26820 | 6705 | 7121 | 24266 | 3332 | 0.78 | 11 | 55 | 0/4 | 4 | 532 |
| pr | 4.3.0 | 23957 | 5989 | 5201 | 23957 | 3358 | 0.63 | 24 | 33 | 0/2 | 2 | 276 |
| project | 2.3.0 | 3602 | 900 | 0 | 3602 | 495 | 0.4 | 6 | 8 | 0/2 | 2 | 280 |
| illustrate | 2.5.0 | 249775 | 62443 | 52088 | 65890 | 31939 | 0.38 | 46 | 135 | 0/4 | 4 | 549 |
| memory | 2.3.0 | 29717 | 7429 | 2008 | 31862 | 4012 | 1.17 | 11 | 27 | 0/7 | 7 | 983 |
| progress | 1.3.0 | 9195 | 2298 | 0 | 4192 | 1387 | 1.08 | 6 | 4 | 0/5 | 5 | 678 |
| all | | 444299 | 111071 | 82631 | 245060 | 58195 | 0.66 | 135 | 332 | 11/47 | 47 | 8604 |

## Duplicates (top 25 of 4)

| paragraph | words | files |
| --- | ---: | --- |
| when generating a new diagram, keep these intact in the template: - the two cdn  | 131 | extensions/illustrate/skill/references/technical-color-architecture.md, extensions/illustrate/skill/references/technical-color-process-flow.md |
| every diagram ships with a single unobtrusive ⋯ toggle in the header. click it t | 91 | extensions/illustrate/skill/references/technical-color-architecture.md, extensions/illustrate/skill/references/technical-color-process-flow.md |
| caveats: clipboard api needs a user gesture and a secure context (https/file/loc | 36 | extensions/illustrate/skill/references/technical-color-architecture.md, extensions/illustrate/skill/references/technical-color-process-flow.md |
| set --format, --size, --detail, and --audience from [output-spec.md](output-spec | 36 | extensions/illustrate/skill/references/import-excalidraw.md, extensions/illustrate/skill/references/import-mermaid.md |
