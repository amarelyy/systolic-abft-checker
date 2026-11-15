"""Prototype study of the ABFT checksums, in Python only (no hardware).

Part 1  Checksum identity without wrap-around (100 random matrices).
Part 2  False alarms with wrap-around mod 2^W, at W = 16, 17, 18, 32, and how many of the
        matrices really overflow. Plus a reference that saturates instead of wrapping.
Part 3  Abstract fault patterns applied to C, and what the checksums do with them:
        single wrong element, two wrong elements, four errors in a rectangle.
Part 4  Faults in the array datapath, modelled at the level of the values they corrupt
        (not cycle-accurate): one corrupted activation, and a stuck-at bit in the register that
        passes activations along a row, or in a stored weight.

Part 3 and 4 are predictions to compare with the hardware fault-injection results later.

Run:  python model/abft_study.py        (writes logs/<time>_abft_prototype/)
"""

import datetime
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from model.abft import error_flag  # noqa: E402

N = 4
SEED = 12345
rng = np.random.default_rng(SEED)
out = []


def say(text=""):
    print(text)
    out.append(text)


def random_batch(M):
    """M pairs of INT8 matrices: uniform, extreme (-128 / 127) and sparse kinds mixed."""
    A = rng.integers(-128, 128, size=(M, N, N))
    B = rng.integers(-128, 128, size=(M, N, N))
    kind = rng.integers(0, 10, size=M)
    ext = np.where(rng.random((M, N, N)) < 0.5, -128, 127)
    sparse = rng.random((M, N, N)) < 0.7
    for X in (A, B):
        X[kind == 0] = ext[kind == 0]
        X[kind == 1] = np.where(sparse, 0, X)[kind == 1]
    return A, B


def wrap(C, W):
    return C & ((1 << W) - 1)


def overflowed(C_true, W):
    return ((C_true < -(1 << (W - 1))) | (C_true > (1 << (W - 1)) - 1)).any(axis=(-2, -1))


def force_bit(x, bit, val):
    """Force one bit of INT8 values to val (0 or 1), return signed INT8 values."""
    u = (x & 0xFF & ~(1 << bit)) | (val << bit)
    return np.where(u >= 128, u - 256, u)


# ---------------------------------------------------------------- part 1
say(f"ABFT prototype study, N = {N}, seed {SEED}, numpy {np.__version__}")
say()
say("Part 1: checksum identity without wrap-around, 100 random matrix pairs")
A, B = random_batch(100)
C = A @ B
ok_col = np.array_equal(C.sum(axis=-2), np.einsum("mk,mkj->mj", A.sum(axis=-2), B))
ok_row = np.array_equal(C.sum(axis=-1), np.einsum("mik,mk->mi", A, B.sum(axis=-1)))
say(f"  column identity holds for all 100: {ok_col}")
say(f"  row identity holds for all 100:    {ok_row}")

# ---------------------------------------------------------------- part 2
say()
say("Part 2: false alarms with wrap-around mod 2^W (fault-free runs, 100000 pairs per W)")
say(f"  {'W':>3} {'matrices that overflow':>24} {'false alarms (wrap)':>21}")
M = 100_000
A, B = random_batch(M)
C_true = A @ B
for W in (16, 17, 18, 32):
    flagged = error_flag(wrap(C_true, W), A, B, W).sum()
    say(f"  {W:>3} {int(overflowed(C_true, W).sum()):>24} {int(flagged):>21}")

say()
say("  Same check, but the reference saturates instead of wrapping (a wrong reference):")
say(f"  {'W':>3} {'matrices that overflow':>24} {'false alarms (saturate)':>24}")
for W in (16, 17):
    lo, hi = -(1 << (W - 1)), (1 << (W - 1)) - 1
    sat = wrap(np.clip(C_true, lo, hi), W)
    say(f"  {W:>3} {int(overflowed(C_true, W).sum()):>24} {int(error_flag(sat, A, B, W).sum()):>24}")

# ---------------------------------------------------------------- part 3
say()
say("Part 3: abstract errors in the output C (W = 18, 20000 pairs per row of the table)")
W, M = 18, 20_000
A, B = random_batch(M)
C = wrap(A @ B, W)
idx = np.arange(M)


def flip(Cx, i, j, bit):
    Cx = Cx.copy()
    Cx[idx, i, j] ^= 1 << bit
    return Cx


say(f"  {'error pattern':<52} {'changed':>8} {'detected':>9} {'missed':>7}")


def report(name, Cbad):
    changed = (Cbad != C).any(axis=(-2, -1))
    det = error_flag(Cbad, A, B, W) & changed
    say(f"  {name:<52} {int(changed.sum()):>8} {int(det.sum()):>9} {int((changed & ~det).sum()):>7}")


