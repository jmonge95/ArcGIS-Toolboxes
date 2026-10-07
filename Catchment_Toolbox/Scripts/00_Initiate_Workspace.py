"""
00_Initiate_Workspace.py

Catchment Toolbox

Purpose:
    Initializes a new catchment delineation workspace.

Parameters:
    0 - User Workspace (Folder)
    1 - iwub Shape (Polygon Feature Layer)
    2 - Locale (CONUS | AK)
    3 - EDH GDB (File Geodatabase)
"""

import os
import shutil
import arcpy
import catchment_utils as utils
import json
import urllib.parse

# =============================================================================
# WORKSPACE SETUP
# =============================================================================

def copy_template_structure(user_workspace):

    utils.msg("Copying workflow template structure...")

    shutil.copytree(
        utils.TEMPLATE_DIRECTORY,
        user_workspace,
        dirs_exist_ok=True
    )

def create_inputs_gdb(user_workspace):
    """Create Inputs.gdb."""

    inputs_gdb = utils.get_inputs_gdb(
        user_workspace
    )

    if not arcpy.Exists(inputs_gdb):

        arcpy.management.CreateFileGDB(
            utils.get_input_folder(user_workspace),
            "Inputs.gdb"
        )

    else:

        utils.warn(
            "Inputs.gdb already exists."
        )

    return inputs_gdb


def create_scratch_gdb(user_workspace):
    """Create Scratch.gdb."""

    scratch_gdb = utils.get_scratch_gdb(
        user_workspace
    )

    if not arcpy.Exists(scratch_gdb):

        arcpy.management.CreateFileGDB(
            utils.get_input_folder(user_workspace),
            "Scratch.gdb"
        )

    else:

        utils.warn(
            "Scratch.gdb already exists."
        )

    return scratch_gdb


# =============================================================================
# EDH GDB
# =============================================================================

def copy_edh_gdb(
        source_gdb,
        target_gdb):
    """
    Copy EDH geodatabase into project workspace.
    """

    utils.msg(
        "Copying EDH geodatabase..."
    )

    if arcpy.Exists(target_gdb):
        arcpy.management.Delete(
            target_gdb
        )

    arcpy.management.Copy(
        source_gdb,
        target_gdb
    )


# =============================================================================
# iwub
# =============================================================================

def import_iwub(
        iwub_input,
        iwub_output):
    """
    Import iwub using project CRS environment.
    """

    utils.delete_if_exists(
        iwub_output
    )

    arcpy.management.CopyFeatures(
        iwub_input,
        iwub_output
    )


# =============================================================================
# CREATE OUTSIDE LINES
# =============================================================================

def create_headwater_points(
        outside_flowlines,
        scratch_gdb):
    """
    Create headwater points from a flowline network.

    Headwater points are defined as:

        Start Points
            MINUS
        End Points
    """

    start_pts = os.path.join(
        scratch_gdb,
        "Start_Points"
    )

    end_pts = os.path.join(
        scratch_gdb,
        "End_Points"
    )

    headwater_pts = os.path.join(
        scratch_gdb,
        "Headwater_Points"
    )

    utils.delete_if_exists(
        start_pts
    )

    utils.delete_if_exists(
        end_pts
    )

    utils.delete_if_exists(
        headwater_pts
    )

    arcpy.management.FeatureVerticesToPoints(
        outside_flowlines,
        start_pts,
        "START"
    )

    arcpy.management.FeatureVerticesToPoints(
        outside_flowlines,
        end_pts,
        "END"
    )

    arcpy.analysis.Erase(
        start_pts,
        end_pts,
        headwater_pts
    )

    utils.delete_if_exists(
        start_pts
    )

    utils.delete_if_exists(
        end_pts
    )

    return headwater_pts

