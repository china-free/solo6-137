#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys

from codec import (
    bytes_per_tile,
    decode_tiles,
    export_dictionary,
    import_dictionary,
    inject_rom,
    parse_offset,
    read_rom_slice,
)
from renderer import DEFAULT_CHARSET, print_preview


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
        default=DEFAULT_CHARSET,
        help=f"ASCII 密度字符集(从最亮到最暗, 默认: {DEFAULT_CHARSET!r})",
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


def _cmd_inject(args) -> int:
    if not args.rom:
        build_arg_parser().error("使用 --inject 注回时必须同时指定 --rom <path>")

    print(f"读取字典文件: {args.inject}")
    meta, tiles = import_dictionary(args.inject)
    print(
        f"解析到 {len(tiles)} 个图块 (size={meta['size']}x{meta['size']}, "
        f"bpp={meta['bpp']}, offset=0x{meta['offset']:X})"
    )
    written = inject_rom(
        args.rom, meta["offset"], tiles, meta["size"], meta["bpp"]
    )
    print(
        f"已成功将 {len(tiles)} 个图块注回到 {args.rom} "
        f"(偏移 0x{meta['offset']:X}, 共 {written} 字节)"
    )
    return 0


def _cmd_extract(args) -> int:
    if not args.rom:
        build_arg_parser().error("必须通过 -r/--rom 指定 ROM 文件路径，或使用 --inject 模式")
    if not os.path.isfile(args.rom):
        print(f"错误: ROM 文件不存在 -> {args.rom}", file=sys.stderr)
        return 2
    if args.offset is None:
        build_arg_parser().error("必须通过 -o/--offset 指定起始偏移量")

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

    tiles = decode_tiles(raw, size, bpp, count)

    print(
        f"ROM: {args.rom}  |  偏移: 0x{offset:X}  |  "
        f"{size}x{size} @ {bpp}bpp  |  图块数: {count}  |  "
        f"每块 {bpt} 字节  |  共读取 {total_bytes} 字节"
    )
    print("-" * 72)

    if not args.no_preview:
        print_preview(
            tiles, size, bpp, offset, args.columns, charset, args.invert
        )

    if args.export:
        export_dictionary(tiles, size, bpp, offset, args.export)
        print("-" * 72)
        print(f"已导出点阵字典 -> {args.export}")

    return 0


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.inject:
        return _cmd_inject(args)
    return _cmd_extract(args)


if __name__ == "__main__":
    raise SystemExit(main())
