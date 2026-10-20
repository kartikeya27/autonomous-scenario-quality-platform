# Autonomous Scenario Quality & Maintenance Platform

![Python](https://img.shields.io/badge/Python-3.11%2B-blue) ![Storage](https://img.shields.io/badge/Database-SQLite-lightgrey) ![Tests](https://img.shields.io/badge/Tests-unittest-green) ![Environment](https://img.shields.io/badge/Runtime-Localhost-orange)

An **independent, local-first engineering portfolio demo** showing how teams can validate synthetic autonomous-driving test scenarios, prioritize quality reviews, track test-health problems, and record maintenance actions. Built with Python and SQLite; runs on macOS without paid services, a cloud account, or external Python packages.

> **Disclaimer:** Inspired by publicly described scenario quality and maintenance engineering responsibilities. This project is **not affiliated with Waymo** and uses **only synthetic data**. Its heuristic risk scores are not suitable for real vehicle safety decisions.

## Table of contents

1. [Why this project exists](#why-this-project-exists)
2. [What the application does](#what-the-application-does)
3. [Architecture and data flow](#architecture-and-data-flow)
4. [Technology stack](#technology-stack)
5. [Repository structure](#repository-structure)
6. [Prerequisites](#prerequisites)
7. [Run locally on a Mac](#run-locally-on-a-mac)
8. [Explore the dashboard](#explore-the-dashboard)
9. [Command reference](#command-reference)
10. [REST-style JSON endpoints](#rest-style-json-endpoints)
11. [Run the automated tests](#run-the-automated-tests)
12. [How quality scoring and maintenance work](#how-quality-scoring-and-maintenance-work)
13. [Upload to GitHub](#upload-to-github)
14. [Troubleshooting](#troubleshooting)
15. [Current limitations and roadmap](#current-limitations-and-roadmap)

## Why this project exists

Large-scale scenario testing creates practical quality engineering challenges:

- Test scenarios may not include sufficient evidence of observed behavior.
- A scenario can behave differently than its expected result.
- Repeated failures can indicate an underlying defect or an unreliable test.
- Flaky or out-of-date tests consume investigation time.
- Teams need a consistent way to prioritize work and record decisions.

This demo assembles these concerns into one reproducible local workflow. It is intended to demonstrate systems test engineering, Python/SQL automation, test health, issue triage, and traceable quality reviews—not autonomous vehicle control or simulation physics.

## What the application does

| Capability | Implemented behavior |
| --- | --- |
| Synthetic scenario generation | Creates deterministic example records for intersections, pedestrians, lane changes, unprotected turns, and construction. |
| Quality evaluation | Flags missing evidence, unexpected behavior, high failure rates, flaky tests, and stale tests. |
| Risk prioritization | Calculates a bounded heuristic risk score and sorts scenarios highest-risk first. |
| Maintenance queue | Creates issue records with recommended investigation actions. |
| Audit trail | Records dataset initialization, evaluation, and maintenance-resolution notes. |
| Local dashboard | Displays health totals, the top 25 risk-ranked scenarios, the top 30 open issues, and recent audit activity. |
| JSON APIs | Exposes summary metrics, risk-ranked scenarios, and open issues. |
| Automated validation | Includes Python `unittest` tests and a GitHub Actions CI workflow. |

### Example workflow

1. Generate 250 synthetic scenarios.
2. Evaluate each record using deterministic quality rules.
3. Inspect healthy/unhealthy totals and open findings.
4. Investigate the highest-risk scenarios in the dashboard.
5. Enter a maintenance-review note and mark an issue resolved.
6. Inspect the audit trail showing that the review action was recorded.

**Important:** Resolving a maintenance issue **does not automatically fix the scenario** or switch it to healthy. A real system would require validation and re-execution evidence before doing that.

## Architecture and data flow

```text
                   +------------------------+
                   |  CLI: python -m        |
                   |  scenario_quality      |
                   +-----------+------------+
                               |
               +---------------+------------------+
               |               |                  |
       +-------v------+ +------v-------+  +-------v-------+
       | Scenario     | | Quality      |  | Risk scoring  |
       | generator    | | evaluator    |  | and ranking   |
       +-------+------+ +------+-------+  +-------+-------+
               |               |                  |
               +---------------+------------------+
                               |
                       +-------v--------+
                       | SQLite         |
                       | scenarios      |
                       | issues         |
                       | audit_log      |
                       +-------+--------+
                               |
                       +-------v--------+
                       | Python HTTP    |
                       | dashboard/API  |
                       +-------+--------+
                               |
                     http://127.0.0.1:8000
```

The `scenario_quality.core` module handles the database, deterministic test-data generation, evaluation rules, risk ranking, summary metrics, and issue resolution. `scenario_quality.webapp` serves the HTML dashboard and JSON endpoints; `scenario_quality.__main__` defines the command-line interface.

## Technology stack

- **Python 3.11+** — application and command-line interface
- **SQLite** — local tables for `scenarios`, `issues`, and `audit_log`
- **Python standard-library HTTP server** — dashboard and JSON APIs
- **HTML/CSS** — dashboard UI generated by the server
- **`unittest`** — automated regression tests
- **GitHub Actions** — tests and smoke checks on pushes and pull requests

No Docker, Node.js, AWS, external API key, or `pip install` is required for the current starter.

## Repository structure

```text
autonomous-scenario-quality-platform/
├── .github/
│   └── workflows/
│       └── ci.yml              # Automated tests and smoke checks
├── scenario_quality/
│   ├── __init__.py
│   ├── __main__.py              # CLI: init/evaluate/report/sample/serve
│   ├── core.py                  # SQLite, scenario generator, quality rules
│   └── webapp.py                # Local HTML dashboard and JSON APIs
├── tests/
│   └── test_core.py            # unittest suite
├── .gitignore
├── requirements.txt            # Notes: no external runtime requirements
└── README.md
```

The generated `scenario_quality.db` database and `.venv/` virtual environment are **local-only** and should not be committed to Git.

## Prerequisites

- macOS Terminal (other systems with Python 3.11+ should work, but the commands below target Mac)
- Python **3.11 or newer**
- Git, if you want to publish to GitHub
- A browser such as Chrome or Safari

Check your tools:

```bash
python3 --version
git --version
```

If `python3` is missing or older than 3.11, install an appropriate Python release before continuing.

## Run locally on a Mac

### Step 1 — Open the project folder

If the ZIP was extracted in your Downloads folder:

```bash
cd ~/Downloads/autonomous-scenario-quality-platform
```

If you saved it elsewhere, use that actual location. Confirm you are in the repository root:

```bash
pwd
ls -la
```

You should see `README.md`, `scenario_quality/`, and `tests/`.

### Step 2 — Create a Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python --version
```

Your prompt should now include `(.venv)`. This application uses only the Python standard library, so you **do not need to install dependencies**.

### Step 3 — Initialize 250 synthetic scenarios

```bash
python -m scenario_quality init --count 250
```

Expected message:

```text
Loaded and evaluated 250 scenarios in scenario_quality.db
```

This creates `scenario_quality.db` in the current folder, loads a **repeatable** set of scenarios (random seed `42`), runs quality checks, and populates maintenance findings.

**Warning:** Running `init` again deletes and regenerates the demo's existing scenario, issue, and audit-log data. Do not run it after recording maintenance-review actions you want to preserve.

### Step 4 — Display the quality summary

```bash
python -m scenario_quality report
```

Example output for the starter's default deterministic dataset:

```json
{
  "total": 250,
  "healthy": 112,
  "unhealthy": 138,
  "health_pct": 44.8,
  "open_issues": 175,
  "resolved_issues": 0
}
```

These numbers describe synthetic demo records, not real-world autonomous-driving performance.

### Step 5 — Inspect high-risk scenarios

```bash
python -m scenario_quality sample --size 10
```

This prints the **10 highest-risk scenarios** as JSON. Despite the command name `sample`, the implementation is a **sorted, risk-prioritized selection**; it is **not** random statistical sampling or a formal AQL procedure.

### Step 6 — Run the tests

```bash
python -m unittest discover -s tests -v
```

The initial project includes six tests. A successful execution ends with `OK`.

### Step 7 — Start the local dashboard

```bash
python -m scenario_quality serve --port 8000
```

Expected message:

```text
Local dashboard: http://127.0.0.1:8000
```

Open **http://127.0.0.1:8000** in your browser. Keep this Terminal window running while you use the dashboard.

To stop the server, return to Terminal and press **Control+C**.

When you are finished with the Python virtual environment:

```bash
deactivate
```

### Quick start (after initial setup)

```bash
cd ~/Downloads/autonomous-scenario-quality-platform
source .venv/bin/activate
python -m scenario_quality serve --port 8000
```

If the database does not yet exist, first run `python -m scenario_quality init --count 250`.

## Explore the dashboard

At **http://127.0.0.1:8000**, review these sections:

1. **Quality metrics** — total records, healthy and unhealthy records, percentage healthy, and maintenance issue counts.
2. **Priority scenarios** — top 25 scenarios ordered by calculated risk score.
3. **Open maintenance work** — up to 30 high-priority open findings, suggested investigation actions, and a resolution-note form.
4. **Audit log** — most recent 12 logged operations, including review notes.

### Demonstrate issue resolution

1. Find a row in **Open maintenance work**.
2. Enter an investigation or review note in the text field.
3. Click **Mark resolved**.
4. Confirm the resolved-issue count increased and the audit log contains the recorded action.

Closing the issue records an **administrative review action**, not an actual fix to scenario behavior. The scenario status remains governed by evaluation findings.

## Command reference

Run these commands from the repository root with your virtual environment activated:

| Command | What it does |
| --- | --- |
| `python -m scenario_quality init --count 250` | Resets and rebuilds the demo data, then evaluates it. |
| `python -m scenario_quality evaluate` | Re-runs evaluation rules against the current scenarios. |
| `python -m scenario_quality report` | Prints aggregate health and issue counts as JSON. |
| `python -m scenario_quality sample --size 20` | Prints the 20 highest-risk scenarios as JSON. |
| `python -m scenario_quality serve --port 8000` | Starts the localhost dashboard and APIs. |
| `python -m unittest discover -s tests -v` | Runs automated unit tests. |

You can point CLI commands to a separate SQLite database using `--db`:

```bash
python -m scenario_quality init --db demo_alt.db --count 100
python -m scenario_quality report --db demo_alt.db
python -m scenario_quality serve --db demo_alt.db --port 8001
```

The supported `--count` range is **1–100,000**. This is an input limit, **not a verified performance benchmark**.

## REST-style JSON endpoints

Once the local server is running, open another Terminal window and try:

```bash
curl http://127.0.0.1:8000/api/summary
curl http://127.0.0.1:8000/api/sample
curl http://127.0.0.1:8000/api/issues
```

| Route | Method | Response |
| --- | --- | --- |
| `/` | GET | HTML dashboard |
| `/api/summary` | GET | Aggregate scenario and issue counts |
| `/api/sample` | GET | Risk-ordered scenario records (default top 20) |
| `/api/issues` | GET | Up to 100 open issue records (issue-ID order) |
| `/resolve` | POST | Form submission to resolve an issue and create an audit entry |

These endpoints are intended for **local demonstration only**. The server binds to `127.0.0.1` and does not implement production authentication or authorization.

## Run the automated tests

From the project root:

```bash
python -m unittest discover -s tests -v
```

## How quality scoring and maintenance work

### Example scenario data

Each synthetic scenario has fields such as:

- `id`, `kind`, and `weather`
- `severity` (1–5)
- `runs` and `failures`
- `flaky` (boolean-like integer)
- `age_days`
- `owner`
- `expected_behavior` and `observed_behavior`
- Calculated `risk` and `status`

### Classification rules

A scenario is marked **unhealthy** when one or more of these conditions is true:

| Finding | Trigger |
| --- | --- |
| Missing evidence | `observed_behavior` is empty |
| Unexpected behavior | Observed behavior differs from expected behavior |
| High failure rate | Failures / runs is at least **15%** |
| Flaky test | `flaky` flag is set |
| Stale test | `age_days` is greater than **60** |

Multiple findings can be raised for one scenario. Each finding can create an open issue with a suggested investigation action.

### Risk scoring

The code calculates a heuristic score bounded at 100:

```text
risk = min(100,
    18 × severity
    + 65 × (failures / max(runs, 1))
    + 20 if flaky
    + 15 if age_days > 60
    + 18 if observed_behavior is missing
)
```

The actual source implementation is in `scenario_quality/core.py`. The equation is for **demo prioritization only**: the weights are illustrative and have not been validated against operational safety risk.

### Maintenance lifecycle

```text
Quality rule finds a problem
           |
           v
   Open issue is created
           |
           v
  Engineer reviews evidence
           |
           v
 Resolution note is recorded
           |
           v
  Issue marked resolved
           |
           v
 Scenario remains as evaluated
```

This intentionally separates **issue tracking** from **verified test-health recovery**.


```

## Troubleshooting

**`No module named scenario_quality`**

Run the command from the **repository root** where `scenario_quality/` is located, not from inside the package directory.

**`python: command not found`**

Activate `.venv` with `source .venv/bin/activate`, or use `python3` instead.

**`Address already in use`**

Another process is using port 8000. Stop the old server with `Control+C` or use:

```bash
python -m scenario_quality serve --port 8001
```

Then open http://127.0.0.1:8001.

**Dashboard shows zero scenarios**

Initialize your database:

```bash
python -m scenario_quality init --count 250
```

## local-first engineering additions

provides tested **local prototypes** of statistical design, signed replay evidence, workers, API controls, and performance measurement. It does **not** claim full ISO certification, real vehicle interoperability, or enterprise production readiness.

### Setup (macOS, Python 3.11+)

```bash
cd autonomous-scenario-quality-platform-v3
python3 -m venv .venv
source .venv/bin/activate
python -m unittest discover -s tests -v
python -m scenario_quality init --count 250
python -m scenario_quality serve --port 8000
```

Open http://127.0.0.1:8000. **Never expose the built-in HTTP server to the Internet.** The development server binds only to loopback.

### Exact finite-lot acceptance sampling (not ISO 2859-1 table lookup)

```bash
python -m scenario_quality aql-plan --count 250 --n 40 --c 2 --aql 0.01 --lq 0.10
```

Reports acceptance number, rejection number, exact hypergeometric operating-characteristic probabilities, and estimated producer/consumer risks for an explicitly specified single-sampling plan. It does **not** automatically select the legally/contractually appropriate plan from ISO 2859-1 lot size, inspection level, and switching rules. `--aql` here means an **assumed defect fraction for operating-characteristic analysis**, not formal ISO AQL compliance. Review your sampling plan with a qualified quality/statistics engineer.

### Stratified population estimate with design weights

```bash
python -m scenario_quality design-ci --n 60 --seed 42
```

Reports population stratum weights, random draws, a weighted defect-rate estimate, finite population variance correction, approximate 95% normal confidence interval, and weight-only Kish design-effect diagnostic. Small strata with `n=1` do not have estimable within-stratum variance; the reported interval may understate uncertainty. This is a demonstrator, not a verified survey inference library.

### Cryptographically signed local replay evidence and provenance

```bash
export SCENARIO_SIGNING_KEY='replace-with-a-long-random-local-secret'
python -m scenario_quality replay --scenario-id 1
# copy artifact_id from result
python -m scenario_quality verify-artifact --artifact-id 1
```

Replay runs a deterministic **synthetic rule adapter**, stores a snapshot of scenario inputs, observed and expected behavior, Python version, runner version, optional `GIT_REVISION`, configuration digest, and HMAC-SHA256 signature. Tampering with stored payload invalidates the signature. This is authenticity under a shared local secret **not** hardware-backed signing, a real simulator run, or trusted build attestation. Do not commit signing secrets.

### Local work queue with multiple consumers

```bash
python -m scenario_quality queue --count 100
python -m scenario_quality worker --count 100
```

Use two Terminal windows running `python -m scenario_quality worker --count 100` simultaneously to demonstrate contention-safe SQLite `BEGIN IMMEDIATE` job claiming. This is **multi-process capable on one machine**, not a fault-tolerant distributed broker. There are no leases/retries after worker crash or network job transport.

### Hardware-labelled concurrency benchmark

Run against a **throwaway database**, because benchmarking resets its demo scenario data:

```bash
python -m scenario_quality loadtest --db benchmark_only.db --count 1000 --workers 4
```

Outputs p50/p95/p99 observed job durations, synthetic job throughput, Python/SQLite/platform versions, CPU count, and concurrency. Compare repeated runs on the **same hardware, same workload and same Python version** before claiming improvements. The benchmark is a local SQLite/threads experiment and is **not evidence of autonomous-driving test infrastructure scale**.

### API authentication and CSRF / RBAC demo

By default the HTTP server is open to the local machine only. To require tokens:

```bash
export SCENARIO_TOKENS='my-read-token:viewer,my-write-token:operator,my-approve-token:approver'
python -m scenario_quality serve --port 8000
# Another terminal:
curl -H 'Authorization: Bearer my-read-token' http://127.0.0.1:8000/api/summary
curl -H 'Authorization: Bearer my-read-token' http://127.0.0.1:8000/metrics
```

Roles: viewer (`read`), operator (`read,resolve`), approver (`read,resolve,approve`). Write operations require a matching role. The browser maintenance form uses a same-site, signed CSRF token; when bearer authorization is configured, use an HTTP client that supplies the header. This is a **local static-token illustration**, not enterprise-grade identity. The local UI does not provide a login screen.

### Observability

- `/healthz`: basic liveness JSON
- `/metrics`: Prometheus-text-formatted current scenario counters
- SQLite `audit_log`, `jobs`, `replay_artifacts`: local evidence and audit trail

**Not implemented:** OpenTelemetry distributed tracing, Prometheus server setup/dashboards, retention, alerting, or instrumented production request latency.

### Repair workflow: important integrity limit

The existing V2 `propose`, `approve`, `verify` commands still operate on **synthetic stale-test remediation**. They do **not** apply executable simulator patches, do not prove real-world repairs, and must not be used to claim a true patched-simulator verification. The new `replay` command re-evaluates real values stored in the synthetic scenario and **does not override a failing result to pass**. Real patch application needs an explicitly provisioned sandbox simulator/test-runner with patch provenance and rollback controls.

### Boundaries and remaining production requirements

| Capability |  status |
|---|---|
| Exact hypergeometric OC curves and configurable acceptance plans | Implemented local prototype |
| ISO 2859-1 certified AQL table lookup and switching rules | Not implemented |
| Design-weighted stratified estimate + approximate CI | Implemented local prototype |
| Synthetic replay with signed payload and environment metadata | Implemented local prototype |
| Genuine third-party simulator replay and software patch verification | Not implemented |
| Local role-based bearer tokens and HTML CSRF | Implemented demo |
| External OIDC login, JWKS JWT signature verification, session lifecycle | Not implemented |
| Secret manager and managed HTTPS/TLS ingress | Not implemented |
| SQLite concurrency-safe work queue | Implemented local multi-process capability |
| Distributed cluster scheduling and crash-safe retries | Not implemented |
| Basic Prometheus metrics endpoint | Implemented demo |
| End-to-end OpenTelemetry trace correlation and production monitoring | Not implemented |
| Reproducible hardware-labelled local p50/p95/p99 | Implemented local benchmark 