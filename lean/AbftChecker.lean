/-!
# ABFT checker: the checksum algebra, proved for all inputs and all widths

This file is a mathematical model of the arithmetic in `rtl/abft_checker.sv` for the 4 x 4 array.
It proves, for every pair of matrices A and B (any integers, so in particular INT8) and for every
modulus m (the hardware uses m = 2^W, for any W):

* `no_false_alarm_col`, `no_false_alarm_row`:
    if the array output is the true product modulo m, every column checksum and every row
    checksum of the checker agrees (the checker raises no false alarm);
* `single_error_located`:
    if exactly one element of the output is wrong by an amount that is not a multiple of m, then
    exactly one column checksum and exactly one row checksum disagree, and they are the column
    and the row of the wrong element (so the flag is raised and the location is exact);
* `detect_row_pattern`, `detect_col_pattern`:
    any error pattern confined to one row (or one column), with at least one element wrong by
    a non-multiple of m, makes some column (or row) checksum disagree, so it is detected.

What the model is, and is not.
* The functions `outCol`, `outRow`, `refCol`, `refRow` follow the hardware equations: sums are
  taken one wrapped addition at a time (`hwAdd`, modulo m, starting from 0), and the reference
  accumulates `colsum(A)[k] * B[k][j]` and `A[i][k] * rowsum(B)[k]` for k = 0..3.
* The link from this model to the SystemVerilog is by reading the two side by side (and by the
  simulation and injection runs, which agree with it). It is not a machine-checked refinement of
  the RTL.
* The model assumes that the checker's intermediate values (the column sum of A in 10 bits, the
  product in 18 bits) are not truncated. `colsum_range` and `product_range` below prove that this
  holds for INT8 inputs.
* The array output is taken to be the true product mod m (`hC`). That the array does this is
  covered by the simulation tests and by the formal proof of the processing element, not here.
-/

set_option linter.deprecated false   -- if_pos / if_neg are still the clearest names here

namespace Abft

/-- A 4 x 4 matrix of integers. -/
abbrev Mat := Fin 4 → Fin 4 → Int

/-- The sum of four integers. -/
def s4 (f : Fin 4 → Int) : Int := f 0 + f 1 + f 2 + f 3

/-- The exact (unwrapped) element C[i][j] of A x B. -/
def prod (A B : Mat) (i j : Fin 4) : Int := s4 fun k => A i k * B k j

/-- One W-bit addition in hardware: the sum wraps modulo m (m = 2^W). -/
def hwAdd (m a b : Int) : Int := (a + b) % m

/-- Four values added in hardware, from 0, one wrapped addition at a time. -/
def hwSum4 (m : Int) (f : Fin 4 → Int) : Int :=
  hwAdd m (hwAdd m (hwAdd m (hwAdd m 0 (f 0)) (f 1)) (f 2)) (f 3)

/-- Column sum k of A, and row sum k of B (what the checker adds up before multiplying). -/
def colSumA (A : Mat) (k : Fin 4) : Int := s4 fun i => A i k
def rowSumB (B : Mat) (k : Fin 4) : Int := s4 fun j => B k j

/-- Reference checksums, accumulated over k = 0..3 as in the checker (each product wrapped). -/
def refCol (m : Int) (A B : Mat) (j : Fin 4) : Int :=
  hwSum4 m fun k => (colSumA A k * B k j) % m
def refRow (m : Int) (A B : Mat) (i : Fin 4) : Int :=
  hwSum4 m fun k => (A i k * rowSumB B k) % m

/-- Checksums of the output matrix C (column j, row i), as the checker adds them. -/
def outCol (m : Int) (C : Mat) (j : Fin 4) : Int := hwSum4 m fun i => C i j
def outRow (m : Int) (C : Mat) (i : Fin 4) : Int := hwSum4 m fun j => C i j

/-! ## Helper facts about wrapped addition -/

theorem add_mod_mod (a b m : Int) : (a % m + b % m) % m = (a + b) % m := by
  rw [Int.emod_add_emod, Int.add_emod_emod]

