"""A plugin. Registers itself on import -- and nothing imports it.

That sentence is the entire lesson. `factory_method.py` deliberately does not
import this module: importing every implementation is exactly the coupling a
registry exists to remove. So the decorator below runs only if something else
imports this file, and in a real service nothing does.

The test suite imports it explicitly, which is why this bug survives CI: pytest
collection, a fixture, or one `import` in a conftest is enough to populate the
registry for every test in the run. Production has no equivalent accident.
"""

from factory_method import register


@register("json")
class JsonCodec:
    name = "json"

    def encode(self, obj: dict) -> str:
        import json
        return json.dumps(obj, separators=(",", ":"), sort_keys=True)