def create_lone_end_points(
        outside_flowlines,
        scratch_gdb):
    """
    Create lone end points from a flowline network.

    Lone end points are defined as:

        End Points
            MINUS
        Start Points
    """

    start_pts = os.path.join(
        scratch_gdb,
        "LEP_Start_Points"
    )

    end_pts = os.path.join(
        scratch_gdb,
        "LEP_End_Points"
    )

    lone_end_points = os.path.join(
        scratch_gdb,
        "Lone_End_Points"
    )

    utils.delete_if_exists(
        start_pts
    )

    utils.delete_if_exists(
        end_pts
    )

    utils.delete_if_exists(
        lone_end_points
    )

    arcpy.management.FeatureVerticesToPoints(
        outside_flowlines,
        start_pts,
        "START"
    )

    arcpy.management.FeatureVerticesToPoints(
        outside_flowlines,
        end_pts,
        "END"
    )

    arcpy.analysis.Erase(
        end_pts,
        start_pts,
        lone_end_points
    )

    arcpy.management.DeleteIdentical(
        lone_end_points,
        ["Shape"]
    )

    arcpy.management.AddSpatialIndex(
        lone_end_points
    )

    utils.delete_if_exists(
        start_pts
    )

    utils.delete_if_exists(
        end_pts
    )

    return lone_end_points

def prepare_outside_lines(
        iwub_fc,
        reference_flowlines,
        scratch_gdb):
    """
    Creates a 1000 m exterior ring around the iwub and
    extracts reference flowlines falling within that ring.

    Returns:
        Outside_Reference_Flowlines feature class
    """

    # -------------------------------------------------------------------------
    # Paths
    # -------------------------------------------------------------------------

    iwub_buffer = os.path.join(
        scratch_gdb,
        "iwub_Buffer_1000m"
    )

    iwub_ring = os.path.join(
        scratch_gdb,
        "iwub_Ring_1000m"
    )

    merged_flowlines = os.path.join(
        scratch_gdb,
        "Merged_Reference_Flowlines"
    )

    outside_flowlines = os.path.join(
        scratch_gdb,
        "Outside_Reference_Flowlines"
    )

    outside_flowlines_sp = os.path.join(
        scratch_gdb,
        "Outside_Reference_Flowlines_SP"
    )

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    utils.delete_if_exists(
        iwub_buffer
    )

    utils.delete_if_exists(
        iwub_ring
    )

    utils.delete_if_exists(
        merged_flowlines
    )

    utils.delete_if_exists(
        outside_flowlines
    )

    utils.delete_if_exists(
        outside_flowlines_sp
    )

    # -------------------------------------------------------------------------
    # Create 1000 m iwub buffer
    # -------------------------------------------------------------------------

    arcpy.analysis.Buffer(
        in_features=iwub_fc,
        out_feature_class=iwub_buffer,
        buffer_distance_or_field="1000 Meters",
        dissolve_option="ALL",
        method="PLANAR"
    )

    # -------------------------------------------------------------------------
    # Remove original iwub to create ring
    # -------------------------------------------------------------------------

    arcpy.analysis.Erase(
        in_features=iwub_buffer,
        erase_features=iwub_fc,
        out_feature_class=iwub_ring
    )

    # -------------------------------------------------------------------------
    # Handle single vs multiple flowline inputs
    # -------------------------------------------------------------------------

    flowline_list = [
        fc.strip()
        for fc in reference_flowlines.split(";")
        if fc.strip()
    ]

    if len(flowline_list) == 0:

        raise ValueError(
            "No Reference_Flowlines were supplied."
        )

    elif len(flowline_list) == 1:

        arcpy.management.CopyFeatures(
            flowline_list[0],
            merged_flowlines
        )

    else:

        arcpy.management.Merge(
            flowline_list,
            merged_flowlines
        )

    # -------------------------------------------------------------------------
    # Clip flowlines to iwub ring
    # -------------------------------------------------------------------------

    arcpy.analysis.Clip(
        in_features=merged_flowlines,
        clip_features=iwub_ring,
        out_feature_class=outside_flowlines
    )

    arcpy.management.MultipartToSinglepart(
        outside_flowlines,
        outside_flowlines_sp
    )

    headwater_points = create_headwater_points(
        outside_flowlines_sp,
        scratch_gdb
    )

    lone_end_points = create_lone_end_points(
        outside_flowlines_sp,
        scratch_gdb
    )

    return (
        outside_flowlines_sp,
        headwater_points,
        lone_end_points
    )


