"""
Tiny dependency-free ASCII sparklines for trend rendering.

Used by the /chart command to draw multi-week metric trends inline in the
terminal (no matplotlib, no files). Pure functions — easy to unit-test.
"""

_BLOCKS = "▁▂▃▄▅▆▇█"


def sparkline(values: list[float | None]) -> str:
    """Render a sequence as a Unicode block sparkline.

    Gaps (None) render as a space so missing days are visible rather than
    silently collapsing the series. A flat series renders as the lowest block.
    Returns "" when there is no numeric data at all.
    """
    nums = [v for v in values if v is not None]
    if not nums:
        return ""
    lo, hi = min(nums), max(nums)
    rng = hi - lo
    out = []
    for v in values:
        if v is None:
            out.append(" ")
        elif rng == 0:
            out.append(_BLOCKS[0])
        else:
            idx = round((v - lo) / rng * (len(_BLOCKS) - 1))
            out.append(_BLOCKS[idx])
    return "".join(out)


def render_row(label: str, values: list[float | None], unit: str = "") -> str:
    """One compact trend line: 'label  <spark>  first→last (min–max)'.

    Direction arrow reflects first vs last non-None value. Intended for a
    fixed-width table of several metrics.
    """
    nums = [v for v in values if v is not None]
    spark = sparkline(values)
    if not nums:
        return f"{label:<14} {spark}  (no data)"
    first, last = nums[0], nums[-1]
    arrow = "→" if first == last else ("↑" if last > first else "↓")
    rng = f"{min(nums):g}–{max(nums):g}"
    return f"{label:<14} {spark}  {first:g}{arrow}{last:g} {unit} ({rng})".rstrip()
