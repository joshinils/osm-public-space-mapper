import pyproj

from example_application import local_variables as local_var
from osm_public_space_mapper.data_analysis import (
    analyse_access, analyse_space_type, analyse_traffic_area, clean_data,
    export_data, get_undefined_space, load_data
)
from osm_public_space_mapper.utils.bounding_box import BoundingBox

### PARAMETERS TO SET ###
source_filepath = "example_application/vienna-rennweg-to-arenbergpark_20230308.osm.pbf"
bounding_box = BoundingBox(top=48.1999, left=16.3843, bottom=48.1931, right=16.3977)
local_crs = pyproj.CRS.from_epsg(3035)  # EPSG 3035 is recommended as default for European Lambert Azimuthal Equal Area, but can be adapted for a more suitable CRS
target_filepath = "example_application/public-space-vienna-rennweg-to-arenbergpark.geojson"
print_status = True  # Should the current analysis step be printed to the terminal?

### CLEANING AND PREPARING DATA ###
if print_status:
    print('Loading elements from', source_filepath)
dataset = load_data.load_elements(source_filepath)
if print_status:
    print('Dropping invalid geometries')
dataset = clean_data.drop_invalid_geometries(dataset)
if print_status:
    print('Dropping empty geometries')
dataset = clean_data.drop_empty_geometries(dataset)
if print_status:
    print('Dropping elements without tags')
dataset = clean_data.drop_elements_without_tags(dataset)
if print_status:
    print('Cleaning geometries')
clean_data.clean_geometries(dataset)
if print_status:
    print('Projecting geometries')
clean_data.project_geometries(dataset, local_crs)
if print_status:
    print('Marking buildings')
analyse_space_type.mark_buildings(dataset)
if print_status:
    print('Returning buildings as separate list and drop from dataset')
dataset, buildings = clean_data.get_and_drop_buildings(dataset)
if print_status:
    print('Dropping irrelevant elements based on tags')
dataset = clean_data.drop_irrelevant_elements_based_on_tags(dataset)

### ANALYSING ACCESS ###
if print_status:
    print('Interpreting tags for access')
analyse_access.interpret_tags(dataset)
if print_status:
    print('Interpreting barriers - be patient, that may take a while.')
analyse_access.interpret_barriers(dataset)
if print_status:
    print('Getting inaccessible barriers')
inaccessible_barriers = analyse_access.get_inaccessible_barriers(dataset)
if print_status:
    print('Getting inaccessible enclosed areas')
inaccessible_enclosed_areas = analyse_access.get_inaccessible_enclosed_areas(inaccessible_barriers, buildings)
if print_status:
    print('Cleaning inaccessible enclosed areas and adding related access attribute to OsmElements - be patient, that may take a while.')
inaccessible_enclosed_areas_cleaned = analyse_access.compare_osm_elements_to_inaccessible_enclosed_areas_and_drop_intersections(dataset, inaccessible_enclosed_areas)
if print_status:
    print('Clearing temporary attributes and dropping barriers from dataset')
dataset = analyse_access.clear_temporary_attributes_and_drop_linestring_barriers(dataset)

### GETTING TRAFFIC AREA ###
if print_status:
    print('Getting car/bicycle traffic areas as polygons - be patient, that may take a while.')
traffic_areas = analyse_traffic_area.get_traffic_areas_as_polygons(
    dataset,
    inaccessible_enclosed_areas_cleaned,
    buildings,
    local_var.highway_default_widths,
    local_var.cycleway_default_widths,
    local_var.tram_gauge,
    local_var.tram_buffer,
    local_var.train_gauge,
    local_var.train_buffer
)

### CLEANING DATA ###
if print_status:
    print('Dropping points')
dataset = clean_data.drop_points(dataset)
if print_status:
    print('Dropping all traffic areas from dataset')
dataset = clean_data.drop_traffic_elements(dataset)
if print_status:
    print('Dropping linestrings from dataset')
dataset = clean_data.drop_linestrings(dataset)
if print_status:
    print('Dropping elements within inaccessible enclosed areas - be patient, that may take a while.')
dataset = clean_data.drop_elements_within_inaccessible_enclosed_areas(dataset, inaccessible_enclosed_areas_cleaned)
if print_status:
    print('Cropping overlapping polygons - be patient, that may take a while.')
clean_data.crop_overlapping_polygons(dataset)

### SETTING MISSING SPACE TYPE AND GUESSING MISSING ACCESS ###
if print_status:
    print('Setting missing space types based on tags')
analyse_space_type.set_missing_space_types(dataset)
if print_status:
    print('Dropping elements with undefined space type')
dataset = clean_data.drop_elements_with_undefined_space_type(dataset)
if print_status:
    print('Setting missing access attribute based on space type')
analyse_access.assume_and_clean_access_based_on_space_type(dataset)


### PREPARING FOR EXPORT ###
if print_status:
    print('Combining all element lists that define space in a dictionary')
all_defined_space_lists = {'dataset': dataset, 'buildings': buildings, 'inaccessible_enclosed_areas': inaccessible_enclosed_areas_cleaned, 'traffic_areas': list(traffic_areas.geoms)}
if print_status:
    print('Projecting bounding box')
bounding_box.project(local_crs)
if print_status:
    print('Cropping all element lists to projected bounding box')
all_defined_space_lists_cropped = clean_data.crop_defined_space_to_bounding_box(all_defined_space_lists, bounding_box)
if print_status:
    print('Getting undefined space within bounding box - be patient, that may take a while.')
undefined_space_within_bbox = get_undefined_space.load(all_defined_space_lists_cropped, bounding_box)

### EXPORTIN ###
if print_status:
    print('Exporting all defined space and the undefined space to GeoJSON:', target_filepath)
export_data.save2geojson(all_defined_space_lists_cropped, undefined_space_within_bbox, target_filepath, local_crs)
