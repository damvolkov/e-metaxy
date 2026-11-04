"""e_organon.models.doc: what the doc/ tools take and give — files by path, never bytes in the arguments."""

import msgspec


##### CONVERT #####
class ConvertIn(msgspec.Struct, frozen=True, kw_only=True):
    """`path`: the document, under one of ORGANON_FILES__ROOTS (`~` expands)."""

    path: str


class ConvertOut(msgspec.Struct, frozen=True, kw_only=True):
    """The document as Markdown: tables as tables, scans read, in page order."""

    name: str
    markdown: str
