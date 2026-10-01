import arcpy
import os
import csv
import timeit

arcpy.env.overwriteOutput = True

"""

Catchment Cleanup Workflow

For each HU12:


1. Copy {HUC12}_final_basins.shp from:
      02_HRT_Inputs\\Outputs
   to:
      03_Catchment_Cleanup\\{HUC12}_final_basins_cleaned.shp

2. Copy {HUC12}_prepped_streams.shp from:
      02_HRT_Inputs\\Outputs
   to:
      03_Catchment_Cleanup\\{HUC12}_prepped_streams_temp.shp

3. Spatially join the copied planarized streams to:
      OUTPUT_Flowlines_by_HU12.shp
   using:
      SHARE_A_LINE_SEGMENT_WITH

   Output:
      {HUC12}_prepped_streams_join.shp

   This transfers HUC12 ownership from the attributed flowline network to the planarized stream network.

4. Join the HUC12 field from:
      {HUC12}_prepped_streams_join.shp
   back to
      {HUC12}_final_basins_cleaned.shp
   using the SID field.

   Join:
      final_basins_cleaned.sid
         =
      prepped_streams_join.sid

5. Identify catchments that did not receive a HUC12 value through the SID join process (typically SID = -888 catchments).

6. Build stream-network ownership groups:

      • Primary HU12 network:
        03_lines_by_HU\\{HUC12}.shp
      • Neighboring subnetworks:
        Features within
        {HUC12}_prepped_streams_join.shp
        whose HUC12 differs from the current HU12.

7. For each catchment with a blank HUC12:

      a. Calculate the centroid of the catchment polygon.
      b. Measure the distance from the centroid to the primary HU12 stream network.
      c. Measure the distance from the centroid to each neighboring subnetwork.
      d. Identify the nearest subnetwork and its associated HUC12.
      e. Assign ownership based on the closest stream network:
            • MAIN
                Assign current HU12
            • SUBNETWORK
                Assign the HUC12 of the nearest subnetwork
            • AMBIGUOUS
                Distances fall within the ambiguity threshold and require QA review

8. Export QA datasets:

      • DistanceAssigned.shp
          Catchments assigned through the distance-based ownership method.
      • AmbiguousCatchments.shp
          Catchments whose ownership could not be confidently determined.
      • RemovedCatchments.shp
          Catchments assigned to neighboring subnetworks and scheduled for removal.

9. Remove catchments whose assigned HUC12 does not match the current HU12.

      • Catchments flagged as AMBIGUOUS are retained for manual review and are not automatically removed.

10. Delete temporary processing datasets:

      • {HUC12}_prepped_streams_temp.shp

    Retain:

      • {HUC12}_prepped_streams_join.shp

    for QA, auditing, and troubleshooting.

11. Record processing statistics and write:

      • Cleanup_Summary.csv
      • Missing_Files.csv

12. Output the final cleaned catchment dataset:

      03_Catchment_Cleanup\\{HUC12}_final_basins_cleaned.shp

    containing only catchments associated with the primary HU12 stream network.


"""

""" Begin CHANGING INPUTS """

working_directory = r"W:\2025_MA_Narragansett_D25_H\18_WBD\catchment"
HUshp = r"W:\2025_MA_Narragansett_D25_H\18_WBD\catchment\00_EDH_Inputs\MA_Narragansett_D25_H_HU12s.shp"
fieldlist = ["HUC12"]

""" END CHANGING INPUTS """

flowlines_by_hu = os.path.join(
    working_directory,
    "01_Generate_PourPoints",
    "02_Attribution",
    "OUTPUT_Flowlines_by_HU12.shp"
)

output_folder = r"W:\2025_MA_Narragansett_D25_H\18_WBD\catchment\z_old\Outputs_new"


cleanup_folder = r"W:\2025_MA_Narragansett_D25_H\18_WBD\catchment\z_old\Outputs_new\cleanup"

qa_folder = os.path.join(
    cleanup_folder,
    "QA"
)

os.makedirs(cleanup_folder, exist_ok=True)
os.makedirs(qa_folder, exist_ok=True)

