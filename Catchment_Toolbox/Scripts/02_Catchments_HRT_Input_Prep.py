import arcpy
import os
import timeit

arcpy.env.overwriteOutput = True

"""

This script prepares HU12-specific waterbody and flowline datasets
for HRT processing.

Waterbodies:
    - Select all polygon features whose center falls within the HU12.
    - Convert FCode 43600 to 39000.
    - Export to 02_HRT_Inputs\\Waterbodies.

Flowlines:
    - Select subnetworks near HU12 start and stop points.
    - Add flowlines within 250 meters of the HU12 boundary.
    - Retain selected flowlines within 500 meters of the HU12 boundary.
    - Remove flowlines identical to the HU12 network.
    - Merge subnetworks with the HU12 network.
    - Export to 02_HRT_Inputs\\Streams.

"""

""" BEGIN CHANGING INPUTS """

HUshp = r"W:\2025_MA_Narragansett_D25_H\18_WBD\catchment\00_EDH_Inputs\MA_Narragansett_D25_H_HU12s.shp"
fieldlist = ["HUC12"]
edh_gdb = r"W:\2025_MA_Narragansett_D25_H\18_WBD\catchment\00_EDH_Inputs\301183_edh.gdb"
working_directory = r"W:\2025_MA_Narragansett_D25_H\18_WBD\catchment"

""" END CHANGING INPUTS """

# --------------------------------------------------------------------------
# START TIMER
# --------------------------------------------------------------------------

overall_start = timeit.default_timer()

# --------------------------------------------------------------------------
# PROCESS EACH HU12
# --------------------------------------------------------------------------

with arcpy.da.SearchCursor(HUshp, fieldlist + ["SHAPE@"]) as cursor:

    for row in cursor:

        HUnum = row[0]
        hu12_shape = row[1]

        print(f"Starting {HUnum}...")

        # ------------------------------------------------------------------
        # PREPARE WATERBODIES
        # ------------------------------------------------------------------

        print(f"        Selecting waterbodies within {HUnum}...")

        polygons_layer = "Polygons_Layer"

        arcpy.MakeFeatureLayer_management(
            os.path.join(edh_gdb, "Polygons"),
            polygons_layer
        )

        arcpy.SelectLayerByLocation_management(
            polygons_layer,
            "HAVE_THEIR_CENTER_IN",
            hu12_shape
        )

        output_waterbodies = os.path.join(
            working_directory,
            "02_HRT_Inputs",
            "Waterbodies",
            f"{HUnum}.shp"
        )

        arcpy.CopyFeatures_management(
            polygons_layer,
            output_waterbodies
        )

        # Convert reservoirs (43600) to lakes (39000)
        with arcpy.da.UpdateCursor(output_waterbodies, ["FCode"]) as update_cursor:
            for update_row in update_cursor:

                if update_row[0] == 43600:
                    update_row[0] = 39000
                    update_cursor.updateRow(update_row)

        print(f"        Waterbodies completed for {HUnum}...")

        # ------------------------------------------------------------------
        # PREPARE FLOWLINES
        # ------------------------------------------------------------------

        print(f"        Prepping {HUnum} flowlines for HRT processing...")

        flowlines_layer = "Flowlines_Layer"

        flowlines_shp = os.path.join(
            working_directory,
            "01_Generate_PourPoints",
            "02_Attribution",
            "OUTPUT_Flowlines_by_HU12.shp"
        )

        arcpy.MakeFeatureLayer_management(
            flowlines_shp,
            flowlines_layer
        )

        # Select subnetworks near HU12 start points
        start_shp = os.path.join(
            working_directory,
            "01_Generate_PourPoints",
            "02_Attribution",
            "01_Starts",
            f"{HUnum}.shp"
        )

        arcpy.SelectLayerByLocation_management(
            flowlines_layer,
            "WITHIN_A_DISTANCE",
            start_shp,
            "500 Meters"
        )

        # Add subnetworks near HU12 stop points
        stop_shp = os.path.join(
            working_directory,
            "01_Generate_PourPoints",
            "02_Attribution",
            "02_Stops",
            f"{HUnum}.shp"
        )

        arcpy.SelectLayerByLocation_management(
            flowlines_layer,
            "WITHIN_A_DISTANCE",
            stop_shp,
            "500 Meters",
            "ADD_TO_SELECTION"
        )

        # HU12 stream network
        lines_by_HU_shp = os.path.join(
            working_directory,
            "01_Generate_PourPoints",
            "02_Attribution",
            "03_lines_by_HU",
            f"{HUnum}.shp"
        )

        # Add all flowlines within 250 m of the HU12 boundary
        arcpy.SelectLayerByLocation_management(
            flowlines_layer,
            "WITHIN_A_DISTANCE",
            hu12_shape,
            "250 Meters",
            "ADD_TO_SELECTION"
        )

        # Retain selected flowlines within 500 m of the HU12 boundary
        arcpy.SelectLayerByLocation_management(
            flowlines_layer,
            "WITHIN_A_DISTANCE",
            hu12_shape,
            "500 Meters",
            "SUBSET_SELECTION"
        )

        # Remove flowlines already present in the HU12 network
        arcpy.SelectLayerByLocation_management(
            flowlines_layer,
            "ARE_IDENTICAL_TO",
            lines_by_HU_shp,
            selection_type="REMOVE_FROM_SELECTION"
        )

        # Merge subnetworks with the HU12 network
        output_flowlines = os.path.join(
            working_directory,
            "02_HRT_Inputs",
            "Streams",
            f"{HUnum}.shp"
        )

        arcpy.Merge_management(
            [
                flowlines_layer,
                lines_by_HU_shp
            ],
            output_flowlines
        )

        print(f"        Streams completed for {HUnum}...")

        # ------------------------------------------------------------------
        # CLEANUP
        # ------------------------------------------------------------------

        if arcpy.Exists(polygons_layer):
            arcpy.Delete_management(polygons_layer)

        if arcpy.Exists(flowlines_layer):
            arcpy.Delete_management(flowlines_layer)

# --------------------------------------------------------------------------
# FINISHED
# --------------------------------------------------------------------------

overall_end = timeit.default_timer()
total_minutes = (overall_end - overall_start) / 60

print(f"HRT Data Preparation completed in {total_minutes:.2f} minutes")
