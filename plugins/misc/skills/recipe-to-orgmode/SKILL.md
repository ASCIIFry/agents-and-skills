---
name: "recipe-to-orgmode"
description: "Konvertiert ein Online-Rezept (URL) oder eingefügten Rezepttext in eine Org-Mode-Datei mit fester Outline (Zutaten / Arbeitsschritte / Anmerkungen), auf Deutsch mit Umlauten."
---

# Recipe to Org-mode

Converts a recipe (from a URL or pasted text) into a single, consistently
structured Org-mode file. The point of this skill is consistency: every
recipe the user converts should come out with the same outline and the same
conventions, so their recipe collection stays uniform no matter which site
a recipe came from.

## Workflow

1. **Get the recipe content.**
   - If given a URL, fetch it (e.g. with WebFetch) and ask specifically for
     the title, serving size, total time, full ingredient list with
     quantities (including any ingredient groups), the numbered preparation
     steps in order, and any author notes/tips, wortgetreu (verbatim), not
     paraphrased. Recipe sites bury the actual recipe under blog-post
     preamble, so a targeted extraction prompt matters more than a generic
     "summarize this page".
   - If given pasted text instead of a URL, work directly from that text.
   - If a step or field genuinely isn't present on the source (e.g. no
     serving size given, or the site returns no notes), don't invent one.
     Leave it out rather than guessing.
2. **Translate to German if needed.** The output is always German with
   proper Umlauts (ä/ö/ü/ß), regardless of the source language. Translate
   ingredient names, units, and steps naturally. Don't leave English
   fragments in a German sentence. Keep proper nouns (brand names, dish
   names that don't translate well) as-is.
3. **Build the .org file** using the template below. Keep the outline fixed
   at exactly three top-level headings (`Zutaten`, `Arbeitsschritte`,
   `Anmerkungen`) in that order, every time. This fixed shape is the whole
   point: the user is building a collection of recipes that all look the
   same.
   Convert **weight** (oz/lb to g/kg) and **temperature** (°F to °C) to
   metric wherever the source uses imperial units. Leave **volume** units
   (cups, tablespoons/EL, teaspoons/TL, fl oz, pints, quarts, ...) exactly
   as given in the source, even if they're imperial. Don't convert these
   to ml or l and don't add a converted value in parentheses. Weight and
   temperature convert losslessly, but converting cups or spoons to ml
   implies a precision the original recipe doesn't have (a "cup" of chopped
   vegetables isn't a precise volume), so those stay as the reader found
   them.
4. **Save the file** as `<YYYYMMDDHHMMSS>-<slug>.org`, the org-roam
   naming convention (e.g. `20261010204953-kidneybohnen_erdnuss_eintopf.org`),
   in the directory the user named, or in the current working directory if
   they named none. The timestamp is the current local time, the same moment
   as `#+created`: use the one given in the request if there is one,
   otherwise run `date '+%Y%m%d%H%M%S'`. The slug is the title in lower case,
   with diacritics stripped (ä→a, ö→o, ü→u) and every run of characters other
   than letters and digits replaced by a single `_`, without leading or
   trailing `_` (same rule as `org-roam-node-slug`).
   Don't ask where to save it: the skill may run non-interactively (e.g. in
   a CI/CD container), so the working directory is the default. Finish by
   reporting the file's path.

## Template

```org
#+title: <Rezeptname>
#+created: [<YYYY-MM-DD Day HH:MM>]
#+filetags: :rezept:

Portionen: <n> | <Zeitangabe, falls vorhanden>

* Zutaten
  :PROPERTIES:
  :URL: <Quell-URL>
  :END:

  - <Zutat 1>
  - <Zutat 2>

* Arbeitsschritte

  1. <Schritt 1>
  2. <Schritt 2>

* Anmerkungen

  - <Anmerkung/Tipp 1>
```

**Indentation**: everything that belongs to a heading (its properties
drawer, its list items) is indented by (heading level + 1) spaces, never
flush against the left margin. Under a single-star heading like `* Zutaten`
that's 2 spaces; under a two-star subheading like `** Für die Soße` (see
grouped ingredients below) it's 3 spaces. The `*`/`**` stars themselves are
always flush left; only the content underneath is indented. This is the
standard Org convention (what you get from `org-indent-mode` or `M-RET`
inside a list) and the user expects it, so don't skip it even though a
flat, unindented list also parses.

Notes on filling it in:

- **Header**: exactly these three keyword lines, lower case, in this order.
  `#+created` is an inactive Org timestamp with the English weekday
  abbreviation, e.g. `[2026-10-10 Sat 20:49]`, same moment as the filename
  timestamp. Don't add other keywords (`#+AUTHOR`, `#+DATE`, ...), an
  org-roam `:ID:` drawer or a `#+template:` line; a calling pipeline adds
  the org-roam parts.
- Drop the parts of the "Portionen: ... |" line that aren't given (e.g. no
  time found: just "Portionen: 4"; neither found: omit the line).
- **Source URL**: the recipe's URL is not a top-level `#+PROPERTY:`. It goes
  into an Org properties drawer directly under the `* Zutaten` heading
  (`:PROPERTIES:` / `:URL: ...` / `:END:`), immediately before the
  ingredient list (or before the first `**` group, if the ingredients are
  grouped). If the user pasted the recipe text directly instead of giving a
  URL, omit the drawer entirely; there's no source URL to record.
- **Grouped ingredients**: when the source recipe splits ingredients into
  named groups (e.g. "für die Soße", "für den Teig"), reproduce those groups
  as `**` subheadings under `* Zutaten` instead of flattening them into one
  list. The grouping is part of the recipe's structure and losing it makes
  the steps harder to follow. The `:PROPERTIES:` drawer still sits right
  under `* Zutaten` itself (indented 2 spaces), above the first `**`
  subheading; each group's own ingredient list is then indented 3 spaces.
- **No notes/tips on the source**: still emit the `* Anmerkungen` heading,
  just leave it empty underneath. The outline must always have exactly
  these three top-level headings so every converted recipe has the same
  shape. Never drop a heading just because it would otherwise be empty.
- **Nutrition facts**: never carry these into `* Anmerkungen` (or anywhere
  else). Calories/fat/carbs/protein figures are common on recipe blogs but
  aren't a recipe instruction or tip. Leave them out entirely, even when
  the source presents them right alongside genuine author notes.
- **Numbered vs. bulleted steps**: `Arbeitsschritte` is always a numbered
  list (`1.`, `2.`, ...) even if the source uses bullets, since preparation
  order matters.
- Quote author tips/notes reasonably closely to the source rather than
  heavily paraphrasing them. Full verbatim quoting isn't required the way it
  is for the extraction step; natural German phrasing is fine.
