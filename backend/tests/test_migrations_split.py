"""v0.7.3c: ensure split migrations preserve registry invariants.

The bodies of every migration function were carved out of the legacy
``app/db/migrations.py`` monolith into version-bucketed modules under
``app/db/migrations/`` (``v04_initial``, ``v05_features``, etc.). The
parent package's ``__init__`` re-exports the runner symbols and
concatenates the bucket lists into the canonical ``VERSIONED_MIGRATIONS``
registry. These tests guard the contract:

* Versions are unique across all buckets (no duplicate IDs).
* Migration *names* are unique (logged when applied; collisions would mask
  bugs).
* The runner entrypoints (``init_db`` and the ``run_migrations`` alias)
  remain callable.
* Each bucket exposes a list named ``VXX_MIGRATIONS`` of 3-tuples.

The tests deliberately do NOT require strict numeric ordering — the
historical list interleaves a few late-numbered fixes (versions 82, 84,
85, 86, 87, 88) and reordering them would change the runtime apply order
in a way that could break already-deployed databases.
"""

from app.db.migrations import (
    V04_MIGRATIONS,
    V05_MIGRATIONS,
    V06_MIGRATIONS,
    V07_MIGRATIONS,
    VERSIONED_MIGRATIONS,
    init_db,
    run_migrations,
)


def test_versions_unique():
    versions = [v for v, _, _ in VERSIONED_MIGRATIONS]
    assert len(versions) == len(set(versions)), (
        "Migration version IDs must be unique across all buckets; "
        f"got duplicates in {sorted(v for v in versions if versions.count(v) > 1)}"
    )


def test_no_duplicate_names():
    names = [n for _, n, _ in VERSIONED_MIGRATIONS]
    assert len(names) == len(set(names)), (
        "Migration names must be unique (they are logged when applied)."
    )


def test_runner_callable():
    assert callable(run_migrations)
    assert callable(init_db)
    assert run_migrations is init_db, "run_migrations is documented as an alias for init_db"


def test_buckets_concatenate_to_registry():
    """The package __init__ should be a pure concatenation of the buckets."""
    expected = V04_MIGRATIONS + V05_MIGRATIONS + V06_MIGRATIONS + V07_MIGRATIONS
    assert list(VERSIONED_MIGRATIONS) == list(expected)


def test_bucket_shapes():
    """Every entry in every bucket is (int_version, str_name, callable_func)."""
    for label, bucket in [
        ("V04", V04_MIGRATIONS),
        ("V05", V05_MIGRATIONS),
        ("V06", V06_MIGRATIONS),
        ("V07", V07_MIGRATIONS),
    ]:
        for entry in bucket:
            assert isinstance(entry, tuple) and len(entry) == 3, (
                f"{label} entry malformed: {entry!r}"
            )
            ver, name, func = entry
            assert isinstance(ver, int), f"{label}: version must be int, got {ver!r}"
            assert isinstance(name, str) and name, (
                f"{label}: name must be non-empty str, got {name!r}"
            )
            assert callable(func), f"{label}: func must be callable, got {func!r}"


def test_bucket_version_ranges():
    """Each bucket holds only versions in its declared range."""
    for ver, _, _ in V04_MIGRATIONS:
        assert 1 <= ver <= 50, f"V04 contains out-of-range version {ver}"
    for ver, _, _ in V05_MIGRATIONS:
        assert 51 <= ver <= 100, f"V05 contains out-of-range version {ver}"
    for ver, _, _ in V06_MIGRATIONS:
        assert 101 <= ver <= 115, f"V06 contains out-of-range version {ver}"
    for ver, _, _ in V07_MIGRATIONS:
        assert ver >= 116, f"V07 contains out-of-range version {ver}"
