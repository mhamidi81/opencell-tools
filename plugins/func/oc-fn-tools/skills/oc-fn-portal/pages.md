# Opencell Portal — page catalogue

**Read-only seed catalogue.** This file ships with the skill — treat it as immutable reference;
do **not** append to or edit it in place. When you **confirm** a page's URL path, its functional
role, and any stable selectors/landmarks worth reusing, append a row to your *user catalogue* at
`~/.local/state/oc-fn-portal/catalog/pages.md` (create it on first use, mirroring the table format
below — copy the header row to start). Consult both this seed and your user catalogue when
navigating. A catalogued page turns future visits into a direct navigate-and-act (no exploratory
snapshot) — the biggest long-term token saving.

The base URL is `OC_PORTAL_URL` (from `~/.config/oc-fn-portal/credentials`); paths below are
relative to it. The portal is a React SPA, so paths are typically hash/route fragments —
record exactly what the address bar shows.

The base URL embeds the tenant/provider code — e.g. `…/opencell/frontend/DEMO/portal/` where
`DEMO` is the provider. Login is delegated to Keycloak on the same host (`/auth/realms/opencell/…`).

| Path (relative to base) | Page / view | Functional role | Stable selectors / landmarks | Notes |
|---|---|---|---|---|
| `/auth/realms/opencell/protocol/openid-connect/auth?…` (Keycloak host) | Login | Keycloak OIDC login form | textbox `Username or email`, textbox `Password`, button `Sign In`; link `Opencell Internal` = SSO broker | Reached by redirect from the portal base URL. Use the username/password form; **ignore** the `Opencell Internal` link. |
| _(portal base URL, post-login)_ | Home hub | Persona / module launcher | Title `Opencell \| Portal` → `- Opencell`; radial tiles: **Catalogue, Service client, Finance, Opérations, Vendeur, Responsable Marketing, Paramètres généraux** | Landing page after auth. UI in **French**. Tiles are graphical (canvas/img), so the a11y snapshot is sparse here — navigate by clicking a tile and record the resulting route. |
| `CPQ/offers/list` | Commercial offers | List of commercial offers in the Catalogue module | Breadcrumb `Catalog > Commercial offers`; left sidebar links: Commercial offers, Products, Price lists, Discount plans, Catalog manager; data grid with columns Code / Name / Status / Enabled / From / To / Media; toolbar: filter, add, history, export; `text=Catalogue` clicks the hub tile | Entry point when clicking the Catalogue hub tile. Status badges: `PUBLISHED` (green), `DRAFT` (orange). "Switch to new design" toggle top-right. Version footer `OPENCELL 19.0.0-SNAPSHOT`. |

<!--
Append confirmed pages to your user catalogue `~/.local/state/oc-fn-portal/catalog/pages.md`
(not this read-only seed). Suggested ordering: follow the Quote-to-Cash flow
(Quote → Order → Subscription → Usage → Rating → Billing → Payment → Accounting → RevRec)
plus Administration. Capture the address-bar route, the human page name, what it's for, and
one or two selectors/text landmarks that make the page identifiable and re-navigable.
-->