/-- Adding four values one wrapped step at a time equals wrapping the exact sum. -/
theorem hwSum4_mod (m : Int) (g : Fin 4 → Int) :
    hwSum4 m (fun t => g t % m) = s4 g % m := by
  have h0 : hwAdd m 0 (g 0 % m) = g 0 % m := by
    simp [hwAdd]
  have h1 : hwAdd m (g 0 % m) (g 1 % m) = (g 0 + g 1) % m := by
    simp only [hwAdd]; exact add_mod_mod _ _ _
  have h2 : hwAdd m ((g 0 + g 1) % m) (g 2 % m) = (g 0 + g 1 + g 2) % m := by
    simp only [hwAdd]; exact add_mod_mod _ _ _
  have h3 : hwAdd m ((g 0 + g 1 + g 2) % m) (g 3 % m) = (g 0 + g 1 + g 2 + g 3) % m := by
    simp only [hwAdd]; exact add_mod_mod _ _ _
  simp only [hwSum4, s4]
  rw [h0, h1, h2, h3]

/-- Every element of Fin 4 is one of the four literals. -/
theorem fin4_cases (x : Fin 4) : x = 0 ∨ x = 1 ∨ x = 2 ∨ x = 3 := by
  revert x; decide

/-- A value that differs from the right one by a non-multiple of m has a different residue. -/
theorem ne_of_delta (S d m : Int) (hd : d % m ≠ 0) : (S + d) % m ≠ S % m := by
  intro h
  have h2 := Int.emod_eq_emod_iff_emod_sub_eq_zero.mp h
  rw [show S + d - S = d by omega] at h2
  exact hd h2

/-! ## The exact identities behind the checksums -/

theorem col_identity (A B : Mat) (j : Fin 4) :
    s4 (fun i => prod A B i j) = s4 (fun k => colSumA A k * B k j) := by
  simp only [prod, s4, colSumA]
  grind

theorem row_identity (A B : Mat) (i : Fin 4) :
    s4 (fun j => prod A B i j) = s4 (fun k => A i k * rowSumB B k) := by
  simp only [prod, s4, rowSumB]
  grind

/-- The reference column checksum is the wrapped exact column sum of the true product. -/
theorem refCol_eq (m : Int) (A B : Mat) (j : Fin 4) :
    refCol m A B j = s4 (fun i => prod A B i j) % m := by
  rw [col_identity]
  exact hwSum4_mod m (fun k => colSumA A k * B k j)

theorem refRow_eq (m : Int) (A B : Mat) (i : Fin 4) :
    refRow m A B i = s4 (fun j => prod A B i j) % m := by
  rw [row_identity]
  exact hwSum4_mod m (fun k => A i k * rowSumB B k)

/-! ## No false alarm -/

/-- The array output is the true product modulo m. -/
def IsCorrect (m : Int) (A B C : Mat) : Prop := ∀ i j, C i j = prod A B i j % m

theorem outCol_correct (m : Int) (A B C : Mat) (hC : IsCorrect m A B C) (j : Fin 4) :
    outCol m C j = s4 (fun i => prod A B i j) % m := by
  have : (fun i => C i j) = fun i => prod A B i j % m := funext fun i => hC i j
  simp only [outCol, this]
  exact hwSum4_mod m (fun i => prod A B i j)

theorem outRow_correct (m : Int) (A B C : Mat) (hC : IsCorrect m A B C) (i : Fin 4) :
    outRow m C i = s4 (fun j => prod A B i j) % m := by
  have : (fun j => C i j) = fun j => prod A B i j % m := funext fun j => hC i j
  simp only [outRow, this]
  exact hwSum4_mod m (fun j => prod A B i j)

/-- **No false alarm, columns**: when the array output is right, every column checksum agrees. -/
theorem no_false_alarm_col (m : Int) (A B C : Mat) (hC : IsCorrect m A B C) (j : Fin 4) :
    outCol m C j = refCol m A B j := by
  rw [outCol_correct m A B C hC, refCol_eq]

/-- **No false alarm, rows**. -/
theorem no_false_alarm_row (m : Int) (A B C : Mat) (hC : IsCorrect m A B C) (i : Fin 4) :
    outRow m C i = refRow m A B i := by
  rw [outRow_correct m A B C hC, refRow_eq]

/-! ## Detection and location -/

