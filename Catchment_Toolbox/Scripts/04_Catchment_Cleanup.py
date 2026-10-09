"""
04_Catchment_Cleanup.py

Catchment Toolbox

Purpose:
    Clean HRT catchments using HUC12-attributed
    stream ownership.

Parameter:
    0 - User Workspace
"""

import os
import csv
import timeit
import arcpy
import catchment_utils as utils

arcpy.env.overwriteOutput = True

AMBIGUITY_DISTANCE = 10


# =============================================================================
# HELPERS
# =============================================================================

def delete_if_exists(dataset):

    if arcpy.Exists(dataset):

        arcpy.management.Delete(
            dataset
        )


def ensure_folder(folder):

    if not os.path.exists(folder):

        os.makedirs(folder)


# =============================================================================
# PATHS
# =============================================================================

def initialize_paths(user_workspace):

    cleanup_folder = os.path.join(
        user_workspace,
        "03_Catchment_Cleanup"
    )

    cleaned_folder = os.path.join(
        cleanup_folder,
        "A_Cleaned_Catchments"
    )

    qa_folder = os.path.join(
        cleanup_folder,
        "B_QA"
    )

    temp_folder = os.path.join(
        cleanup_folder,
        "C_Temp"
    )

    ensure_folder(cleaned_folder)
    ensure_folder(qa_folder)
    ensure_folder(temp_folder)

    return {

        "huc12_fc":
            utils.get_huc12_fc(
                user_workspace
            ),

        "flowlines_gdb":
            utils.get_flowlines_by_huc_gdb(
                user_workspace
            ),

        "merged_flowlines":
            os.path.join(
                utils.get_flowlines_by_huc_gdb(
                    user_workspace
                ),
                "MERGED_Flowlines_by_HU12"
            ),

        "hrt_outputs":
            os.path.join(
                utils.get_hrt_folder(
                    user_workspace
                ),
                "E_Outputs"
            ),

        "cleaned_folder":
            cleaned_folder,

        "qa_folder":
            qa_folder,

        "temp_folder":
            temp_folder

    }


# =============================================================================
# INPUT VALIDATION
# =============================================================================

def validate_inputs(
        basin_fc,
        stream_fc):

    return (
        arcpy.Exists(
            basin_fc
        )
        and
        arcpy.Exists(
            stream_fc
        )
    )


# =============================================================================
# SPATIAL JOIN
# =============================================================================

def spatial_join_streams(
        temp_streams,
        merged_flowlines,
        joined_streams):

    delete_if_exists(
        joined_streams
    )

    arcpy.analysis.SpatialJoin(
        target_features=temp_streams,
        join_features=merged_flowlines,
        out_feature_class=joined_streams,
        join_operation="JOIN_ONE_TO_ONE",
        join_type="KEEP_ALL",
        match_option="SHARE_A_LINE_SEGMENT_WITH"
    )


# =============================================================================
# JOIN HUC12 TO BASINS
# =============================================================================

def join_huc12_to_basins(
        cleaned_basins,
        joined_streams):

    existing_fields = [
        f.name
        for f in arcpy.ListFields(
            cleaned_basins
        )
    ]

    if "HUC12" in existing_fields:

        arcpy.management.DeleteField(
            cleaned_basins,
            "HUC12"
        )

    arcpy.management.JoinField(
        cleaned_basins,
        "sid",
        joined_streams,
        "sid",
        ["HUC12"]
    )


# =============================================================================
# NETWORK GEOMETRIES
# =============================================================================

def get_main_network_geometries(
        main_network_fc):

    geoms = []

    with arcpy.da.SearchCursor(
            main_network_fc,
            ["SHAPE@"]
    ) as cursor:

        for row in cursor:

            geoms.append(
                row[0]
            )

    return geoms


def build_subnetwork_geometries(
        joined_streams,
        huc12):

    subnetworks = {}

    with arcpy.da.SearchCursor(
            joined_streams,
            ["SHAPE@", "HUC12"]
    ) as cursor:

        for geom, sub_huc in cursor:

            if sub_huc is None:
                continue

            sub_huc = str(
                sub_huc
            ).strip()

            if not sub_huc:
                continue

            if sub_huc == huc12:
                continue

            subnetworks.setdefault(
                sub_huc,
                []
            ).append(
                geom
            )

    return subnetworks


# =============================================================================
# ADD QC FIELDS
# =============================================================================

def add_qc_fields(cleaned_basins):

    existing_fields = [
        f.name
        for f in arcpy.ListFields(
            cleaned_basins
        )
    ]

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


# =============================================================================
# RESOLVE BLANK HUC12s
# =============================================================================

