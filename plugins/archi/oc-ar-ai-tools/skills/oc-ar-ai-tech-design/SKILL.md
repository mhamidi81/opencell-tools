---
name: oc-ar-ai-tech-design
description: Generate an AI-friendly, behaviour-focused technical design for an Opencell Jira story and write it into the Description field under a large red "AI-Friendly Technical Design" title. Triggers on "design a US", "write the technical design", "do the tech design for INTRD-XXXXX / MACRD-XXXXX", and on any reference to Opencell story keys (INTRD-*, MACRD-*).
argument-hint: <STORY-KEY> (e.g., INTRD-36922 or MACRD-12345)
---

## Purpose

This skill turns the functional requirements of an Opencell Jira story into a **technical design** and writes it **into the issue's standard Description field** — not into the Technical Design custom field.

The design it produces is deliberately **AI-friendly**: it describes *what the system must do*, *the data it must hold*, *the messages it must surface*, and *the scenarios it must satisfy* — in prose and simple bullet lists — without prescribing code-level identifiers. It is meant to give a downstream implementer (human or AI) clear intent and latitude, instead of a brittle, name-by-name code recipe.

This is a variant of `/oc-ar-tech-design`. The differences are intentional and listed under **Design output rules** below.

## Context

Parse `$ARGUMENTS` to get:

- **[STORY-KEY]**: a single Opencell Jira story key, e.g. `INTRD-36922` or `MACRD-12345`.

**Validation**

- If [STORY-KEY] is missing or does not match `INTRD-*` / `MACRD-*`, stop and ask the user for a valid story key.
- If the user instead asks to "show my design queue", list the stories assigned to them in **To Design - Tech**, grouped by fix version, for interactive selection, then continue with the chosen key.

## Tasks

### Step 1 — Gather context

Using the Atlassian MCP (and the local `.claude/cache/jira-tickets.json` cache when present and fresh):

- Read the target story's **Requirement**, **Functional Design**, and **Acceptance** fields.
- Read the **story comments** — they may correct or override the functional text; treat the latest comments as authoritative.
- Read any **sibling / related stories** and their existing designs, so this design stays consistent with them.
- Read any Java source the user provides.

Use this context to understand the behaviour to build. You are describing behaviour, so you do not need to confirm or reproduce code identifiers — see the output rules below.

### Step 2 — Identify the design type

Classify the story as one of: **new feature / API**, **enhancement**, **bug fix**, or **config / model-only**, and adapt which sections you fill. Omit sections that do not apply rather than padding them.

### Step 3 — Apply the critical design principles

- **Reuse, don't introduce.** Prefer extending existing behaviour over adding a parallel path. Express this as intent ("extend the existing X handling so that …"), without naming the specific service or method.
- **Correct persistence / `isVirtual` usage.** Make clear when an entity is persisted versus computed/virtual, in behavioural terms.
- **Prevention at source for bug fixes.** Describe where the root cause lives and the behaviour that prevents it recurring, not a line-level patch.
- **Consistency across siblings.** Align terminology, flows, and messages with related stories.

### Step 4 — Write the design (see Design output rules)

Produce the design as the **content of the Description field**, beginning with the required red title, then the sections below.

### Step 5 — Write to Jira

Set the story's standard **Description** field (ADF) to the design via the Atlassian MCP. If the existing Description already holds functional content the team relies on, preserve it below the design rather than discarding it, and tell the user what you did.

---

## Design output rules

These rules define how this skill differs from the standard technical-design skill. Follow all of them.

### 1. Everything goes in the Description field

All technical-design sections are cleaned up and placed in the issue **Description** field. Do **not** write to the Technical Design custom field.

### 2. Lead with a large red title

The first block of the Description is a level-1 heading reading exactly **AI-Friendly Technical Design**, coloured red.

In ADF this is a `heading` (level 1) whose text carries a red `textColor` mark, e.g.:

```json
{
  "type": "heading",
  "attrs": { "level": 1 },
  "content": [
    {
      "type": "text",
      "text": "AI-Friendly Technical Design",
      "marks": [ { "type": "textColor", "attrs": { "color": "#FF0000" } } ]
    }
  ]
}
```

(The HTML equivalent, if writing HTML, is an `<h1>` with red text colour.)

### 3. No tables, no grids

Never use tables or column/grid layouts. Present everything as prose and simple (optionally nested) bullet lists. The error/message list in particular is bullets, not a table.

### 4. Describe behaviour and intent, not code identifiers

- **No data-layer scripts.** Do not include Liquibase changesets or `ALTER TABLE` / DDL statements. Describe what new information must be stored or made configurable, and how it relates to existing data, in plain language.
- **No service/method targeting.** Do not say which service or method to modify. Describe the responsibility or behaviour to add or change.
- **No unit-test names.** Do not invent test method or class names. Describe the **test scenarios** to cover (the situation, the action, and the expected outcome).
- **No concrete class names in deliverables.** List deliverables by capability or outcome, not by class name.
- **No static / constant variable names.** For errors and messages, give the human-readable **message text** only (in EN and FR). Do not name the constant or static variable that holds it.

---

## Sections to produce (in the Description, after the red title)

Adapt to the design type from Step 2; drop sections that do not apply.

- **Overview** — one short paragraph: the problem and the intended outcome.
- **Scope** — what is in and out of scope; the design type.
- **Behaviour & flow** — the functional flow described as responsibilities and steps. What happens, in what order, and the rules that govern it. No service/method names.
- **API surface** (if any) — for each endpoint, the HTTP verb, path, and purpose, plus the meaningful request and response information described as bullets. Behavioural description only; no implementation class names.
- **Data & model impact** — the new information the system must hold or make configurable, what it represents, and how it relates to existing data. Conceptual only: no changesets, no DDL, no column/constant names.
- **Messages & errors** — a bullet list. Each item gives the EN message text and the FR message text, plus when it is shown. No constant names.
- **GUI / UX impact** — what changes for the user, described in prose.
- **Reuse & consistency** — which existing behaviour is being extended (as intent), and how this stays consistent with sibling stories.
- **Deliverables** — the capabilities/outcomes to be delivered, described by what they achieve. No concrete class names.
- **Test scenarios** — 3–5 (or more) specific scenarios, including non-regression checks. Each describes the situation, the action, and the expected result. No test names.
- **Open questions / assumptions** — anything unconfirmed.

## Quality checklist (verify before writing to Jira)

- Output goes to the **Description** field, not the Technical Design custom field.
- Description starts with the **red level-1 title** "AI-Friendly Technical Design".
- **No tables or grids** anywhere — prose and bullets only.
- **No Liquibase changesets / DDL**; data changes described conceptually.
- **No named services or methods**; responsibilities described as behaviour.
- **No test names**; only described test scenarios.
- **No concrete class names** in deliverables.
- **No static/constant variable names**; messages given as EN + FR text only.
- Messages are **bilingual** (EN + FR).
- **Sibling stories read first** and terminology kept consistent.
- Reuse intent expressed (extend existing behaviour rather than introduce a parallel path).
- **Story comments** taken into account; later comments override earlier functional text.
- All applicable sections filled; inapplicable sections omitted.

## Examples

```bash
# Generate the AI-friendly design and write it into the Description of INTRD-36922
/oc-ar-ai-tech-design INTRD-36922

# Same for a MACRD story
/oc-ar-ai-tech-design MACRD-12345

# Natural-language triggers also work:
#   "do the tech design for INTRD-37000"
#   "write the technical design for this US"
```
