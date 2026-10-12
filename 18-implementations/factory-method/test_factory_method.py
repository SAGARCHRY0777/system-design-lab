"""Tests that assert the defining properties, not that the code runs.

The headline is `test_the_decorator_never_ran_because_nobody_imported_the_module`
and its partner `test_importing_the_plugin_is_what_populates_the_registry`. Same
registry, same factory call, same name: `UnknownCodec` before the import and a
working codec after it. The difference between a green CI run and a 3am page is
one `import` statement that production does not execute.

That pair only means anything if the fixture is honest, which is the awkward
part of testing this bug: pytest will have imported `codec_json` for some other
test in the same session, and `sys.modules` keeps it forever. So
`unregistered` pops the plugin modules out of `sys.modules` *and* clears the
registry, reconstructing the state a fresh process actually starts in. Without
that, the first test would pass by accident and prove nothing -- which is
precisely how the bug survives real test suites.

The second pair is the fix: `App(validate=True)` raises during `start()` and
has served zero requests; `App(validate=False)` starts cleanly, serves one
request successfully, and dies on the second. Identical configuration.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

from factory_method import (
    _REGISTRY,
    App,
    ComposedExporter,
    CsvExporter,
    CsvFormatter,
    Exporter,
    Playlist,
    ReversedPlaylist,
    SortedPlaylist,
    TsvExporter,
    UnknownCodec,
    codec,
    validate_configured,
)

HERE = Path(__file__).parent
PLUGINS = ("codec_json", "codec_csv")
ROWS = [["id", "name"], ["1", "ada"]]
TITLES = ["delta", "alpha", "charlie"]


@pytest.fixture
def unregistered():
    """Reconstruct the state a freshly started process is actually in.

    Two things have to be undone, and missing either makes the test lie:

    1. `_REGISTRY` is module-level, so anything registered earlier in the
       session is still there.
    2. `sys.modules` caches the plugin, so a later `import_module` would be a
       no-op and the decorator would not re-run.

    Restores both afterwards, so the order tests run in cannot change what they
    prove.
    """
    saved_registry = dict(_REGISTRY)
    saved_modules = {m: sys.modules[m] for m in PLUGINS if m in sys.modules}

    _REGISTRY.clear()
    for m in PLUGINS:
        sys.modules.pop(m, None)
    yield
    _REGISTRY.clear()
    _REGISTRY.update(saved_registry)
    sys.modules.update(saved_modules)


# ── headline pair 1: the registration that never happened ───────────────────


def test_a_fresh_process_importing_only_the_factory_has_an_empty_registry():
    """The claim, pinned in a real interpreter rather than a simulated one.

    This is the test that actually guards the design, and it needs a
    subprocess: the `unregistered` fixture below *reconstructs* a fresh
    registry by clearing the one in this process, and that reconstruction
    masks the only thing worth checking. Add `import codec_json` to the top of
    `factory_method.py` and every fixture-based test still passes, because the
    fixture wipes the registry the import populated. Verified by doing exactly
    that -- which is why this test exists and why it runs out of process.

    A fresh interpreter cannot be fooled: whatever `import factory_method`
    pulls in is what a production process gets.
    """
    out = subprocess.run(
        [sys.executable, "-c", "import factory_method as f; print(sorted(f._REGISTRY))"],
        cwd=HERE, capture_output=True, text=True, check=True)

    assert out.stdout.strip() == "[]", (
        "importing the factory registered something, so it imports a plugin -- "
        "which is the coupling the registry exists to remove")


def test_the_decorator_never_ran_because_nobody_imported_the_module(unregistered):
    """The bug. `codec_json.py` exists, is correct, and is not registered.

    Nothing is broken and nothing is missing: the file is on disk, the class is
    written, the decorator is spelled right. The registry is empty because
    `register("json")` is a line of code, and lines of code only run when their
    module is imported. `factory_method.py` does not import it -- importing
    every implementation is the coupling a registry exists to remove.

    In a test suite something always imports it by accident. In a service,
    nothing does.
    """
    assert "codec_json" not in sys.modules
    assert _REGISTRY == {}, "a fresh process starts here"

    with pytest.raises(UnknownCodec) as e:
        codec("json")
    assert "known: []" in str(e.value), "the error should say the registry is empty"


def test_importing_the_plugin_is_what_populates_the_registry(unregistered):
    """Same call, after one import. The import IS the registration."""
    with pytest.raises(UnknownCodec):
        codec("json")

    importlib.import_module("codec_json")       # ← the entire difference

    assert codec("json").name == "json"
    assert codec("json").encode({"b": 2, "a": 1}) == '{"a":1,"b":2}'


# ── headline pair 2: fail at boot, or fail at 3am ───────────────────────────


def test_without_startup_validation_the_app_dies_on_a_later_request(unregistered):
    """Starts cleanly. Serves traffic. Then dies on the request that needs csv.

    This is the shape that makes the bug expensive. There is no failure at
    deploy, no failure in the smoke test, and no failure on the endpoints
    anybody checked -- so the deploy is declared good and the process is hours
    old before anyone finds out. The typo was in the configuration the whole
    time.
    """
    importlib.import_module("codec_json")       # json ships; csv does not
    app = App(["json", "csv"], validate=False)

    app.start()                                 # no complaint
    assert app.handle("json")                   # and it genuinely works
    assert app.requests_served == 1

    with pytest.raises(UnknownCodec):
        app.handle("csv")                       # ← first request that needs it
    assert app.requests_served == 2, "the failure arrived as traffic, not as a deploy"


def test_with_startup_validation_it_dies_at_boot_and_names_the_culprit(unregistered):
    """Identical configuration. Three lines earlier, and before any traffic."""
    importlib.import_module("codec_json")
    app = App(["json", "csv"], validate=True)

    with pytest.raises(UnknownCodec) as e:
        app.start()

    assert "csv" in str(e.value), "it must name which key is missing"
    assert "json" in str(e.value), "and show what IS available, for the typo case"
    assert app.requests_served == 0, "no user ever saw this"


def test_validation_passes_once_every_configured_plugin_is_imported(unregistered):
    """And it must not cry wolf, or nobody will keep it."""
    for m in PLUGINS:
        importlib.import_module(m)

    validate_configured(["json", "csv"])        # does not raise
    assert App(["json", "csv"]).handle("csv").startswith("ok\nTrue")


def test_unknown_codec_is_a_keyerror_so_old_handlers_still_catch_it():
    """The name came from config or a header, so it is input validation.

    A distinct exception type lets a handler answer 400 instead of 500, and
    subclassing KeyError means code that already catches KeyError around this
    factory does not silently stop working.
    """
    assert issubclass(UnknownCodec, KeyError)


# ── the pattern itself, and what it costs ───────────────────────────────────


def test_the_hierarchy_costs_two_classes_for_what_a_parameter_does():
    """Identical output. One version needs a subclass per product; one does not.

    The subclasses in `Exporter`'s hierarchy exist only to answer "which class
    do I instantiate", and `__subclasses__()` counts the price of asking that
    question with inheritance instead of an argument. In Python a class is a
    value: `CsvFormatter` is already a callable meaning "make me one of these",
    so wrapping it in a class that returns it is a layer with no content.
    """
    assert CsvExporter().export(ROWS) == ComposedExporter(CsvFormatter).export(ROWS)
    assert CsvExporter().export(ROWS) == "id,name\n1,ada"
    assert TsvExporter().export(ROWS) == "id\tname\n1\tada"

    assert len(Exporter.__subclasses__()) == 2, "one class per product, forever"
    assert ComposedExporter.__subclasses__() == [], "the parameter needed none"


def test_iter_is_the_real_factory_method_one_algorithm_three_products():
    """`preview` is written once and never overridden. Only the product varies.

    This is the pattern with nothing else mixed in: the creator is the
    playlist, the product is the iterator, the base class's algorithm consumes
    a product it cannot name, and each subclass supplies its own. No registry,
    no string key, no switch.

    `preview` is order-sensitive on purpose -- an algorithm whose result cannot
    distinguish the three iterators would demonstrate nothing.
    """
    assert Playlist(TITLES).preview() == ["delta", "alpha", "charlie"]
    assert SortedPlaylist(TITLES).preview() == ["alpha", "charlie", "delta"]
    assert ReversedPlaylist(TITLES).preview() == ["charlie", "alpha", "delta"]

    # The algorithm really is inherited, not reimplemented three times.
    for cls in (SortedPlaylist, ReversedPlaylist):
        assert "preview" not in vars(cls)
        assert cls.preview is Playlist.preview


def test_the_subclass_decides_at_construction_not_at_call_time():
    """The axis that separates Factory Method from a registry: WHEN.

    A registry is asked a question at every call and can answer differently
    each time. A Factory Method subclass answered once, when the object was
    constructed, and cannot change its mind -- which is a feature when you want
    the guarantee, and the reason people who wanted runtime dispatch and
    reached for this pattern end up disappointed.
    """
    e = CsvExporter()
    assert e.export(ROWS) == e.export(ROWS), "same object, same product, always"
    assert type(e._create_formatter()) is type(e._create_formatter())
    assert type(e._create_formatter()) is CsvFormatter