def resolve_blank_huc12s(
        cleaned_basins,
        huc12,
        main_geoms,
        subnetwork_geoms):

    assigned_oids = []

    assigned_count = 0
    ambiguous_count = 0

    oid_field = arcpy.Describe(
        cleaned_basins
    ).OIDFieldName

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
    ) as cursor:

        for row in cursor:

            oid = row[0]

            geom = row[1]

            current_huc = ""

            if row[2] is not None:

                current_huc = str(
                    row[2]
                ).strip()

            if current_huc:

                continue

            centroid = arcpy.PointGeometry(
                geom.centroid,
                geom.spatialReference
            )

            dist_main = min(
                centroid.distanceTo(
                    x
                )
                for x in main_geoms
            )

            nearest_sub_huc = None

            nearest_sub_dist = float(
                "inf"
            )

            for sub_huc, geom_list in \
                    subnetwork_geoms.items():

                dist = min(
                    centroid.distanceTo(
                        g
                    )
                    for g in geom_list
                )

                if dist < nearest_sub_dist:

                    nearest_sub_dist = dist

                    nearest_sub_huc = sub_huc

            row[4] = dist_main
            row[5] = nearest_sub_dist

            if abs(
                    dist_main -
                    nearest_sub_dist
            ) < AMBIGUITY_DISTANCE:

                row[3] = "AMBIGUOUS"

                ambiguous_count += 1

            elif dist_main < nearest_sub_dist:

                row[2] = huc12

                row[3] = "MAIN"

                assigned_count += 1

                assigned_oids.append(
                    oid
                )

            else:

                row[2] = nearest_sub_huc

                row[3] = "SUBNETWORK"

                assigned_count += 1

                assigned_oids.append(
                    oid
                )

            cursor.updateRow(
                row
            )

    return (
        assigned_count,
        ambiguous_count,
        assigned_oids,
        oid_field
    )


# =============================================================================
# QA EXPORTS
# =============================================================================

def export_distance_assigned(
        cleaned_basins,
        oid_field,
        oid_list,
        output_fc):

    if len(oid_list) == 0:

        return

    lyr = "distance_lyr"

    arcpy.management.MakeFeatureLayer(
        cleaned_basins,
        lyr
    )

    oid_string = ",".join(
        [
            str(x)
            for x in oid_list
        ]
    )

    arcpy.management.SelectLayerByAttribute(
        lyr,
        "NEW_SELECTION",
        f"{oid_field} IN ({oid_string})"
    )

    delete_if_exists(
        output_fc
    )

    arcpy.management.CopyFeatures(
        lyr,
        output_fc
    )

    delete_if_exists(
        lyr
    )


def export_assignment(
        cleaned_basins,
        assignment_value,
        output_fc):

    lyr = "qa_lyr"

    arcpy.management.MakeFeatureLayer(
        cleaned_basins,
        lyr
    )

    arcpy.management.SelectLayerByAttribute(
        lyr,
        "NEW_SELECTION",
        f"Assignment = '{assignment_value}'"
    )

    count = int(
        arcpy.management.GetCount(
            lyr
        )[0]
    )

    if count > 0:

        delete_if_exists(
            output_fc
        )

        arcpy.management.CopyFeatures(
            lyr,
            output_fc
        )

    delete_if_exists(
        lyr
    )

# =============================================================================
# EXPORT REMOVED CATCHMENTS
# =============================================================================

def export_removed_catchments(
        cleaned_basins,
        huc12,
        output_fc):
    """
    Export the exact catchments that
    will be removed during cleanup.
    """

    lyr = "removed_lyr"

    arcpy.management.MakeFeatureLayer(
        cleaned_basins,
        lyr
    )

    arcpy.management.SelectLayerByAttribute(
        lyr,
        "NEW_SELECTION",
        (
            f"HUC12 <> '{huc12}' "
            f"AND "
            f"(Assignment IS NULL "
            f"OR Assignment <> 'AMBIGUOUS')"
        )
    )

    count = int(
        arcpy.management.GetCount(
            lyr
        )[0]
    )

    if count > 0:

        delete_if_exists(
            output_fc
        )

        arcpy.management.CopyFeatures(
            lyr,
            output_fc
        )

    delete_if_exists(
        lyr
    )

    return count


# =============================================================================
# REMOVE SUBNETWORK CATCHMENTS
# =============================================================================

def remove_subnetwork_catchments(
        cleaned_basins,
        huc12):

    removed_count = 0

    with arcpy.da.UpdateCursor(
            cleaned_basins,
            [
                "HUC12",
                "Assignment"
            ]
    ) as cursor:

        for row in cursor:

            basin_huc = str(
                row[0]
            ).strip()

            assignment = str(
                row[1]
            ).strip()

            if (
                basin_huc != huc12
                and
                assignment != "AMBIGUOUS"
            ):

                cursor.deleteRow()

                removed_count += 1

    return removed_count


# =============================================================================
# MAIN
# =============================================================================

