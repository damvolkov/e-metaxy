"""e_organon.models.image: what the image/ tools take — a file by path under ORGANON_ROOTS; what they give is a `FileOut`
(`models.doc`), the file in the outbox, named by its content."""

import msgspec


##### CUTOUT #####
class CutoutIn(msgspec.Struct, frozen=True, kw_only=True):
    """`path`: the photo (`~` expands). `color`: the ink keeps its own colour; off, it is black. `crop`: the PNG is cut to
    the ink with a small margin; off, it is the photo's size."""

    path: str
    color: bool = True
    crop: bool = True
