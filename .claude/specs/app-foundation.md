# Software Specification Document (Implementation Addendum)

**Version:** 1.0.0
**Companion Documents:** `docs/PRD.md`, `docs/TDD.md`
**Scope:** Implementation-level behavior only

---

## 1. Scope

This document captures the implementation-level behavior required to reproduce the application exactly as it behaves in the source tree. It intentionally omits:

- Product goals, learning outcomes, and educational positioning (see PRD §Executive Summary, §1).
- Architecture diagrams and component responsibilities at a conceptual level (see TDD §2, §3).
- Technology stack justification, dependency version policy, and tooling choices (see TDD §2.2, §11.1).
- Vulnerability descriptions, exploitation walkthroughs, CVSS scores, and OWASP classifications (see PRD §3.2, §6; TDD §4, §5).
- Database schema definitions and column-level semantics beyond what is needed for runtime reproduction (see TDD §3.1.4, §11.3).
- Endpoint inventory tables and method/path listings (see TDD §3.1.2, §11.4).

Where a behavior described here conflicts with PRD/TDD wording, this addendum takes precedence for implementation purposes only; the source documents should be considered authoritative for design rationale.

---

## 2. Runtime Behavior

### 2.1 Startup

- On application boot, the database initialization routine runs unconditionally before the first request is served.
- The init routine creates the `users` table if it does not already exist (see TDD §3.1.4 for the canonical `CREATE TABLE IF NOT EXISTS users (...)` statement).
- Init is idempotent: invoking it on a database that already has the table is a no-op.

### 2.2 Missing Database File Recovery

- If the database file is absent at startup, the connection routine creates a fresh empty file at the configured path and the init routine then creates the table.
- No manual schema setup is ever required.

### 2.3 Restart Persistence

- Restarting the application process does not reset, truncate, or migrate existing user records.
- All rows previously inserted into `users` remain queryable after restart.

### 2.4 Static Assets

- All static assets (CSS, logo PNGs) are served from a `static/` mount once the application has booted.
- Asset paths under `/static/...` resolve to files on disk; no asset is missing from the served set after a clean boot.

### 2.5 Template Loading

- HTML templates are read from disk at the moment of each request.
- No in-memory template cache is used. Editing a template file on disk and reloading the page reflects the new content immediately.
- A missing template file results in an unhandled exception (see EC-06 in §12).

### 2.6 Dashboard Content Injection

- The dashboard template contains a literal placeholder token (`{{username}}`).
- The route handler performs a single-pass `str.replace('{{username}}', username)` against the raw template text before responding.
- No HTML escaping is applied during substitution.

### 2.7 Authentication State

- The presence of a `user_id` key in the session is the sole gate for authenticated routes.
- No token validation, role lookup, or DB re-check is performed on each protected request.

---

## 3. User Flows

### 3.1 Registration

1. User navigates to `/signup` and the signup template is served.
2. User fills in four fields: username, email, password, confirm-password.
3. Client-side JavaScript validates that `password === confirm-password`. If not, a red inline error appears immediately below the confirm field and the form does not submit.
4. On a valid client-side match, the browser issues a `POST /signup` with form-encoded body.
5. The handler computes the password hash and inserts a row into `users` via a string-concatenated `INSERT` statement.
6. On insert success, the handler responds with a redirect to `/login`.
7. On a unique-constraint violation (duplicate username), the handler responds with an HTML error page rendered inline that states the username is taken.

### 3.2 Login

1. User navigates to `/login` and the login template is served.
2. User fills in two fields: username and password.
3. The form's submit handler issues an asynchronous `fetch('POST', '/login', ...)` from the browser; the page does not perform a native form POST.
4. The handler computes the password hash, executes a string-concatenated `SELECT` query against `users`, and returns a JSON response.
5. On a matching row:
   - The handler sets `session['user_id']`, `session['username']`, and `session['email']`.
   - The JSON response carries success metadata that the client uses to navigate to `/welcome`.
6. On no matching row, the JSON response carries failure metadata; the client displays an inline error and stays on the login page (no full reload).