# =============================================================================
# FINALIZE OUTSIDE LINES
# =============================================================================

def analyze_reference_lines(
        outside_flowlines,
        headwater_points,
        lone_end_points,
        iwub,
        scratch_gdb):
    """
    Uses a trace network to identify valid
    exterior reference flowlines.
    """

    utils.msg(
        "Creating reference line trace network..."
    )

    merged_reference_flowlines = os.path.join(
        scratch_gdb,
        "Merged_Reference_Flowlines"
    )

    outside_reference_flowlines = os.path.join(
        scratch_gdb,
        "Outside_Reference_Flowlines"
    )

    scratch_folder = os.path.dirname(
        scratch_gdb
    )

    # -------------------------------------------------------------------------
    # Create Feature Dataset
    # -------------------------------------------------------------------------

    spatial_reference = arcpy.Describe(
        outside_flowlines
    ).spatialReference

    trace_fd = os.path.join(
        scratch_gdb,
        "RefLines_Trace"
    )

    if arcpy.Exists(trace_fd):

        arcpy.management.Delete(
            trace_fd
        )

    arcpy.management.CreateFeatureDataset(
        scratch_gdb,
        "RefLines_Trace",
        spatial_reference
    )

    # -------------------------------------------------------------------------
    # Copy flowlines into feature dataset
    # -------------------------------------------------------------------------

    trace_flowlines = os.path.join(
        trace_fd,
        "Trace_Flowlines"
    )

    utils.delete_if_exists(
        trace_flowlines
    )

    arcpy.management.CopyFeatures(
        outside_flowlines,
        trace_flowlines
    )

    # -------------------------------------------------------------------------
    # Create Trace Network
    # -------------------------------------------------------------------------

    arcpy.tn.CreateTraceNetwork(
        trace_fd,
        "TraceNetwork",
        "",
        "Trace_Flowlines SIMPLE_EDGE"
    )

    trace_network = os.path.join(
        trace_fd,
        "TraceNetwork"
    )

    arcpy.tn.EnableNetworkTopology(
        trace_network
    )

    # -------------------------------------------------------------------------
    # Select bad lone end points
    # -------------------------------------------------------------------------

    utils.msg(
        "Tracing upstream from invalid boundary outlets..."
    )

    lone_end_lyr = "lep_lyr"

    arcpy.management.MakeFeatureLayer(
        lone_end_points,
        lone_end_lyr
    )

    iwub_boundary = os.path.join(
        scratch_gdb,
        "iwub_Boundary"
    )

    utils.delete_if_exists(
        iwub_boundary
    )

    arcpy.management.PolygonToLine(
        iwub,
        iwub_boundary
    )

    arcpy.management.SelectLayerByLocation(
        in_layer=lone_end_lyr,
        overlap_type="INTERSECT",
        select_features=iwub_boundary,
        selection_type="NEW_SELECTION"
    )

    lone_end_points_bad = os.path.join(
        scratch_gdb,
        "Lone_End_Points_Bad"
    )

    utils.delete_if_exists(
        lone_end_points_bad
    )

    arcpy.management.CopyFeatures(
        lone_end_lyr,
        lone_end_points_bad
    )

    # -------------------------------------------------------------------------
    # Upstream Trace
    # -------------------------------------------------------------------------

    upstream_json = os.path.join(
        scratch_folder,
        "upstream_trace.json"
    )

    if os.path.exists(upstream_json):
        os.remove(upstream_json)

    arcpy.tn.Trace(
        in_trace_network=trace_network,
        trace_type="UPSTREAM",
        starting_points=lone_end_points_bad,
        result_types="ELEMENTS",
        out_json_file=upstream_json
    )

    with open(
            upstream_json,
            "r",
            encoding="utf-8"
    ) as f:

        upstream_data = json.load(f)

    upstream_ids = {
        element["objectId"]
        for element in upstream_data.get(
            "elements",
            []
        )
    }

    # -------------------------------------------------------------------------
    # Select valid headwaters
    # -------------------------------------------------------------------------

    utils.msg(
        "Tracing downstream from valid headwaters..."
    )

    headwater_lyr = "hw_lyr"

    arcpy.management.MakeFeatureLayer(
        headwater_points,
        headwater_lyr
    )

    arcpy.management.SelectLayerByLocation(
        in_layer=headwater_lyr,
        overlap_type="INTERSECT",
        select_features=iwub_boundary,
        selection_type="NEW_SELECTION",
        invert_spatial_relationship="INVERT"
    )

    headwater_points_to_trace = os.path.join(
        scratch_gdb,
        "Headwater_Points_To_Trace"
    )

    utils.delete_if_exists(
        headwater_points_to_trace
    )

    arcpy.management.CopyFeatures(
        headwater_lyr,
        headwater_points_to_trace
    )

    downstream_json = os.path.join(
        scratch_folder,
        "downstream_trace.json"
    )

    if os.path.exists(downstream_json):
        os.remove(downstream_json)

    arcpy.tn.Trace(
        in_trace_network=trace_network,
        trace_type="DOWNSTREAM",
        starting_points=headwater_points_to_trace,
        result_types="ELEMENTS",
        out_json_file=downstream_json
    )

    with open(
            downstream_json,
            "r",
            encoding="utf-8"
    ) as f:

        downstream_data = json.load(f)

    downstream_ids = {
        element["objectId"]
        for element in downstream_data.get(
            "elements",
            []
        )
    }

    for json_file in [
        upstream_json,
        downstream_json
    ]:
        if os.path.exists(json_file):
            os.remove(json_file)


    # -------------------------------------------------------------------------
    # Remove Bad Lines
    # -------------------------------------------------------------------------

    utils.msg(
        "Removing invalid traced flowlines..."
    )

    valid_flowlines = os.path.join(
        scratch_gdb,
        "Outside_Reference_Flowlines_Valid"
    )

    utils.delete_if_exists(
        valid_flowlines
    )

    valid_ids = (
            downstream_ids -
            upstream_ids
    )

    valid_flowlines_lyr = (
        "valid_flowlines_lyr"
    )

    arcpy.management.MakeFeatureLayer(
        outside_flowlines,
        valid_flowlines_lyr
    )

    oid_field = arcpy.Describe(
        outside_flowlines
    ).OIDFieldName

    if not valid_ids:
        utils.msg(
            "No valid exterior flowlines found."
        )

        return None

    sql = (
        f"{oid_field} IN "
        f"({','.join(map(str, valid_ids))})"
    )

    arcpy.management.SelectLayerByAttribute(
        valid_flowlines_lyr,
        "NEW_SELECTION",
        sql
    )

    utils.delete_if_exists(
        valid_flowlines
    )

    arcpy.management.CopyFeatures(
        valid_flowlines_lyr,
        valid_flowlines
    )

    utils.msg(
        "Removing flowlines with headwaters on work unit boundary..."
    )

    valid_start_points = os.path.join(
        scratch_gdb,
        "Valid_Flowline_Start_Points"
    )

    utils.delete_if_exists(
        valid_start_points
    )

    arcpy.management.FeatureVerticesToPoints(
        valid_flowlines,
        valid_start_points,
        "START"
    )

    valid_start_lyr = "valid_start_lyr"

    arcpy.management.MakeFeatureLayer(
        valid_start_points,
        valid_start_lyr
    )

    arcpy.management.SelectLayerByLocation(
        valid_start_lyr,
        "INTERSECT",
        iwub_boundary
    )

    bad_start_points = os.path.join(
        scratch_gdb,
        "Bad_Start_Points"
    )

    utils.delete_if_exists(
        bad_start_points
    )

    arcpy.management.CopyFeatures(
        valid_start_lyr,
        bad_start_points
    )

    valid_flowlines_lyr = "valid_flowlines_lyr"

    arcpy.management.MakeFeatureLayer(
        valid_flowlines,
        valid_flowlines_lyr
    )

    arcpy.management.SelectLayerByLocation(
        valid_flowlines_lyr,
        "INTERSECT",
        bad_start_points
    )

    arcpy.management.DeleteFeatures(
        valid_flowlines_lyr
    )

    utils.msg(
        "Creating dissolved burn lines..."
    )

    outside_burn_lines = os.path.join(
        scratch_gdb,
        "Outside_Burn_Lines"
    )

    utils.delete_if_exists(
        outside_burn_lines
    )

    arcpy.management.Dissolve(
        valid_flowlines,
        outside_burn_lines,
        multi_part="SINGLE_PART"
    )

    utils.msg(
        "Cleaning up intermediate datasets..."
    )

    merged_reference_flowlines = os.path.join(
        scratch_gdb,
        "Merged_Reference_Flowlines"
    )

    cleanup_items = [
        trace_fd,
        trace_flowlines,
        bad_start_points,
        headwater_points,
        headwater_points_to_trace,
        lone_end_points,
        lone_end_points_bad,
        merged_reference_flowlines,
        outside_reference_flowlines,
        outside_flowlines,
        valid_flowlines,
        valid_start_points,
        iwub_boundary
    ]

    for item in cleanup_items:
        utils.delete_if_exists(
            item
        )

    utils.msg(
        "Reference line tracing completed."
    )

    return outside_burn_lines

