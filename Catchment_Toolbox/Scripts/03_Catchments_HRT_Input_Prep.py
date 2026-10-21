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
import shutil

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
        "1005 Meters",
        "ADD_TO_SELECTION"
    )

    arcpy.management.SelectLayerByLocation(
        "flowlines_lyr",
        "WITHIN_A_DISTANCE",
        hu12_geom,
        "1005 Meters",
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
# HU12 DEMS
# =============================================================================

def create_hu12_dem_rasters(
        locale,
        flowlines_by_huc,
        existing_wbdhu12,
        user_workspace,
        scratch_gdb,
        work_unit_dem=None,
        hu12_dem_folder=None):
    """
    Populate the A_DEMs folder.

    AK:
        Build a convex hull around each HUC12's
        flowlines, buffer 1005 meters, then
        Extract By Mask from the Work Unit DEM.

    CONUS:
        Copy matching HUC12 DEMs from a DEM folder.
    """

    utils.msg(
        "Creating HU12 DEM Rasters..."
    )

    dem_folder = os.path.join(
        user_workspace,
        "02_HRT_Processing",
        "A_DEMs"
    )

    # ---------------------------------------------------------------------
    # AK
    # ---------------------------------------------------------------------

    if locale.upper() == "AK":

        oid_field = arcpy.Describe(
            existing_wbdhu12
        ).OIDFieldName

        for huc12, in arcpy.da.SearchCursor(
                existing_wbdhu12,
                ["HUC12"]
        ):

            huc12_name = str(
                huc12
            ).strip()

            where_clause = (
                f"HUC12 = '{huc12_name}'"
            )

            flowlines_fc = os.path.join(
                scratch_gdb,
                "HU12_Flowlines"
            )

            hu12_fc = os.path.join(
                scratch_gdb,
                "HU12_Polygon"
            )

            hull_fc = os.path.join(
                scratch_gdb,
                "HU12_Hull"
            )

            hull_fc_buff = os.path.join(
                scratch_gdb,
                "HU12_Hull_Buff"
            )

            hu12_fc_buff = os.path.join(
                scratch_gdb,
                "HU12_Polygon_Buff"
            )

            merged_mask_fc = os.path.join(
                scratch_gdb,
                "HU12_Mask_Merge"
            )

            final_mask_fc = os.path.join(
                scratch_gdb,
                "HU12_Mask"
            )

            for item in [
                flowlines_fc,
                hu12_fc,
                hull_fc,
                hull_fc_buff,
                hu12_fc_buff,
                merged_mask_fc,
                final_mask_fc
            ]:
                utils.delete_if_exists(item)

            arcpy.analysis.Select(
                flowlines_by_huc,
                flowlines_fc,
                where_clause
            )

            arcpy.analysis.Select(
                existing_wbdhu12,
                hu12_fc,
                where_clause
            )

            count = int(
                arcpy.management.GetCount(
                    flowlines_fc
                ).getOutput(0)
            )

            if count == 0:
                continue

            arcpy.management.MinimumBoundingGeometry(
                flowlines_fc,
                hull_fc,
                "CONVEX_HULL",
                group_option="ALL"
            )

            arcpy.analysis.Buffer(
                hull_fc,
                hull_fc_buff,
                "1005 Meters",
                dissolve_option="ALL"
            )

            arcpy.analysis.Buffer(
                hu12_fc,
                hu12_fc_buff,
                "1005 Meters",
                dissolve_option="ALL"
            )

            arcpy.management.Merge(
                [
                    hull_fc_buff,
                    hu12_fc_buff
                ],
                merged_mask_fc
            )

            arcpy.management.Dissolve(
                merged_mask_fc,
                final_mask_fc
            )

            out_tif = os.path.join(
                dem_folder,
                f"{huc12_name}.tif"
            )

            from arcpy.sa import ExtractByMask

            with arcpy.EnvManager(
                    scratchWorkspace=dem_folder):

                out_raster = ExtractByMask(
                    in_raster=work_unit_dem,
                    in_mask_data=final_mask_fc,
                    extraction_area="INSIDE"
                )

                out_raster.save(
                    out_tif
                )

        flowlines_fc = os.path.join(
            scratch_gdb,
            "HU12_Flowlines"
        )

        hull_fc = os.path.join(
            scratch_gdb,
            "HU12_Hull"
        )

        buffer_fc = os.path.join(
            scratch_gdb,
            "HU12_Buffer"
        )

        flowlines_fc = os.path.join(
            scratch_gdb,
            "HU12_Flowlines"
        )

        hu12_fc = os.path.join(
            scratch_gdb,
            "HU12_Polygon"
        )

        hull_fc_buff = os.path.join(
            scratch_gdb,
            "HU12_Hull_Buff"
        )

        hu12_fc_buff = os.path.join(
            scratch_gdb,
            "HU12_Polygon_Buff"
        )

        merged_mask_fc = os.path.join(
            scratch_gdb,
            "HU12_Mask_Merge"
        )

        final_mask_fc = os.path.join(
            scratch_gdb,
            "HU12_Mask"
        )

        for huc12, in arcpy.da.SearchCursor(
                existing_wbdhu12,
                ["HUC12"]
        ):

            for item in [
                flowlines_fc,
                hu12_fc,
                hull_fc,
                hull_fc_buff,
                merged_mask_fc,
                final_mask_fc
            ]:
                utils.delete_if_exists(
                    item
                )

    # ---------------------------------------------------------------------
    # CONUS
    # ---------------------------------------------------------------------

    elif locale.upper() == "CONUS":

        huc12_values = set()

        with arcpy.da.SearchCursor(
                existing_wbdhu12,
                ["HUC12"]
        ) as rows:

            for (huc12,) in rows:

                huc12_values.add(
                    str(huc12).strip()
                )

        for file_name in os.listdir(
                hu12_dem_folder
        ):

            if not file_name.lower().endswith(
                    ".tif"
            ):
                continue

            stem = os.path.splitext(
                file_name
            )[0]

            if stem in huc12_values:

                shutil.copy2(
                    os.path.join(
                        hu12_dem_folder,
                        file_name
                    ),
                    os.path.join(
                        dem_folder,
                        file_name
                    )
                )

    utils.msg(
        "HU12 DEM raster creation complete."
    )


# =============================================================================
# MAIN
# =============================================================================

def main():

    user_workspace = (
        arcpy.GetParameterAsText(0)
    )
    locale = arcpy.GetParameterAsText(1)
    work_unit_dem = arcpy.Describe(
        arcpy.GetParameterAsText(2)
    ).catalogPath
    hu12_dem_folder = arcpy.GetParameterAsText(3)


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

    scratch_gdb = utils.get_scratch_gdb(
        user_workspace
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

    create_hu12_dem_rasters(
        locale=locale,
        flowlines_by_huc=merged_flowlines_fc,
        existing_wbdhu12=huc12_fc,
        user_workspace=user_workspace,
        scratch_gdb=scratch_gdb,
        work_unit_dem=work_unit_dem,
        hu12_dem_folder=hu12_dem_folder
    )

    utils.separator()

    arcpy.AddMessage("HRT input preparation complete.")

    utils.separator()


if __name__ == "__main__":
    main()
