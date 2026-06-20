#!/usr/bin/env python3
import argparse
import os
import sys


def parse_offset(s: str) -> int:
    s = s.strip()
    if s.lower().startswith("0x"):
        return int(s, 16)
    if s.lower().startswith("$"):
        return int(s[1:], 16)
    return int(s, 10)


def bytes_per_tile(size: int, bpp: int) -> int:
    return (size * size * bpp) // 8


def read_rom_slice(path: str, offset: int, length: int) -> bytes:
    with open(path, "rb") as f:
        f.seek(offset)
        data = f.read(length)
    if len(data) < length:
        raise ValueError(
            f"文件读取不足: 需要 {length} 字节，实际只读到 {len(data)} 字节。"
            f" 请检查偏移量 0x{offset:X} 是否超出文件末尾。"
        )
    return data


def decode_tile_1bpp(data: bytes, size: int) -> list[list[int]]:
    pixels = [[0] * size for _ in range(size)]
    row_bytes = size // 8
    idx = 0
    for y in range(size):
        for rb in range(row_bytes):
            b = data[idx]
            idx += 1
            for bi in range(8):
                x = rb * 8 + bi
                if x < size:
                    pixels[y][x] = (b >> (7 - bi)) & 1
    return pixels


def decode_tile_2bpp(data: bytes, size: int) -> list[list[int]]:
    pixels = [[0] * size for _ in range(size)]
    row_bytes = size // 8
    idx = 0
    for y in range(size):
        lo = [0] * size
        hi = [0] * size
        for rb in range(row_bytes):
            b_lo = data[idx]
            idx += 1
            b_hi = data[idx]
            idx += 1
            for bi in range(8):
                x = rb * 8 + bi
                if x < size:
                    lo[x] = (b_lo >> (7 - bi)) & 1
                    hi[x] = (b_hi >> (7 - bi)) & 1
        for x in range(size):
            pixels[y][x] = (hi[x] << 1) | lo[x]
    return pixels


def decode_tile(data: bytes, size: int, bpp: int) -> list[list[int]]:
    if bpp == 1:
        return decode_tile_1bpp(data, size)
    elif bpp == 2:
        return decode_tile_2bpp(data, size)
    else:
        raise ValueError(f"不支持的 bpp: {bpp}")


def pixel_to_ascii(value: int, bpp: int, charset: str, invert: bool) -> str:
    max_val = (1 << bpp) - 1
    if invert:
        value = max_val - value
    if max_val == 0:
        return charset[0]
    ratio = value / max_val
    idx = int(round(ratio * (len(charset) - 1)))
    return charset[idx]


def render_tile_lines(
    pixels: list[list[int]], bpp: int, charset: str, invert: bool
) -> list[str]:
    lines = []
    for row in pixels:
        line = "".join(pixel_to_ascii(v, bpp, charset, invert) for v in row)
        lines.append(line)
    return lines


def print_preview(
    tiles: list[list[list[int]]],
    size: int,
    bpp: int,
    charset: str,
    invert: bool,
    columns: int,
    offset: int,
) -> None:
    if not tiles:
        print("(没有可预览的图块)")
        return

    n = len(tiles)
    rendered = [render_tile_lines(t, bpp, charset, invert) for t in tiles]
    bpt = bytes_per_tile(size, bpp)

    rows = (n + columns - 1) // columns

    tile_w = size
    gap_w = 3
    idx_h = 1
    sep = " " * gap_w

    for r in range(rows):
        start = r * columns
        end = min(start + columns, n)

        header_parts = []
        for i in range(start, end):
            tile_offset = offset + i * bpt
            header = f"#{i:<3d} @{tile_offset:06X}"
            header_parts.append(header.ljust(tile_w + idx_h))
        print(sep.join(header_parts))

        for y in range(size):
            line_parts = []
            for i in range(start, end):
                line_parts.append(" " + rendered[i][y])
            print(sep.join(line_parts))

        if r < rows - 1:
            print()


def export_dictionary(
    tiles: list[list[list[int]]],
    size: int,
    bpp: int,
    offset: int,
    out_path: str,
) -> None:
    bpt = bytes_per_tile(size, bpp)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# ROM 点阵字体字典\n")
        f.write(f"# 字模尺寸: {size}x{size}\n")
        f.write(f"# 位深: {bpp}bpp\n")
        f.write(f"# 起始偏移: 0x{offset:X}\n")
        f.write(f"# 图块数量: {len(tiles)}\n")
        f.write(f"# 每图块字节数: {bpt}\n")
        f.write(f"# 格式: [index] @hex_offset  # 可选注释\n")
        f.write(f"# 每行 {size} 个像素值(0-{ (1<<bpp)-1 })\n")
        f.write(f"# 编辑像素数据即可，'注回'时以行为单位解析\n")
        f.write("\n")

        for idx, pixels in enumerate(tiles):
            tile_offset = offset + idx * bpt
            f.write(f"[{idx}] @0x{tile_offset:X}\n")
            for row in pixels:
                f.write("".join(str(v) for v in row) + "\n")
            f.write("\n")


