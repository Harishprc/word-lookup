---
name: Word Lookup Register
colors:
  primary: "#14171C"
  secondary: "#5B6472"
  tertiary: "#7150F0"
  neutral: "#F6F8FC"
  surface: "#FFFFFF"
  on-surface: "#14171C"
  on-primary: "#FFFFFF"
  on-tertiary: "#FFFFFF"
  tertiary-hover: "#6535E0"
  tertiary-subtle: "#F1EDFF"
  brand-identity: "#7C5CFF"
  outline: "#E3E8F0"
  header-surface: "#EEF2F9"
  header-on-surface: "#4A5261"
  error: "#B3261E"
  surface-dark: "#1A1D23"
  neutral-dark: "#111318"
  on-surface-dark: "#E7E9EE"
  secondary-dark: "#A2AAB8"
  tertiary-dark: "#B7A4FF"
  outline-dark: "#2C313A"
  header-surface-dark: "#20242B"
  error-dark: "#F2B8B5"
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Noto Sans Kannada
    fontSize: 19px
    fontWeight: 500
    lineHeight: 1.7
  body-md:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: 400
    lineHeight: 1.55
  body-sm:
    fontFamily: Inter
    fontSize: 13.5px
    fontWeight: 400
    lineHeight: 1.5
  body-native:
    fontFamily: Noto Sans Kannada
    fontSize: 15px
    fontWeight: 400
    lineHeight: 1.75
  label-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: 500
    lineHeight: 1.4
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: 600
    lineHeight: 1
    letterSpacing: 0.07em
rounded:
  sm: 4px
  md: 8px
  lg: 12px
  xl: 16px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 32px
  xl: 64px
  gutter: 24px
  container-padding: 24px
  cell-x: 16px
  cell-y: 14px
components:
  button-primary:
    backgroundColor: "{colors.tertiary}"
    textColor: "{colors.on-tertiary}"
    typography: "{typography.label-md}"
    rounded: "{rounded.md}"
    height: 36px
    padding: 0 16px
  button-primary-hover:
    backgroundColor: "{colors.tertiary-hover}"
    textColor: "{colors.on-tertiary}"
  button-secondary:
    backgroundColor: transparent
    textColor: "{colors.tertiary}"
    typography: "{typography.label-md}"
    rounded: "{rounded.md}"
    height: 36px
    padding: 0 12px
  button-secondary-hover:
    backgroundColor: "{colors.tertiary-subtle}"
    textColor: "{colors.tertiary}"
  input-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    padding: "{spacing.sm}"
    height: 40px
  input-field-focus:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
  table-header:
    backgroundColor: "{colors.header-surface}"
    textColor: "{colors.header-on-surface}"
    typography: "{typography.label-sm}"
    height: 36px
    padding: 0 16px
  table-row:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    padding: "{spacing.md}"
  table-row-hover:
    backgroundColor: "{colors.tertiary-subtle}"
    textColor: "{colors.on-surface}"
  headword:
    textColor: "{colors.primary}"
    typography: "{typography.headline-md}"
  translation:
    textColor: "{colors.primary}"
    typography: "{typography.body-lg}"
  metadata:
    textColor: "{colors.secondary}"
    typography: "{typography.body-sm}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: "{spacing.gutter}"
  empty-state:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.secondary}"
    typography: "{typography.body-md}"
    padding: "{spacing.xl}"
---

## Overview

The Word Register is the quiet half of Word Lookup. The popup is a two-second
glance; this is the page you open on purpose, to find a word you half-remember
or to re-read the ten you met this week. It is a personal record, not a
dashboard - there is no one to impress and nothing to sell, so the design's
only job is to get out of the way of the text.

Three adjectives drive it: **calm, legible, focused**. Calm means one accent
colour and no decoration that isn't carrying information. Legible means the
native-script column - Kannada, Devanagari, Tamil - is set larger and looser
than the English around it, because conjunct scripts need vertical room that
Latin does not. Focused means the search field is the only control on the
page.

## Colors

A near-neutral page with a single violet accent, carried over from the tray
icon so the register reads as the same product as the popup.

