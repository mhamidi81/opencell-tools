# oc-fn-portal — replaying a failing call against the API

Load this the moment a Portal action fails **server-side**: a save that returns 400 or 500, a
"Server communication error" toast, or a reported defect you have to reproduce and diagnose.
Navigation and screenshot work does not need this file.

## 1. When to switch

**The moment a Portal action fails with a server error, stop driving the UI.** The UI can only
tell you *that* something failed; the API tells you *why*. Every further click, re-navigation
and `wait_for` after that point buys nothing — the answer is in the response body, and the
browser is throwing it away (see § 5).

The cost is not theoretical. In the Story review this lane came from — a Seller save returning
`400 Bad request` with, apparently, no body — **~25 tool calls went into fighting the browser
and produced no diagnosis. The switch to `curl` found the root cause in 4.**

Unlike a headless observation (`SKILL.md` § *What you observe is not evidence about the
product*), a replayed request is unambiguous evidence about the product — the status and body
come from the server, not from Chromium. **When the question is "is this broken and why", the
API is the instrument; the browser is not.**

Before you leave the UI, take the one thing the browser is genuinely good for: call
`browser_network_requests` to capture the failing call exactly as the app made it — method,
full URL, request payload, status. That is your replay target; you are not guessing at it.

## 2. Get a token

Authentication is Keycloak (OpenID Connect) on the same host as the Portal, direct grant
(`grant_type=password`). **The Portal's own `public/app-properties.js` is the authority for the
parameters** — `KEYCLOAK_CLIENT_ID: 'opencell-portal'`, `KEYCLOAK_APP_REALM: 'opencell'`,
`KEYCLOAK_APP_AUTH_URL: '/auth'` on `opencell-portal@dev`. Read that file to pin them for any
other instance rather than assuming these.

Three details, each of which costs a failed attempt if you get it wrong:

- **The realm is `opencell`** — literally, always. It is *not* the tenant name. The tenant
  appears only in the Portal URL path (`…/opencell/frontend/DEMO/portal/`), never in the realm
  segment. `<host>` is the scheme + host of `OC_PORTAL_URL` with its path stripped.
- **`client_id` must be `opencell-portal`.** Only that client has direct grant enabled — the
  failure codes below were observed on the scn2 sandbox:

  | `client_id` | Result |
  |---|---|
  | `opencell-portal` | token issued |
  | `opencell-web` | `401 unauthorized_client` |
  | `opencell` | `401 invalid_client` |

- **Re-fetch the token inside any loop or long bisect** rather than reusing one — ~300 s
  observed on the scn2 sandbox, and the Portal's own refresh rate is 270 s
  (`KEYCLOAK_APP_TOKEN_REFRESH_RATE`). A sudden `401` halfway through a sequence is an expired
  token, not a permissions change.

Credentials come from the same file the rest of the skill uses,
`~/.config/oc-fn-portal/credentials` (`OC_PORTAL_URL`, `OC_PORTAL_USER`, `OC_PORTAL_PASS`; see
`setup.md`). **Keep `OC_PORTAL_PASS` out of argv and out of your shell history the same way you
keep it out of context** — source the file and pipe the form body in on stdin rather than
writing the value anywhere it can be read back. **The block below is the only token command this
file offers**; never hand-roll a `-d "password=$OC_PORTAL_PASS"` variant, which expands the
password into argv where `ps` and the history file can read it back.

```bash
set -a; . ~/.config/oc-fn-portal/credentials; set +a
HOST=$(printf '%s' "$OC_PORTAL_URL" | sed -E 's#(https?://[^/]+).*#\1#')
TOKEN=$(printf 'grant_type=password&client_id=opencell-portal&username=%s&password=%s' \
          "$OC_PORTAL_USER" "$OC_PORTAL_PASS" |
        curl -s --data-binary @- \
          "$HOST/auth/realms/opencell/protocol/openid-connect/token" | jq -er .access_token)
```

Never echo `$TOKEN` or `$OC_PORTAL_PASS`. **Check success with `jq -er`, not with
`[ -n "$TOKEN" ]`** — on a Keycloak error body `jq -r .access_token` prints the literal string
`null`, which satisfies `-n` and sends you on with a garbage bearer token. `-e` exits non-zero
on a null result, and the assignment inherits that status, so `TOKEN=$(…) || <bail>` is a real
check; `[ "$TOKEN" != "null" ]` works too. If the password contains URL-reserved characters
(`&`, `%`, `+`, `=`), percent-encode it before it goes into the form body.