def import_dictionary(path: str):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    meta = {"size": None, "bpp": None, "offset": None}
    tiles = []
    current = None

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            if current is not None:
                if meta["size"] and len(current) == meta["size"]:
                    tiles.append(current)
                current = None
            continue

        if stripped.startswith("#"):
            if stripped.startswith("# 字模尺寸:"):
                try:
                    meta["size"] = int(stripped.split(":")[1].strip().split("x")[0])
                except Exception:
                    pass
            elif stripped.startswith("# 位深:"):
                try:
                    meta["bpp"] = int(stripped.split(":")[1].strip().rstrip("bpp"))
                except Exception:
                    pass
            elif stripped.startswith("# 起始偏移:"):
                try:
                    off_str = stripped.split(":")[1].strip()
                    meta["offset"] = parse_offset(off_str)
                except Exception:
                    pass
            continue

        if stripped.startswith("[") and "]" in stripped:
            current = []
            continue

        if current is not None and all(c in "0123" for c in stripped):
            row = [int(c) for c in stripped]
            current.append(row)
            if meta["size"] is None:
                meta["size"] = len(row)

    if current is not None and meta["size"] and len(current) == meta["size"]:
        tiles.append(current)

    if meta["bpp"] is None and tiles:
        mx = max(max(r) for t in tiles for r in t)
        if mx <= 1:
            meta["bpp"] = 1
        elif mx <= 3:
            meta["bpp"] = 2

    return meta, tiles


def encode_tile_1bpp(pixels: list[list[int]], size: int) -> bytes:
    out = bytearray()
    row_bytes = size // 8
    for y in range(size):
        for rb in range(row_bytes):
            b = 0
            for bi in range(8):
                x = rb * 8 + bi
                v = pixels[y][x] if (x < size and y < size) else 0
                b |= (v & 1) << (7 - bi)
            out.append(b)
    return bytes(out)


def encode_tile_2bpp(pixels: list[list[int]], size: int) -> bytes:
    out = bytearray()
    row_bytes = size // 8
    for y in range(size):
        for rb in range(row_bytes):
            b_lo = 0
            b_hi = 0
            for bi in range(8):
                x = rb * 8 + bi
                v = pixels[y][x] if (x < size and y < size) else 0
                b_lo |= ((v & 1) << (7 - bi))
                b_hi |= (((v >> 1) & 1) << (7 - bi))
            out.append(b_lo)
            out.append(b_hi)
    return bytes(out)


def encode_tile(pixels: list[list[int]], size: int, bpp: int) -> bytes:
    if bpp == 1:
        return encode_tile_1bpp(pixels, size)
    elif bpp == 2:
        return encode_tile_2bpp(pixels, size)
    else:
        raise ValueError(f"不支持的 bpp: {bpp}")


