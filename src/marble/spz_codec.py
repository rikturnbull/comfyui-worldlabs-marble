"""Pure-Python SPZ -> PLY decoder for 3D Gaussian splats.

SPZ is Niantic's gzip-compressed, quantized container for gaussian splats
(https://github.com/nianticlabs/spz). This module decodes the v1/v2/v3 binary
layout using only numpy + the stdlib, then writes the standard INRIA 3DGS PLY
layout (binary_little_endian) that other splat tools/viewers expect.

Keeping this dependency-free (no compiled C++ bindings) matches the rest of the
package and works on Windows ComfyUI installs with no build toolchain.
"""

from __future__ import annotations

import gzip
import struct
from dataclasses import dataclass

import numpy as np

SPZ_MAGIC = 0x5053474E  # "NGSP" little-endian
HEADER_SIZE = 16

# SH coefficient count per (rgb) channel for each SH degree.
_SH_DIM_FOR_DEGREE = {0: 0, 1: 3, 2: 8, 3: 15, 4: 24}

# Quantization constants, mirrored from the reference load-spz.cc.
_COLOR_SCALE = 0.15
_SQRT_HALF = 0.7071067811865476


@dataclass
class GaussianCloud:
    """Decoded gaussian splat fields, ready to serialize to PLY.

    Arrays are float32 with one row per gaussian:
      positions (N, 3), scales (N, 3, log-space), rotations (N, 4, xyzw),
      alphas (N, pre-sigmoid logit), colors (N, 3, SH DC / f_dc),
      sh (N, K, 3) extra SH coefficients where K = sh_dim_for_degree(sh_degree).
    """

    positions: np.ndarray
    scales: np.ndarray
    rotations: np.ndarray
    alphas: np.ndarray
    colors: np.ndarray
    sh: np.ndarray
    sh_degree: int
    antialiased: bool

    @property
    def num_points(self) -> int:
        return int(self.positions.shape[0])


def sh_dim_for_degree(degree: int) -> int:
    try:
        return _SH_DIM_FOR_DEGREE[degree]
    except KeyError as e:
        raise ValueError(f"unsupported SH degree {degree} (expected 0-4)") from e


def _inv_sigmoid(y: np.ndarray) -> np.ndarray:
    y = np.clip(y, 1e-6, 1.0 - 1e-6)
    return np.log(y / (1.0 - y)).astype(np.float32)


def _decode_positions(buf: np.ndarray, num: int, fractional_bits: int) -> np.ndarray:
    """24-bit little-endian signed fixed-point, 9 bytes per point."""
    b = buf.reshape(num * 3, 3).astype(np.int32)
    vals = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
    vals = np.where(vals & 0x800000, vals - (1 << 24), vals)
    scale = float(1 << fractional_bits)
    return (vals.astype(np.float32) / scale).reshape(num, 3)


def _decode_rotations_v2(buf: np.ndarray, num: int) -> np.ndarray:
    """3 bytes/point; w reconstructed from the unit-length constraint."""
    xyz = buf.reshape(num, 3).astype(np.float32) / 127.5 - 1.0
    w = np.sqrt(np.clip(1.0 - np.sum(xyz * xyz, axis=1), 0.0, None))
    out = np.empty((num, 4), dtype=np.float32)
    out[:, :3] = xyz
    out[:, 3] = w
    return out


def _decode_rotations_smallest_three(packed: np.ndarray, num: int) -> np.ndarray:
    """v3+ 'smallest three' quaternion packing, 4 bytes/point.

    Bits 30-31 select the omitted (largest) component; the other three are
    9-bit magnitude + 1 sign bit each, scaled by sqrt(1/2). The omitted
    component is reconstructed from the unit-length constraint.
    """
    out = np.zeros((num, 4), dtype=np.float32)
    largest = (packed >> 30) & 0x3
    for slot in range(4):
        # comp index = number of non-largest slots before `slot`
        comp_index = np.zeros(num, dtype=np.int64)
        for prev in range(slot):
            comp_index += (largest != prev).astype(np.int64)
        shift = comp_index * 10
        raw = (packed >> shift) & 0x3FF
        mag = (raw & 0x1FF).astype(np.float32)
        sign = np.where((raw & 0x200) != 0, -1.0, 1.0).astype(np.float32)
        value = (sign * (_SQRT_HALF * mag) / 511.0).astype(np.float32)
        out[:, slot] = np.where(largest == slot, 0.0, value)
    sum_sq = np.sum(out * out, axis=1)
    largest_val = np.sqrt(np.clip(1.0 - sum_sq, 0.0, None)).astype(np.float32)
    rows = np.arange(num)
    out[rows, largest] = largest_val
    return out


