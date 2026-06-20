from __future__ import annotations


def bytes_per_tile(size: int, bpp: int) -> int:
    return (size * size * bpp) // 8


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


def decode_tile_2bpp_planar(data: bytes, size: int) -> list[list[int]]:
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
        return decode_tile_2bpp_planar(data, size)
    else:
        raise ValueError(f"不支持的 bpp: {bpp}")


def decode_tiles(
    data: bytes, size: int, bpp: int, count: int
) -> list[list[list[int]]]:
    bpt = bytes_per_tile(size, bpp)
    tiles = []
    for i in range(count):
        start = i * bpt
        end = start + bpt
        tile_data = data[start:end]
        tiles.append(decode_tile(tile_data, size, bpp))
    return tiles


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


def encode_tile_2bpp_planar(pixels: list[list[int]], size: int) -> bytes:
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
        return encode_tile_2bpp_planar(pixels, size)
    else:
        raise ValueError(f"不支持的 bpp: {bpp}")


def encode_tiles(tiles: list[list[list[int]]], size: int, bpp: int) -> bytes:
    out = bytearray()
    for t in tiles:
        out.extend(encode_tile(t, size, bpp))
    return bytes(out)


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


def parse_offset(s: str) -> int:
    s = s.strip()
    if s.lower().startswith("0x"):
        return int(s, 16)
    if s.lower().startswith("$"):
        return int(s[1:], 16)
    return int(s, 10)


def inject_rom(
    path: str, offset: int, tiles: list[list[list[int]]], size: int, bpp: int
) -> int:
    bpt = bytes_per_tile(size, bpp)
    total = bpt * len(tiles)
    file_size = _file_size(path)
    if offset + total > file_size:
        raise ValueError(
            f"注回范围超出 ROM 文件: 需要 0x{offset + total:X}, 文件仅 0x{file_size:X}"
        )

    with open(path, "r+b") as f:
        f.seek(offset)
        written = 0
        for idx, pixels in enumerate(tiles):
            data = encode_tile(pixels, size, bpp)
            if len(data) != bpt:
                raise RuntimeError(
                    f"图块 #{idx} 编码长度不符: {len(data)} != {bpt}"
                )
            f.write(data)
            written += len(data)
    return written


def _file_size(path: str) -> int:
    import os
    return os.path.getsize(path)


def import_dictionary(path: str):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    meta = {"size": None, "bpp": None, "offset": None, "count": 0}
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
                    bpp_str = stripped.split(":")[1].strip()
                    if bpp_str.endswith("bpp"):
                        bpp_str = bpp_str[:-3]
                    meta["bpp"] = int(bpp_str)
                except Exception:
                    pass
            elif stripped.startswith("# 起始偏移:"):
                try:
                    off_str = stripped.split(":")[1].strip()
                    meta["offset"] = parse_offset(off_str)
                except Exception:
                    pass
            elif stripped.startswith("# 图块数量:"):
                try:
                    meta["count"] = int(stripped.split(":")[1].strip())
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

    meta["count"] = len(tiles)
    return meta, tiles


def export_dictionary(
    tiles: list[list[list[int]]],
    size: int,
    bpp: int,
    offset: int,
    out_path: str,
) -> None:
    bpt = bytes_per_tile(size, bpp)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# ROM 点阵字体字典\n")
        f.write(f"# 字模尺寸: {size}x{size}\n")
        f.write(f"# 位深: {bpp}bpp\n")
        f.write(f"# 起始偏移: 0x{offset:X}\n")
        f.write(f"# 图块数量: {len(tiles)}\n")
        f.write(f"# 每图块字节数: {bpt}\n")
        f.write("# 格式: [index] @hex_offset\n")
        f.write(f"# 每行 {size} 个像素值(0-{ (1 << bpp) - 1 })\n")
        f.write("# 编辑像素数据即可，'注回'时以行为单位解析\n")
        f.write("\n")

        for idx, pixels in enumerate(tiles):
            tile_offset = offset + idx * bpt
            f.write(f"[{idx}] @0x{tile_offset:X}\n")
            for row in pixels:
                f.write("".join(str(v) for v in row) + "\n")
            f.write("\n")
