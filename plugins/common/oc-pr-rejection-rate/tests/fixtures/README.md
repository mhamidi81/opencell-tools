# Fixtures

`activity_drafted.json` is a real Bitbucket activity feed, trimmed to the keys the
classifier reads and stripped of authors, titles, links and comment bodies.

Probed on 2026-09-16 against `opencellsoft/opencell-portal` PR 16041, a PR that was
opened ready, pushed back to draft, and later readied again — so it exercises a genuine
ready → draft transition rather than an opened-as-draft one.

**How Bitbucket represents a draft transition here:** both ways, in the same feed —
`update.changes.draft` as `{"old": <bool>, "new": <bool>}` on the entry that flips it,
and a plain `update.draft` snapshot boolean on every other update entry. Both are real
JSON booleans, never strings, which is why `pr_classify._coerce_draft` accepts only
`bool` and degrades the detection mode for anything else.

Two shape details that are easy to get wrong and are load-bearing:

- Each entry is `{"<kind>": {...}, "pull_request": {...}}`. The sibling `pull_request`
  is the PR's metadata, **not** the event, and it comes *first* in Bitbucket's key
  order — it even carries its own `draft` field. Reading "the first value with a
  timestamp" would eventually read the wrong one.
- `comment` entries date themselves with `created_on`, not `date`.

This is the fixture spec §4 asks for. It exists so `pr_classify` is tested against the
real shape rather than a guessed one — do not replace it with a hand-written file.
