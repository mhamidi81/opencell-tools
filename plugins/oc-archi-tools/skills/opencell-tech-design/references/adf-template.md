# ADF Template for customfield_10137 (Technical Design)

This is the canonical ADF structure to use when writing technical designs to Jira.
Every section must be present. Use "NO IMPACT" info panels for sections with no changes.

## Full template structure

```json
{
  "type": "doc",
  "version": 1,
  "content": [

    // ── TITLE ──────────────────────────────────────────────────────────────
    {
      "type": "heading", "attrs": {"level": 1},
      "content": [{"type": "text", "text": "Technical design",
        "marks": [{"type": "strong"}, {"type": "textColor", "attrs": {"color": "#bf2600"}}]}]
    },
    {"type": "rule"},

    // ── OVERVIEW ───────────────────────────────────────────────────────────
    {
      "type": "heading", "attrs": {"level": 2},
      "content": [{"type": "text", "text": "Overview",
        "marks": [{"type": "strong"}, {"type": "textColor", "attrs": {"color": "#bf2600"}}]}]
    },
    {"type": "rule"},
    {
      "type": "paragraph",
      "content": [{"type": "text", "text": "<2-3 sentence description of what this story does and why, naming the exact class/method impacted>"}]
    },

    // ── API ────────────────────────────────────────────────────────────────
    {
      "type": "heading", "attrs": {"level": 2},
      "content": [{"type": "text", "text": "API",
        "marks": [{"type": "strong"}, {"type": "textColor", "attrs": {"color": "#bf2600"}}]}]
    },
    {"type": "rule"},

    // Use info panel for NO IMPACT:
    // {"type": "panel", "attrs": {"panelType": "info"}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "NO NEW API — ...reason..."}]}]}

    // Or use warning panel for guideline reminder:
    {
      "type": "panel", "attrs": {"panelType": "warning"},
      "content": [{"type": "paragraph", "content": [
        {"type": "text", "text": "New API should be defined as Restful v2 API as explained in R&D's REST "},
        {"type": "text", "text": "API Guideline", "marks": [{"type": "link", "attrs": {"href": "https://opencellsoft.atlassian.net/wiki/spaces/docs/pages/1772912641"}}]},
        {"type": "text", "text": "."}
      ]}]
    },

    // API table: one row per endpoint
    {
      "type": "table", "attrs": {"isNumberColumnEnabled": false, "layout": "default"},
      "content": [
        // Header row
        {
          "type": "tableRow", "content": [
            {"type": "tableHeader", "attrs": {}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "API", "marks": [{"type": "strong"}]}]}]},
            {"type": "tableHeader", "attrs": {}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Description", "marks": [{"type": "strong"}]}]}]}
          ]
        },
        // Data row
        {
          "type": "tableRow", "content": [
            {
              "type": "tableCell", "attrs": {},
              "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "<methodName>", "marks": [{"type": "strong"}]},
                {"type": "hardBreak"},
                {"type": "text", "text": "PUT", "marks": [{"type": "code"}]},
                {"type": "hardBreak"},
                {"type": "text", "text": "/api/rest/v2/<path>", "marks": [{"type": "code"}]},
                {"type": "hardBreak"},
                {"type": "text", "text": "Existing — modified", "marks": [{"type": "em"}]}
              ]}]
            },
            {
              "type": "tableCell", "attrs": {},
              "content": [
                {"type": "paragraph", "content": [
                  {"type": "text", "text": "Summary", "marks": [{"type": "strong"}]},
                  {"type": "hardBreak"},
                  {"type": "text", "text": "<one sentence description>"}
                ]},
                {"type": "paragraph", "content": [{"type": "text", "text": "Request", "marks": [{"type": "strong"}]}]},
                {"type": "codeBlock", "attrs": {"language": "json"}, "content": [{"type": "text", "text": "{\n  \"property\": \"value\"\n}"}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "Business logic", "marks": [{"type": "strong"}]}]},
                {"type": "bulletList", "content": [
                  {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "<rule 1>"}]}]},
                  {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "<rule 2>"}]}]}
                ]},
                {"type": "paragraph", "content": [
                  {"type": "text", "text": "Class to modify", "marks": [{"type": "strong"}]}
                ]},
                {"type": "codeBlock", "attrs": {"language": "java"}, "content": [{"type": "text", "text": "// File: <package>/<ClassName>.java\n// Method: <methodName>()\n\n<code block>"}]},
                {"type": "paragraph", "content": [
                  {"type": "text", "text": "Response", "marks": [{"type": "strong"}]},
                  {"type": "hardBreak"},
                  {"type": "text", "text": "200 OK / 204 No Content. Refer to Error dictionary for error responses."}
                ]}
              ]
            }
          ]
        }
      ]
    },

    // ── ERROR DICTIONARY ───────────────────────────────────────────────────
    {
      "type": "heading", "attrs": {"level": 3},
      "content": [{"type": "text", "text": "Error dictionary",
        "marks": [{"type": "strong"}, {"type": "textColor", "attrs": {"color": "#bf2600"}}]}]
    },
    {"type": "rule"},
    {
      "type": "panel", "attrs": {"panelType": "warning"},
      "content": [{"type": "bulletList", "content": [
        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "No hardcoded error messages."}]}]},
        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "All Java exceptions must be trapped."}]}]}
      ]}]
    },
    // Error table with 4 columns: HTTP code | Error code | Message EN | Message FR
    {
      "type": "table", "attrs": {"isNumberColumnEnabled": false, "layout": "default"},
      "content": [
        {"type": "tableRow", "content": [
          {"type": "tableHeader", "attrs": {}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "HTTP code", "marks": [{"type": "strong"}]}]}]},
          {"type": "tableHeader", "attrs": {}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Error code", "marks": [{"type": "strong"}]}]}]},
          {"type": "tableHeader", "attrs": {}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Error message (en)", "marks": [{"type": "strong"}]}]}]},
          {"type": "tableHeader", "attrs": {}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Error message (fr)", "marks": [{"type": "strong"}]}]}]}
        ]},
        {"type": "tableRow", "content": [
          {"type": "tableCell", "attrs": {}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "400"}]}]},
          {"type": "tableCell", "attrs": {}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "<entity.context.rule>", "marks": [{"type": "code"}]}]}]},
          {"type": "tableCell", "attrs": {}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "<English message>"}]}]},
          {"type": "tableCell", "attrs": {}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "<Message en français>"}]}]}
        ]}
      ]
    },

    // ── MODEL ──────────────────────────────────────────────────────────────
    {
      "type": "heading", "attrs": {"level": 2},
      "content": [{"type": "text", "text": "Model",
        "marks": [{"type": "strong"}, {"type": "textColor", "attrs": {"color": "#bf2600"}}]}]
    },
    {"type": "rule"},
    // Use info panel if no model changes:
    // {"type": "panel", "attrs": {"panelType": "info"}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "NO MODEL CHANGES — <reason>"}]}]}

    // ── MIGRATION ──────────────────────────────────────────────────────────
    {
      "type": "heading", "attrs": {"level": 2},
      "content": [{"type": "text", "text": "Migration",
        "marks": [{"type": "strong"}, {"type": "textColor", "attrs": {"color": "#bf2600"}}]}]
    },
    {"type": "rule"},
    // Use info panel if no migration:
    // {"type": "panel", "attrs": {"panelType": "info"}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "NO MIGRATION SCRIPT — <reason>"}]}]}

    // ── GUI ────────────────────────────────────────────────────────────────
    {
      "type": "heading", "attrs": {"level": 2},
      "content": [{"type": "text", "text": "GUI",
        "marks": [{"type": "strong"}, {"type": "textColor", "attrs": {"color": "#bf2600"}}]}]
    },
    {"type": "rule"},
    // Use info panel if no GUI changes:
    // {"type": "panel", "attrs": {"panelType": "info"}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "NO GUI CHANGES — <reason>"}]}]}

    // ── NON REGRESSION CHECKS ──────────────────────────────────────────────
    {
      "type": "heading", "attrs": {"level": 2},
      "content": [{"type": "text", "text": "Non regression checks",
        "marks": [{"type": "strong"}, {"type": "textColor", "attrs": {"color": "#bf2600"}}]}]
    },
    {"type": "rule"},
    {
      "type": "panel", "attrs": {"panelType": "note"},
      "content": [{"type": "paragraph", "content": [
        {"type": "text", "text": "Development may have impact on the features listed below. Please check that everything is still working fine."}
      ]}]
    },
    {
      "type": "bulletList", "content": [
        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "<specific scenario 1: method name, status, expected outcome>"}]}]},
        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "<specific scenario 2>"}]}]},
        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "<specific scenario 3>"}]}]}
      ]
    }

  ]
}
```

## Panel type reference

| panelType | Use for |
|---|---|
| `info` | NO IMPACT sections |
| `warning` | Rules, constraints, important caveats |
| `note` | Non-regression preamble, informational notes |
| `error` | Critical blocking issues |

## ADF node types used

- `heading` (level 1–3) + textColor `#bf2600` for section titles
- `rule` = horizontal line separator after each heading
- `paragraph` + `hardBreak` for inline line breaks
- `codeBlock` with `language: "java"` or `language: "json"` or `language: "sql"`
- `table` / `tableRow` / `tableHeader` / `tableCell`
- `bulletList` / `orderedList` / `listItem`
- `panel` with `panelType: info | warning | note`
- `text` with optional `marks`: `strong`, `em`, `code`, `textColor`, `link`
