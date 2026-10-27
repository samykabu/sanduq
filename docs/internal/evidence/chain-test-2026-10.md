# Chain acceptance check, October 2026 (PH-02-T15)

Findings: SEC-01 (delegated workers launched with the whole parent environment) and SEC-04 (no rules on
`main`). The chain to break: a delegated worker holds the owner's GitHub token, pushes to `main`, and the
release workflow publishes whatever lands there. The check has two parts:

- (a) a push to `main` by a token without bypass is rejected (PH-01 ruleset). **Done, recorded below.**
- (b) a delegated worker starts without `GH_TOKEN` / `GITHUB_TOKEN` unless its route needs GitHub (PH-02
  clean-environment launch). **To run after the delegation stream merges.**

Part (a) alone already stops a token holder from pushing to `main`. Part (b) stops a worker from holding the
token in the first place. A push that does land on `main` (through a merged pull request) still cannot
publish by itself: `release-extensions.yml` publishes only when `extensions/pending-releases.json` is
`ready`, the push `ci` run for that commit succeeded and, from PH-02-T11, a scheduled or dispatched `ci`
run with the Windows legs succeeded on the same commit.

## Part (a): a non-bypass push to `main` is rejected

Run on 2026-10-26 (UTC) from a Windows workstation, as `samykabu` (the repository owner, an admin token
with `repo` and `workflow` scopes). If the owner's token is refused, every weaker token is too.

### 1. The ruleset (read-only)

`gh api repos/samykabu/sanduq/rules/branches/main` returned four active rules, all from ruleset
`25877966`:

| rule | parameters |
| --- | --- |
| `deletion` | none |
| `non_fast_forward` | none |
| `pull_request` | 0 approvals; merge, squash and rebase allowed |
| `required_status_checks` | `lint` (integration 15368), not strict |

`gh api repos/samykabu/sanduq/rulesets/25877966 --jq '{name,enforcement,bypass_actors,current_user_can_bypass,conditions}'`:

```json
{"name":"main-protection","enforcement":"active","bypass_actors":[],
 "current_user_can_bypass":"never",
 "conditions":{"ref_name":{"exclude":[],"include":["refs/heads/main"]}}}
```

No bypass actors, and the API itself says the current (owner) token can never bypass.

### 2. The attempted push

In a disposable shallow clone under `%TEMP%` (deleted afterwards), one empty commit on top of `main`, so the
push was a fast-forward and only the ruleset could refuse it:

```text
git clone --depth 1 --branch main https://github.com/samykabu/sanduq.git <temp>
git commit --allow-empty -m 'chain-test: throwaway direct push to main (must be rejected)'
  HEAD   846d636330160dee95024de701c3ca6f36269a76
  parent 4dd0d9245cfb50ca14474e46e7d074557184a37c (main at 2026-10-26T23:04:39Z)
git push origin HEAD:main
```

Output (exit code 1):

```text
remote: error: GH013: Repository rule violations found for refs/heads/main.
remote: Review all repository rules at https://github.com/samykabu/sanduq/rules?ref=refs%2Fheads%2Fmain
remote:
remote: - Changes must be made through a pull request.
remote:
remote: - Required status check "lint" is expected.
remote:
To https://github.com/samykabu/sanduq.git
 ! [remote rejected] HEAD -> main (push declined due to repository rule violations)
error: failed to push some refs to 'https://github.com/samykabu/sanduq.git'
```

`git ls-remote origin refs/heads/main` afterwards: `4dd0d9245cfb50ca14474e46e7d074557184a37c`, unchanged.

Result: **pass**. To repeat it, run the same commands; any result other than `GH013` and an unchanged
`main` is a failure of SEC-04.

## Part (b): the worker environment lacks the token

Status: **to run after the delegation stream merges.** It needs the PH-02 change to
`extensions/workflow/scripts/delegate_dispatch.py` (SEC-01: `--clean-env` with a `--keep-env` allowlist,
`GH_TOKEN` / `GITHUB_TOKEN` kept only for routes with GitHub access, `--sandbox` for read-only review
routes, and `clean_env` / `kept_env_names` / `permission` in the attempt ledger).

### Procedure

1. With the delegation change merged, set `GH_TOKEN=chain-test-sentinel` and
   `GITHUB_TOKEN=chain-test-sentinel` in the test process, plus one unrelated name
   (`CHAIN_TEST_LEAK=1`).
2. Point the dispatcher at the fake harness the delegation tests already use (a stand-in agent CLI that
   writes its own `os.environ` names and its argv to a JSON file and exits 0). No model is called.
3. Start one attempt per route type: an implementation route without GitHub access, an orchestrator or
   decision route that declares GitHub access, and a `review` route.
4. Read each fake-harness dump and the attempt's `meta.json` / ledger entry.

### Assertions (fake-harness test names)

| test | asserts |
| --- | --- |
| `test_worker_env_has_no_github_token_without_github_access` | the implementation route's dump has neither `GH_TOKEN` nor `GITHUB_TOKEN`, and no `CHAIN_TEST_LEAK` |
| `test_worker_env_keeps_github_token_only_when_route_declares_it` | the GitHub route's dump has `GH_TOKEN`; its ledger lists it in `kept_env_names` |
| `test_worker_env_is_exactly_the_allowlist` | every dumped name is in `keep_env_names(harness, env, github)` plus the driver's own runtime names |
| `test_driver_argv_has_clean_env_and_keep_env_per_name` | argv holds `--clean-env` and one `--keep-env <name>` per kept name |
| `test_review_route_starts_with_sandbox_not_bypass` | the review route's argv holds `--sandbox`; its ledger says `permission: sandbox` |
| `test_meta_records_clean_env_and_kept_names` | `meta.json` has `clean_env: true` and the kept names for every attempt |

Pass condition, matching SEC-01's acceptance: no worker without declared GitHub access sees either token,
review routes start read-only, and the ledger records `clean_env=true` with the kept names. Record the
command, the commit it ran on and the test output in this file under a new heading when it has run.