### 3.3 Dashboard

1. User requests `/welcome`.
2. The route handler inspects the session for `user_id`. If absent, redirect to `/login`.
3. If present, the handler reads `dashboard.html` from disk.
4. The handler substitutes the stored username into the template text via `str.replace`.
5. The substituted HTML is returned with `text/html` content type.

### 3.4 Logout

1. User clicks the logout control on the dashboard (a link to `/logout`).
2. The route handler clears the session.
3. The handler responds with a redirect to `/login`.
4. Any subsequent request to `/welcome` (or any other session-gated route) finds no `user_id` and redirects to `/login`.

---

## 4. Functional Requirements

| ID | Requirement | Implementation Detail |
|----|-------------|------------------------|
| FR-01 | Session Management | Starlette `SessionMiddleware` is registered on the FastAPI app. Session payload includes `user_id`, `username`, `email`. |
| FR-02 | Dynamic User Context | Dashboard response body is generated per-request by substituting the session's username into the template placeholder. |
| FR-03 | Route Protection | The `/welcome` route returns a redirect when `session.get('user_id')` is falsy. No other protected routes exist. |
| FR-04 | Error Handling | Form-level validation errors render inline. Backend errors return a FastAPI default error response (500). Missing template files propagate as unhandled exceptions. |
| FR-05 | Search Processing | `/search` reads the `q` query parameter, queries `users` for matches against both `username` and `email`, and returns an HTML response that includes the raw `q` value and any matching rows. The query parameter is reflected into the response body without escaping. |
| FR-06 | Persistence | User rows are persisted in `vulnerable_app.db` via `sqlite3`. Hashes are stored using MD5 (no salt). |

---

## 5. Complete Visual Design Specification

### 5.1 Global Design System

#### 5.1.1 Typography

- **Font stack:** `Segoe UI`, `system-ui`, `-apple-system`, `sans-serif`.

| Role | Size | Weight | Usage |
|------|------|--------|-------|
| Main titles | 2rem | 800 | Top-level page titles (e.g., dashboard hero) |
| Section titles | 1.4rem | 700 | Section headings within a page |
| Form titles | 1.7rem | 700 | Headings above login/signup forms |
| Card titles | 0.95rem | 700 | Vulnerability card headings, process step titles |
| Body | 0.9rem | 400 | Default paragraph and list text |
| Labels | 0.82rem | 600 | Form field labels |
| Buttons | 1rem | 600 | All button labels |

#### 5.1.2 Primary Color Palette

| Token | Hex | Usage |
|-------|-----|-------|
| Primary deep | `#1a237e` | Buttons, header accents, dashboard hero, decorative gradient end |
| Primary | `#3949ab` | Hover/focus accents, gradient mid-point |
| Primary dark | `#283593` | Gradient end on auth left panel |
| Slate 900 | `#0f172a` | Deep text, brand alt |
| Surface | `#eef1f8` | Page background of dashboard |
| White | `#ffffff` | Card backgrounds, form panel |

#### 5.1.3 Text Colors

| Token | Hex | Usage |
|-------|-----|-------|
| Text primary | `#1e293b` | Default body text |
| Text secondary | `#475569` | Subtitles, supporting copy |
| Text muted | `#64748b` | Captions, helper text |
| Text on primary | `#c5cae9` | Light indigo for headings on dark backgrounds |
| Brand link | `#1a237e` | Hyperlinks |

#### 5.1.4 Border Radius

| Element | Radius |
|---------|--------|
| Inputs | 8px |
| Buttons | 8px |
| Cards | 10–12px |
| Status tags / pills | 6px |

#### 5.1.5 Shadows

| Shadow name | Value | Applied to |
|-------------|-------|------------|
| Header shadow | `0 2px 10px rgba(26, 35, 126, 0.08)` | Fixed header bottom edge |
| Card hover shadow | `0 4px 16px rgba(26, 35, 126, 0.10)` | Vulnerability cards on hover |
| Focus glow | `0 0 0 3px rgba(57, 73, 171, 0.12)` | Input fields when focused |

