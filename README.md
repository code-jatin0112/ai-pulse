# AI Pulse — Engineering Assessment & Implementation

AI Pulse is an enterprise AI readiness assessment platform designed to help organizations measure and improve how teams leverage artificial intelligence, while strictly protecting employee privacy and preventing cross-tenant data leaks.

---

## 1. Project Overview

AI Pulse provides two tailored experiences:
- **For Employees**: Authenticate, select an active organization, and complete an adaptive diagnostic tailored to their role and seniority. Diagnostics include multiple-choice questions and an open-ended practical scenario evaluated by an LLM scoring engine. Upon completion, employees receive an individualized personal report showing their AI maturity level, specific risk flags, generic next steps, and **My AI Growth Insights**—a 4-pillar competency breakdown identifying their key strength and priority improvement area. Employees have the autonomous right to permanently delete their diagnostic data.
- **For Organization Administrators**: View an aggregated company-wide dashboard detailing team maturity levels, participation rates, and organizational AI risk exposures. Departmental scores and risk tags are strictly suppressed unless a privacy threshold of at least five distinct completed diagnostics is satisfied. Cross-tenant access is strictly denied.

---

## 2. Technology Stack

- **Backend API**: Python 3.12, FastAPI, Starlette, Uvicorn
- **Data & ORM**: SQLAlchemy 2.0, SQLite (default local file `aipulse.db`), PostgreSQL compatible
- **Validation & Schemas**: Pydantic v2
- **Authentication**: JWT (JSON Web Tokens) with cryptographically validated signing secrets (`pyjwt`)
- **Testing**: pytest, Starlette `TestClient`, anyio
- **Frontend SPA**: React 18, Vite 5, standard modern CSS
- **AI Scoring Engine**: Pluggable architecture supporting `AI_MODE=mock` (reproducible deterministic canned evaluation) and `AI_MODE=live` (OpenAI-compatible HTTP chat completions via `httpx` with retries and timeout boundaries)

---

## 3. Local Setup & Reproducible Execution

### Prerequisites
- Python 3.12 (Verify with `python3.12 --version` or `python3 --version`. Note: on macOS, the default system `/usr/bin/python3` is Python 3.9.6. Ensure Python 3.12 is installed, e.g. via Homebrew: `brew install python@3.12`).
- Node.js 18+ and npm (`node -v`, `npm -v`)

### Step 1: Backend Setup

```bash
cd backend

# 1. Verify Python 3.12 and create a virtual environment
python3.12 --version  # Must output Python 3.12.x
python3.12 -m venv .venv || python3 -m venv .venv
source .venv/bin/activate

# Confirm active interpreter is Python 3.12:
python --version

# 2. Install backend dependencies (including bcrypt)
pip install -r requirements.txt

# 3. Create .env from template and configure a cryptographically secure JWT secret
cp .env.example .env

# Generate a strong 64-character hex secret and insert it directly into .env (without printing):
python -c "import secrets; key = secrets.token_hex(32); content = open('.env').read().replace('replace-with-a-secure-random-secret-key-at-least-32-chars', key); open('.env', 'w').write(content)"

# 4. Seed initial demonstration data with secure bcrypt hashes (all user passwords: pulse123)
python -m app.seed

# 5. Start the FastAPI backend server
# Standard port 8000:
uvicorn app.main:app --reload

# Alternatively, if port 8000 is occupied, run on port 8001:
uvicorn app.main:app --reload --port 8001
```

### Step 2: Frontend Setup

```bash
cd frontend

# 1. Install dependencies
npm install

# 2. Configure environment (optional, defaults to http://localhost:8001 on port 5174)
cp .env.example .env
# Edit .env if pointing to a custom port (e.g., VITE_API_URL=http://localhost:8000, VITE_PORT=5173)

# 3. Start the Vite development server
npm run dev
```

The frontend will run at `http://localhost:5174` (or `http://localhost:5173` if configured).

### Configuration Matrix

| Component | Standard / Default | Tested Alternative (When 8000/5173 Occupied) | Configuration Variable |
|---|---|---|---|
| **Backend Port** | `8000` | `8001` | `--port 8001` in uvicorn command |
| **Frontend Port** | `5173` | `5174` | `VITE_PORT` in `frontend/.env` |
| **Frontend API Target** | `http://localhost:8000` | `http://localhost:8001` | `VITE_API_URL` in `frontend/.env` |
| **AI Mode** | `mock` | `live` | `AI_MODE` in `backend/.env` |

### Step 3: Run Automated Tests & Production Build

```bash
# Run full backend test suite (90 passing tests)
cd backend
pytest

# Verify frontend production build
cd frontend
npm run build
```

---

## 4. What I Found and Fixed

During the technical review and security audit of the initial codebase, several critical architectural and security defects were identified and resolved:

