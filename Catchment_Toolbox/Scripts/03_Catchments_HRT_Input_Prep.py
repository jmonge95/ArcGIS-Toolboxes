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

arcpy.env.parallelProcessingFactor = "100%"


# =============================================================================
# HELPERS
# =============================================================================

def delete_if_empty(fc):
    """
    Delete a feature class if it exists
    and contains zero features.

    Returns:
        True  = dataset deleted
        False = dataset retained
    """

    if not arcpy.Exists(fc):
        return False

    count = int(
        arcpy.management.GetCount(
            fc
        ).getOutput(0)
    )

    if count == 0:

        arcpy.management.Delete(
            fc
        )

        return True

    return False

# =============================================================================
# WATERBODIES
# =============================================================================

def export_waterbodies(
        polygons_fc,
        lake_master,
        river_master,
        hu12_geom,
        huc12,
        output_folder,
        scratch_gdb):
    """
    Export HU12 waterbodies.

    Lake/Pond (FCode 39000):
        Select by center-in-HU12.

    Stream/River (FCode 46000):
        Clip to a 1005-meter HU12 buffer.
    """

    # utils.msg(
    #     f"Creating waterbodies for {huc12}..."
    # )

    output_fc = os.path.join(
        output_folder,
        f"{huc12}.shp"
    )

    lake_fc = os.path.join(
        scratch_gdb,
        f"lake_fc_{huc12}"
    )

    river_clip = os.path.join(
        scratch_gdb,
        f"river_clip_{huc12}"
    )

    hu12_buffer = os.path.join(
        scratch_gdb,
        f"hu12_buffer_{huc12}"
    )

    scratch_items = [
        lake_fc,
        river_clip,
        hu12_buffer
    ]

    try:

        utils.delete_if_exists(
            output_fc
        )

        for item in scratch_items:
            utils.delete_if_exists(item)

        # -----------------------------------------------------
        # Lakes / Ponds (FCode = 39000)
        # -----------------------------------------------------

        arcpy.management.SelectLayerByLocation(
            lake_master,
            "HAVE_THEIR_CENTER_IN",
            hu12_geom,
            selection_type="NEW_SELECTION"
        )

        lake_count = int(
            arcpy.management.GetCount(
                lake_master
            ).getOutput(0)
        )

        if lake_count > 0:

            arcpy.management.CopyFeatures(
                lake_master,
                lake_fc
            )

        # -----------------------------------------------------
        # River / Stream Polygons (FCode = 46000)
        # -----------------------------------------------------

        arcpy.analysis.Buffer(
            hu12_geom,
            hu12_buffer,
            "1005 Meters",
            dissolve_option="ALL"
        )

        arcpy.management.SelectLayerByLocation(
            river_master,
            "INTERSECT",
            hu12_buffer,
            selection_type="NEW_SELECTION"
        )

        river_count = int(
            arcpy.management.GetCount(
                river_master
            ).getOutput(0)
        )

        if river_count > 0:

            arcpy.analysis.Clip(
                river_master,
                hu12_buffer,
                river_clip
            )

        # -----------------------------------------------------
        # Build output
        # -----------------------------------------------------

        inputs = []

        if arcpy.Exists(lake_fc):

            if int(
                    arcpy.management.GetCount(
                        lake_fc
                    ).getOutput(0)
            ) > 0:

                inputs.append(
                    lake_fc
                )

        if arcpy.Exists(river_clip):

            if int(
                    arcpy.management.GetCount(
                        river_clip
                    ).getOutput(0)
            ) > 0:

                inputs.append(
                    river_clip
                )

        if len(inputs) > 0:

            arcpy.management.Merge(
                inputs,
                output_fc
            )

        else:

            arcpy.management.CreateFeatureclass(
                output_folder,
                f"{huc12}.shp",
                "POLYGON",
                polygons_fc
            )

        # -----------------------------------------------------
        # Delete empty outputs
        # -----------------------------------------------------

        if delete_if_empty(
                output_fc
        ):

            # utils.msg(
            #     f"Deleted empty waterbody "
            #     f"file for {huc12}"
            # )

            return

        # -----------------------------------------------------
        # Normalize FCode
        # -----------------------------------------------------

        if "FCode" in [
            f.name
            for f in arcpy.ListFields(
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

    finally:

        for item in scratch_items:

            utils.delete_if_exists(
                item
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

    # utils.msg(
    #     f"Creating streams for {huc12}..."
    # )

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

    arcpy.management.Merge(
        [
            temp_subnetwork,
            hu_network_fc
        ],
        output_fc
    )

    # ---------------------------------------------------------
    # Delete empty output
    # ---------------------------------------------------------

    if delete_if_empty(output_fc):
        utils.msg(
            f"Deleted empty stream file for {huc12}"
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

        return

    arcpy.management.Delete(
        temp_subnetwork
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
        ExtractByMask from the Work Unit DEM.

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

        from arcpy.sa import ExtractByMask

        arcpy.management.MakeFeatureLayer(
            existing_wbdhu12,
            "hu12_lyr"
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

        for huc12, in arcpy.da.SearchCursor(
                existing_wbdhu12,
                ["HUC12"]):

            huc12_name = str(
                huc12
            ).strip()

            try:

                # utils.msg(
                #     f"Creating DEM: "
                #     f"{huc12_name}.tif"
                # )

                flowlines_fc = os.path.join(
                    utils.get_flowlines_by_huc_gdb(
                        user_workspace
                    ),
                    f"HU_{huc12_name}"
                )

                if not arcpy.Exists(
                        flowlines_fc):

                    utils.warn(
                        f"Missing flowlines: "
                        f"HU_{huc12_name}"
                    )

                    continue

                count = int(
                    arcpy.management.GetCount(
                        flowlines_fc
                    ).getOutput(0)
                )

                if count == 0:

                    utils.warn(
                        f"Empty flowlines: "
                        f"HU_{huc12_name}"
                    )

                    continue

                where_clause = (
                    f"HUC12 = '{huc12_name}'"
                )

                arcpy.management.SelectLayerByAttribute(
                    "hu12_lyr",
                    "NEW_SELECTION",
                    where_clause
                )

                arcpy.management.CopyFeatures(
                    "hu12_lyr",
                    hu12_fc
                )

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

                out_raster = ExtractByMask(
                    work_unit_dem,
                    final_mask_fc
                )

                out_raster.save(
                    out_tif
                )

            except Exception as ex:

                utils.warn(
                    f"DEM failed for "
                    f"{huc12_name}: {ex}"
                )

            finally:

                for item in [
                    hu12_fc,
                    hull_fc,
                    hull_fc_buff,
                    hu12_fc_buff,
                    merged_mask_fc,
                    final_mask_fc
                ]:
                    utils.delete_if_exists(
                        item
                    )

        if arcpy.Exists(
                "hu12_lyr"):

            arcpy.management.Delete(
                "hu12_lyr"
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
# REBUILD HU12 NETWORKS
# =============================================================================

def rebuild_hu12_networks(
        merged_flowlines_fc,
        flowlines_gdb):
    """
    Rebuild individual HU_{huc12} feature classes
    from MERGED_Flowlines_by_HU12.

    Allows analysts to perform QC edits on the
    merged feature class and propagate those edits
    throughout downstream processing.
    """

    utils.msg(
        "Rebuilding HU12 networks from "
        "MERGED_Flowlines_by_HU12..."
    )

    huc12_values = sorted({

        str(row[0]).strip()

        for row in arcpy.da.SearchCursor(
            merged_flowlines_fc,
            ["HUC12"]
        )

        if row[0]
    })

    arcpy.management.MakeFeatureLayer(
        merged_flowlines_fc,
        "merged_lyr"
    )

    for huc12 in huc12_values:

        output_fc = os.path.join(
            flowlines_gdb,
            f"HU_{huc12}"
        )

        where_clause = (
            f"HUC12 = '{huc12}'"
        )

        utils.delete_if_exists(
            output_fc
        )

        arcpy.management.SelectLayerByAttribute(
            "merged_lyr",
            "NEW_SELECTION",
            where_clause
        )

        arcpy.management.CopyFeatures(
            "merged_lyr",
            output_fc
        )

        # arcpy.analysis.Select(
        #     merged_flowlines_fc,
        #     output_fc,
        #     where_clause
        # )

        # count = int(
        #     arcpy.management.GetCount(
        #         output_fc
        #     ).getOutput(0)
        # )

        # utils.msg(
        #     f"Rebuilt HU_{huc12} "
        #     f"({count:,} features)"
        # )

    utils.msg(
        "HU12 network rebuild complete."
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

    utils.separator()

    utils.msg(
        "Catchment Toolbox - "
        "03 Prepare HRT Inputs"
    )

    utils.separator()

    rebuild_hu12_networks(
        merged_flowlines_fc,
        flowlines_gdb
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

    arcpy.management.MakeFeatureLayer(
        polygons_fc,
        "lake_master",
        "FCode = 39000"
    )

    arcpy.management.MakeFeatureLayer(
        polygons_fc,
        "river_master",
        "FCode = 46000"
    )

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
                "lake_master",
                "river_master",
                hu12_geom,
                huc12,
                waterbodies_folder,
                scratch_gdb
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