# =============================================================================
# WBD EXPORTS
# =============================================================================

def export_wbd_layer(
        service_url,
        iwub_fc,
        output_fc,
        scratch_gdb):
    """
    Query WBD service using iwub geometry,
    then apply local HAVE_THEIR_CENTER_IN filtering.

    This reproduces ArcGIS Pro's
    'Have Their Center In' behavior while
    minimizing data downloaded from USGS.
    """

    output_name = os.path.basename(
        output_fc
    )

    query_fc = os.path.join(
        scratch_gdb,
        f"qry_{output_name}"
    )

    layer_name = (
        f"{output_name}_lyr"
    )

    utils.msg(
        f"Retrieving {output_name}..."
    )

    utils.delete_if_exists(
        query_fc
    )

    utils.delete_if_exists(
        output_fc
    )

    # -------------------------------------------------------------
    # Build extent-based REST query
    # -------------------------------------------------------------

    desc = arcpy.Describe(iwub_fc)

    wgs84 = arcpy.SpatialReference(4326)

    extent_poly = arcpy.Polygon(
        arcpy.Array([
            arcpy.Point(desc.extent.XMin, desc.extent.YMin),
            arcpy.Point(desc.extent.XMin, desc.extent.YMax),
            arcpy.Point(desc.extent.XMax, desc.extent.YMax),
            arcpy.Point(desc.extent.XMax, desc.extent.YMin)
        ]),
        desc.spatialReference
    )

    extent_poly = extent_poly.projectAs(
        wgs84
    )

    extent = extent_poly.extent

    params = {
        "where": "1=1",
        "geometry": json.dumps(
            {
                "xmin": extent.XMin,
                "ymin": extent.YMin,
                "xmax": extent.XMax,
                "ymax": extent.YMax,
                "spatialReference": {
                    "wkid": 4326
                }
            }
        ),
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "true",
        "outFields": "*",
        "f": "json"
    }

    query_url = (
        f"{service_url}/query?"
        f"{urllib.parse.urlencode(params)}"
    )

    # -------------------------------------------------------------
    # Load query results
    # -------------------------------------------------------------

    fs = arcpy.FeatureSet()

    arcpy.AddMessage(query_url)

    utils.msg("Creating FeatureSet...")

    fs.load(
        query_url
    )

    utils.msg("FeatureSet loaded.")

    arcpy.management.CopyFeatures(
        fs,
        query_fc
    )

    utils.msg("CopyFeatures complete.")

    # -------------------------------------------------------------
    # Apply centroid filtering locally
    # -------------------------------------------------------------

    arcpy.management.MakeFeatureLayer(
        query_fc,
        layer_name
    )

    arcpy.management.SelectLayerByLocation(
        in_layer=layer_name,
        overlap_type="HAVE_THEIR_CENTER_IN",
        select_features=iwub_fc,
        selection_type="NEW_SELECTION"
    )

    arcpy.management.CopyFeatures(
        layer_name,
        output_fc
    )

    # -------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------

    utils.delete_if_exists(
        query_fc
    )

    arcpy.management.Delete(
        layer_name
    )