1. **Flawed Seniority Comparison**:
   - *Problem*: In `questions.py`, seniority ranks were compared using raw string checks or string list membership, incorrectly filtering out eligible senior questions.
   - *Fix*: Introduced an explicit hierarchical ranking dictionary (`SENIORITY_RANKS = {"junior": 1, "mid": 2, "senior": 3, "lead": 4}`) ensuring users receive strictly eligible questions for their rank.
2. **Cross-Tenant Dashboard Authorization Bypass**:
   - *Problem*: In `dashboard.py`, any authenticated admin from Organization A could view full analytics for Organization B simply by supplying `?org_id=B` in query parameters.
   - *Fix*: Enforced strict tenant scoping: `if m.org_id != org_id: raise HTTPException(403, "Not authorized for this organization")`.
3. **Unauthorized Organization Selection**:
   - *Problem*: The `/auth/select-org` endpoint allowed users to request an authentication token for any arbitrary organization ID without validating membership.
   - *Fix*: Verified that the user possesses a valid `Membership` record for the requested `org_id` before issuing a scoped token.
4. **Hardcoded / Weak JWT Secret Key**:
   - *Problem*: The application fell back to hardcoded insecure strings (`"ai-pulse-dev-secret"`), and accepted empty or trivially short secrets.
   - *Fix*: Enforced a minimum 32-character requirement (`MIN_SECRET_LENGTH = 32`), rejected known compromised placeholder defaults (`DISALLOWED_SECRETS`), and required validated environment configuration without leaking secret values in exceptions.
5. **Incomplete and Duplicate Diagnostic Submissions**:
   - *Problem*: Submissions permitted partial question responses, accepted duplicate answers for the same question, and appended rows into the database without replacing older attempts.
   - *Fix*: Added comprehensive payload validation verifying: no duplicate question IDs, exact set-equality with assigned questions for the user's role and seniority, and executed atomic deletion and replacement in a single database transaction.
6. **Weak Open-Ended & MCQ Input Validation**:
   - *Problem*: Open-ended questions allowed blank inputs or arbitrarily large payloads; MCQ answers were not checked against valid option choices.
   - *Fix*: Enforced non-blank answers, length limits ($\le 5000$ characters), and strict option membership validation for MCQs before invoking scoring.
7. **Unvalidated AI Output & Unsafe Exception Leaks**:
   - *Problem*: LLM scoring did not validate response schema, allowing arbitrary JSON or invalid scores ($>5$), accepted invented risk flags, and leaked internal stack traces with HTTP 500 errors.
   - *Fix*: Built a strict Pydantic model (`AIScoreOutput`) validating bounded numeric scores ($1.0 \le \text{score} \le 5.0$), non-empty reasons ($\le 1000$ chars), and whitelisted risk flags (`APPROVED_RISK_FLAGS`). Handled Markdown code fences safely, logged sanitized errors without sensitive data, and returned safe HTTP 502 user notices.
8. **Silent Fallback for Unmapped Question IDs**:
   - *Problem*: `insights.py` used `QUESTION_CATEGORY_MAP.get(qid, "practical_application")`, silently defaulting unmapped questions to practical workflow impact.
   - *Fix*: Replaced the silent fallback with `get_question_category()` which raises a `KeyError` on unmapped questions, and added automated tests confirming all 15 question bank entries have explicit mappings.
9. **Personal Report Completion Inconsistency**:
   - *Problem*: `GET /reports/me` previously calculated averages and risk tags over incomplete responses, showing a maturity score even when `growth_insights` returned `null` and the dashboard considered the diagnostic incomplete.
   - *Fix*: Standardized personal report calculations on the canonical completion validator (`get_completed_diagnostic`). Incomplete profiles consistently report `average_score: null`, `level: "Not assessed"`, and `risks: []`.
10. **Insecure Password Storage & Missing Salt**:
   - *Problem*: Passwords were stored using unsalted single-pass SHA-256 (`hashlib.sha256`), vulnerable to dictionary and rainbow table attacks.
   - *Fix*: Upgraded password hashing to `bcrypt` with cryptographically secure random salts (work factor 12 in production, 4 in test environments). Implemented backwards-compatible constant-time verification for legacy SHA-256 hashes with automatic on-login rehashing to bcrypt. Added automated tests confirming demo users authenticate and legacy hashes migrate seamlessly.

---

## 5. Client Requirements

### 1. Small-Group Privacy Suppression ($\ge 5$ Completers)
- **Rule**: Departments with fewer than five distinct completed diagnostics are completely suppressed from the administrative dashboard.
- **Protection**: Suppressed departments omit employee counts, completer counts, average maturity scores, and maturity levels. Furthermore, risk flags from suppressed departments are excluded from the company-wide `top_risks` aggregation to prevent re-identification through unique risk signatures.
- **Scope**: Protections apply to the application's active database queries.

