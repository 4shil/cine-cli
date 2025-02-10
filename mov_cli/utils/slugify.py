import unicodedata
import re

__all__ = (
    "slugify",
)

def slugify(value): # https://github.com/django/django/blob/main/django/utils/text.py#L452-L469
    value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )

    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-_")