### 5.2 Shared Header

- Position: `fixed`, top of viewport.
- Height: `70px`.
- Background: `#ffffff`.
- Border: `1px solid` bottom border using a light neutral.
- Shadow: header shadow per §5.1.5.
- Left side: app title text.
- Right side: three logo images (`54px × 54px`) displayed in a row, separated by small horizontal spacing.

### 5.3 Login Page

- Layout: two-column split-screen, `50% / 50%`.
- **Left panel (decorative):**
  - Background: linear gradient `#0d1b5e → #1a237e → #283593`.
  - Content stack (top-to-bottom, left-aligned with padding):
    - Small uppercase badge label.
    - Welcome heading (light indigo text color).
    - Description paragraph.
    - Bullet list of feature/value statements.
  - Decorative overlay: two or more semi-transparent white circles at ~7% opacity positioned as background flourishes.
- **Right panel (form):**
  - Background: `#ffffff`.
  - Form container: max width `400px`, horizontally centered within the panel, vertically centered.
  - Form contents (in order):
    1. Form title.
    2. Subtitle / helper line.
    3. Username input.
    4. Password input.
    5. Error message area (hidden when no error).
    6. Full-width login button (`#1a237e` background, white text).
    7. "Don't have an account?" link to `/signup`.

#### 5.3.1 Input Styling

- Background: `#f8f9ff`.
- Border: `1.5px solid #c5cae9`.
- Border radius: 8px.
- On focus: border color changes to `#3949ab` and focus glow shadow appears.

#### 5.3.2 Error Message Styling

- Background: light red (e.g., `#fef2f2`).
- Border: thin red border.
- Text: dark red.

### 5.4 Signup Page

- Identical outer structure to login: same two-column split, same gradient left panel, same decorative circles, same white right panel with a max-`400px` form container.
- Form contents (in order):
  1. Form title.
  2. Subtitle / helper line.
  3. Username input.
  4. Email input.
  5. Password input.
  6. Confirm-password input.
  7. Error message area.
  8. Full-width signup button (`#1a237e` background, white text).
  9. "Already have an account?" link to `/login`.
- Validation behavior: if `password !== confirmPassword` at submit time, a red inline message is rendered immediately below the confirm field. **No page reload occurs.** The form does not submit while the mismatch is present.

### 5.5 Dashboard Page

- Page background: `#eef1f8`.
- Header: as per §5.2 (fixed).
- **Hero banner:** directly below the header.
  - Background: linear gradient `#1a237e → #3949ab`.
  - Left section: page title + subtitle (light indigo text).
  - Right section: the logged-in username as a label, plus a semi-transparent white logout button.
- **Content area:** centered, `max-width: 1100px`.
- **Mission card:** white card, rounded (`10–12px`), light border, containing a section title and description paragraph.
- **"Vulnerabilities to Discover" section:**
  - Uppercase, small, bold header.
  - Two-column grid of 8 vulnerability cards.
  - Each card: white background, rounded corners, light border, hover triggers card-hover shadow.
  - Each card contains:
    - A colored pill tag (top-left or top-right) using the per-category color (see §5.5.1).
    - A title.
    - A description paragraph.
- **Process steps section:** three cards in a row (collapses vertically on small viewports).
  - Card background: `#1a237e`.
  - Each card has a circular numbered badge (white-on-primary) and white text.
  - Step labels (in order): **Find**, **Exploit**, **Mitigate**.

#### 5.5.1 Vulnerability Tag Colors

| Category | Color |
|----------|-------|
| SQLi | Yellow |
| XSS | Red |
| Session | Purple |
| Brute | Orange |
| Crypto | Green |
| Exposed | Blue |
| CSRF | Pink |

### 5.6 Responsive Behavior

- **Desktop (≥ ~900px width):** auth pages render side-by-side split; dashboard vulnerability grid is two columns; process steps are horizontal.
- **Mobile (< ~900px width):**
  - Auth pages stack vertically (decorative panel on top, form panel below).
  - Dashboard vulnerability grid collapses to a single column.
  - Process steps stack vertically.
  - Header logo images shrink (target ~36–40px).

