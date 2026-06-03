"""Tests for the pure-Python SPZ -> PLY codec."""

from __future__ import annotations

import gzip
import struct

import numpy as np
import pytest

from src.marble import spz_codec


def _build_spz(
    positions: np.ndarray,
    alphas: np.ndarray,
    colors: np.ndarray,
    scales: np.ndarray,
    rotations: np.ndarray,
    *,
    version: int = 2,
    sh_degree: int = 0,
    sh: np.ndarray | None = None,
    fractional_bits: int = 12,
    flags: int = 0,
) -> bytes:
    """Encode a minimal SPZ stream from already-quantized uint8/int values.

    `rotations` is the raw per-point rotation bytes (3 wide for v2, 4 for v3+).
    """
    num = positions.shape[0]
    header = struct.pack("<IIIBBBB", spz_codec.SPZ_MAGIC, version, num, sh_degree, fractional_bits, flags, 0)

    pos_i24 = positions.astype(np.int32) & 0xFFFFFF
    pos_bytes = np.empty((num * 3, 3), dtype=np.uint8)
    flat = pos_i24.reshape(-1)
    pos_bytes[:, 0] = flat & 0xFF
    pos_bytes[:, 1] = (flat >> 8) & 0xFF
    pos_bytes[:, 2] = (flat >> 16) & 0xFF

    payload = (
        header
        + pos_bytes.tobytes()
        + alphas.astype(np.uint8).tobytes()
        + colors.astype(np.uint8).tobytes()
        + scales.astype(np.uint8).tobytes()
        + rotations.astype(np.uint8).tobytes()
    )
    if sh is not None:
        payload += sh.astype(np.uint8).tobytes()
    return gzip.compress(payload)


def test_decode_roundtrip_values():
    # Two gaussians with hand-picked quantized bytes.
    positions = np.array([[4096, -4096, 8192], [0, 2048, -2048]], dtype=np.int32)  # /2^12
    alphas = np.array([200, 50], dtype=np.uint8)
    colors = np.array([[128, 64, 200], [255, 0, 90]], dtype=np.uint8)
    scales = np.array([[160, 80, 0], [255, 16, 200]], dtype=np.uint8)
    rots = np.array([[128, 128, 128], [200, 60, 10]], dtype=np.uint8)

    raw = _build_spz(positions, alphas, colors, scales, rots)
    cloud = spz_codec.load_spz_bytes(raw)

    assert cloud.num_points == 2
    assert cloud.sh_degree == 0
    np.testing.assert_allclose(cloud.positions, positions.astype(np.float32) / 4096.0)
    # color decode: ((v/255)-0.5)/0.15
    expected_color = ((colors.astype(np.float32) / 255.0) - 0.5) / 0.15
    np.testing.assert_allclose(cloud.colors, expected_color, rtol=1e-5)
    # scale decode: v/16 - 10
    np.testing.assert_allclose(cloud.scales, scales.astype(np.float32) / 16.0 - 10.0, rtol=1e-5)
    # opacity decode: invSigmoid(v/255)
    a = np.clip(alphas.astype(np.float32) / 255.0, 1e-6, 1 - 1e-6)
    np.testing.assert_allclose(cloud.alphas, np.log(a / (1 - a)), rtol=1e-5)


def test_rotation_v2_is_unit_quaternion():
    # Bytes kept near 128 so each xyz stays small (sum of squares <= 1), as in
    # real data encoded from a normalized quaternion; w then makes it unit.
    positions = np.zeros((4, 3), dtype=np.int32)
    alphas = np.full(4, 128, dtype=np.uint8)
    colors = np.full((4, 3), 128, dtype=np.uint8)
    scales = np.zeros((4, 3), dtype=np.uint8)
    rots = np.array([[128, 128, 128], [160, 120, 140], [100, 150, 130], [90, 170, 110]], dtype=np.uint8)
    cloud = spz_codec.load_spz_bytes(_build_spz(positions, alphas, colors, scales, rots))
    norms = np.linalg.norm(cloud.rotations, axis=1)
    np.testing.assert_allclose(norms, 1.0, atol=1e-5)