### 2. Employee Right to Delete (Self-Service)
- **Rule**: Employees can delete their diagnostic responses via `DELETE /diagnostic/me`.
- **Protection**:
  - Scoped strictly to the employee's authenticated organization membership.
  - Removes all diagnostic answers, scores, AI reasons, and risk flags atomically.
  - Idempotent (subsequent calls succeed safely with 0 rows deleted).
  - Immediately reflected: personal reports reset to `"Not assessed"`, growth insights disappear, and admin dashboards update immediately. If deletion reduces a department below five completers, the department is immediately re-suppressed.
- **Scope Notice**: Deletion permanently removes records from the active AI Pulse database. It does not claim control over external system cold backups or third-party LLM provider logs.

---

## 6. Original Feature — My AI Growth Insights

### Background & Rationale
Prior to this feature, employees only received a single overall score (e.g. `3.2`) and generic, static text based on their job role. This failed to provide meaningful feedback on specific strengths or actionable guidance on where to improve.

### Architecture & Competency Pillars
**My AI Growth Insights** categorizes all assigned diagnostic questions into four core AI competency pillars:
1. **Data Security & Policy Compliance**: Safe data handling, policy adherence, redacting sensitive customer details.
2. **Output Verification & Quality Review**: Fact-checking, testing, and reviewing AI suggestions prior to deployment.
3. **Adoption & Daily Habit**: Regularity and integration of AI tools into daily workflows.
4. **Practical Workflow Impact**: Concrete role-specific productivity and quality gains.

### Deterministic Calculation & Tie-Breaking
- **Deterministic Averaging**: Category scores are calculated as the unweighted arithmetic mean of assigned question scores in that pillar, clamped between 1.0 and 5.0, rounded to one decimal place.
- **Strength Tie-Breaking**: When multiple categories share the top score, practical workflow impact is prioritized, followed by output verification, data security, and adoption.
- **Improvement Tie-Breaking**: When multiple categories share the lowest score, risk reduction is prioritized (data security first, then output verification, practical workflow impact, and adoption).
- **Zero Additional API Overhead**: Growth insights are calculated deterministically in-memory from existing scored responses without triggering additional LLM API calls.
- **Employee-Only Access**: Insights are returned solely via `GET /reports/me` for the authenticated employee and are never exposed to administrators on `GET /dashboard`.
- **Reactivity**: Automatically updates on diagnostic retakes and disappears immediately upon deletion.

---

## 7. Testing & Evidence

### Test Execution Summary
- **Backend Tests**: **95 passed** across 9 test suites in `backend/tests/` (100% pass rate).
- **Frontend Production Build**: **Passed** in 439ms via `vite build` with zero compiler warnings or errors.
- **API Integration Smoke Test**: Verified complete 12-step employee workflow and 8-step administrator workflow against running FastAPI application.

### Isolated Privacy Demonstration Script
To verify the 5-completer privacy threshold without modifying the main database or changing the production threshold:

```bash
cd backend
.venv/bin/python3 scripts/demo_privacy.py
```

**Demonstration Workflow Output**:
1. *Stage 1 (4 Completers)*: 4 employees submit diagnostics. Dashboard shows `departments: []` and `top_risks: []` (Department is hidden).
2. *Stage 2 (5 Completers)*: 5th employee submits diagnostic. Dashboard shows `Customer Operations` with `5/5` completers, average score `4.17` (`Leader`), and unmasked risk tags.
3. *Stage 3 (Right to Delete: 5 $\to$ 4)*: 5th employee executes deletion. Completers drop to 4; dashboard immediately re-suppresses the department.
4. *Cleanup*: The script operates on an isolated temporary database (`/tmp/*.db`) and deletes it upon completion.

*Note on Browser Testing*: Full browser automation was restricted due to macOS sandbox execution policies blocking loopback network sockets (`net::ERR_ACCESS_DENIED`). Full end-to-end behavior was verified via ASGI HTTP integration tests, React production builds, and component state inspection. Manual verification in a real browser is recommended before final demonstration recordings.

---

## 8. Engineering Decisions and Trade-offs

1. **Server-Side Authorization Over Client Filtering**:
   - *Decision*: Authorization and tenant isolation are enforced strictly in FastAPI dependency injections (`current_membership`), returning 403 Forbidden on invalid tenant requests rather than filtering client-side.
2. **Strict Five-Person Privacy Threshold**:
   - *Decision*: Set `MIN_COMPLETERS_THRESHOLD = 5`. Department scores and aggregated risk totals are suppressed for smaller groups to prevent individual answer de-anonymization.
3. **Canonical Diagnostic Completion Rules**:
   - *Decision*: A diagnostic is only considered completed when all role- and seniority-assigned questions have non-empty answers and valid numeric scores. Both the dashboard and `/reports/me` enforce this identical rule.