summary_csv = os.path.join(
    qa_folder,
    "Cleanup_Summary.csv"
)

missing_csv = os.path.join(
    qa_folder,
    "Missing_Files.csv"
)

# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------

def delete_dataset(dataset):
    if arcpy.Exists(dataset):
        arcpy.Delete_management(dataset)

# ------------------------------------------------------------------
# TRACKING
# ------------------------------------------------------------------

summary_rows = []
missing_rows = []

# ------------------------------------------------------------------
# START TIMER
# ------------------------------------------------------------------

overall_start = timeit.default_timer()

# ------------------------------------------------------------------
# PROCESS HU12s
# ------------------------------------------------------------------

with arcpy.da.SearchCursor(HUshp, fieldlist,
                           # where_clause="HUC12 = '010802010602'"
                           ) as cursor:

    for row in cursor:

        HUnum = str(row[0])

        print(f"Starting cleanup for {HUnum}...")

        source_basins = os.path.join(
            output_folder,
            f"{HUnum}_final_basins.shp"
        )

        source_streams = os.path.join(
            output_folder,
            f"{HUnum}_prepped_streams.shp"
        )

        if not arcpy.Exists(source_basins):

            print(f"    WARNING: Missing final basins for {HUnum}")

            missing_rows.append(
                [HUnum, "final_basins"]
            )

            continue

        if not arcpy.Exists(source_streams):

            print(f"    WARNING: Missing planarized streams for {HUnum}")

            missing_rows.append(
                [HUnum, "prepped_streams"]
            )

            continue

        cleaned_basins = os.path.join(
            cleanup_folder,
            f"{HUnum}_final_basins_cleaned.shp"
        )

        temp_streams = os.path.join(
            cleanup_folder,
            f"{HUnum}_prepped_streams_temp.shp"
        )

        joined_streams = os.path.join(
            cleanup_folder,
            f"{HUnum}_prepped_streams_join.shp"
        )

        print("    Copying inputs...")

        arcpy.CopyFeatures_management(
            source_basins,
            cleaned_basins
        )

        arcpy.CopyFeatures_management(
            source_streams,
            temp_streams
        )

        print("    Spatial joining streams...")

        arcpy.analysis.SpatialJoin(
            target_features=temp_streams,
            join_features=flowlines_by_hu,
            out_feature_class=joined_streams,
            join_operation="JOIN_ONE_TO_ONE",
            join_type="KEEP_ALL",
            match_option="SHARE_A_LINE_SEGMENT_WITH"
        )

        print("    Joining HUC12 to catchments...")

        arcpy.management.JoinField(
            in_data=cleaned_basins,
            in_field="sid",
            join_table=joined_streams,
            join_field="sid",
            fields=["HUC12"]
        )

        original_count = int(
            arcpy.management.GetCount(
                cleaned_basins
            )[0]
        )

        # ----------------------------------------------------------
        # ASSIGN BLANK HUC12 VALUES
        # ----------------------------------------------------------