Then replay against the API root, which is `<host>/opencell/api/rest/`:

```bash
curl -s -w '\n%{http_code}\n' -X PUT "$HOST/opencell/api/rest/v2/seller" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @payload.json
```

Keep the payload in a file, not inline — you will edit it repeatedly during the bisect (§ 4),
and it stays out of context.

## 3. Confirm which build you are reasoning about — before reading any source

**Do this first, every time.** Reading the local checkout to explain a sandbox's behaviour is
only valid if the sandbox is running that code. **Core and Portal deploy from separate builds
and drift independently**, so establish each one on its own — and each has its own method.

**Core** — unauthenticated, no token needed. Returns version + commit + date:

```bash
curl -s "$HOST/opencell/api/rest/v2/version" | jq .
```

**Portal** — two methods. The **UI version panel is canonical**: unfold the left menu and click the
version number at the bottom-left (observed on the scn2 sandbox, 2026-08-03; placement may differ by
version or theme). The panel shows `Version` / `Build` (the full commit sha) / `Date` for the Portal
and, where configured, other components. Prefer it whenever a login is available. Do not expect the
Core call above to fill the gap — it reports Core's own component only.

**Login-free fallback — read the build constants out of the shell bundle.** The browser lane is not
always open: reading `OC_PORTAL_PASS` out of `~/.config/oc-fn-portal/credentials` is refused by the
permission classifier, and without the password Keycloak cannot be driven — which closes the UI panel
entirely. (The fix is `--secrets` on the MCP registration, which fills the password without ever
revealing it — `setup.md` § 6. Until that is in effect, do not chase the secret.) Don't stop there and
ask the user either: the build constants are readable unauthenticated.

```bash
BASE="https://<host>/opencell/frontend/<TENANT>/portal"
IDX=$(curl -s "$BASE/" | grep -oE 'assets/index-[^"]+\.js' | head -1)
curl -s "$BASE/$IDX" \
  | grep -oE 'VITE_APP_GIT_SHA[A-Z_]*:"[^"]{1,60}"|npm_package_version:"[^"]{1,40}"'
```

| Key | Meaning |
|---|---|
| `VITE_APP_GIT_SHA` | full 40-char commit sha of the Portal build |
| `VITE_APP_GIT_SHA_DATE` | commit date, **epoch seconds** (`git log -1 --format=%ct`) |
| `npm_package_version` | the Portal version, e.g. `18.2.0-SNAPSHOT` |

They are present **by construction, not by luck**: `package.json`'s `build` script sets
`VITE_APP_GIT_SHA=$(git rev-parse HEAD)` and `VITE_APP_GIT_SHA_DATE=$(git log -1 --format=%ct)`, and
`vite.config.js` carries `define: { 'process.env': process.env, … }`, which inlines the whole
build-machine env into the bundle. The shell chunk is ~18 MB uncompressed — **pipe it, or `curl -o` to
the scratchpad; never `Read` it.**

**Verification is mandatory, not optional.** A sha lifted out of a bundle is a claim until it is
placed. Two independent checks, both cheap:

```bash
cd $GIT_HOME/opencell-portal
git cat-file -t <sha>                                     # must resolve to `commit`
git log -1 --format=%ct <sha>                             # must equal VITE_APP_GIT_SHA_DATE exactly
git log -1 --format='%cd %an: %s' --date=iso-strict <sha>  # for the record
```

If the sha does not resolve, **or** the dates disagree, stop — fall back to the UI panel or ask the
user. Do not report the value.

> **This is a lookup, not an inference — the ban below still stands in full.** Reading one *fixed,
> known* key that the build pipeline guarantees is in the shell chunk is not the same act as searching
> served code for feature-specific symbols to decide whether a change is deployed. That second thing
> remains forbidden, for the reasons in the block further down: it produced a wrong, publicly
> retracted conclusion, and it cannot work. The test: if you are grepping for a **name you chose
> because of the feature under review**, you are inferring — stop. If you are reading
> `VITE_APP_GIT_SHA`, you are looking up a constant, and the answer is verifiable against the repo.