def load_spz_bytes(raw: bytes) -> GaussianCloud:
    """Decode raw .spz file bytes into a GaussianCloud."""
    try:
        data = gzip.decompress(raw)
    except OSError as e:
        raise ValueError(f"not a valid gzip-compressed SPZ stream: {e}") from e

    if len(data) < HEADER_SIZE:
        raise ValueError("SPZ data too short for header")

    magic, version, num_points = struct.unpack_from("<III", data, 0)
    sh_degree, fractional_bits, flags, _reserved = struct.unpack_from("<BBBB", data, 12)
    if magic != SPZ_MAGIC:
        raise ValueError(f"bad SPZ magic 0x{magic:08x} (expected 0x{SPZ_MAGIC:08x} 'NGSP')")
    if version not in (1, 2, 3):
        raise ValueError(f"unsupported SPZ version {version} (expected 1, 2, or 3)")
    if flags & 0x2:
        raise ValueError("SPZ extension data (flags bit 1) is not supported")

    antialiased = bool(flags & 0x1)
    sh_dim = sh_dim_for_degree(sh_degree)
    rot_bytes = 3 if version <= 2 else 4

    off = HEADER_SIZE

    def take(count: int) -> np.ndarray:
        nonlocal off
        end = off + count
        if end > len(data):
            raise ValueError(f"SPZ stream truncated: need {end} bytes, have {len(data)}")
        arr = np.frombuffer(data, dtype=np.uint8, count=count, offset=off)
        off = end
        return arr

    pos_raw = take(num_points * 9)
    alpha_raw = take(num_points * 1)
    color_raw = take(num_points * 3)
    scale_raw = take(num_points * 3)
    rot_raw = take(num_points * rot_bytes)
    sh_raw = take(num_points * sh_dim * 3) if sh_dim else np.empty(0, dtype=np.uint8)

    positions = _decode_positions(pos_raw, num_points, fractional_bits)
    alphas = _inv_sigmoid(alpha_raw.astype(np.float32) / 255.0)
    colors = ((color_raw.reshape(num_points, 3).astype(np.float32) / 255.0) - 0.5) / _COLOR_SCALE
    scales = scale_raw.reshape(num_points, 3).astype(np.float32) / 16.0 - 10.0
    if version <= 2:
        rotations = _decode_rotations_v2(rot_raw, num_points)
    else:
        packed = (
            rot_raw.reshape(num_points, 4).astype(np.uint32)[:, 0]
            | (rot_raw.reshape(num_points, 4).astype(np.uint32)[:, 1] << 8)
            | (rot_raw.reshape(num_points, 4).astype(np.uint32)[:, 2] << 16)
            | (rot_raw.reshape(num_points, 4).astype(np.uint32)[:, 3] << 24)
        )
        rotations = _decode_rotations_smallest_three(packed, num_points)

    if sh_dim:
        sh = (sh_raw.reshape(num_points, sh_dim, 3).astype(np.float32) - 128.0) / 128.0
    else:
        sh = np.zeros((num_points, 0, 3), dtype=np.float32)

    return GaussianCloud(
        positions=positions,
        scales=scales,
        rotations=rotations,
        alphas=alphas,
        colors=colors,
        sh=sh,
        sh_degree=sh_degree,
        antialiased=antialiased,
    )


def _ply_property_names(sh_dim: int) -> list[str]:
    names = ["x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2"]
    # f_rest is channel-major: all R coeffs, then G, then B (INRIA convention).
    names += [f"f_rest_{i}" for i in range(sh_dim * 3)]
    names += ["opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"]
    return names


def cloud_to_ply_bytes(cloud: GaussianCloud) -> bytes:
    """Serialize a GaussianCloud to binary_little_endian 3DGS PLY bytes."""
    num = cloud.num_points
    sh_dim = cloud.sh.shape[1]
    names = _ply_property_names(sh_dim)

    cols = [
        cloud.positions,  # x, y, z
        np.zeros((num, 3), dtype=np.float32),  # normals (unused by 3DGS, kept for layout)
        cloud.colors,  # f_dc_0..2
    ]
    if sh_dim:
        # (N, K, 3) interleaved -> (N, 3*K) channel-major: R coeffs, G coeffs, B coeffs.
        sh_channel_major = np.transpose(cloud.sh, (0, 2, 1)).reshape(num, sh_dim * 3)
        cols.append(sh_channel_major)
    cols.append(cloud.alphas.reshape(num, 1))  # opacity
    cols.append(cloud.scales)  # scale_0..2
    # PLY stores rotation as wxyz; SPZ decodes to xyzw -> reorder.
    rot_wxyz = cloud.rotations[:, [3, 0, 1, 2]]
    cols.append(rot_wxyz)  # rot_0..3

    table = np.concatenate([np.ascontiguousarray(c, dtype=np.float32) for c in cols], axis=1)
    assert table.shape[1] == len(names), (table.shape[1], len(names))

    header = (
        f"ply\nformat binary_little_endian 1.0\nelement vertex {num}\n" + "".join(f"property float {n}\n" for n in names) + "end_header\n"
    ).encode("ascii")

    return header + table.astype("<f4").tobytes()


def spz_bytes_to_ply_bytes(raw: bytes) -> bytes:
    """Convenience: raw .spz bytes -> binary PLY bytes."""
    return cloud_to_ply_bytes(load_spz_bytes(raw))