def main():

    start_time = timeit.default_timer()

    user_workspace = (
        arcpy.GetParameterAsText(
            0
        )
    )

    paths = initialize_paths(
        user_workspace
    )

    summary_rows = []
    missing_rows = []

    utils.separator()

    utils.msg(
        "Catchment Toolbox - "
        "04 Catchment Cleanup"
    )

    utils.separator()

    with arcpy.da.SearchCursor(
            paths["huc12_fc"],
            ["HUC12"]
    ) as cursor:

        for row in cursor:

            huc12 = str(
                row[0]
            )

            utils.msg(
                f"Processing {huc12}"
            )

            source_basins = os.path.join(
                paths["hrt_outputs"],
                f"{huc12}_final_basins.shp"
            )

            source_streams = os.path.join(
                paths["hrt_outputs"],
                f"{huc12}_prepped_streams.shp"
            )

            if not validate_inputs(
                    source_basins,
                    source_streams):

                missing_rows.append(
                    [huc12]
                )

                continue

            cleaned_basins = os.path.join(
                paths["cleaned_folder"],
                f"{huc12}_final_basins_cleaned.shp"
            )

            temp_streams = os.path.join(
                paths["temp_folder"],
                f"{huc12}_prepped_streams_temp.shp"
            )

            joined_streams = os.path.join(
                paths["qa_folder"],
                f"{huc12}_prepped_streams_join.shp"
            )

            delete_if_exists(
                cleaned_basins
            )

            delete_if_exists(
                temp_streams
            )

            arcpy.management.CopyFeatures(
                source_basins,
                cleaned_basins
            )

            arcpy.management.CopyFeatures(
                source_streams,
                temp_streams
            )

            spatial_join_streams(
                temp_streams,
                paths["merged_flowlines"],
                joined_streams
            )

            join_huc12_to_basins(
                cleaned_basins,
                joined_streams
            )

            add_qc_fields(
                cleaned_basins
            )

            main_network_fc = os.path.join(
                paths["flowlines_gdb"],
                f"HU_{huc12}"
            )

            main_geoms = (
                get_main_network_geometries(
                    main_network_fc
                )
            )

            subnetworks = (
                build_subnetwork_geometries(
                    joined_streams,
                    huc12
                )
            )

            (
                assigned_count,
                ambiguous_count,
                assigned_oids,
                oid_field
            ) = resolve_blank_huc12s(
                cleaned_basins,
                huc12,
                main_geoms,
                subnetworks
            )

            export_distance_assigned(
                cleaned_basins,
                oid_field,
                assigned_oids,
                os.path.join(
                    paths["qa_folder"],
                    f"{huc12}_DistanceAssigned.shp"
                )
            )

            export_assignment(
                cleaned_basins,
                "AMBIGUOUS",
                os.path.join(
                    paths["qa_folder"],
                    f"{huc12}_AmbiguousCatchments.shp"
                )
            )

            removed_output = os.path.join(
                paths["qa_folder"],
                f"{huc12}_RemovedCatchments.shp"
            )

            export_removed_catchments(
                cleaned_basins,
                huc12,
                removed_output
            )

            original_count = int(
                arcpy.management.GetCount(
                    cleaned_basins
                )[0]
            )

            removed_count = (
                remove_subnetwork_catchments(
                    cleaned_basins,
                    huc12
                )
            )

            remaining_count = int(
                arcpy.management.GetCount(
                    cleaned_basins
                )[0]
            )

            delete_if_exists(
                temp_streams
            )

            summary_rows.append(
                [
                    huc12,
                    original_count,
                    removed_count,
                    remaining_count,
                    assigned_count,
                    ambiguous_count
                ]
            )

    summary_csv = os.path.join(
        paths["qa_folder"],
        "Cleanup_Summary.csv"
    )

    with open(
            summary_csv,
            "w",
            newline=""
    ) as csvfile:

        writer = csv.writer(
            csvfile
        )

        writer.writerow(
            [
                "HUC12",
                "Original_Count",
                "Removed_Count",
                "Remaining_Count",
                "Distance_Assigned",
                "Ambiguous_Count"
            ]
        )

        writer.writerows(
            summary_rows
        )

    missing_csv = os.path.join(
        paths["qa_folder"],
        "Missing_Files.csv"
    )

    with open(
            missing_csv,
            "w",
            newline=""
    ) as csvfile:

        writer = csv.writer(
            csvfile
        )

        writer.writerow(
            [
                "HUC12"
            ]
        )

        writer.writerows(
            missing_rows
        )

    elapsed = (
        timeit.default_timer()
        - start_time
    ) / 60

    utils.separator()

    utils.msg(
        f"Catchment Cleanup "
        f"completed in "
        f"{elapsed:.2f} minutes."
    )

    utils.separator()


if __name__ == "__main__":
    main()