*Worked example, verified 2026-08-03 on `energie-18.oc-nsb.eu`:* the bundle gave
`VITE_APP_GIT_SHA:"dab5763e58786868d0b70067a29ffef6e5611df4"`,
`VITE_APP_GIT_SHA_DATE:"1785763585"`, `npm_package_version:"18.2.0-SNAPSHOT"`. `git cat-file -t`
resolved to `commit` and `git log -1 --format=%ct` returned `1785763585` — an exact match — for
*Merged in bugfix/INTRD-45534-regportal-error-loading-invo-18x* by Vladimir Morev. Both checks passed,
so the value could be used.

**Then place each sha in its local checkout** — a bare sha tells you nothing until you locate it.
**Find the branch first:** sandboxes commonly run a release branch, not `dev`, and comparing against
the wrong one reports an alarming "NOT an ancestor" when nothing is wrong.

```bash
git branch -r --contains <sha> | head          # DO THIS FIRST — which branch is this build from?
# then compare against whichever branch actually contains it (BR below), not reflexively origin/dev
# --is-ancestor is exit-status-only; it prints nothing either way
git merge-base --is-ancestor <sha> "$BR" && echo ancestor || echo 'NOT an ancestor'
git log --oneline <sha>.."$BR" -- <paths>      # does the gap touch the files under review?
```

The example above sits on `origin/18.X` and is **not** an ancestor of `origin/dev` — entirely normal
for a sandbox on a release branch, and meaningless as a signal.

**What matters is not the size of the gap but whether it touches the code you are reasoning
about.** A sandbox two days behind your checkout is fine if nothing in between went near the
feature. Worked example from the review this lane came from: the sandbox Portal was
`37b71da83c` (19.0.0-SNAPSHOT, 2026-07-31), **4 commits** behind the checkout, and none of the 4
touched the seller card — so the gap was irrelevant and every finding stood.

> **Do NOT try to establish this by grepping the served JS.** A worked failure from that same
> review: the session downloaded `assets/index-<hash>.js`, found none of the string literals
> introduced by the commit under review, and concluded the sandbox front end did not match
> `dev`. **That conclusion was wrong**, and it reached a Jira ticket (INTRD-45543) and the PO
> review comment before it had to be retracted publicly.
>
> The method cannot work: **the Portal is code-split into ~330 lazy chunks.**
> `assets/index-<hash>.js` is only the shell and contains none of the business widgets; a chunk
> is served only once something imports it. The seller module lived in `index-D5HSIrO6.js`,
> which had never loaded because the session never opened the seller edit form.
>
> Two corollaries if you ever *genuinely* need to search served code: enumerate **all** chunks
> first — `grep -o 'assets/[A-Za-z0-9_.-]*\.js'` over the main bundle lists them — and search
> the whole set (~330 chunks, several MB — ≈7 MB gzipped over the wire, and the main chunk alone
> is ~18 MB uncompressed — all returning 200). **Minification strips *function* names but keeps
> object keys and string literals**, so a missing helper name proves nothing either (`splitName`
> was unfindable for that reason while `bankIban` was present all along — in the right chunk).

## 4. Reconstruct the payload from source, not by guessing

Guessing the body wastes calls and produces validation errors that look like the bug. The Portal
source states exactly what it sends — but **the endpoint and the body shape live in two
different places, so do not look for the mapping in the provider:**

| What you need | Where it is |
|---|---|
| URL + HTTP method for the failing action | the `CREATE` / `UPDATE` entry in the resource's `provider/provider.js` |
| Shape of the request body | `mapFormToRequestBody` under the **widget's** `mapRecord/` |
| How the loaded record was turned into form state | `mapRecordToForm`, alongside it |
| Anything applied on submit before the call | that widget's `save/onSave.ts` |

Providers live under `src/srcProject/layout/<area>/modules/<resource>/provider/provider.js` and
carry only the url and the method — e.g. `…/layout/seller/modules/sellers/provider/provider.js`,
whose `UPDATE` is `url: 'v2/seller', method: 'PUT'` (relative to the `/opencell/api/rest/` root).
The mappings are a **widget** convention, under `src/srcProject/widgets/<area>/<Widget>/mapRecord/`
— for the seller card, `src/srcProject/widgets/seller/SellerCard/mapRecord/`. **A widget that
defines none maps identity**: the form state is the body. Locate both by name rather than
assuming the area:

