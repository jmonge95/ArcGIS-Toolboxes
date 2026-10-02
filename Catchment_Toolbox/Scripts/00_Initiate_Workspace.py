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

    extent = desc.extent

    params = {
        "where": "1=1",
        "geometry": json.dumps(
            {
                "xmin": extent.XMin,
                "ymin": extent.YMin,
                "xmax": extent.XMax,
                "ymax": extent.YMax,
                "spatialReference": {
                    "wkid": desc.spatialReference.factoryCode
                }
            }
        ),
        "geometryType": "esriGeometryEnvelope",
        "inSR": desc.spatialReference.factoryCode,
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

    fs.load(
        query_url
    )

    arcpy.management.CopyFeatures(
        fs,
        query_fc
    )

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

    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------

    validate_edh_gdb(
        edh_gdb
    )

    desc = arcpy.Describe(
        dpa_shape
    )

    if desc.shapeType != "Polygon":

        raise ValueError(
            "DPA Shape must be polygon geometry."
        )

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

    utils.msg(
        "Catchment Toolbox - 00 Initiate Workspace"
    )

    utils.separator()

    utils.msg(
        f"Locale: {locale}"
    )

    utils.msg(
        f"Output WKID: "
        f"{spatial_reference.factoryCode}"
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

    project_edh_gdb = utils.get_edh_gdb(
        user_workspace
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

    utils.msg(
        "Workspace initialization completed successfully."
    )

    utils.separator()


if __name__ == "__main__":
    main()