- **Primary (#14171C):** Near-black ink for headwords, meanings and
  translations. Softened off pure black so long reading sessions don't glare.
- **Secondary (#5B6472):** Slate for metadata - language, date, part of
  speech. Passes AA at 5.98:1, so it recedes without becoming unreadable.
- **Tertiary (#7150F0):** The interaction colour - search focus ring, links,
  primary buttons. This is a deliberately darkened version of the tray icon's
  **#7C5CFF**, which fails WCAG AA on white at 4.35:1; #7150F0 reaches 5.11:1
  and is indistinguishable at a glance. The original violet survives as
  `brand-identity` for the icon only, where it never sits under text.
- **Neutral (#F6F8FC):** Cool off-white page behind the table, so the white
  card floats without needing a heavy border.
- **Surface (#FFFFFF):** The table and card. Pure white maximises contrast for
  native scripts, whose thin strokes suffer on tinted backgrounds.
- **Tertiary-subtle (#F1EDFF):** Row hover and secondary-button hover. Tints
  rather than outlines, so hovering never shifts layout.
- **Error (#B3261E):** Reserved for genuine failures. Never used for emphasis.

Dark mode mirrors every pair rather than inverting the page: surfaces lift to
**#1A1D23** on a **#111318** ground, ink drops to **#E7E9EE**, and the accent
*lightens* to **#B7A4FF** (7.85:1) because the light-mode violet is far too
dark to read on a dark surface. Every pairing above was verified against WCAG
AA; the palette contains no pair below 4.5:1 in either theme.

## Typography

Two families, split by writing system rather than by decoration. **Inter**
sets all Latin text; **Noto Sans Kannada** (falling back to Nirmala UI, then
Segoe UI) sets every native-script cell. This mirrors the popup, which already
switches families for the translation row - Segoe UI has no Indic glyphs, and
letting the browser pick a fallback produces inconsistent conjunct rendering.

- **display-lg (28px/600):** The page title only. Appears once.
- **headline-md (18px/600):** The headword. The heaviest thing in each row,
  because scanning this column is the primary task.
- **body-lg (19px/500, Noto Sans Kannada):** The translation. Larger than the
  English body text on purpose - Indic conjuncts carry more detail per glyph
  and are genuinely harder to read at Latin sizes.
- **body-md / body-sm (15px / 13.5px):** Meanings and English examples.
- **body-native (15px, line-height 1.75):** Native example sentences. The
  loosest line-height in the system; stacked conjuncts collide at 1.5.
- **label-sm (11px/600, 0.07em):** Uppercase column headers. Letter-spaced
  because uppercase at small sizes is hard to parse without it.

## Layout

An 8px base unit throughout. The table is fluid - `min(100%, 1680px)` - so it
fills the window instead of sitting in a fixed column that looks stranded on a
large monitor. Reading measure is protected per-*column* rather than by
starving the whole table of width: columns are sized in percentages, so they
grow together and no single column swallows the slack. The 1680px cap exists
because past roughly that point rows get wide enough that the eye loses its
place moving from Meaning to Translation.

(This replaces an earlier fixed `1100px`, which protected measure at the cost
of wasting most of a wide screen - the wrong side of that trade.)

The table is the whole page. Cells use asymmetric padding (`16px` horizontal,
`14px` vertical) because rows are visually separated by rules rather than
gaps, and the extra horizontal room is what keeps adjacent columns from
reading as one block. Columns are ordered by scanning frequency: headword,
meaning, English example, synonyms, translation, native example, then language
and date last - the two you almost never search by.

The search field is sticky at the top. Filtering happens live on every
keystroke, over every column, so there is no submit button and no result
count to interpret.

## Elevation & Depth

Depth is carried by a single soft shadow and nothing else. The table gets one
`0 4px 24px rgba(0,0,0,.06)` shadow to lift it off the page; rows are divided
by 1px `outline` rules, never by shadows or alternating fills. Zebra striping
is deliberately absent - with a native-script column already drawing the eye,
a second competing rhythm makes the table harder to scan, not easier.

In dark mode a drop shadow does essentially nothing on a dark ground, so it is
dropped - but the surface being lighter than the page is **not** enough to
replace it. `#1A1D23` on `#111318` measures 1.10:1, and the header against the
surface 1.08:1: both imperceptible. Shipped that way, the table had no visible
edge at all, which read as a header that didn't line up and a date column
floating outside the table.

Dark mode therefore draws the table's edge with an explicit 1px `outline`
border (1.29:1 against the surface) instead of elevation - the usual way dark
UIs replace shadow. Light mode keeps the shadow and needs no border: page vs
surface is only 1.06:1 there too, so the shadow is doing that work.

**The general rule:** a surface boundary needs a shadow or a border. Tonal
difference alone does not survive contact with a real screen - this section
previously claimed it did, and it was wrong.

## Shapes

Soft but not playful: `12px` on the table and cards, `8px` on inputs and
buttons, `4px` reserved for the smallest chips. Corners are rounded enough to
feel like the popup's card - which uses the same 12px radius - and no more.
Nothing is a pill; fully-rounded shapes read as marketing, and this is a
reference tool.

## Components

**Search field.** The only always-visible control. Full width up to `420px`,
`8px` radius, resting on a 1px `outline` border that becomes a 2px
`tertiary` ring on focus. Placeholder names what is actually searched
("Search word, meaning, synonym…") rather than a bare "Search".

**Table.** Header row in `header-surface` with `label-sm` uppercase labels,
sticky so column meaning survives scrolling. Body rows tint to
`tertiary-subtle` on hover - a tint, never a border change, so nothing
reflows under the cursor.

**Headword cell.** Headword in `headline-md`, with the part of speech
immediately after it in `metadata` style, italic. This mirrors the popup's
"word · adjective" arrangement exactly.

**Translation cell.** Translation in `body-lg`, native synonyms directly
beneath in `metadata` at native size. The native example sentence lives in its
own column, not stacked here - long sentences stretched this cell wide enough
to bury the translation itself.

**Buttons.** Primary is solid `tertiary` with white text at 36px tall - small,
because nothing on this page is a call to action. Secondary is text-only in
`tertiary`, gaining a `tertiary-subtle` background on hover.

**Empty state.** Centred `body-md` in `secondary`, with no illustration and no
button: "No lookups yet - select a word and press the Forward button." It
states the action that fills the page, then stops.

## Do's and Don'ts

- **Do** set every native-script string in the Noto Sans Kannada stack, never
  the Latin family. Indic conjuncts break in fonts that lack them.
- **Do** keep the native-script size at or above the surrounding Latin size.
  Matching sizes makes conjuncts measurably harder to read.
- **Do** use `tertiary` (#7150F0) for anything with text on it, and reserve
  `brand-identity` (#7C5CFF) for the icon. The brighter violet fails WCAG AA.
- **Do** convey row state with background tint only. Changing borders or
  weight on hover shifts layout and makes long lists feel unstable.
- **Don't** add zebra striping, column dividers, or a second accent colour.
  The native column is already the visual anchor; anything else competes.
- **Don't** introduce a second interaction colour for destructive actions -
  use `error` for the text or icon and keep the surface neutral.
- **Don't** truncate meanings or examples with ellipsis. This page exists to
  be read; let rows grow taller instead.
- **Don't** add pagination, sorting controls, or filter chips. Live search
  over one flat list is the entire interaction model.