4. **Atomic Transaction Replacement**:
   - *Decision*: Diagnostic submissions and retakes delete previous responses and insert new responses within a single database transaction (`db.commit()`), preventing corrupted partial states if AI scoring fails midway.
5. **Strict Pydantic AI Validation Over Flexible Fallbacks**:
   - *Decision*: Reject any malformed LLM responses rather than guessing or providing random fallback scores. If the model fails or returns unapproved risk tags, the transaction rolls back cleanly with a 502 notice.
6. **Deterministic Insights Over LLM Synthesis**:
   - *Decision*: Calculated My AI Growth Insights using deterministic category mappings and predefined recommendations rather than calling an LLM. This guarantees reproducible results, zero cost, instant response times, and zero hallucinations.
7. **Mock-Mode AI by Default**:
   - *Decision*: Enabled deterministic mock scoring based on MD5 hashing to canned responses. Half of the mock fixtures intentionally contain malformed outputs to continuously validate error handling.

---

## 9. Known Limitations and Deliberately Deferred Work

1. **Token Storage in LocalStorage**:
   - *Limitation*: JWT tokens are stored in browser `localStorage`.
   - *Deferred*: Moving to `HttpOnly`, `SameSite=Strict` secure cookies was deferred to avoid requiring HTTPS termination and domain configuration in local development.
2. **Live LLM Testing**:
   - *Limitation*: Live AI mode was designed and tested against mock endpoints and unit mocks, but was not tested against a live paid OpenAI/Claude endpoint in this offline environment.
3. **Active Database Scope of Deletion**:
   - *Limitation*: Self-service deletion removes records from the active SQLite/PostgreSQL database. It cannot scrub external LLM provider API logs or offsite system backups.

---

## 10. Client Clarifications & Future Considerations

Before deploying AI Pulse to enterprise production, the following clarifications should be resolved with the client:
1. **Definition of Completion Under Schema Migrations**: If questions are added or retired from the question bank over time, should employees with legacy submissions be marked as incomplete, or should their historical completion status be grandfathered?
   - *Current Assumption*: Diagnostic completion is dynamically evaluated against current assigned questions for the user's role and seniority.
2. **Cohort Privacy & Department Re-organizations**: If an employee transfers between departments or leaves the company, should their historical diagnostic remain attributed to their former department's five-person threshold?
   - *Current Assumption*: Membership is tied to current department association; deletion removes all responses for that membership immediately.
3. **Backup Retention & Data Erasure Compliance**: What is the company's regulatory policy regarding cold backups (e.g., 30-day rolling backup purge)?
   - *Current Assumption*: The application guarantees immediate erasure from the active operational database.
4. **Approved LLM Providers & Data Processing Agreements (DPA)**: Which enterprise LLM endpoints are approved for employee diagnostic evaluation, and does the client's agreement permit sending redacted role-task descriptions?
   - *Current Assumption*: Prompts contain only role descriptions and employee answers; risk flags identify and warn against sharing customer or confidential data.

---

## 11. AI Tool Usage & Review Transparency

In accordance with academic and engineering integrity guidelines:
- **ChatGPT**: Used during initial phases for task planning, prompt preparation, exploring alternative UX copy, and reviewing technical report structures.
- **Google Antigravity**: Used for codebase exploration, refactoring routes and services, generating test fixtures, executing regression suites, and auditing Git state.
- **Critical Human Review**: All AI-generated outputs and code were rigorously reviewed, tested, and modified before acceptance.
- **Identified AI Mistake During Development**:
  - *Initial Generation*: The initial AI-generated scoring service defined `flags: list[str] = []` with a default empty list in the Pydantic schema, making flags optional despite the specification requiring explicit risk labels. Additionally, early Pydantic validation error logging logged raw exception objects, which risked printing rejected sensitive employee answers into application logs.
  - *Correction*: Identified during code review. The schema was corrected to `flags: list[str]` (strictly required), and error logging was updated to log only sanitized error types without raw input strings. Both fixes were locked in with automated regression tests in `test_ai_scoring.py`.

---

## Demo Accounts

Password for all seeded accounts: `pulse123`

| Email | Organization(s) | Role | Notes |
|---|---|---|---|
| `asha@northwind.test` | Northwind Logistics | Admin | Northwind admin dashboard access |
| `meera@bluepeak.test` | Bluepeak Retail | Admin | Bluepeak admin dashboard access |
| `ravi@consult.test` | Both | Employee (NW), Admin (BP) | Multi-org consultant account |
| `priya@northwind.test` | Northwind Logistics | Employee (Support, Junior) | Primary employee demonstration account |
| `dev@northwind.test` | Northwind Logistics | Employee (Engineering, Lead) | Lead role adaptive questions |
| `admin@apex.test` | Apex Solutions (isolated) | Admin | Created by `scripts/demo_privacy.py` |