def test_ply_header_and_size():
    positions = np.zeros((3, 3), dtype=np.int32)
    alphas = np.full(3, 100, dtype=np.uint8)
    colors = np.full((3, 3), 128, dtype=np.uint8)
    scales = np.zeros((3, 3), dtype=np.uint8)
    rots = np.full((3, 3), 128, dtype=np.uint8)
    ply = spz_codec.spz_bytes_to_ply_bytes(_build_spz(positions, alphas, colors, scales, rots))

    assert ply.startswith(b"ply\n")
    header, _, body = ply.partition(b"end_header\n")
    assert b"format binary_little_endian 1.0" in header
    assert b"element vertex 3" in header
    # SH degree 0: 3 pos + 3 normals + 3 f_dc + opacity + 3 scale + 4 rot = 17 floats/point.
    assert b"property float rot_3" in header
    assert b"f_rest_0" not in header
    assert len(body) == 3 * 17 * 4


def test_ply_rotation_reordered_to_wxyz():
    positions = np.zeros((1, 3), dtype=np.int32)
    alphas = np.array([128], dtype=np.uint8)
    colors = np.full((1, 3), 128, dtype=np.uint8)
    scales = np.zeros((1, 3), dtype=np.uint8)
    rots = np.array([[200, 60, 10]], dtype=np.uint8)
    raw = _build_spz(positions, alphas, colors, scales, rots)
    cloud = spz_codec.load_spz_bytes(raw)
    ply = spz_codec.cloud_to_ply_bytes(cloud)

    _, _, body = ply.partition(b"end_header\n")
    vals = np.frombuffer(body, dtype="<f4")
    # rot_0..3 are the last four floats; PLY order is wxyz.
    rot_wxyz = vals[-4:]
    np.testing.assert_allclose(rot_wxyz, cloud.rotations[0, [3, 0, 1, 2]], rtol=1e-5)


def _pack_smallest_three(quat_xyzw: np.ndarray) -> np.ndarray:
    """Encode unit quaternions (xyzw) into v3 'smallest three' uint32 -> 4 bytes."""
    num = quat_xyzw.shape[0]
    out = np.zeros((num, 4), dtype=np.uint8)
    for i in range(num):
        q = quat_xyzw[i]
        largest = int(np.argmax(np.abs(q)))
        # Reference convention: make the largest component positive.
        if q[largest] < 0:
            q = -q
        packed = largest << 30
        comp = 0
        for slot in range(4):
            if slot == largest:
                continue
            value = q[slot]
            mag = int(round(abs(value) * 511.0 / spz_codec._SQRT_HALF))
            mag = min(mag, 0x1FF)
            code = mag | (0x200 if value < 0 else 0)
            packed |= code << (comp * 10)
            comp += 1
        out[i, 0] = packed & 0xFF
        out[i, 1] = (packed >> 8) & 0xFF
        out[i, 2] = (packed >> 16) & 0xFF
        out[i, 3] = (packed >> 24) & 0xFF
    return out


def test_v3_smallest_three_roundtrip():
    quats = np.array(
        [
            [0.0, 0.0, 0.0, 1.0],
            [0.5, 0.5, 0.5, 0.5],
            [0.1, -0.2, 0.3, np.sqrt(1 - 0.14)],
        ],
        dtype=np.float32,
    )
    quats /= np.linalg.norm(quats, axis=1, keepdims=True)
    rots = _pack_smallest_three(quats)
    num = quats.shape[0]
    raw = _build_spz(
        np.zeros((num, 3), dtype=np.int32),
        np.full(num, 128, dtype=np.uint8),
        np.full((num, 3), 128, dtype=np.uint8),
        np.zeros((num, 3), dtype=np.uint8),
        rots,
        version=3,
    )
    cloud = spz_codec.load_spz_bytes(raw)
    norms = np.linalg.norm(cloud.rotations, axis=1)
    np.testing.assert_allclose(norms, 1.0, atol=1e-3)
    # Decoded quaternion matches up to global sign (largest forced positive).
    for i in range(num):
        ref = quats[i] if quats[i][np.argmax(np.abs(quats[i]))] > 0 else -quats[i]
        np.testing.assert_allclose(cloud.rotations[i], ref, atol=2e-2)


