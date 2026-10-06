"""
00_Initiate_Workspace.py

Catchment Toolbox

Purpose:
    Initializes a new catchment delineation workspace.

Parameters:
    0 - User Workspace (Folder)
    1 - DPA Shape (Polygon Feature Layer)
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
# DPA
# =============================================================================

def import_dpa(
        dpa_input,
        dpa_output):
    """
    Import DPA using project CRS environment.
    """

    utils.delete_if_exists(
        dpa_output
    )

    arcpy.management.CopyFeatures(
        dpa_input,
        dpa_output
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

def prepare_outside_lines(
        dpa_fc,
        reference_flowlines,
        scratch_gdb):
    """
    Creates a 1000 m exterior ring around the DPA and
    extracts reference flowlines falling within that ring.

    Returns:
        Outside_Reference_Flowlines feature class
    """

    # -------------------------------------------------------------------------
    # Paths
    # -------------------------------------------------------------------------

    dpa_buffer = os.path.join(
        scratch_gdb,
        "DPA_Buffer_1000m"
    )

    dpa_ring = os.path.join(
        scratch_gdb,
        "DPA_Ring_1000m"
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
        dpa_buffer
    )

    utils.delete_if_exists(
        dpa_ring
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
    # Create 1000 m DPA buffer
    # -------------------------------------------------------------------------

    arcpy.analysis.Buffer(
        in_features=dpa_fc,
        out_feature_class=dpa_buffer,
        buffer_distance_or_field="1000 Meters",
        dissolve_option="ALL",
        method="PLANAR"
    )

    # -------------------------------------------------------------------------
    # Remove original DPA to create ring
    # -------------------------------------------------------------------------

    arcpy.analysis.Erase(
        in_features=dpa_buffer,
        erase_features=dpa_fc,
        out_feature_class=dpa_ring
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
    # Clip flowlines to DPA ring
    # -------------------------------------------------------------------------

    arcpy.analysis.Clip(
        in_features=merged_flowlines,
        clip_features=dpa_ring,
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

    return (
        outside_flowlines_sp,
        headwater_points
    )


# =============================================================================
# WBD EXPORTS
# =============================================================================

def export_wbd_layer(
        service_url,
        dpa_fc,
        output_fc,
        scratch_gdb):
    """
    Query WBD service using DPA geometry,
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

    desc = arcpy.Describe(dpa_fc)

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

    utils.msg(query_url)

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
        select_features=dpa_fc,
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
    dpa_shape = arcpy.GetParameterAsText(2)
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

    dpa_fc = utils.get_dpa_fc(
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

    # -------------------------------------------------------------------------
    # IMPORT DPA
    # -------------------------------------------------------------------------

    import_dpa(
        dpa_shape,
        dpa_fc
    )

    # -------------------------------------------------------------------------
    # CREATE OUTSIDE LINES
    # -------------------------------------------------------------------------

    outside_reference_flowlines, headwater_points = (
        prepare_outside_lines(
            dpa_fc=dpa_fc,
            reference_flowlines=reference_flowlines,
            scratch_gdb=scratch_gdb
        )
    )

    # -------------------------------------------------------------------------
    # EXPORT HUC12
    # -------------------------------------------------------------------------

    export_wbd_layer(
        service_url=utils.WBD_HU12_URL,
        dpa_fc=dpa_fc,
        output_fc=huc12_fc,
        scratch_gdb=scratch_gdb
    )

    # -------------------------------------------------------------------------
    # EXPORT HUC10
    # -------------------------------------------------------------------------

    export_wbd_layer(
        service_url=utils.WBD_HU10_URL,
        dpa_fc=dpa_fc,
        output_fc=huc10_fc,
        scratch_gdb=scratch_gdb
    )

    # -------------------------------------------------------------------------
    # EXPORT HUC8
    # -------------------------------------------------------------------------

    export_wbd_layer(
        service_url=utils.WBD_HU8_URL,
        dpa_fc=dpa_fc,
        output_fc=huc8_fc,
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