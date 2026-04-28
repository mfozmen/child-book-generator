# Printing the A4 booklet

Every render produces two PDFs in `.book-gen/output/`:

- `<slug>.pdf` — A5 reading copy. Open this on screen.
- `<slug>_A4_booklet.pdf` — A4 saddle-stitch imposition. Print this, fold, and staple to get a real book.

This document covers the print + fold + staple workflow for the booklet. The reading copy needs no setup — just open it in any PDF viewer.

## Why two files

The A4 booklet PDF is a **printing artefact**, not a reading file. Its pages are deliberately scrambled — when you scroll through it on screen, story page 4 appears before story page 1, story page 2 sits next to story page 3, and so on. That's how saddle-stitch printing works: the printer needs the pages in a specific imposition order so that, after duplex printing and folding, the reading order comes out right. **Don't try to read the booklet on screen — open the A5 file for that.**

If you only ever read the book on a screen, you don't need to print at all. Use the A5 file.

## Print settings

The booklet must be printed:

- **On A4 paper** (or Letter — Letter prints with a bit of margin slack)
- **Double-sided** (duplex)
- **Flipped on the short edge** (NOT the long edge — long edge inverts every other page)
- **At actual size** (do not enable "fit to page" / "shrink oversized pages" if the printer's paper matches the PDF size; otherwise let it scale to fit)
- **Without Adobe's "Booklet" mode** — the PDF is already imposed; Adobe's booklet feature would impose it again, ruining everything

### Adobe Acrobat / Adobe Reader

1. Open `<slug>_A4_booklet.pdf`
2. **File → Print** (or `Ctrl+P` / `Cmd+P`)
3. **"Page Sizing & Handling"** section — leave on **"Size"** (the default button). Pick **"Actual size"**. **Do NOT click "Booklet"** — our PDF is pre-imposed.
4. Check **"Print on both sides of paper"**
5. Choose **"Flip on short edge"** (sometimes labelled "Short-edge binding")
6. **Orientation: Auto** — the PDF is landscape A4; auto detects this correctly
7. **Pages: All**
8. Print

Turkish UI (Yazdır dialog):

| English | Türkçe |
|---|---|
| Print on both sides of paper | Kağıdın iki tarafını da yazdır |
| Flip on short edge | Kısa kenardan döndür |
| Actual size | Gerçek boyut |
| Booklet (avoid this) | Kitapçık (kullanma) |
| Pages: All | Yazdırılacak Sayfalar: Tümü |
| Orientation: Auto | Yönlendirme: Otomatik |

### Chrome / Edge browser PDF

1. Open the PDF in the browser
2. `Ctrl+P` → printer dialog
3. **More settings** (expand)
4. **Two-sided** ON, choose **"Print on both sides"** + **"Short edge"** binding
5. **Paper size: A4**, **Margins: Default**, **Scale: Default** or **100%**
6. Print

### macOS Preview

1. Open the PDF
2. `Cmd+P`
3. **Two-Sided**: ON, **Short-Edge binding**
4. **Scale: 100%** or "Fit to page" (paper-size dependent)
5. Print

## Manual duplex (printers without auto-duplex)

Many home printers (e.g. Canon Pixma MX-series) don't have automatic duplex. The print driver guides you through it:

1. Print as above (two-sided checkbox + short-edge)
2. Printer prints **front sides only** (PDF pages 1 + 3 for a 4-page imposition)
3. A dialog or prompt says "now flip the pages and reload them"
4. **Take the printed sheets** out of the output tray
5. **Flip them** so the printed side faces DOWN, with the **top edge facing the back of the printer**
6. Put the stack back into the input tray
7. Click "OK" in the prompt
8. Printer prints the **back sides** (PDF pages 2 + 4)

Different printer drivers describe the flip slightly differently. **Test with a single sheet first** — print the first 2 pages of your booklet on one A4, see whether front + back align correctly before printing the whole thing.

If the back side comes out upside-down on the same sheet, you flipped wrong. Common fixes:

- Rotate the stack 180° around the short edge (top↔bottom)
- Or just keep the orientation but feed top edge first (instead of bottom edge first)

## Fold + staple

After printing, the booklet for our example shape (4 visible story pages = 6 source pages = 2 physical A4 sheets) comes out like this:

| Sheet | Front side | Back side |
|---|---|---|
| Sheet 1 (outer) | back cover \| front cover | blank \| blank |
| Sheet 2 (inner) | story 4 \| story 1 | story 2 \| story 3 |

(The blank sheet is intentional — it folds to the inside-front-cover and inside-back-cover, both blank. That's how children's books print. See [the imposition section](#why-the-blank-page-is-correct) below if it bothers you.)

To fold:

1. **Stack the sheets in print order**: Sheet 1 ON TOP, Sheet 2 UNDERNEATH. (The printer outputs them in this order; don't shuffle.)
2. **Fold the stack in half**, bringing the right side over to meet the left side. The fold becomes the **spine** on the **left**.
3. **Open up the booklet** to check: cover should be on the front, back cover on the back, story pages flow in order when you turn pages.

To staple:

1. Use a **long-reach stapler** (saddle stapler) if you have one — it can reach the centre fold from outside.
2. If you only have a regular stapler:
   - Open the folded booklet to the centre spread (story 2 + story 3 facing you)
   - Staple **through the fold** twice — once near the top of the spine, once near the bottom
   - The staples should pierce all pages and bend on the inside of the spine
3. Re-fold and check the binding holds.

Two staples is enough for a 2-sheet booklet. For thicker booklets (more story pages), use 2-3 staples spaced evenly along the spine.

## Reading order after fold

When you open the printed booklet, you should see:

1. **Outside front**: the cover (your title + author + cover artwork or poster style)
2. **Open the cover**: blank (inside-front cover) on the left, story 1 on the right
3. **Turn the page**: story 2 on the left, story 3 on the right
4. **Turn the page**: story 4 on the left, blank (inside-back cover) on the right
5. **Close**: back cover (your blurb if you set one)

If the order is wrong, the most likely cause is **wrong duplex flip orientation** — short-edge vs long-edge confusion. Re-print one sheet with the other binding option and see.

## Why the blank page is correct

For a book with 4 story pages plus the cover and back cover, the source PDF has 6 pages. Saddle-stitch booklets need a **multiple of 4** pages to fold cleanly. 6 is not a multiple of 4, so the imposition adds 2 padding blanks: one at the inside-front-cover position, one at the inside-back-cover position.

Those 2 blanks land on the same physical A4 sheet — the verso of the outer cover sheet. When duplex printed, that A4 sheet's back side is fully blank, while its front side has the cover/back-cover. **No paper is wasted in duplex mode** — the printer prints on both sides; the back side just happens to have nothing on it.

If you print **single-sided**, you'd get one extra blank A4 sheet (the back-side blank prints as its own page). To avoid that, either print duplex or expand the book to 6 story pages (cover + 6 story + back = 8 = multiple of 4, no padding, no blank A4 sheet).

The fold-time effect: the inside-front-cover and inside-back-cover are blank, which is the standard layout in printed children's books. Open any picture book — the inside covers are usually blank or carry a publisher logo, never main story content.

## Quick reference

```
Print settings (most viewers)
─────────────────────────────
  Pages         All
  Paper size    A4
  Orientation   Auto / Landscape
  Two-sided     ON
  Binding       Short edge      ← critical
  Scale         100% / Actual
  Booklet mode  OFF             ← critical (don't double-impose)
```

```
After printing (4-page booklet)
───────────────────────────────
  Sheet 1: covers outside, blank inside
  Sheet 2: stories outside, stories inside
  Stack:   sheet 1 on top, sheet 2 below
  Fold:    in half, spine on the LEFT
  Staple:  through the fold, 2 staples
```