def export_wbd_lines(
        existing_wbdhu12,
        output_fc,
        scratch_gdb):
    """
    Export WBDLine features corresponding to the
    exported Existing_WBDHU12 polygons.
    """

    wbdhu12_lines = os.path.join(
        scratch_gdb,
        "Existing_WBDHU12_Lines"
    )

    query_fc = os.path.join(
        scratch_gdb,
        "qry_WBDLines"
    )

    layer_name = "wbd_lines_lyr"

    arcpy.management.PolygonToLine(
        existing_wbdhu12,
        wbdhu12_lines
    )

    desc = arcpy.Describe(
        existing_wbdhu12
    )

    query_url = r"https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer/0"

    fs = arcpy.FeatureSet()

    fs.load(
        query_url
    )

    arcpy.management.CopyFeatures(
        fs,
        query_fc
    )

    arcpy.management.MakeFeatureLayer(
        query_fc,
        layer_name
    )

    arcpy.management.SelectLayerByLocation(
        in_layer=layer_name,
        overlap_type="SHARE_A_LINE_SEGMENT_WITH",
        select_features=wbdhu12_lines,
        selection_type="NEW_SELECTION"
    )

    arcpy.management.CopyFeatures(
        layer_name,
        output_fc
    )

    for item in [
        wbdhu12_lines,
        query_fc
    ]:
        utils.delete_if_exists(item)

    arcpy.management.Delete(
        layer_name
    )

