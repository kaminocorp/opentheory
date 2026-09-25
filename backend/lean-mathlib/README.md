# Optional Mathlib lake project

Scaffold for the `lean.prove` Mathlib path (`0.26.0`). This directory is **not**
a proof and is **not** used at runtime unless a `lake` cache has been built
beside it (`.lake/packages/mathlib`).

- CI and the default Fly image do **not** build this.
- Production Grade A with Mathlib requires:

  ```bash
  fly deploy --build-arg INSTALL_LEAN=1 --build-arg INSTALL_MATHLIB=1 \
    --build-arg LEAN_TOOLCHAIN=leanprover/lean4:v4.14.0 \
    --build-arg MATHLIB_REV=v4.14.0
  ```

- Runtime checks are `lake --offline env lean` on an overlay. A missing cache
  is `undecided` / `mathlib_unavailable`, never a proof.

See `docs/operations/deploy.md`.
