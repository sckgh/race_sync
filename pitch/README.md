# Pitch deck — RaceSync for MRA

`MRA-RaceSync-pitch.md` is a 12-slide pitch deck for **Terry / Motor Racing Australia**,
making the case for running a virtual class alongside the Viola Private Wealth Sydney 300.

It's written in [Marp](https://marp.app/) Markdown, so it renders to slides, PDF, or PPTX.

## Render it

**VS Code:** install the *Marp for VS Code* extension, open the file, and use
"Export slide deck…" for PDF/PPTX/HTML.

**CLI:**

```bash
npx @marp-team/marp-cli MRA-RaceSync-pitch.md --pdf      # -> PDF
npx @marp-team/marp-cli MRA-RaceSync-pitch.md --pptx     # -> editable PowerPoint
npx @marp-team/marp-cli MRA-RaceSync-pitch.md            # -> HTML
```

## Tailoring before you send it

- Drop in MRA / event branding (logos, colours) via the `style:` block in the front-matter.
- Add real numbers once known: target virtual-grid size, entry-fee/sponsorship figures, and
  the pilot timeline.
- The deck is deliberately honest about the one hard unknown (putting real cars *inside* the
  sim) and the guaranteed fallback — keep that slide; it builds credibility with an operator.

## Source material

The claims map to the specs in [`../specs/`](../specs/) and the working code in
[`../src/racesync/`](../src/racesync/) — e.g. the audio bridge (`specs/07`), Safety
Car → Code 60 (`specs/06`), scoring (`specs/08`), collidable phantoms (`specs/13` §13.9),
and the delivery/rollout plan (`specs/10`).