# =============================================================================
# EXTRA BURN FEATURES
# =============================================================================

def export_outside_burn_features(
        outside_burn_lines,
        existing_wbdhu12,
        user_workspace,
        scratch_gdb):
    """
    Spatially assign HUC12 values to Outside_Burn_Lines
    and export one shapefile per HUC12 into the
    Extra Burn Features folder.
    """

    utils.msg(
        "Exporting outside burn features..."
    )

    extra_burn_folder = os.path.join(
        user_workspace,
        "02_HRT_Processing",
        "D_Extra_Burn_Features"
    )

    outside_burn_lines_sj = os.path.join(
        scratch_gdb,
        "Outside_Burn_Lines_sj"
    )

    utils.delete_if_exists(
        outside_burn_lines_sj
    )

    # -----------------------------------------------------------------
    # Spatial Join
    # -----------------------------------------------------------------

    arcpy.analysis.SpatialJoin(
        target_features=outside_burn_lines,
        join_features=existing_wbdhu12,
        out_feature_class=outside_burn_lines_sj,
        join_operation="JOIN_ONE_TO_ONE",
        join_type="KEEP_ALL",
        match_option="CLOSEST"
    )

    # -----------------------------------------------------------------
    # Split by HUC12
    # -----------------------------------------------------------------

    arcpy.analysis.SplitByAttributes(
        Input_Table=outside_burn_lines_sj,
        Target_Workspace=extra_burn_folder,
        Split_Fields=["HUC12"]
    )

    # -----------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------

    utils.delete_if_exists(
        outside_burn_lines_sj
    )

    utils.msg(
        "Outside burn features exported."
    )

# =============================================================================
# MAIN
# =============================================================================