```bash
find src -ipath '*<resource>*' -name 'provider.js'
find src/srcProject/widgets -ipath '*<Resource>*' \( -name 'map*.ts' -o -name 'onSave.ts' \)
```

Then **bisect field by field**: post the smallest body that succeeds, re-add the mapped fields
one at a time, and stop at the first one that reproduces the failure. In the review this took
the diagnosis from "400, no idea" to an exact line of Java in four calls.

## 5. Two Opencell traps that make server bugs look like client errors

Either one on its own is enough to mis-triage a ticket — a genuine server-side crash reaches
the PO as "the UI says nothing and the request is a 400", which reads exactly like bad input.

### 5.1 apiv2 returns `400`, not `500`, for internal faults

The apiv2 resource implementations are `@Stateless` EJBs, so a runtime exception thrown inside
one is wrapped by the container into `EJBTransactionRolledbackException`. That is then caught by
a dedicated mapper —
`opencell-api/src/main/java/org/meveo/apiv2/generic/exception/EJBTransactionRolledbackExceptionMapper.java`
— which builds `new ExceptionSerializer(Response.Status.BAD_REQUEST)` (line 14) and returns
`Response.status(Response.Status.BAD_REQUEST)` (line 19). **An internal server fault therefore
surfaces as `400`, never `500`.** "It's a 400, so the client sent something wrong" is not a valid
inference anywhere in apiv2.

**Read `details` before you decide whose bug it is:**

| `details` contains | Verdict |
|---|---|
| A validation message naming a field or a business rule | bad input — client side |
| A JDK helpful-NPE string (`Cannot invoke "X.y()" because … is null`) | **server bug** |
| An exception class name or a stack trace | **server bug** |

### 5.2 The Portal discards apiv2 error messages — on the resources that opt in

The server's real error text is received and then thrown away. Three steps, in the Portal
checkout:

1. `src/providers/dataProvider.js:88` destructures the request options with
   `const { headers, errorContainer = 'message', ...cleanOptions } = options;` — so unless a
   resource overrides it, **the error container is `message`**.
2. `src/providers/apiErrorHandler.js:37-41` computes `details` **correctly**, falling back
   through `body.<errorContainer> || body.details || ERRORS[body.errorCode] || body.status` — an
   apiv2 body of `{status, details, causes}` resolves to the real `details` text.
3. `src/providers/apiErrorHandler.js:61-62` then **overwrites** that result — but only under a
   condition:

   ```js
   if (showErrorFromContainer || get(error, `body.${errorContainer}`)) {
     finalError = get(error, `body.${errorContainer}`);
   }
   ```

An apiv2 body has no `message` key, so where the condition holds `finalError` becomes
`undefined` and ra-core falls back to rendering **"Server communication error"**. The diagnosis
was on the wire and never reached the screen.

**The trap fires only when the resource's provider sets `showErrorFromContainer: true`** (or the
body actually carries the container key). Without it the `if` is false and the real `details`
**does** reach the screen. **So check the provider before concluding the message was
swallowed** — grep the resource's `provider.js` for `showErrorFromContainer`. The seller card
opts in (`src/srcProject/layout/seller/modules/sellers/provider/provider.js:87`), and so do ~35
provider files on `opencell-portal@dev`: common, not exotic.

**Rule: on such a resource, *"the UI showed no error message"* is never evidence that the server
sent none.** It is the expected behaviour of this Portal against any apiv2 error.

### 5.3 Consequence

**A user-reported HTTP status and message are second-hand — always replay the call and read the
raw response before analysing.** Both traps corrupt the report on the way to you: the status is
downgraded to `400` by the mapper, and — on any resource that opts in — the message is erased by
the error handler. Nothing you reason about the failure is sound until you have seen the
server's own `details`.

## 6. Why in-page `fetch` is not a shortcut

Issuing a `fetch` from page context via `browser_evaluate` looks like a way to skip the token
dance. It is not: the app attaches its `Authorization` header **per request**, in its own data
provider, so a bare `fetch` you inject inherits no `Authorization` header and reaches the API
without a bearer token — there is no ambient credential in page context that apiv2 will accept.
Get a token (§ 2) and replay with `curl`.
