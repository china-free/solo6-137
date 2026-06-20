from __future__ import annotations

from codec import bytes_per_tile


DEFAULT_CHARSET = " .:-=+*#%@"


def pixel_to_ascii(value: int, bpp: int, charset: str, invert: bool = False) -> str:
    max_val = (1 << bpp) - 1
    if invert:
        value = max_val - value
    if max_val == 0:
        return charset[0]
    ratio = value / max_val
    idx = int(round(ratio * (len(charset) - 1)))
    return charset[idx]


def render_tile_lines(
    pixels: list[list[int]],
    bpp: int,
    charset: str = DEFAULT_CHARSET,
    invert: bool = False,
) -> list[str]:
    lines = []
    for row in pixels:
        line = "".join(
            pixel_to_ascii(v, bpp, charset, invert) for v in row
        )
        lines.append(line)
    return lines


def render_preview_text(
    tiles: list[list[list[int]]],
    size: int,
    bpp: int,
    offset: int,
    columns: int = 8,
    charset: str = DEFAULT_CHARSET,
    invert: bool = False,
) -> str:
    if not tiles:
        return "(没有可预览的图块)"

    n = len(tiles)
    rendered = [render_tile_lines(t, bpp, charset, invert) for t in tiles]
    bpt = bytes_per_tile(size, bpp)
    rows = (n + columns - 1) // columns
    tile_w = size
    gap_w = 3
    sep = " " * gap_w
    out_lines = []

    for r in range(rows):
        start = r * columns
        end = min(start + columns, n)

        header_parts = []
        for i in range(start, end):
            tile_offset = offset + i * bpt
            header = f"#{i:<3d} @{tile_offset:06X}"
            header_parts.append(header.ljust(tile_w + 1))
        out_lines.append(sep.join(header_parts))

        for y in range(size):
            line_parts = []
            for i in range(start, end):
                line_parts.append(" " + rendered[i][y])
            out_lines.append(sep.join(line_parts))

        if r < rows - 1:
            out_lines.append("")

    return "\n".join(out_lines)


def print_preview(
    tiles: list[list[list[int]]],
    size: int,
    bpp: int,
    offset: int,
    columns: int = 8,
    charset: str = DEFAULT_CHARSET,
    invert: bool = False,
) -> None:
    print(render_preview_text(
        tiles, size, bpp, offset, columns, charset, invert
    ))
