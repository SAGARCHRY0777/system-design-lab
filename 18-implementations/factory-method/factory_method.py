"""Factory Method, and the three other things people call "factory".

The Gang of Four pattern is the one in the title and the one you will use
least. Most of what this file demonstrates is the gap between it and the three
neighbours it gets confused with, because that confusion is what actually costs
people time -- in review, in interviews, and in one specific production bug
that CI cannot see.

Four things, and the only question that separates them is **who decides, and
when**:

    registry / dict of classes   CONFIGURATION decides, at startup
    static factory method        the CALLER decides, at call time
    Factory Method (GoF)         the SUBCLASS decides, fixed at construction
    passing the class            whoever wired it decides, at construction

`_REGISTRY` below is the first one, and it is what people mean nine times out
of ten when they say "I'll add a factory". It also carries the bug this file
exists for: **a registration decorator only runs when its module is imported,
and nothing imports it.** The factory cannot import the plugins -- that is the
coupling it was added to remove -- so in production the registry is empty and
`codec("json")` raises KeyError. In tests it works, because the test imported
the module. CI is green. See `codec_json.py`, which nothing here imports, and
`test_the_decorator_never_ran_because_nobody_imported_the_module`.

`validate_configured` is the fix, and it is three lines nobody writes: at boot,
check that every key the configuration mentions actually resolves. That turns
"fails on the first request that needs it, at 3am" into "fails at deploy".

The GoF pattern itself is `Exporter`, and `ComposedExporter` beside it is the
same behaviour with two fewer classes, because in Python a class is an ordinary
value you can pass as an argument. Factory Method is largely a workaround for
languages where that is not true -- and since Java 8, `Supplier<T>` plus a
method reference gives Java the same option.

`Playlist` at the bottom is the one honest textbook instance: `__iter__` *is*
Factory Method, it is in every collection library ever written, and it is a
better thing to point at than any `create_thing(kind)` switch.

Stdlib only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Iterator

# ─────────────────────────────────────────────────────────────────────────────
# 1. The registry -- what people actually mean by "a factory"
# ─────────────────────────────────────────────────────────────────────────────

# Module-level mutable state, deliberately. This IS the mechanism: the decorator
# below writes into it as a side effect of its module being imported, which is
# the single fact everything in section 1 turns on.
_REGISTRY: dict[str, type] = {}


class UnknownCodec(KeyError):
    """Raised for a name nothing registered.

    A distinct type rather than a bare KeyError because this is a *trust
    boundary*: the name arrived from a config file or an HTTP header, so
    "unknown" is an input-validation outcome and not an internal error. Callers
    that want to answer 400 rather than 500 need to be able to tell them apart.
    """


def register(name: str) -> Callable[[type], type]:
    """Add a class to the registry under `name`, at import time.

    The returned decorator runs exactly once, when the module containing the
    decorated class is first imported -- and *only* then. That is the whole
    bug: nothing in this module imports `codec_json`, because importing every
    implementation is precisely the coupling a registry exists to avoid.
    """
    def deco(cls: type) -> type:
        _REGISTRY[name] = cls
        return cls
    return deco


def codec(name: str):
    """The factory. Build whatever was registered under `name`."""
    try:
        return _REGISTRY[name]()
    except KeyError:
        raise UnknownCodec(
            f"no codec registered for {name!r}; known: {sorted(_REGISTRY)}") from None


def validate_configured(names: list[str]) -> None:
    """Fail at startup for any configured name that will not resolve later.

    Three lines, and almost nobody writes them. Without this the process starts
    cleanly, serves traffic, and dies on the first request that happens to need
    the missing codec -- which may be hours later, on one endpoint, at 3am. The
    typo was in `config.yaml` the whole time.

    Call it from the composition root, after the plugin modules are imported
    and before the server binds a port. `App.start` below shows the shape.
    """
    missing = [n for n in names if n not in _REGISTRY]
    if missing:
        raise UnknownCodec(
            f"configured but not registered: {missing}; known: {sorted(_REGISTRY)}")


class App:
    """A server reduced to its two relevant moments: boot, and first request.

    Exists so the difference between the two failure modes is a thing a test can
    assert rather than a thing a paragraph can claim. Same configuration, same
    missing codec; `validate=True` raises in `start()` and `validate=False`
    raises in whichever `handle()` call first asks for it.
    """

    def __init__(self, configured: list[str], validate: bool = True) -> None:
        self.configured = configured
        self.validate = validate
        self.requests_served = 0

    def start(self) -> None:
        if self.validate:
            validate_configured(self.configured)

    def handle(self, name: str) -> str:
        self.requests_served += 1
        return codec(name).encode({"ok": True})


# ─────────────────────────────────────────────────────────────────────────────
# 2. The Gang of Four pattern
# ─────────────────────────────────────────────────────────────────────────────


class Formatter(ABC):
    """The *product*. What the factory method returns."""

    @abstractmethod
    def row(self, cells: list[str]) -> str: ...


class CsvFormatter(Formatter):
    def row(self, cells: list[str]) -> str:
        return ",".join(cells)


class TsvFormatter(Formatter):
    def row(self, cells: list[str]) -> str:
        return "\t".join(cells)


class Exporter(ABC):
    """The *creator*. Owns an algorithm; delegates one creation step downward.

    The inversion is the pattern, and it is easy to miss: `export` is written
    here, in the base class, and it calls `_create_formatter`, which is *not*
    implemented here. The base class owns WHAT HAPPENS; the subclass owns WHICH
    OBJECTS it happens to. Structurally this is Template Method -- which is why
    a "Creational" pattern looks exactly like a Behavioural one.
    """

    @abstractmethod
    def _create_formatter(self) -> Formatter:
        """THE factory method. One hole, filled by each subclass."""

    def export(self, rows: list[list[str]]) -> str:
        # Deliberately not overridable in spirit -- Java would mark this
        # `final`. If a subclass may replace the algorithm as well as the
        # product, the guarantee the pattern exists to provide is gone, and
        # "one algorithm, many products" becomes "anything, anything".
        f = self._create_formatter()
        return "\n".join(f.row(r) for r in rows)


class CsvExporter(Exporter):
    def _create_formatter(self) -> Formatter:
        return CsvFormatter()


class TsvExporter(Exporter):
    def _create_formatter(self) -> Formatter:
        return TsvFormatter()


# ─────────────────────────────────────────────────────────────────────────────
# 3. The same thing, with the hierarchy deleted
# ─────────────────────────────────────────────────────────────────────────────


class ComposedExporter:
    """Identical behaviour. No abstract base, no subclass per product.

    In Python a class is an ordinary object: you can put it in a dict, pass it
    as an argument, and call it. `CsvFormatter` *is* the factory -- it needs no
    wrapper, because calling a class is already "make me one of these".

    The two subclasses in section 2 exist only to answer the question "which
    class do I instantiate", and that question is answerable with a parameter.
    `test_the_hierarchy_costs_two_classes_for_what_a_parameter_does` asserts
    both the equivalence and the cost.

    Java is not stuck with the hierarchy either, since 8:

        class Exporter {
            private final Supplier<Formatter> make;
            Exporter(Supplier<Formatter> make) { this.make = make; }
        }
        new Exporter(CsvFormatter::new);
    """

    def __init__(self, make_formatter: Callable[[], Formatter] = CsvFormatter) -> None:
        self._make = make_formatter

    def export(self, rows: list[list[str]]) -> str:
        f = self._make()
        return "\n".join(f.row(r) for r in rows)


# ─────────────────────────────────────────────────────────────────────────────
# 4. The one genuine textbook instance
# ─────────────────────────────────────────────────────────────────────────────


class Playlist:
    """`__iter__` is Factory Method, and it is in every collection library.

    Creator: the playlist. Product: the iterator. The base class's algorithm
    (`preview`) consumes the product without knowing which one it got, and each
    subclass returns its own. That is the pattern, complete, with no
    `create_thing(kind)` switch anywhere near it.

    Point at this in an interview rather than at a registry. It is the example
    the GoF book itself uses, and it is the one that survives the follow-up
    "where have you actually seen it".
    """

    def __init__(self, titles: list[str]) -> None:
        self._titles = list(titles)

    def _iterator(self) -> Iterator[str]:
        """THE factory method. `__iter__` delegates to it so subclasses need
        only answer "in what order", not "how does iteration work"."""
        return iter(self._titles)

    def __iter__(self) -> Iterator[str]:
        return self._iterator()

    def preview(self, n: int = 3) -> list[str]:
        """The algorithm. Written once; never overridden; order-sensitive, so
        the product it receives is observable in the result."""
        out = []
        for title in self._iterator():
            if len(out) == n:
                break
            out.append(title)
        return out


class SortedPlaylist(Playlist):
    def _iterator(self) -> Iterator[str]:
        return iter(sorted(self._titles))


class ReversedPlaylist(Playlist):
    def _iterator(self) -> Iterator[str]:
        return iter(reversed(self._titles))


def demo() -> None:
    """Assert the four findings with no test runner. `python factory_method.py`."""
    import importlib
    import sys

    # 1. The registry is empty until something imports the plugin module.
    for mod in ("codec_json", "codec_csv"):
        sys.modules.pop(mod, None)
    _REGISTRY.clear()
    try:
        codec("json")
        raise AssertionError("expected UnknownCodec from an unpopulated registry")
    except UnknownCodec:
        pass
    importlib.import_module("codec_json")
    assert codec("json").name == "json"

    # 2. Startup validation names the missing one before any request is served.
    app = App(["json", "csv"], validate=True)
    try:
        app.start()
        raise AssertionError("expected startup to reject the unregistered codec")
    except UnknownCodec as e:
        assert "csv" in str(e)
    assert app.requests_served == 0

    # 3. Hierarchy and parameter produce the same bytes.
    rows = [["a", "b"], ["c", "d"]]
    assert CsvExporter().export(rows) == ComposedExporter(CsvFormatter).export(rows)
    assert len(Exporter.__subclasses__()) == 2

    # 4. One algorithm, three products.
    p = ["delta", "alpha", "charlie"]
    assert Playlist(p).preview() == ["delta", "alpha", "charlie"]
    assert SortedPlaylist(p).preview() == ["alpha", "charlie", "delta"]
    assert ReversedPlaylist(p).preview() == ["charlie", "alpha", "delta"]

    print("registry empty until imported · startup validation caught it before "
          "request 1 · hierarchy == parameter · one algorithm, three iterators")


if __name__ == "__main__":
    import sys as _sys

    # Running this file as a script names it `__main__`. A plugin's
    # `from factory_method import register` would then import a SECOND copy of
    # this module, with its own empty _REGISTRY -- the decorator writes into
    # that one and `codec()` reads this one. It is the same "the registry you
    # read is not the registry that was written" failure in a different
    # costume, and it is worth meeting here rather than in a service at 3am:
    # the usual sighting is a package imported once as `pkg.mod` and once as
    # `mod`, which gives you two of every class and two of every registry.
    _sys.modules.setdefault("factory_method", _sys.modules["__main__"])
    demo()