# ----------------------------------------------------------
        # ASSIGN BLANK HUC12 VALUES USING STREAM PROXIMITY
        # ----------------------------------------------------------

        print("    Resolving blank HUC12 values...")

        existing_fields = [f.name for f in arcpy.ListFields(cleaned_basins)]

        if "Assignment" not in existing_fields:
            arcpy.management.AddField(
                cleaned_basins,
                "Assignment",
                "TEXT",
                field_length=20
            )

        if "Dist_Main" not in existing_fields:
            arcpy.management.AddField(
                cleaned_basins,
                "Dist_Main",
                "DOUBLE"
            )

        if "Dist_Sub" not in existing_fields:
            arcpy.management.AddField(
                cleaned_basins,
                "Dist_Sub",
                "DOUBLE"
            )

        # ----------------------------------------------------------
        # BUILD MAIN NETWORK GEOMETRY
        # ----------------------------------------------------------

        main_network_shp = os.path.join(
            working_directory,
            "01_Generate_PourPoints",
            "02_Attribution",
            "03_lines_by_HU",
            f"{HUnum}.shp"
        )

        print("    Loading main network geometries...")

        main_geoms = []

        with arcpy.da.SearchCursor(
            main_network_shp,
            ["SHAPE@"]
        ) as search_cursor:

            for search_row in search_cursor:

                main_geoms.append(
                    search_row[0]
                )

        # ----------------------------------------------------------
        # BUILD SUBNETWORK GEOMETRIES BY HUC12
        # ----------------------------------------------------------

        print("    Loading subnetwork geometries...")

        subnetwork_geoms = {}

        with arcpy.da.SearchCursor(
            joined_streams,
            ["SHAPE@", "HUC12"]
        ) as search_cursor:

            for stream_geom, stream_huc in search_cursor:

                stream_huc = str(stream_huc).strip()

                if stream_huc == "":
                    continue

                if stream_huc == HUnum:
                    continue

                if stream_huc not in subnetwork_geoms:

                    subnetwork_geoms[stream_huc] = []

                subnetwork_geoms[stream_huc].append(
                    stream_geom
                )

        # ----------------------------------------------------------
        # ASSIGN BLANK HUC12 VALUES
        # ----------------------------------------------------------

        assigned_count = 0
        ambiguous_count = 0

        oid_field = arcpy.Describe(
            cleaned_basins
        ).OIDFieldName

        distance_assigned_oids = []

        with arcpy.da.UpdateCursor(
            cleaned_basins,
            [
                oid_field,
                "SHAPE@",
                "HUC12",
                "Assignment",
                "Dist_Main",
                "Dist_Sub"
            ]
        ) as update_cursor:

            for update_row in update_cursor:

                oid = update_row[0]
                basin_geom = update_row[1]

                current_huc = str(
                    update_row[2]
                ).strip()

                if current_huc != "":
                    continue

                # Use centroid instead of full polygon geometry

                basin_centroid = arcpy.PointGeometry(
                    basin_geom.centroid,
                    basin_geom.spatialReference
                )

                dist_main = min(
                    basin_centroid.distanceTo(
                        geom
                    )
                    for geom in main_geoms
                )

                nearest_sub_huc = None
                nearest_sub_dist = float("inf")

                for sub_huc, geom_list in subnetwork_geoms.items():

                    test_dist = min(
                        basin_centroid.distanceTo(
                            geom
                        )
                        for geom in geom_list
                    )

                    if test_dist < nearest_sub_dist:

                        nearest_sub_dist = test_dist
                        nearest_sub_huc = sub_huc

                update_row[4] = dist_main
                update_row[5] = nearest_sub_dist

                # Ambiguous

                if abs(
                    dist_main - nearest_sub_dist
                ) < 10:

                    update_row[3] = "AMBIGUOUS"

                    ambiguous_count += 1

                # Main network

                elif dist_main < nearest_sub_dist:

                    update_row[2] = HUnum
                    update_row[3] = "MAIN"

                    assigned_count += 1
                    distance_assigned_oids.append(
                        oid
                    )

                # Subnetwork

                else:

                    update_row[2] = nearest_sub_huc
                    update_row[3] = "SUBNETWORK"

                    assigned_count += 1
                    distance_assigned_oids.append(
                        oid
                    )

                update_cursor.updateRow(
                    update_row
                )

        print(
            f"    Assigned {assigned_count} "
            f"blank HUC12 values."
        )

        print(
            f"    Found {ambiguous_count} "
            f"ambiguous catchments."
        )

        # ----------------------------------------------------------
        # EXPORT DISTANCE-ASSIGNED CATCHMENTS
        # ----------------------------------------------------------

        if len(distance_assigned_oids) > 0:

            assigned_layer = "assigned_layer"

            oid_string = ",".join(
                [str(x) for x in distance_assigned_oids]
            )

            arcpy.MakeFeatureLayer_management(
                cleaned_basins,
                assigned_layer
            )

            arcpy.SelectLayerByAttribute_management(
                assigned_layer,
                "NEW_SELECTION",
                f"{oid_field} IN ({oid_string})"
            )

            assigned_output = os.path.join(
                qa_folder,
                f"{HUnum}_AmbiguousRemovals.shp"
            )

            arcpy.CopyFeatures_management(
                assigned_layer,
                assigned_output
            )

            delete_dataset(
                assigned_layer
            )

        # ----------------------------------------------------------
        # EXPORT AMBIGUOUS CATCHMENTS
        # ----------------------------------------------------------

        if ambiguous_count > 0:

            ambiguous_layer = "ambiguous_layer"

            arcpy.MakeFeatureLayer_management(
                cleaned_basins,
                ambiguous_layer
            )

            arcpy.SelectLayerByAttribute_management(
                ambiguous_layer,
                "NEW_SELECTION",
                "Assignment = 'AMBIGUOUS'"
            )

            ambiguous_output = os.path.join(
                qa_folder,
                f"{HUnum}_AmbiguousCatchments.shp"
            )

            arcpy.CopyFeatures_management(
                ambiguous_layer,
                ambiguous_output
            )

            delete_dataset(
                ambiguous_layer
            )

        # ----------------------------------------------------------
        # EXPORT REMOVED CATCHMENTS
        # ----------------------------------------------------------

        basin_layer = "basin_layer"

        arcpy.MakeFeatureLayer_management(
            cleaned_basins,
            basin_layer
        )

        arcpy.SelectLayerByAttribute_management(
            basin_layer,
            "NEW_SELECTION",
            f"HUC12 <> '{HUnum}' "
            f"AND Assignment <> 'AMBIGUOUS'"
        )

        removed_count = int(
            arcpy.management.GetCount(
                basin_layer
            )[0]
        )

        if removed_count > 0:

            removed_output = os.path.join(
                qa_folder,
                f"{HUnum}_RemovedCatchments.shp"
            )

            arcpy.CopyFeatures_management(
                basin_layer,
                removed_output
            )

        # ----------------------------------------------------------
        # DELETE REMOVED CATCHMENTS
        # ----------------------------------------------------------

        print(
            f"    Removing "
            f"{removed_count} "
            f"subnetwork catchments..."
        )

        with arcpy.da.UpdateCursor(
            cleaned_basins,
            ["HUC12", "Assignment"]
        ) as update_cursor:

            for update_row in update_cursor:

                huc_value = str(
                    update_row[0]
                ).strip()

                assignment = str(
                    update_row[1]
                ).strip()

                if (
                    huc_value != HUnum
                    and
                    assignment != "AMBIGUOUS"
                ):
                    update_cursor.deleteRow()

        remaining_count = int(
            arcpy.management.GetCount(
                cleaned_basins
            )[0]
        )

        delete_dataset(
            temp_streams
        )

        delete_dataset(
            basin_layer
        )

        summary_rows.append([
            HUnum,
            original_count,
            removed_count,
            remaining_count,
            assigned_count
        ])

        print(
            f"    Cleanup completed "
            f"for {HUnum}"
        )

# ------------------------------------------------------------------
# WRITE SUMMARY
# ------------------------------------------------------------------

with open(
    summary_csv,
    "w",
    newline=""
) as csvfile:

    writer = csv.writer(csvfile)

    writer.writerow([
        "HUC12",
        "Original_Count",
        "Removed_Count",
        "Remaining_Count",
        "Blank_Assigned"
    ])

    writer.writerows(
        summary_rows
    )

# ------------------------------------------------------------------
# WRITE MISSING FILE REPORT
# ------------------------------------------------------------------

with open(
    missing_csv,
    "w",
    newline=""
) as csvfile:

    writer = csv.writer(csvfile)

    writer.writerow([
        "HUC12",
        "Missing_File"
    ])

    writer.writerows(
        missing_rows
    )

# ------------------------------------------------------------------
# FINISH
# ------------------------------------------------------------------

overall_end = timeit.default_timer()

total_minutes = (
    overall_end - overall_start
) / 60

print(
    f"Catchment Cleanup completed in "
    f"{total_minutes:.2f} minutes"
)