/-- If one column of the output differs from the right one only in row i0, by dj (mod m), its
checksum is the right one plus dj (mod m). -/
theorem outCol_one_delta (m : Int) (A B C Cb : Mat) (hC : IsCorrect m A B C) (i0 j : Fin 4)
    (dj : Int) (hb : ∀ i, Cb i j = if i = i0 then (C i j + dj) % m else C i j) :
    outCol m Cb j = (s4 (fun i => prod A B i j) + dj) % m := by
  have key : (fun i => Cb i j) =
      fun i => (prod A B i j + (if i = i0 then dj else 0)) % m := by
    funext i
    rw [hb i]
    by_cases h : i = i0
    · rw [if_pos h, if_pos h, hC i j, Int.emod_add_emod]
    · rw [if_neg h, if_neg h, hC i j, Int.add_zero]
  have hs : s4 (fun i => prod A B i j + (if i = i0 then dj else 0)) =
      s4 (fun i => prod A B i j) + dj := by
    rcases fin4_cases i0 with rfl | rfl | rfl | rfl <;> simp [s4] <;> grind
  simp only [outCol, key]
  rw [hwSum4_mod m (fun i => prod A B i j + (if i = i0 then dj else 0)), hs]

theorem outRow_one_delta (m : Int) (A B C Cb : Mat) (hC : IsCorrect m A B C) (i j0 : Fin 4)
    (di : Int) (hb : ∀ j, Cb i j = if j = j0 then (C i j + di) % m else C i j) :
    outRow m Cb i = (s4 (fun j => prod A B i j) + di) % m := by
  have key : (fun j => Cb i j) =
      fun j => (prod A B i j + (if j = j0 then di else 0)) % m := by
    funext j
    rw [hb j]
    by_cases h : j = j0
    · rw [if_pos h, if_pos h, hC i j, Int.emod_add_emod]
    · rw [if_neg h, if_neg h, hC i j, Int.add_zero]
  have hs : s4 (fun j => prod A B i j + (if j = j0 then di else 0)) =
      s4 (fun j => prod A B i j) + di := by
    rcases fin4_cases j0 with rfl | rfl | rfl | rfl <;> simp [s4] <;> grind
  simp only [outRow, key]
  rw [hwSum4_mod m (fun j => prod A B i j + (if j = j0 then di else 0)), hs]

/-- **A single wrong element is detected and located exactly.**
Exactly one column checksum disagrees (column j0) and exactly one row checksum disagrees (row i0). -/
theorem single_error_located (m : Int) (A B C Cb : Mat) (hC : IsCorrect m A B C)
    (i0 j0 : Fin 4) (d : Int) (hd : d % m ≠ 0)
    (hb : ∀ i j, Cb i j = if i = i0 ∧ j = j0 then (C i j + d) % m else C i j) :
    (∀ j, outCol m Cb j ≠ refCol m A B j ↔ j = j0) ∧
    (∀ i, outRow m Cb i ≠ refRow m A B i ↔ i = i0) := by
  constructor
  · intro j
    by_cases hj : j = j0
    · subst hj
      have := outCol_one_delta m A B C Cb hC i0 j d (fun i => by rw [hb i j]; simp)
      rw [this, refCol_eq]
      simpa using ne_of_delta _ d m hd
    · have hsame : ∀ i, Cb i j = C i j := fun i => by rw [hb i j]; simp [hj]
      have h1 : outCol m Cb j = outCol m C j := by
        simp only [outCol, show (fun i => Cb i j) = fun i => C i j from funext hsame]
      rw [h1, no_false_alarm_col m A B C hC j]
      simp [hj]
  · intro i
    by_cases hi : i = i0
    · subst hi
      have := outRow_one_delta m A B C Cb hC i j0 d (fun j => by rw [hb i j]; simp)
      rw [this, refRow_eq]
      simpa using ne_of_delta _ d m hd
    · have hsame : ∀ j, Cb i j = C i j := fun j => by rw [hb i j]; simp [hi]
      have h1 : outRow m Cb i = outRow m C i := by
        simp only [outRow, show (fun j => Cb i j) = fun j => C i j from funext hsame]
      rw [h1, no_false_alarm_row m A B C hC i]
      simp [hi]

/-- **Any error pattern inside one row is detected**: if only row i0 of the output is wrong, with
element j wrong by `d j`, and at least one `d j1` is not a multiple of m, some column checksum
disagrees. This covers a corrupted activation, and any stuck bit that corrupts several rows of
the same activation column, because each column then holds at most one wrong value. -/
theorem detect_row_pattern (m : Int) (A B C Cb : Mat) (hC : IsCorrect m A B C) (i0 : Fin 4)
    (d : Fin 4 → Int) (j1 : Fin 4) (hd : d j1 % m ≠ 0)
    (hb : ∀ i j, Cb i j = if i = i0 then (C i j + d j) % m else C i j) :
    ∃ j, outCol m Cb j ≠ refCol m A B j := by
  refine ⟨j1, ?_⟩
  have := outCol_one_delta m A B C Cb hC i0 j1 (d j1) (fun i => hb i j1)
  rw [this, refCol_eq]
  exact ne_of_delta _ _ m hd

