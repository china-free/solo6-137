#!/usr/bin/env python3
import os
import sys
import tempfile
import subprocess
import shutil


HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "rom_font_extractor.py")


def encode_tile_1bpp(pixels):
    size = len(pixels)
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


def encode_tile_2bpp(pixels):
    size = len(pixels)
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


def build_font_A_8x8_1bpp():
    s = [
        "00111100",
        "01111110",
        "11000011",
        "11000011",
        "11111111",
        "11000011",
        "11000011",
        "11000011",
    ]
    return [[int(c) for c in row] for row in s]


def build_font_B_8x8_1bpp():
    s = [
        "11111100",
        "11000110",
        "11000011",
        "11111110",
        "11000011",
        "11000011",
        "11000110",
        "11111100",
    ]
    return [[int(c) for c in row] for row in s]


def build_heart_8x8_2bpp():
    s = [
        "00000000",
        "01100110",
        "12211221",
        "12333321",
        "12333321",
        "01233210",
        "00122100",
        "00011000",
    ]
    return [[int(c) for c in row] for row in s]


def build_checker_16x16_1bpp():
    px = [[0] * 16 for _ in range(16)]
    for y in range(16):
        for x in range(16):
            px[y][x] = 1 if ((x // 2) + (y // 2)) % 2 == 0 else 0
    return px


def build_test_rom(path):
    data = bytearray()
    header = bytearray(0x1000)
    data.extend(header)

    tiles_1bpp_8 = [build_font_A_8x8_1bpp(), build_font_B_8x8_1bpp()]
    offset_1bpp_8 = len(data)
    for px in tiles_1bpp_8:
        data.extend(encode_tile_1bpp(px))

    tiles_2bpp_8 = [build_heart_8x8_2bpp()]
    offset_2bpp_8 = len(data)
    for px in tiles_2bpp_8:
        data.extend(encode_tile_2bpp(px))

    tiles_1bpp_16 = [build_checker_16x16_1bpp()]
    offset_1bpp_16 = len(data)
    for px in tiles_1bpp_16:
        data.extend(encode_tile_1bpp(px))

    data.extend(bytearray(256))

    with open(path, "wb") as f:
        f.write(bytes(data))

    return {
        "offset_1bpp_8": offset_1bpp_8,
        "count_1bpp_8": len(tiles_1bpp_8),
        "tiles_1bpp_8": tiles_1bpp_8,
        "offset_2bpp_8": offset_2bpp_8,
        "count_2bpp_8": len(tiles_2bpp_8),
        "tiles_2bpp_8": tiles_2bpp_8,
        "offset_1bpp_16": offset_1bpp_16,
        "count_1bpp_16": len(tiles_1bpp_16),
        "tiles_1bpp_16": tiles_1bpp_16,
        "total_size": len(data),
    }


def run(args, expect_fail=False):
    cmd = [sys.executable, TOOL] + args
    print(f"\n>>> 运行: {' '.join(cmd)}")
    p = subprocess.run(cmd, capture_output=True, text=True)
    print("STDOUT:")
    print(p.stdout)
    if p.stderr:
        print("STDERR:")
        print(p.stderr)
    if expect_fail:
        assert p.returncode != 0, f"预期失败但返回码为 0: {p.returncode}"
    else:
        assert p.returncode == 0, f"返回码非 0: {p.returncode}\n{p.stderr}"
    return p.stdout, p.stderr


def pixels_equal(a, b):
    if len(a) != len(b):
        return False
    for r1, r2 in zip(a, b):
        if list(r1) != list(r2):
            return False
    return True


def test_all():
    tmp = tempfile.mkdtemp(prefix="rom_font_test_")
    try:
        rom = os.path.join(tmp, "test.nes")
        info = build_test_rom(rom)
        print(f"测试 ROM 已生成: {rom} ({info['total_size']} 字节)")

        run(["-r", rom, "-o", f"0x{info['offset_1bpp_8']:X}",
             "-b", "1", "-s", "8", "-n", str(info["count_1bpp_8"]), "-c", "2"])

        dict_1bpp = os.path.join(tmp, "dict_1bpp.txt")
        run(["-r", rom, "-o", str(info["offset_1bpp_8"]),
             "-b", "1", "-s", "8", "-n", str(info["count_1bpp_8"]),
             "-e", dict_1bpp, "--no-preview"])
        assert os.path.isfile(dict_1bpp), "字典文件未生成"

        run(["-r", rom, "-o", f"0x{info['offset_2bpp_8']:X}",
             "-b", "2", "-s", "8", "-n", str(info["count_2bpp_8"]),
             "-i", "-d", " .:oO@"])

        dict_2bpp = os.path.join(tmp, "dict_2bpp.txt")
        run(["-r", rom, "-o", f"0x{info['offset_2bpp_8']:X}",
             "-b", "2", "-s", "8", "-n", str(info["count_2bpp_8"]),
             "-e", dict_2bpp, "--no-preview"])

        run(["-r", rom, "-o", f"0x{info['offset_1bpp_16']:X}",
             "-b", "1", "-s", "16", "-n", str(info["count_1bpp_16"]), "-c", "1"])

        with open(dict_1bpp, "r", encoding="utf-8") as f:
            content = f.read()
        content = content.replace("11111111", "11111100").replace("1111110", "1111100", 1)
        modified_dict = os.path.join(tmp, "dict_modified.txt")
        with open(modified_dict, "w", encoding="utf-8") as f:
            f.write(content)

        rom_copy = os.path.join(tmp, "test_copy.nes")
        shutil.copyfile(rom, rom_copy)
        run(["--inject", modified_dict, "-r", rom_copy])

        with open(rom, "rb") as f:
            orig = f.read()
        with open(rom_copy, "rb") as f:
            modified = f.read()
        assert orig != modified, "注回后 ROM 应发生变化"
        print("注回后 ROM 已成功被修改 ✔")

        run(["-r", "nonexistent.nes", "-o", "0x0"], expect_fail=True)
        run(["-r", rom, "-o", f"0x{info['total_size'] + 0xFF:X}"], expect_fail=True)
        run(["--inject", dict_1bpp], expect_fail=True)

        print("\n" + "=" * 60)
        print("全部测试通过! ✅")
        print("=" * 60)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_all()
