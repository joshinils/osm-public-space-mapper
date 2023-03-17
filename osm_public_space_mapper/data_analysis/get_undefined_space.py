from typing import Dict, List, TypeAlias, Union

import shapely
from shapely.geometry import (
    LinearRing, LineString, MultiLineString, MultiPoint, MultiPolygon, Point,
    Polygon
)

from osm_public_space_mapper.utils.bounding_box import BoundingBox
from osm_public_space_mapper.utils.osm_element import OsmElement

ShapelyGeometry: TypeAlias = Union[LinearRing, Polygon, MultiPolygon, Point, MultiPoint, LineString, MultiLineString]


def load(all_defined_space_lists: Dict[str, List[OsmElement, ShapelyGeometry]], bbox: BoundingBox) -> MultiPolygon:
    """returns space that is not part of all defined space as a Polygon

    Args:
        all_defined_space_lists (dict[str,list[OsmElement | ShapelyGeometry]]): dictionary of all lists with defined space
        bbox (BoundingBox): BoundingBox in which the undefined space should be loaded

    Returns:
        MultiPolygon: undefined space within BoundingBox as Polyon
    """
    defined_space_geometries = []
    for _, elements in all_defined_space_lists.items():
        for e in elements:
            if type(e) == OsmElement:
                defined_space_geometries.append(e.geom)
            else:
                defined_space_geometries.append(e)
    defined_space_union = shapely.ops.unary_union(defined_space_geometries)
    undefined_space = bbox.geom_projected.difference(defined_space_union)
    return undefined_space