def main():

    arcpy.env.overwriteOutput = True

    # -------------------------------------------------------------------------
    # PARAMETERS
    # -------------------------------------------------------------------------

    user_workspace = arcpy.GetParameterAsText(0)
    edh_gdb = arcpy.GetParameterAsText(1)
    iwub_shape = arcpy.GetParameterAsText(2)
    locale = arcpy.GetParameterAsText(3)
    reference_flowlines = arcpy.GetParameterAsText(4)

    # -------------------------------------------------------------------------
    # SPATIAL REFERENCE
    # -------------------------------------------------------------------------

    spatial_reference = (
        utils.get_spatial_reference(
            locale
        )
    )

    arcpy.env.outputCoordinateSystem = (
        spatial_reference
    )

    # -------------------------------------------------------------------------
    # STARTUP
    # -------------------------------------------------------------------------

    utils.separator()

    arcpy.AddMessage(
        "Catchment Toolbox - 00 Initiate Workspace"
    )

    utils.separator()

    utils.msg(
        f"Locale: {locale}"
    )

    # -------------------------------------------------------------------------
    # CREATE WORKSPACE
    # -------------------------------------------------------------------------

    copy_template_structure(
        user_workspace
    )

    create_inputs_gdb(
        user_workspace
    )

    scratch_gdb = create_scratch_gdb(
        user_workspace
    )

    # -------------------------------------------------------------------------
    # COPY EDH GDB
    # -------------------------------------------------------------------------

    edh_name = os.path.basename(
        edh_gdb
    )

    project_edh_gdb = os.path.join(
        utils.get_input_folder(user_workspace),
        edh_name
    )

    copy_edh_gdb(
        edh_gdb,
        project_edh_gdb
    )

    # -------------------------------------------------------------------------
    # DATASET PATHS
    # -------------------------------------------------------------------------

    iwub_fc = utils.get_iwub_fc(
        user_workspace
    )

    huc12_fc = (
        utils.get_huc12_fc(
            user_workspace
        )
    )

    huc10_fc = (
        utils.get_huc10_fc(
            user_workspace
        )
    )

    huc8_fc = (
        utils.get_huc8_fc(
            user_workspace
        )
    )

    wbd_lines_fc = (
        utils.get_wbd_lines_fc(
            user_workspace
        )
    )

    # -------------------------------------------------------------------------
    # IMPORT iwub
    # -------------------------------------------------------------------------

    import_iwub(
        iwub_shape,
        iwub_fc
    )

    # -------------------------------------------------------------------------
    # CREATE OUTSIDE LINES
    # -------------------------------------------------------------------------

    outside_reference_flowlines, headwater_points, lone_end_points = (
        prepare_outside_lines(
            iwub_fc=iwub_fc,
            reference_flowlines=reference_flowlines,
            scratch_gdb=scratch_gdb
        )
    )

    utils.msg(
        "Analyzing exterior flowline network..."
    )

    outside_burn_lines = (
        analyze_reference_lines(
            outside_flowlines=outside_reference_flowlines,
            headwater_points=headwater_points,
            lone_end_points=lone_end_points,
            iwub=iwub_fc,
            scratch_gdb=scratch_gdb
        )
    )

    # -------------------------------------------------------------------------
    # EXPORT HUC12
    # -------------------------------------------------------------------------

    export_wbd_layer(
        service_url=utils.WBD_HU12_URL,
        iwub_fc=iwub_fc,
        output_fc=huc12_fc,
        scratch_gdb=scratch_gdb
    )

    # -------------------------------------------------------------------------
    # EXPORT HUC10
    # -------------------------------------------------------------------------

    export_wbd_layer(
        service_url=utils.WBD_HU10_URL,
        iwub_fc=iwub_fc,
        output_fc=huc10_fc,
        scratch_gdb=scratch_gdb
    )

    # -------------------------------------------------------------------------
    # EXPORT HUC8
    # -------------------------------------------------------------------------

    export_wbd_layer(
        service_url=utils.WBD_HU8_URL,
        iwub_fc=iwub_fc,
        output_fc=huc8_fc,
        scratch_gdb=scratch_gdb
    )

    # -------------------------------------------------------------------------
    # EXPORT WBD_Line
    # -------------------------------------------------------------------------

    export_wbd_layer(
        service_url=utils.WBD_Line_URL,
        iwub_fc=iwub_fc,
        output_fc=wbd_lines_fc,
        scratch_gdb=scratch_gdb
    )

    # -------------------------------------------------------------------------
    # EXPORT EXTRA BURN FEATURES FOR HRT
    # -------------------------------------------------------------------------

    export_outside_burn_features(
        outside_burn_lines=outside_burn_lines,
        existing_wbdhu12=huc12_fc,
        user_workspace=user_workspace,
        scratch_gdb=scratch_gdb
    )

    # -------------------------------------------------------------------------
    # COMPLETE
    # -------------------------------------------------------------------------

    utils.separator()

    arcpy.AddMessage(
        "Workspace initialization completed successfully."
    )

    utils.separator()


if __name__ == "__main__":
    main()