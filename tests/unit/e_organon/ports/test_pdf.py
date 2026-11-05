"""tests/unit/e_organon/ports/pdf: a page's geometry — a point goes to the displayed page and back, whatever the turn and the
crop box, and the displayed axes are the ones the point's move says."""

import pytest

from e_organon.ports.pdf import PageGeometry

POINTS = [(0.0, 0.0), (10.0, 20.0), (123.5, 77.25)]


@pytest.mark.parametrize("rotate", [0, 90, 180, 270])
@pytest.mark.parametrize("point", POINTS)
def test_pdf_geometry_a_point_goes_to_the_page_and_back(rotate: int, point: tuple[float, float]) -> None:
    geometry = PageGeometry(left=50, bottom=80, right=545, top=742, rotate=rotate)
    assert geometry.user(*geometry.shown(*geometry.user(*point))) == pytest.approx(geometry.user(*point))
    assert geometry.shown(*geometry.user(*point)) == pytest.approx(point)


@pytest.mark.parametrize("rotate", [0, 90, 180, 270])
def test_pdf_geometry_axes_are_where_a_step_along_the_displayed_axes_goes(rotate: int) -> None:
    geometry = PageGeometry(left=50, bottom=80, right=545, top=742, rotate=rotate)
    (ox, oy), (ex, ey), (fx, fy) = geometry.user(0, 0), geometry.user(1, 0), geometry.user(0, 1)
    (ax, ay), (bx, by) = geometry.axes
    assert (ex - ox, ey - oy, fx - ox, fy - oy) == pytest.approx((ax, ay, bx, by))


@pytest.mark.parametrize(("rotate", "size"), [(0, (495, 662)), (90, (662, 495)), (180, (495, 662)), (270, (662, 495))])
def test_pdf_geometry_size_is_the_displayed_one(rotate: int, size: tuple[float, float]) -> None:
    assert PageGeometry(left=50, bottom=80, right=545, top=742, rotate=rotate).size == size
