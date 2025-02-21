import copy
from typing import Dict, List, Set, Tuple

import shapely
from shapely.geometry import MultiPolygon, Polygon

from example_application import local_variables as local_var
from osm_public_space_mapper.utils.helpers import buffer_list_of_elements
from osm_public_space_mapper.utils.osm_element import OsmElement


def is_crossing(element):
    tags_with_crossing_values = set(('footway', 'highway'))
    if element.has_tag('crossing'):
        return True
    for tag in tags_with_crossing_values:
        if element.tags.get(tag) == 'crossing':
            return True
    return False


def is_pedestrian_way(element):
    highway_for_pedestrians = ['footway', 'steps', 'path', 'platform', 'pedestrian', 'living_street', 'track']
    return element.tags.get('highway') in highway_for_pedestrians and not element.tags.get('footway') == 'crossing'


def get_traffic_areas_as_polygons(
    elements: List[OsmElement],
    inaccessible_enclosed_areas: List[Polygon, MultiPolygon],
    buildings: List[OsmElement],
    highway_default_widths: Dict[str, Tuple[float, float]] = None,
    cycleway_default_widths: Dict[Dict[str, float]] = None,
    tram_gauge: float = 1.435, tram_buffer: float = 0.5,
    train_gauge: float = 1.435, train_buffer: float = 1.5,
    pedestrian_way_default_width: float = 1.6,
    non_traffic_space_around_buildings_default_width: float = 1.3
) -> List[Polygon, MultiPolygon]:
    def buffer_osm_element(element: OsmElement) -> OsmElement:
        buffer_size = round(element.width / 2, 1)
        element_buffered = copy.deepcopy(element)
        element_buffered.geom = element.geom.buffer(buffer_size, cap_style='flat')
        return element_buffered

    def polygonize_highways(elements: List[OsmElement], highway_default_widths: Dict[str, Tuple[float, float]], cycleway_default_widths: Dict[Dict[str, float]]) -> List[OsmElement]:
        """iterates over list of OsmElements and buffers highways and thus transforms the LineStrings to Polygons based on given or estimated width and sets processed elements in given list to ignore

        Args:
            elements (list[OsmElement]): list of OsmElements to iterate over

        Returns:
            list[OsmElement]: list of only highways as OsmElements with buffered geom attribute
        """
        def set_road_width(element: OsmElement, highway_default_widths: Dict[str, Tuple[float, float]], cycleway_default_widths: Dict[Dict[str, float]]) -> None:
            """Sets road width of a highway element in width attribute, either taken from width tags or estimated based on default values and

            Args:
                element (OsmElement): the OsmElement to analyse
                highway_default_widths (dict[str, Tuple[float, float]]): dictionary with default highway widths of the roadway without parking, cycle lane etc. in a dictionary for each OSM highway type.
                                                                        Each dict element has a tuple consisting of the value for bi-directional and uni-directional highways. Defaults set within function.
                cycleway_default_widths (dict[Dict[str, float]]): default cycleway widths with separate values given for different tags and their values in a nested dictionary. Defaults set within function.
            """
            def set_defaults(highway_default_widths: Dict[str, Tuple[float, float]], cycleway_default_widths: Dict[Dict[str, float]]) -> Set[Dict, Dict]:
                if highway_default_widths is None:
                    highway_default_widths = {
                        'footway': (1.8, 1),
                        'service': (4.5, 3),
                        'residential': (4.5, 3),
                        'steps': (2, 1.5),
                        'tertiary': (4.8, 3.1),
                        'primary': (5.5, 3.1),
                        'cycleway': (2, 1.5),
                        'secondary': (4.8, 3.1),
                        'path': (1.5, 1),
                        'motorway_link': (6.5, 3.23),
                        'platform': (2, 1.5),
                        'pedestrian': (2, 2),
                        'motorway': (6.5, 3.25),
                        'living_street': (4.5, 3),
                        'unclassified': (4.5, 3),
                        'primary_link': (5.5, 3.1),
                        'track': (3, 2.5),
                        'corridor': (2, 1),
                        'proposed': (4.8, 3.1),
                        'secondary_link': (4.8, 3.1),
                        'construction': (5.5, 3.1),
                        'everything else': (4.8, 3.1)}
                if cycleway_default_widths is None:
                    cycletrack_width, cyclelane_width = 1.6, 1.6
                    cycleway_default_widths = {
                        'cycleway': {
                            'lane': cyclelane_width,
                            'opposite': 1,
                            'track': cycletrack_width,
                            'opposite_lane': cyclelane_width,
                            'opposite_track': cycletrack_width
                        },
                        'cycleway:right': {
                            'lane': cyclelane_width,
                            'track': cycletrack_width
                        },
                        'cycleway:both': {
                            'lane': 2 * cyclelane_width,
                            'track': 2 * cycletrack_width
                        },
                        'cycleway:left': {
                            'lane': cyclelane_width,
                            'track': cycletrack_width
                        }
                    }
                return highway_default_widths, cycleway_default_widths

            highway_default_widths, cycleway_default_widths = set_defaults(highway_default_widths, cycleway_default_widths)

            def estimate_road_width(element: OsmElement, highway_default_widths: Dict[str, Tuple[float, float]], cycleway_default_widths: Dict[Dict[str, float]]) -> float:
                """estimates road with of an OsmElement based on default values and tags and returns the width

                Args:
                    element (OsmElement): the OsmElement to analyse
                    highway_default_widths (dict[str, Tuple[float, float]]): dictionary with default highway widths of the roadway without parking, cycle lane etc. in a dictionary for each OSM highway type.
                                                                            Each dict element has a tuple consisting of the value for bi-directional and uni-directional highways.
                    cycleway_default_widths (dict[Dict[str, float]]): default cycleway widths with separate values given for different tags and their values in a nested dictionary

                Returns:
                    float: estimated width
                """

                def set_default_highway_width(element: OsmElement, direction: str, highway_default_widths: Dict[str, Tuple[float, float]]) -> float:
                    i = 1 if direction == 'uni-directional' else 0 if direction == 'bi-directional' else None
                    if element.tags.get('highway') in highway_default_widths:
                        width = highway_default_widths[element.tags.get('highway')][i]
                    else:
                        width = highway_default_widths['everything else'][i]
                    return width

                def adapt_to_lanes(element: OsmElement, width: float, direction: str) -> float:
                    normal_lane_number = 1 if direction == 'uni-directional' else 2 if direction == 'bi-directional' else None
                    if element.has_tag('lanes') and float(element.tags.get('lanes')) != normal_lane_number:
                        width = width * float(element.tags.get('lanes')) / normal_lane_number
                    return width

                def add_cycleway(element: OsmElement, width: float, cycleway_default_widths: Dict[Dict[str, float]]) -> float:
                    if element.tags.get('highway') not in cycleway_default_widths:  # if it's not a cycleway by itself
                        for tag in cycleway_default_widths:
                            if element.has_tag(tag):
                                if element.tags.get(tag) in cycleway_default_widths[tag]:
                                    width += cycleway_default_widths[tag][element.tags.get(tag)]
                    return width

                def add_parking(element: OsmElement,
                                width: float,
                                highway_types_for_default_streetside_parking: List[str] = ['residential', 'tertiary', 'living_street', 'secondary', 'primary'],
                                default_parking_width: float = 6.5) -> float:
                    """adds a default value to the given width if highway is of specific type

                    Args:
                        element (OsmElement): highway OsmElement
                        width (float): current width of the element
                        highway_types_for_default_streetside_parking (list[str], optional): highway tag values where parking is assumed. Defaults to ['residential', 'tertiary', 'living_street', 'secondary', 'primary'].
                        default_parking_width (float, optional): _description_. Defaults to 6.5, assuming one side horizontal (2m) and one side angle parking (4.5m),
                        taken from OSM Verkehrswende project https://parkraum.osm-verkehrswende.org/project-prototype-neukoelln/report/#27-fl%C3%A4chenverbrauch

                    Returns:
                        float: width with added parking
                    """
                    if element.tags.get('highway') in highway_types_for_default_streetside_parking:
                        width += default_parking_width
                    return width

                direction = 'uni-directional' if e.has_tag('oneway') else 'bi-directional'
                width = set_default_highway_width(e, direction, highway_default_widths)
                width = adapt_to_lanes(e, width, direction)
                width = add_cycleway(e, width, cycleway_default_widths)
                width = add_parking(e, width, local_var.highway_types_for_default_streetside_parking, local_var.default_parking_width)
                return width

            if element.has_tag('width:carriageway'):
                element.width = float(e.tags.get('width:carriageway'))
            elif element.has_tag('width'):
                element.width = float(e.tags.get('width'))
            else:
                element.width = estimate_road_width(element, highway_default_widths, cycleway_default_widths)

        def is_irrelevant_highway(element: OsmElement) -> bool:
            irrelevant_highway_tag_values = ['corridor', 'proposed']
            return element.tags.get('highway') in irrelevant_highway_tag_values

        highways_polygons = []
        for e in [e for e in elements if e.has_tag('highway')]:
            if is_pedestrian_way(e):
                if not is_crossing(e):
                    e.space_type = 'walking area'
            elif is_irrelevant_highway(e):
                e.space_type = 'traffic area'
            else:
                if e.is_linestring():
                    set_road_width(e, highway_default_widths, cycleway_default_widths)
                    highways_polygons.append(buffer_osm_element(e))
                e.space_type = 'traffic area'
        return highways_polygons

    def polygonize_railways(elements: List[OsmElement], tram_gauge: float, tram_buffer: float, train_gauge: float, train_buffer: float) -> List[OsmElement]:
        """iterates over list of OsmElements and buffers railways and thus transforms the LineStrings to Polygons based on tram and train gauge and buffer size

        Args:
            elements (list[OsmElement]): list of OsmElements to iterate over
            tram_gauge (float): tram gauge. Defaults to 1.435
            tram_buffer (float): tram buffer size of what should be added to the tram gauge for total tram rail width
            train_gauge (float): train gauge. Defaults to 1.435
            train_buffer (float): train buffer size of what should be added to the train gauge for total train rail width

        Returns:
            list[OsmElement]: list of only railways as OsmElements with buffered geom attribute
        """
        rails_polygons = []
        for e in [e for e in elements if e.is_linestring() and e.has_tag('railway')]:
            if e.tags.get('railway') == 'tram':
                e.width = tram_gauge + tram_buffer
            elif e.tags.get('railway') == 'rail':  # ignore subway because assume it's underground
                e.width = train_gauge + train_buffer
            if e.tags.get('railway') in ['tram', 'rail']:
                rails_polygons.append(buffer_osm_element(e))
            if not e.tags.get('railway') == 'platform':
                e.space_type = 'traffic area'
        return rails_polygons

    def get_traffic_areas(elements: List[OsmElement]) -> List[OsmElement]:
        return polygonize_highways(elements, highway_default_widths, cycleway_default_widths) + polygonize_railways(elements, tram_gauge, tram_buffer, train_gauge, train_buffer)

    def get_cropper_geometries(elements: List[OsmElement], inaccessible_enclosed_areas: List[Polygon, MultiPolygon], buildings: List[OsmElement]) -> List[Polygon, MultiPolygon]:
        """combines and returns all geometries that should be used to crop the traffic areas again

        Args:
            elements (list[OsmElement): list of OsmElements with platform and pedestrian way elements
            inaccessible_enclosed_areas (list[Polygon | MultiPolygon]): list of earlier defined inaccessible_enclosed_areas, because traffic areas will not be accessible there
            buildings (list[OsmElement): list of OsmElements with buildings

        Returns:
            List[Polygon, MultiPolygon]: list of polygon or multipolygon geomtries instead of OsmElements
        """
        pedestrian_ways_buffered = buffer_list_of_elements([e for e in elements if is_pedestrian_way(e)], buffer_size=pedestrian_way_default_width / 2, cap_style='flat')
        buildings_buffered = buffer_list_of_elements(buildings, buffer_size=non_traffic_space_around_buildings_default_width, join_style='mitre')
        platforms = [e for e in elements if e.tags.get('railway') == 'platform']
        cropper_geometries = [e.geom for e in pedestrian_ways_buffered] + [e.geom for e in buildings_buffered] + [e.geom for e in platforms] + inaccessible_enclosed_areas
        return cropper_geometries

    def crop_traffic_areas(traffic_area_elements: List[OsmElement], cropper_geometries: List[Polygon, MultiPolygon]) -> List[OsmElement]:
        """Iterates over traffic area elements and crops them when intersecting with a cropper geometry

        Args:
            traffic_area_elements (list[OsmElement]): traffic area elements to iterate over
            cropper_geometries (list[Polygon | MultiPolygon]): cropper geometries

        Returns:
            list[OsmElement]: list of traffic areas as OsmElements with new, cropped geom attribute
        """
        traffic_areas_cropped = []
        for traffic_area in traffic_area_elements:
            traffic_area_cropped = copy.deepcopy(traffic_area)
            for cropper in cropper_geometries:
                if traffic_area_cropped.geom.intersects(cropper):
                    traffic_area_cropped.geom = traffic_area_cropped.geom.difference(cropper)
            traffic_areas_cropped.append(traffic_area_cropped)
        return traffic_areas_cropped

    def smooth_traffic_areas(traffic_areas_cropped):
        smooth_traffic_areas = traffic_areas_cropped.buffer(1, join_style='mitre').buffer(-1, join_style='mitre').buffer(0.5, join_style='round').buffer(-0.5, join_style='round')
        return smooth_traffic_areas

    traffic_areas = get_traffic_areas(elements)
    cropper_geometries = get_cropper_geometries(elements, inaccessible_enclosed_areas, buildings)
    cropper_geometries_union = shapely.ops.unary_union(cropper_geometries).buffer(0.3).buffer(-0.3)
    traffic_areas_union = shapely.ops.unary_union([e.geom for e in traffic_areas])
    traffic_areas_cropped = traffic_areas_union.difference(cropper_geometries_union)
    return smooth_traffic_areas(traffic_areas_cropped)
