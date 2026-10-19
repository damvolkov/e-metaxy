"""scripts/materialize: the hardened sed — copy the e-templates `systems/core` common set into `src/e_metaxy/`.

libcst parses each source file as real 3.14 syntax (PEP 695 included, verified against the whole
`e_core` tree) and rewrites *only* the import nodes `e_core.{core,ops,adapters,processors} → e_metaxy.{...}`;
every result is re-parsed with `ast.parse` and scanned for leftovers before it is written. The common set
is injected *inside* the service package — `core`, `ops`, `adapters` and `processors` are subpackages of
`e_metaxy`, like `logic` — so every project imports them by full path and they read as first-class modules.
`make core` materializes into `src/e_metaxy/`; `make core-check` regenerates into a throwaway tree under `/tmp`
and diffs, so both modes run the exact same generation path and the drift-check cannot lie about a second one.
"""

import argparse
import ast
import filecmp
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Final

import libcst as cst

if TYPE_CHECKING:
    from collections.abc import Sequence

ROOT: Path = Path(__file__).resolve().parents[1]
PKG: str = "e_metaxy"
### a standalone repo: the core lives in the e-templates checkout beside it; E_CORE_SRC points elsewhere.
CORE_SRC: Path = Path(os.environ.get("E_CORE_SRC", ROOT.parent / "e-templates" / "systems" / "core" / "src" / "e_core"))
SECTIONS: tuple[str, ...] = ("adapters", "core", "ops", "processors")
### e-metaxy's own modules inside a materialized section, never swept and never diffed: its adapters (the coder,
### the OpenHuman caller, the owner's passphrase), the lifespan chain and middleware stack both doors share, and
### the two settings scopes the composer discovers beside the common ones. A path protects itself and its subtree.
PROTECTED: Final[frozenset[Path]] = frozenset(
    Path(path)
    for path in (
        "adapters/coder",
        "adapters/openhuman.py",
        "adapters/passphrase.py",
        "core/lifespan",
        "core/middlewares.py",
        "core/settings/authority.py",
        "core/settings/metaxy.py",
    )
)
### the TUI header belongs to the boilerplate wizard, not to a running service: same topology as the old sed.
### the compose tool belongs to stack management (management materializes the whole ops area), not a service.
### a bridge needs no TUI, snapshot, compose, code registry or redis; docling returns when DocProcessor lands.
EXCLUDES: frozenset[str] = frozenset(
    {
        "ops/tui.py",
        "ops/snap.py",
        "ops/compose.py",
        "ops/registry.py",
        "adapters/redis.py",
    }
)


##### REWRITE #####
def _parts(name: cst.BaseExpression) -> list[str] | None:
    """A dotted name as its segments; None when the node is not a plain dotted expression."""
    match name:
        case cst.Name(value=only):
            return [only]
        case cst.Attribute(value=inner, attr=cst.Name(value=tail)):
            return None if (prefix := _parts(inner)) is None else [*prefix, tail]
        case _:
            return None


def _dotted(parts: Sequence[str]) -> cst.BaseExpression:
    """The left-nested libcst attribute chain spelling `parts`."""
    match parts:
        case []:
            msg = "empty dotted name"
            raise ValueError(msg)
        case [only]:
            return cst.Name(only)
        case [*init, last]:
            return cst.Attribute(value=_dotted(init), attr=cst.Name(last))


def _repackage(name: cst.BaseExpression) -> cst.BaseExpression:
    """`e_core.core.x` → `e_metaxy.core.x`; anything outside a materialized section is returned untouched."""
    parts = _parts(name)
    hit = parts is not None and parts[0] == "e_core" and len(parts) > 1 and parts[1] in SECTIONS
    return _dotted([PKG, *parts[1:]]) if hit else name


def _repackage_alias(alias: object) -> object:
    """One `import a.b [as c]` alias, repackaged whatever its wrapper shape; anything else passes through."""
    match alias:
        case cst.ImportAlias(name=name):
            return alias.with_changes(name=_repackage(name))
        case cst.Element(node=cst.ImportAlias() as inner):
            return alias.with_changes(node=_repackage_alias(inner))
        case _:
            return alias


class _RepackageECore(cst.CSTTransformer):
    """Import statements only: docstrings and comments keep naming the source of truth verbatim."""

    def leave_Import(  # noqa: N802 — libcst dispatches visitor methods by node class name
        self, _original_node: cst.Import, updated_node: cst.Import
    ) -> cst.Import:
        match updated_node.names:
            case cst.ImportStar():
                return updated_node
            case aliases:
                return updated_node.with_changes(names=[_repackage_alias(alias) for alias in aliases])

    def leave_ImportFrom(  # noqa: N802 — libcst dispatches by node class name
        self, _original_node: cst.ImportFrom, updated_node: cst.ImportFrom
    ) -> cst.ImportFrom:
        match updated_node.module:
            case None:
                return updated_node
            case module:
                return updated_node.with_changes(module=_repackage(module))