/-- **Any error pattern inside one column is detected** (some row checksum disagrees). This covers
a corrupted weight. -/
theorem detect_col_pattern (m : Int) (A B C Cb : Mat) (hC : IsCorrect m A B C) (j0 : Fin 4)
    (d : Fin 4 → Int) (i1 : Fin 4) (hd : d i1 % m ≠ 0)
    (hb : ∀ i j, Cb i j = if j = j0 then (C i j + d i) % m else C i j) :
    ∃ i, outRow m Cb i ≠ refRow m A B i := by
  refine ⟨i1, ?_⟩
  have := outRow_one_delta m A B C Cb hC i1 j0 (d i1) (fun j => hb i1 j)
  rw [this, refRow_eq]
  exact ne_of_delta _ _ m hd

/-! ## The intermediate values of the checker do not overflow their widths (INT8 inputs) -/

/-- Column sum of four INT8 values: -512 .. 508, which fits 10 signed bits (-512 .. 511). -/
theorem colsum_range (x0 x1 x2 x3 : Int)
    (h0 : -128 ≤ x0 ∧ x0 ≤ 127) (h1 : -128 ≤ x1 ∧ x1 ≤ 127)
    (h2 : -128 ≤ x2 ∧ x2 ≤ 127) (h3 : -128 ≤ x3 ∧ x3 ≤ 127) :
    -512 ≤ x0 + x1 + x2 + x3 ∧ x0 + x1 + x2 + x3 ≤ 511 := by
  omega

/-- A 10-bit column sum times an INT8 value: at most 65536 in size, which fits 18 signed bits. -/
theorem product_range (x b : Int) (hx : -512 ≤ x ∧ x ≤ 511) (hb : -128 ≤ b ∧ b ≤ 127) :
    -131072 ≤ x * b ∧ x * b ≤ 131071 := by
  have h1 : x.natAbs ≤ 512 := by omega
  have h2 : b.natAbs ≤ 128 := by omega
  have h3 : (x * b).natAbs ≤ 512 * 128 := by
    rw [Int.natAbs_mul]
    exact Nat.mul_le_mul h1 h2
  omega

/-! ## Sanity checks on a concrete example (so the theorems are not vacuous)

A = B = all ones, so every element of C is 4. W = 18, m = 262144. -/

def ones : Mat := fun _ _ => 1
def m18 : Int := 262144

/-- The hypotheses of the theorems can be satisfied: the all-4 matrix is the correct output. -/
example : IsCorrect m18 ones ones (fun _ _ => 4) := by
  intro i j; simp [prod, s4, ones, m18]

/-- A concrete single error (+1 at row 2, column 1): exactly column 1 and exactly row 2 disagree. -/
def oneError : Mat := fun i j => if i = 2 ∧ j = 1 then 5 else 4

example : outCol m18 oneError 1 ≠ refCol m18 ones ones 1 := by decide
example : outCol m18 oneError 0 = refCol m18 ones ones 0 := by decide
example : outRow m18 oneError 2 ≠ refRow m18 ones ones 2 := by decide
example : outRow m18 oneError 3 = refRow m18 ones ones 3 := by decide

/-- The condition `d % m ≠ 0` is needed: an error of exactly m (= 2^18, a whole wrap) is
invisible, because the register cannot tell the difference. -/
def wrapError : Mat := fun i j => if i = 2 ∧ j = 1 then (4 + m18) % m18 else 4

example : outCol m18 wrapError 1 = refCol m18 ones ones 1 := by decide

/-- The known limit of row and column checksums: four errors at the corners of a rectangle
(+1, -1, -1, +1) cancel in every row and every column, so nothing is detected although
the output is wrong. -/
def rect : Mat := fun i j =>
  if i = 0 ∧ j = 0 then 5 else if i = 0 ∧ j = 1 then 3
  else if i = 1 ∧ j = 0 then 3 else if i = 1 ∧ j = 1 then 5 else 4

example : ∀ j, outCol m18 rect j = refCol m18 ones ones j := by decide
example : ∀ i, outRow m18 rect i = refRow m18 ones ones i := by decide
example : rect 0 0 ≠ 4 := by decide

#print axioms no_false_alarm_col
#print axioms no_false_alarm_row
#print axioms single_error_located
#print axioms detect_row_pattern
#print axioms detect_col_pattern
#print axioms colsum_range
#print axioms product_range

end Abft