---

## 6. Form Specifications

### 6.1 Registration Form (`/signup`)

| Field | Type | Required | Client-side rule |
|-------|------|----------|------------------|
| username | text | Yes | None beyond presence |
| email | email | Yes | None beyond presence |
| password | password | Yes | None beyond presence |
| confirm-password | password | Yes | Must equal `password` value before submit |

- Submission: native `POST /signup` (form-encoded) is allowed only when the client-side equality check passes.
- Server-side fallback: even if client-side check is bypassed, the server still inserts the user; the equality check is enforced only on the client.

### 6.2 Login Form (`/login`)

| Field | Type | Required |
|-------|------|----------|
| username | text | Yes |
| password | password | Yes |

- Submission: asynchronous `fetch` from JavaScript. The page never performs a native form POST.
- Success path: response carries success metadata; client navigates to `/welcome`.
- Failure path: response carries failure metadata; client renders the error message inline; **no page reload occurs**.

---

## 7. Validation Rules

| Surface | Field / Parameter | Rule |
|---------|-------------------|------|
| Registration | username | Required (non-empty); uniqueness enforced by the `users.username` UNIQUE constraint at the database level |
| Registration | email | Required (non-empty); no format check |
| Registration | password | Required (non-empty); client-side equality with confirm-password |
| Registration | confirm-password | Required; must equal password before submission |
| Login | username | Required |
| Login | password | Required |
| Search | `q` query parameter | Required; absence yields an "empty search" path (see AP-04) |

---

## 8. Session State Model

### 8.1 Stored Values

| Key | Type | Source |
|-----|------|--------|
| `user_id` | int | DB row id at signup/login |
| `username` | str | Submitted at signup, returned by `SELECT` at login |
| `email` | str | Submitted at signup, returned by `SELECT` at login |

### 8.2 Lifecycle

| Phase | Event |
|-------|-------|
| Creation | First successful login (or first login that matches a row). |
| Read | Every request to a session-aware route (most importantly `/welcome`). |
| Destruction | Successful request to `/logout`; the session is cleared before redirect. |

---

## 9. Data Lifecycle Rules

| Stage | Behavior |
|-------|----------|
| Create | User is created on POST `/signup` after the client-side validation passes. |
| Read | User rows are read on POST `/login`, GET `/welcome` (indirectly, via session lookup is not performed — see FR-03), and GET `/search`. |
| Update | No modification workflow exists. |
| Delete | No deletion workflow exists. |
| Recovery | No password reset, no recovery token, no admin override. |

---

## 10. Success Paths

| ID | Name | Steps |
|----|------|-------|
| SP-01 | Successful registration | (1) GET `/signup` → 200 with signup HTML. (2) User submits valid form. (3) Server inserts row. (4) 303/302 redirect to `/login`. |
| SP-02 | Successful login | (1) GET `/login` → 200 with login HTML. (2) User submits valid credentials. (3) Server finds matching row. (4) Session populated. (5) Client navigates to `/welcome`. |
| SP-03 | Dashboard render | (1) GET `/welcome` with valid session. (2) Template loaded. (3) `{{username}}` replaced with session's `username`. (4) 200 with rendered HTML. |
| SP-04 | Successful logout | (1) GET `/logout`. (2) Session cleared. (3) Redirect to `/login`. |

---

## 11. Alternate Paths

| ID | Trigger | Behavior |
|----|---------|----------|
| AP-01 | Duplicate username on signup | Insert fails on UNIQUE constraint; handler returns an HTML error page stating the username is taken. The response is **not** a redirect. |
| AP-02 | Invalid credentials on login | `SELECT` returns no row; handler returns JSON with failure metadata; client renders inline error and stays on `/login`. No redirect. |
| AP-03 | Unauthorized dashboard request | GET `/welcome` with no `user_id` in session; handler returns a redirect to `/login`. |
| AP-04 | Empty/missing search query | GET `/search` with no `q` parameter (or `q` empty); handler returns a response indicating no query was supplied (HTML page that does not list any results). |