##### VALIDATION #####
def _is_e_core_import(node: ast.AST) -> bool:
    match node:
        case ast.ImportFrom(module=module) | ast.Import(names=[ast.alias(name=module), *_]):
            return bool(module) and module.split(".")[0] == "e_core"
        case _:
            return False


def rewrite_source(text: str, path: str) -> str:
    """One file rewritten structurally, then hard-validated: parseable by `ast`, free of `e_core` imports."""
    out = cst.parse_module(text).visit(_RepackageECore()).code
    match [node for node in ast.walk(ast.parse(out, filename=path)) if _is_e_core_import(node)]:
        case []:
            return out
        case leftovers:
            msg = f"{path}: unresolved e_core imports survive the rewrite: {[n.lineno for n in leftovers]}"
            raise SystemExit(msg)


##### MATERIALIZATION #####
def _sources(section: str) -> list[Path]:
    """Every .py of one section, in stable order, minus the excluded files."""
    return [
        path
        for path in sorted((CORE_SRC / section).rglob("*.py"))
        if "__pycache__" not in path.parts and str(path.relative_to(CORE_SRC)) not in EXCLUDES
    ]


def _protected(rel: Path) -> bool:
    """Whether a package-relative path is e-metaxy's own: itself or an ancestor is protected."""
    return not PROTECTED.isdisjoint((rel, *rel.parents))


def _sweep(package: Path, section: str) -> None:
    """Clear the copied files under a section, sparing e-metaxy's own; directories left empty go with them."""
    copies = [path for path in (package / section).rglob("*.py") if not _protected(path.relative_to(package))]
    _ = [path.unlink() for path in copies]
    empty = [
        path
        for path in sorted((package / section).rglob("*"), reverse=True)
        if path.is_dir() and not any(path.iterdir())
    ]
    _ = [path.rmdir() for path in empty]


def materialize(dest_root: Path) -> None:
    """Write the rewritten sections under `dest_root/src/e_metaxy`, replacing any previous copy in place."""
    package = dest_root / "src" / PKG
    for section in SECTIONS:
        if (package / section).is_dir():
            _sweep(package, section)
        for path in _sources(section):
            rel = path.relative_to(CORE_SRC)
            target = package / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rewrite_source(path.read_text(), str(rel)))


def _materialized(dest_root: Path) -> set[Path]:
    """The .py files materialized under `dest_root/src/e_metaxy`, relative to the package, e-metaxy's own spared."""
    package = dest_root / "src" / PKG
    return {
        rel
        for section in SECTIONS
        for path in (package / section).rglob("*.py")
        if "__pycache__" not in (rel := path.relative_to(package)).parts and not _protected(rel)
    }


def check(dest_root: Path) -> int:
    """Regenerate into a throwaway tree under /tmp and diff against `dest_root`: 0 in sync, 1 on drift."""
    tmp = Path(tempfile.mkdtemp(prefix="e-metaxy-materialize-"))
    try:
        materialize(tmp)
        package = dest_root / "src" / PKG
        expected = {path.relative_to(CORE_SRC) for section in SECTIONS for path in _sources(section)}
        actual = _materialized(dest_root)
        issues = [
            *(f"{rel}: missing" for rel in sorted(expected - actual)),
            *(f"{rel}: extra" for rel in sorted(actual - expected)),
            *(
                f"{rel}: stale"
                for rel in sorted(expected & actual)
                if not filecmp.cmp(tmp / "src" / PKG / rel, package / rel, shallow=False)
            ),
        ]
        match issues:
            case []:
                print(f"✓ materialized {PKG}/{{core,ops,adapters,processors}} in sync")
                return 0
            case _:
                print("✗ drift from systems/core (run make core):")
                print("\n".join(f"  {issue}" for issue in issues))
                return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> None:
    """CLI: default regenerates `src/e_metaxy`; `--check` is the read-only drift gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="regenerate into a tmp tree under /tmp and diff, exit 1 on drift"
    )
    match parser.parse_args(argv).check:
        case True:
            sys.exit(check(ROOT))
        case _:
            materialize(ROOT)
            print(f"✓ materialized {PKG}/{{adapters,core,ops,processors}} from systems/core")


if __name__ == "__main__":
    main()
