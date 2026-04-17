from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.units import mm

PAGE_SIZE = A5
PAGE_W, PAGE_H = PAGE_SIZE

MARGIN = 15 * mm
INNER_MARGIN = 18 * mm
OUTER_MARGIN = 12 * mm
TOP_MARGIN = 15 * mm
BOTTOM_MARGIN = 15 * mm

TITLE_SIZE = 28
AUTHOR_SIZE = 14
BODY_SIZE = 14
BACK_SIZE = 12
# Cover-specific knobs — bigger type than the body for shelf-appeal.
COVER_TITLE_SIZE = 34
COVER_AUTHOR_SIZE = 14
# Height of the translucent band over the full-bleed drawing, and of
# the coloured header band on the title-band-top variant.
COVER_BAND_H = 42 * mm
COVER_BAND_ALPHA = 0.72
# Poster is the type-only template. Title wants to shout, so give it
# a bigger starting preference — shrink-to-fit still guarantees the
# title lands within the page. 52 chosen over a more aggressive 64
# because the shrink-for-fit kicks in earlier the bigger we start,
# and 64 was collapsing long English titles to unreadably small
# sizes before reaching the page edge.
COVER_POSTER_TITLE_SIZE = 52
# Below this point the title is small enough that a different
# template would probably have been the right call. Used as an
# advisory threshold by ``.claude/skills/select-cover-template`` — the
# fit code itself doesn't clamp here, it just shrinks enough to fit.
COVER_TITLE_MIN_READABLE = 14

LINE_HEIGHT = 1.35

FONT_REGULAR = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"

A4_SIZE = A4
