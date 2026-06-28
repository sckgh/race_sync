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

- **Brand colours:** the `style:` front-matter defines MRA brand variables at the top
  (`--mra-red`, `--virtual`, `--gold`). `--mra-red` is a *placeholder* — drop in MRA's exact
  hex from motorrace.com.au (and add the MRA logo to the title/close slides) once available.
  The `--virtual` cyan is intentional: red = the real field, cyan = the virtual field.
- **Trial framing:** the deck is built around trialling at the **Wakefield 300** (One
  Raceway, 28 Feb – 1 Mar 2026), iterating through the **Shelley 300** and other rounds, and
  showcasing at the **Sydney 300** — matching MRA's 2026 calendar (8 rounds, three 300 km
  enduros). Adjust dates/events if the calendar shifts.
- Add real numbers once known: target virtual-grid size, entry-fee/sponsorship figures.
- The deck is deliberately honest about the one hard unknown (putting real cars *inside* the
  sim) and the guaranteed fallback — keep that slide; it builds credibility with an operator.

## Source material

The claims map to the specs in [`../specs/`](../specs/) and the working code in
[`../src/racesync/`](../src/racesync/) — e.g. the audio bridge (`specs/07`), Safety
Car → Code 60 (`specs/06`), scoring (`specs/08`), collidable phantoms (`specs/13` §13.9),
and the delivery/rollout plan (`specs/10`).