---

## 12. Edge Cases

| ID | Scenario | Expected Behavior |
|----|----------|-------------------|
| EC-01 | Existing username registration | AP-01: HTML error page; no row inserted. |
| EC-02 | Empty registration submission | Client-side blocks submit when any of the four fields is empty (browser-native `required`); server receives no request. |
| EC-03 | Empty login submission | Client-side blocks submit; server receives no request. |
| EC-04 | Missing session on protected route | AP-03: redirect to `/login`. |
| EC-05 | Corrupted / forged session | Starlette's signed cookie rejects the cookie; treated identically to EC-04 (no `user_id` key). |
| EC-06 | Missing template file | Unhandled exception propagates; response is FastAPI's default 500. |
| EC-07 | Missing database file | Connection routine recreates the file; init routine recreates the table; startup completes; all prior users are lost (this is intentional — see §2.2). |
| EC-08 | Application restart | Existing rows are preserved (EC-07 is not triggered); init is a no-op; sessions signed with the same secret remain valid until expiry. |

---

## 13. Business Rules

1. **Authentication depends solely on session presence.** No DB lookup occurs when authorizing a request to `/welcome`.
2. **The dashboard requires runtime substitution.** The `{{username}}` placeholder must be replaced with the session's `username` on every request; static HTML files in this location would be a violation of the spec.
3. **User records are immutable after creation.** No update or delete endpoint exists; rows only ever accumulate.
4. **Login and registration use different response formats.** Registration responds with a redirect (or HTML error page); login responds with JSON that the client interprets.
5. **Template edits are visible without restart.** Templates are read from disk per request; a developer can edit an HTML file and reload to see changes.
6. **The DB UNIQUE constraint is the primary uniqueness mechanism.** Uniqueness for username is enforced by SQLite, not by application logic.

---

## 14. Rebuild Requirements

A compatible reimplementation MUST reproduce all of the following:

1. Application starts, ensures `users` table exists, and serves on the configured port (default `3001`).
2. GET `/` redirects to `/signup`.
3. GET `/signup` and GET `/login` serve HTML forms with the styling specified in §5.
4. POST `/signup` inserts a user row and redirects to `/login` on success; renders an inline error on duplicate username.
5. POST `/login` is reachable via a client-side `fetch` from the login page; on success it populates the session and signals success in JSON; on failure it returns failure JSON.
6. GET `/welcome` with a session containing `user_id` returns the dashboard HTML with the username substituted into the `{{username}}` placeholder.
7. GET `/welcome` without a session redirects to `/login`.
8. GET `/logout` clears the session and redirects to `/login`.
9. GET `/search?q=<term>` returns an HTML response containing the query term and any matching rows; missing `q` yields the AP-04 empty-search response.
10. GET `/download/db` returns the SQLite file as a downloadable response without authentication.
11. Static assets under `/static/...` resolve to files in the static directory.
12. Restarting the process preserves all rows currently in `users`.

A compatible reimplementation MAY differ in: source-code organization, file naming, dependency versions above the floor specified in PRD §10, internal helper function names, and CSS variable names — provided the rendered output and HTTP behavior match the above.

---

## 15. Acceptance Criteria

| ID | Criterion |
|----|-----------|
| AC-01 | Submitting the registration form with a unique username inserts a row and the browser ends up on `/login`. |
| AC-02 | Submitting the registration form with an existing username renders an inline error without inserting a row. |
| AC-03 | Submitting the login form with valid credentials lands the browser on `/welcome` with the user's name visible. |
| AC-04 | Submitting the login form with invalid credentials keeps the browser on `/login` and shows an inline error. |
| AC-05 | Visiting `/welcome` while unauthenticated redirects to `/login`. |
| AC-06 | Visiting `/welcome` while authenticated shows the dashboard; visiting `/logout` and then `/welcome` redirects to `/login`. |
| AC-07 | Visiting `/download/db` returns the SQLite file regardless of session state. |
| AC-08 | Restarting the process preserves all previously created users. |
| AC-09 | Editing `templates/dashboard.html` on disk is reflected on the next page load without restarting the app. |