def test_sh_degree_decoded_and_serialized():
    num = 2
    sh_dim = spz_codec.sh_dim_for_degree(1)  # 3 coeffs per channel
    sh = (np.arange(num * sh_dim * 3) % 256).astype(np.uint8).reshape(num, sh_dim, 3)
    raw = _build_spz(
        np.zeros((num, 3), dtype=np.int32),
        np.full(num, 128, dtype=np.uint8),
        np.full((num, 3), 128, dtype=np.uint8),
        np.zeros((num, 3), dtype=np.uint8),
        np.full((num, 3), 128, dtype=np.uint8),
        sh_degree=1,
        sh=sh,
    )
    cloud = spz_codec.load_spz_bytes(raw)
    assert cloud.sh.shape == (num, sh_dim, 3)
    np.testing.assert_allclose(cloud.sh, (sh.astype(np.float32) - 128.0) / 128.0, rtol=1e-5)

    ply = spz_codec.cloud_to_ply_bytes(cloud)
    assert b"f_rest_0" in ply
    assert b"f_rest_8" in ply  # sh_dim*3 - 1 = 8
    # f_rest is channel-major: for point 0, first 3 f_rest are the R coeffs.
    _, _, body = ply.partition(b"end_header\n")
    floats_per_point = 3 + 3 + 3 + sh_dim * 3 + 1 + 3 + 4
    vals = np.frombuffer(body, dtype="<f4").reshape(num, floats_per_point)
    f_rest_0 = vals[0, 9]  # after x,y,z,nx,ny,nz,f_dc_0..2
    np.testing.assert_allclose(f_rest_0, cloud.sh[0, 0, 0], rtol=1e-5)


def test_data_too_short_raises():
    with pytest.raises(ValueError, match="too short"):
        spz_codec.load_spz_bytes(gzip.compress(b"\x00\x00\x00"))


def test_unsupported_version_raises():
    bad = gzip.compress(struct.pack("<IIIBBBB", spz_codec.SPZ_MAGIC, 5, 0, 0, 12, 0, 0))
    with pytest.raises(ValueError, match="unsupported SPZ version"):
        spz_codec.load_spz_bytes(bad)


def test_truncated_stream_raises():
    # Header claims 10 points but no attribute bytes follow.
    bad = gzip.compress(struct.pack("<IIIBBBB", spz_codec.SPZ_MAGIC, 2, 10, 0, 12, 0, 0))
    with pytest.raises(ValueError, match="truncated"):
        spz_codec.load_spz_bytes(bad)


def test_bad_magic_raises():
    bad = gzip.compress(struct.pack("<IIIBBBB", 0xDEADBEEF, 2, 0, 0, 12, 0, 0))
    with pytest.raises(ValueError, match="bad SPZ magic"):
        spz_codec.load_spz_bytes(bad)


def test_non_gzip_raises():
    with pytest.raises(ValueError, match="gzip"):
        spz_codec.load_spz_bytes(b"not gzip at all")


def test_extension_flag_rejected():
    bad = gzip.compress(struct.pack("<IIIBBBB", spz_codec.SPZ_MAGIC, 2, 0, 0, 12, 0x2, 0))
    with pytest.raises(ValueError, match="extension"):
        spz_codec.load_spz_bytes(bad)


def test_sh_degree_dims():
    assert spz_codec.sh_dim_for_degree(0) == 0
    assert spz_codec.sh_dim_for_degree(3) == 15
    with pytest.raises(ValueError):
        spz_codec.sh_dim_for_degree(9)
