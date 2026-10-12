"""A second plugin, kept unimported on purpose.

`codec_json` is imported by the tests that need a populated registry. This one
stays out, so a configuration naming both has exactly one missing key -- which
is what `validate_configured` has to find and name.
"""

from factory_method import register


@register("csv")
class CsvCodec:
    name = "csv"

    def encode(self, obj: dict) -> str:
        keys = sorted(obj)
        return ",".join(keys) + "\n" + ",".join(str(obj[k]) for k in keys)
