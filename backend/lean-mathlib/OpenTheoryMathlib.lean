/-
  Scaffold target for the optional Mathlib image.

  `lake build` here is what warms the oleans cache in the INSTALL_MATHLIB=1
  image. Runtime checks write a throwaway Snippet.lean over an overlay of
  this project and run `lake --offline env lean` — they never fetch.
-/
import Mathlib.Data.Real.Basic
import Mathlib.Tactic.NormNum

example : (2 : ℝ) + 2 = 4 := by norm_num