def inject_back(rom_path: str, meta: dict, tiles: list[list[list[int]]]) -> None:
    size = meta["size"]
    bpp = meta["bpp"]
    offset = meta["offset"]
    if not (size and bpp and offset is not None and tiles):
        raise ValueError("字典文件缺少必要元信息，无法注回。")

    bpt = bytes_per_tile(size, bpp)
    total = bpt * len(tiles)
    file_size = os.path.getsize(rom_path)
    if offset + total > file_size:
        raise ValueError(
            f"注回范围超出 ROM 文件: 需要 0x{offset + total:X}, 文件仅 0x{file_size:X}"
        )

    with open(rom_path, "r+b") as f:
        f.seek(offset)
        for idx, pixels in enumerate(tiles):
            data = encode_tile(pixels, size, bpp)
            f.write(data)
            if len(data) != bpt:
                raise RuntimeError(
                    f"图块 #{idx} 编码长度不符: {len(data)} != {bpt}"
                )
    print(
        f"已成功将 {len(tiles)} 个图块注回到 {rom_path} (偏移 0x{offset:X}, 共 {total} 字节)"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rom_font_extractor",
        description="早期游戏 ROM 点阵字体字节码终端提取/注回工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例:
  # 预览偏移 0x1000 处 16 个 1bpp 8x8 字模
  python rom_font_extractor.py -r game.nes -o 0x1000 -n 16

  # 预览 2bpp 16x16 字模并导出字典
  python rom_font_extractor.py -r game.gb -o 0x2000 --bpp 2 -s 16 -n 32 -e font_dict.txt

  # 黑白反转, 自定义密度字符, 4 列显示
  python rom_font_extractor.py -r game.nes -o 0x4000 -n 64 -i -d " .oO@" -c 4

  # 将编辑过的字典文件注回到 ROM
  python rom_font_extractor.py --inject font_dict.txt -r game.gb
""",
    )

    p.add_argument("-r", "--rom", type=str, help="ROM 文件路径 (.nes/.gb/.bin 等)")
    p.add_argument(
        "-o",
        "--offset",
        type=str,
        help="起始偏移量，支持十进制、0x 或 $ 前缀十六进制，例: 0x1A2B",
    )
    p.add_argument(
        "-b",
        "--bpp",
        type=int,
        choices=[1, 2],
        default=1,
        help="每像素位数 (1 或 2, 默认: 1)",
    )
    p.add_argument(
        "-s",
        "--size",
        type=int,
        choices=[8, 16],
        default=8,
        help="单个字模像素尺寸 (8 或 16, 默认: 8)",
    )
    p.add_argument(
        "-n",
        "--count",
        type=int,
        default=16,
        help="要提取/预览的图块数量 (默认: 16)",
    )
    p.add_argument(
        "-c",
        "--columns",
        type=int,
        default=8,
        help="预览时每行显示多少个图块 (默认: 8)",
    )
    p.add_argument(
        "-d",
        "--density",
        type=str,
        default=" .:-=+*#%@",
        help="ASCII 密度字符集(从最亮到最暗, 默认: ' .:-=+*#%%@')",
    )
    p.add_argument(
        "-i", "--invert", action="store_true", help="反转黑白色(0 与最大值对调)"
    )
    p.add_argument(
        "-e",
        "--export",
        type=str,
        default=None,
        help="将解析出的字模导出为纯文本点阵字典文件路径",
    )
    p.add_argument(
        "--inject",
        type=str,
        default=None,
        help="将点阵字典文件注回到 ROM (需同时指定 --rom)",
    )
    p.add_argument(
        "--no-preview",
        action="store_true",
        help="只导出不预览 (常用于批处理)",
    )

    return p


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.inject:
        if not args.rom:
            parser.error("使用 --inject 注回时必须同时指定 --rom <path>")
        print(f"读取字典文件: {args.inject}")
        meta, tiles = import_dictionary(args.inject)
        print(
            f"解析到 {len(tiles)} 个图块 (size={meta['size']}x{meta['size']}, "
            f"bpp={meta['bpp']}, offset=0x{meta['offset']:X})"
        )
        inject_back(args.rom, meta, tiles)
        return 0

    if not args.rom:
        parser.error("必须通过 -r/--rom 指定 ROM 文件路径，或使用 --inject 模式")
    if not os.path.isfile(args.rom):
        print(f"错误: ROM 文件不存在 -> {args.rom}", file=sys.stderr)
        return 2
    if args.offset is None:
        parser.error("必须通过 -o/--offset 指定起始偏移量")

    try:
        offset = parse_offset(args.offset)
    except ValueError as e:
        print(f"错误: 偏移量无法解析 -> {args.offset} ({e})", file=sys.stderr)
        return 2

    size = args.size
    bpp = args.bpp
    count = max(1, args.count)
    bpt = bytes_per_tile(size, bpp)
    total_bytes = bpt * count

    file_size = os.path.getsize(args.rom)
    if offset >= file_size:
        print(
            f"错误: 偏移量 0x{offset:X} 超出文件长度 0x{file_size:X}",
            file=sys.stderr,
        )
        return 2

    clamped_total = min(total_bytes, file_size - offset)
    actual_count = clamped_total // bpt
    if actual_count < count:
        print(
            f"警告: 文件末尾限制，实际只能读取 {actual_count} 个图块 (需要 {count} 个)\n"
        )
        count = actual_count
        total_bytes = clamped_total

    try:
        raw = read_rom_slice(args.rom, offset, total_bytes)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2

    charset = args.density
    if len(charset) < 2:
        print(
            "警告: 密度字符集至少 2 个字符，使用默认 ' .#'",
            file=sys.stderr,
        )
        charset = " .#"

    tiles = []
    for i in range(count):
        start = i * bpt
        end = start + bpt
        tile_data = raw[start:end]
        pixels = decode_tile(tile_data, size, bpp)
        tiles.append(pixels)

    print(
        f"ROM: {args.rom}  |  偏移: 0x{offset:X}  |  "
        f"{size}x{size} @ {bpp}bpp  |  图块数: {count}  |  "
        f"每块 {bpt} 字节  |  共读取 {total_bytes} 字节"
    )
    print("-" * 72)

    if not args.no_preview:
        print_preview(
            tiles, size, bpp, charset, args.invert, args.columns, offset
        )

    if args.export:
        export_dictionary(tiles, size, bpp, offset, args.export)
        print("-" * 72)
        print(f"已导出点阵字典 -> {args.export}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