i1, j1 = rng.integers(0, N, M), rng.integers(0, N, M)
report("one element, one random bit flipped", flip(C, i1, j1, rng.integers(0, W, M)))

pos = np.stack([rng.permutation(N * N)[:2] for _ in range(M)])      # two distinct positions
Cb = flip(C, pos[:, 0] // N, pos[:, 0] % N, rng.integers(0, W, M))
report("two elements, one random bit flipped in each", flip(Cb, pos[:, 1] // N, pos[:, 1] % N, rng.integers(0, W, M)))

pos = np.stack([rng.permutation(N * N)[:3] for _ in range(M)])
Cb = C.copy()
for q in range(3):
    Cb = flip(Cb, pos[:, q] // N, pos[:, q] % N, rng.integers(0, W, M))
report("three elements, one random bit flipped in each", Cb)

# rectangle: +d at (a,c) and (b,e), -d at (a,e) and (b,c)
a_, b_ = np.array([rng.permutation(N)[:2] for _ in range(M)]).T
c_, e_ = np.array([rng.permutation(N)[:2] for _ in range(M)]).T
d = 1 << rng.integers(0, W - 1, M)
Cb = C.copy()
for (r, c, s) in ((a_, c_, 1), (b_, e_, 1), (a_, e_, -1), (b_, c_, -1)):
    Cb[idx, r, c] = (Cb[idx, r, c] + s * d) & ((1 << W) - 1)
report("four errors +d, -d, -d, +d at the corners of a rectangle", Cb)

# ---------------------------------------------------------------- part 4
say()
say("Part 4: datapath faults at the value level (W = 18, 20000 pairs per fault position)")
say("  A fault is modelled by the values it corrupts, not cycle by cycle.")
say("  'a-token': one activation A[i][k] is wrong from column c0 onwards (affects row i).")
say("  'a-stuck': a stuck bit in the register that passes activations along row k, so every")
say("             activation of column k is forced from column c0 onwards (affects many rows).")
say("  'w-stuck': a stuck bit in a stored weight B[k][j] (affects column j).")
Ct = A @ B                                                    # exact products
say(f"  {'fault':<10} {'locations x values':>19} {'changed':>9} {'detected':>9} {'missed':>8}")


def run(name, build, count):
    ch = det = 0
    for Cbad in build():
        Cbad = wrap(Cbad, W)
        changed = (Cbad != C).any(axis=(-2, -1))
        ch += int(changed.sum())
        det += int((error_flag(Cbad, A, B, W) & changed).sum())
    say(f"  {name:<10} {count:>19} {ch:>9} {det:>9} {ch - det:>8}")


def a_token():
    for k in range(N):
        for c0 in range(N):
            for bit in range(8):                               # flip one bit of one activation
                i = rng.integers(0, N, M)
                delta = np.zeros((M, N), dtype=np.int64)
                old = A[idx, i, k]
                new = np.where(((old & 0xFF) ^ (1 << bit)) >= 128, ((old & 0xFF) ^ (1 << bit)) - 256, (old & 0xFF) ^ (1 << bit))
                delta[idx, i] = new - old
                Cb = Ct.copy()
                for j in range(c0, N):
                    Cb[:, :, j] += delta * B[:, k, j][:, None]
                yield Cb


def a_stuck():
    for k in range(N):
        for c0 in range(1, N):                                 # register after column c0 - 1
            for bit in range(8):
                for val in (0, 1):
                    delta = force_bit(A[:, :, k], bit, val) - A[:, :, k]
                    Cb = Ct.copy()
                    for j in range(c0, N):
                        Cb[:, :, j] += delta * B[:, k, j][:, None]
                    yield Cb


def w_stuck():
    for k in range(N):
        for j in range(N):
            for bit in range(8):
                for val in (0, 1):
                    delta = force_bit(B[:, k, j], bit, val) - B[:, k, j]
                    Cb = Ct.copy()
                    Cb[:, :, j] += A[:, :, k] * delta[:, None]
                    yield Cb


run("a-token", a_token, f"{N * N * 8} x 1")
run("a-stuck", a_stuck, f"{N * (N - 1) * 8 * 2} x 1")
run("w-stuck", w_stuck, f"{N * N * 8 * 2} x 1")

# ---------------------------------------------------------------- save
stamp = datetime.datetime.now().strftime("%Y-%m-%dT%H%M%S")
log_dir = Path(__file__).resolve().parent.parent / "logs" / f"{stamp}_abft_prototype"
log_dir.mkdir(parents=True)
(log_dir / "summary.txt").write_text("\n".join(out) + "\n")
print(f"\nlog: {log_dir}")