---

## 16. Test Cases

| TC | Description | Pre-conditions | Steps | Expected |
|----|-------------|----------------|-------|----------|
| TC-01 | New user can register | Empty `users` table | Submit `/signup` with `alice`, `a@b.c`, `pw`, `pw` | Redirect to `/login`; `users` contains one row |
| TC-02 | Duplicate registration rejected | `users` contains `alice` | Submit `/signup` with `alice`, `a@b.c`, `pw`, `pw` | Inline "username taken" error; row count unchanged |
| TC-03 | Valid login succeeds | TC-01 has run | Submit `/login` with `alice`/`pw` via fetch | Session populated; browser navigates to `/welcome` |
| TC-04 | Invalid login rejected | TC-01 has run | Submit `/login` with `alice`/`wrong` | Inline error; no session change; no redirect |
| TC-05 | Dashboard requires session | TC-04 ran, no successful login | GET `/welcome` | 302 redirect to `/login` |
| TC-06 | Dashboard renders username | TC-03 ran | GET `/welcome` | 200; response body contains `alice` and does **not** contain `{{username}}` |
| TC-07 | Logout clears session | TC-03 ran | GET `/logout`; then GET `/welcome` | First response redirects to `/login`; second response redirects to `/login` |
| TC-08 | Logout endpoint always accessible | None | GET `/logout` while unauthenticated | 302 redirect to `/login`; no error |
| TC-09 | Search with empty query | TC-01 has run | GET `/search` (no `q`) | AP-04 response (no results listed) |
| TC-10 | Search with query | TC-01 has run | GET `/search?q=ali` | 200 HTML; response includes `alice` |
| TC-11 | DB download is unauthenticated | None | GET `/download/db` | 200 with the SQLite file contents; no auth challenge |
| TC-12 | Static CSS resolves | None | GET `/static/css/styles.css` | 200; CSS body served |
| TC-13 | App restart preserves users | TC-01 has run | Restart process; GET `/welcome` after re-login | Row still present; can log in with same credentials |
| TC-14 | DB missing at startup | `vulnerable_app.db` deleted | Restart process | File recreated; `users` table created; app boots |
| TC-15 | Password mismatch blocks submit | None | Open `/signup`; fill `pw` and `confirm = different`; click submit | Browser blocks submission; red inline message under confirm field |

---

## 17. Documentation Gaps

The following discrepancies exist between the PRD/TDD wording and the actual implementation behavior captured above. They are noted so that implementers and reviewers do not silently "fix" them away:

1. **Spec mismatch on the `/download/db` endpoint.** TDD §3.1.2 describes this as a `download_db()` handler; PRD §3.2 lists it as one of the eight vulnerabilities. The implementation in this codebase treats it as a known gap — the endpoint either does not exist or is wired only as a stub. A faithful reimplementation must decide explicitly whether to ship it as VULN-6 (per PRD) or omit it (per the absence in this repo).
2. **Spec mismatch on the homepage (`/`) redirect.** TDD §3.1.2 states that `GET /` redirects to `/signup`. The behavior here describes the same redirect; the gap is that the PRD does not document this redirect at all, leaving implementers to infer it from the auth-flow narrative.
3. **Spec mismatch on the search empty-state response.** PRD §3.1 (FR-5) requires only that `/search` accept a query parameter and return HTML; TDD §3.3.3 shows `q` being interpolated into HTML without specifying what happens when `q` is absent. The AP-04 path is therefore an implementation-defined choice, not a documented contract.
4. **Spec mismatch on session signing.** PRD §3.2 (VULN-4) names the secret `"super-secret-key-12345"`. TDD §6.3 lists `SECRET_KEY` as an environment variable defaulting to that string. The current reimplementation expectation is the literal default (no env override), per the runtime contract in TDD §6.3. Implementers who read `SECRET_KEY` from the environment without keeping the documented default would still satisfy TDD but would diverge from the source's stated behavior.

---

**Document End**