"""
03_Prepare_HRT_Inputs.py

Catchment Toolbox

Purpose:
    Prepare HU12-specific stream and waterbody
    datasets for HRT processing.
"""

import os
import arcpy
import catchment_utils as utils

arcpy.env.overwriteOutput = True


# =============================================================================
# WATERBODIES
# =============================================================================

def export_waterbodies(
        polygons_fc,
        hu12_geom,
        huc12,
        output_folder):
    """
    Export HU12 waterbodies.
    """

    utils.msg(
        f"Creating waterbodies for {huc12}..."
    )

    output_fc = os.path.join(
        output_folder,
        f"{huc12}.shp"
    )

    utils.delete_if_exists(
        output_fc
    )

    arcpy.management.MakeFeatureLayer(
        polygons_fc,
        "polygons_lyr"
    )

    arcpy.management.SelectLayerByLocation(
        "polygons_lyr",
        "HAVE_THEIR_CENTER_IN",
        hu12_geom
    )

    arcpy.management.CopyFeatures(
        "polygons_lyr",
        output_fc
    )

    if "FCode" in [
            f.name for f in arcpy.ListFields(
                output_fc
            )
    ]:

        with arcpy.da.UpdateCursor(
                output_fc,
                ["FCode"]
        ) as cursor:

            for row in cursor:

                if row[0] == 43600:

                    row[0] = 39000

                    cursor.updateRow(
                        row
                    )

    arcpy.management.Delete(
        "polygons_lyr"
    )


# =============================================================================
# STREAMS
# =============================================================================

def export_streams(
        merged_flowlines_fc,
        hu_network_fc,
        pourpoints_fc,
        hu12_geom,
        huc12,
        output_folder):
    """
    Export HU12 stream network and
    connected subnetworks.
    """

    utils.msg(
        f"Creating streams for {huc12}..."
    )

    output_fc = os.path.join(
        output_folder,
        f"{huc12}.shp"
    )

    utils.delete_if_exists(
        output_fc
    )

    arcpy.management.MakeFeatureLayer(
        merged_flowlines_fc,
        "flowlines_lyr"
    )

    huc_field = arcpy.AddFieldDelimiters(
        pourpoints_fc,
        "HUC12"
    )

    start_sql = (
        f"{huc_field} = '{huc12}'"
    )

    stop_sql = (
        f"{huc_field} <> '{huc12}'"
    )

    arcpy.management.MakeFeatureLayer(
        pourpoints_fc,
        "start_pts",
        start_sql
    )

    arcpy.management.MakeFeatureLayer(
        pourpoints_fc,
        "stop_pts",
        stop_sql
    )

    # ---------------------------------------------------------
    # Select nearby subnetworks
    # ---------------------------------------------------------

    arcpy.management.SelectLayerByLocation(
        "flowlines_lyr",
        "WITHIN_A_DISTANCE",
        "start_pts",
        "1005 Meters"
    )

    arcpy.management.SelectLayerByLocation(
        "flowlines_lyr",
        "WITHIN_A_DISTANCE",
        "stop_pts",
        "1005 Meters",
        "ADD_TO_SELECTION"
    )

    # ---------------------------------------------------------
    # Add lines near HU boundary
    # ---------------------------------------------------------

    arcpy.management.SelectLayerByLocation(
        "flowlines_lyr",
        "WITHIN_A_DISTANCE",
        hu12_geom,
        "250 Meters",
        "ADD_TO_SELECTION"
    )

    arcpy.management.SelectLayerByLocation(
        "flowlines_lyr",
        "WITHIN_A_DISTANCE",
        hu12_geom,
        "500 Meters",
        "SUBSET_SELECTION"
    )

    # ---------------------------------------------------------
    # Remove lines already in HU network
    # ---------------------------------------------------------

    arcpy.management.SelectLayerByLocation(
        "flowlines_lyr",
        "ARE_IDENTICAL_TO",
        hu_network_fc,
        selection_type="REMOVE_FROM_SELECTION"
    )

    # ---------------------------------------------------------
    # Merge subnetworks + HU network
    # ---------------------------------------------------------

    temp_subnetwork = "temp_subnetwork"

    utils.delete_if_exists(
        temp_subnetwork
    )

    arcpy.management.CopyFeatures(
        "flowlines_lyr",
        temp_subnetwork
    )

    arcpy.management.Merge(
        [
            temp_subnetwork,
            hu_network_fc
        ],
        output_fc
    )

    arcpy.management.Delete(
        temp_subnetwork
    )

    arcpy.management.Delete(
        "flowlines_lyr"
    )

    arcpy.management.Delete(
        "start_pts"
    )

    arcpy.management.Delete(
        "stop_pts"
    )


# =============================================================================
# MAIN
# =============================================================================

def main():

    user_workspace = (
        arcpy.GetParameterAsText(0)
    )

    polygons_fc = (
        utils.get_edh_polygons(
            user_workspace
        )
    )

    huc12_fc = (
        utils.get_huc12_fc(
            user_workspace
        )
    )

    pourpoints_fc = (
        utils.get_pourpoints_fc(
            user_workspace
        )
    )

    flowlines_gdb = (
        utils.get_flowlines_by_huc_gdb(
            user_workspace
        )
    )

    merged_flowlines_fc = os.path.join(
        flowlines_gdb,
        "MERGED_Flowlines_by_HU12"
    )

    streams_folder = (
        utils.get_streams_folder(
            user_workspace
        )
    )

    waterbodies_folder = (
        utils.get_waterbodies_folder(
            user_workspace
        )
    )

    utils.separator()

    utils.msg(
        "Catchment Toolbox - "
        "03 Prepare HRT Inputs"
    )

    utils.separator()

    with arcpy.da.SearchCursor(
            huc12_fc,
            ["HUC12", "SHAPE@"]
    ) as cursor:

        for huc12, hu12_geom in cursor:

            hu_network_fc = os.path.join(
                flowlines_gdb,
                f"HU_{huc12}"
            )

            if not arcpy.Exists(
                    hu_network_fc
            ):

                utils.warn(
                    f"Missing HU network: "
                    f"{huc12}"
                )

                continue

            export_waterbodies(
                polygons_fc,
                hu12_geom,
                huc12,
                waterbodies_folder
            )

            export_streams(
                merged_flowlines_fc,
                hu_network_fc,
                pourpoints_fc,
                hu12_geom,
                huc12,
                streams_folder
            )

    utils.separator()

    arcpy.AddMessage("HRT input preparation complete.")

    utils.separator()


if __name__ == "__main__":
    main()
