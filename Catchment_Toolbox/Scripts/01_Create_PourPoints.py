"""
01_Create_PourPoints.py

Catchment Toolbox

Purpose:
    Generate watershed pour points for each HU12 by locating
    the lowest elevation flowline crossing along the HU12 boundary.

Parameters:
    0 - User Workspace
    1 - DEM
"""

import os
import arcpy
from arcpy.sa import ExtractValuesToPoints
import catchment_utils as utils


# =============================================================================
# WORKSPACE
# =============================================================================

def create_pourpoints_gdb(user_workspace):
    """
    Creates PourPoints.gdb if it does not exist.
    """

    pourpoints_folder = utils.get_pourpoints_folder(
        user_workspace
    )

    pourpoints_gdb = utils.get_pourpoints_gdb(
        user_workspace
    )

    if not os.path.isdir(pourpoints_folder):

        os.makedirs(
            pourpoints_folder
        )

    if not arcpy.Exists(
            pourpoints_gdb):

        arcpy.management.CreateFileGDB(
            pourpoints_folder,
            "PourPoints.gdb"
        )

    return pourpoints_gdb


# =============================================================================
# DATA PREPARATION
# =============================================================================

def create_candidate_pour_points(
        huc12_fc,
        flowlines_fc,
        pourpoints_gdb):
    """
    Creates candidate pour points where flowlines
    intersect HU12 boundaries.
    """

    hu12_lines = os.path.join(
        pourpoints_gdb,
        "HU12_Boundary_Lines"
    )

    boundary_intersections = os.path.join(
        pourpoints_gdb,
        "Flowline_HU12_Intersections"
    )

    buffered_huc12 = os.path.join(
        pourpoints_gdb,
        "HU12_Buffer_1m"
    )

    intersection_points = os.path.join(
        pourpoints_gdb,
        "Candidate_PourPoints"
    )

    utils.delete_if_exists(
        hu12_lines
    )

    utils.delete_if_exists(
        boundary_intersections
    )

    utils.delete_if_exists(
        buffered_huc12
    )

    utils.delete_if_exists(
        intersection_points
    )

    arcpy.management.PolygonToLine(
        huc12_fc,
        hu12_lines,
        "IDENTIFY_NEIGHBORS"
    )

    arcpy.analysis.Intersect(
        [hu12_lines, flowlines_fc],
        boundary_intersections,
        output_type="POINT"
    )

    arcpy.analysis.Buffer(
        huc12_fc,
        buffered_huc12,
        "1 Meters",
        dissolve_option="NONE"
    )

    temp_intersections = os.path.join(
        pourpoints_gdb,
        "Temp_Intersection_Points"
    )

    utils.delete_if_exists(
        temp_intersections
    )

    arcpy.analysis.Intersect(
        [buffered_huc12,
         boundary_intersections],
        temp_intersections,
        output_type="POINT"
    )

    arcpy.management.MultipartToSinglepart(
        temp_intersections,
        intersection_points
    )

    utils.delete_if_exists(
        temp_intersections
    )

    return intersection_points


# =============================================================================
# DEM SAMPLING
# =============================================================================

def sample_dem(
        candidate_points,
        dem,
        pourpoints_gdb):
    """
    Extract DEM elevation values to candidate points.
    """

    z_points = os.path.join(
        pourpoints_gdb,
        "Candidate_PourPoints_Z"
    )

    utils.delete_if_exists(
        z_points
    )

    arcpy.CheckOutExtension(
        "Spatial"
    )

    ExtractValuesToPoints(
        candidate_points,
        dem,
        z_points
    )

    return z_points


# =============================================================================
# LOWEST POINT SELECTION
# =============================================================================

def create_final_pour_points(
        z_points,
        output_fc):
    """
    Select lowest elevation point
    for each HUC12.
    """

    utils.delete_if_exists(
        output_fc
    )

    min_elev = {}

    with arcpy.da.SearchCursor(
            z_points,
            ["HUC12", "RASTERVALU"]
    ) as cursor:

        for huc12, elev in cursor:

            if elev is None:
                continue

            if huc12 not in min_elev:

                min_elev[huc12] = elev

            else:

                min_elev[huc12] = min(
                    min_elev[huc12],
                    elev
                )

    oid_list = []

    oid_field = arcpy.Describe(
        z_points
    ).OIDFieldName

    with arcpy.da.SearchCursor(
            z_points,
            [oid_field,
             "HUC12",
             "RASTERVALU"]
    ) as cursor:

        for oid, huc12, elev in cursor:

            if elev is None:
                continue

            if elev == min_elevoid_list.append(
                    str(oid)
            )

    if not oid_list:

        raise ValueError(
            "No pour points were identified."
        )

    where_clause = (
        f"{oid_field} IN "
        f"({','.join(oid_list)})"
    )

    arcpy.management.MakeFeatureLayer(
        z_points,
        "pourpoints_lyr",
        where_clause
    )

    arcpy.management.CopyFeatures(
        "pourpoints_lyr",
        output_fc
    )

    arcpy.management.Delete(
        "pourpoints_lyr"
    )


# =============================================================================
# MAIN
# =============================================================================

def main():

    arcpy.env.overwriteOutput = True

    user_workspace = arcpy.GetParameterAsText(0)
    dem = arcpy.GetParameterAsText(1)

    utils.separator()

    utils.msg(
        "Catchment Toolbox - 01 Create Pour Points"
    )

    utils.separator()

    inputs_gdb = utils.get_inputs_gdb(
        user_workspace
    )

    huc12_fc = utils.get_huc12_fc(
        user_workspace
    )

    flowlines_fc = utils.get_edh_lines(
        user_workspace
    )

    pourpoints_gdb = create_pourpoints_gdb(
        user_workspace
    )

    utils.msg(
        "Generating candidate pour points..."
    )

    candidate_points = (
        create_candidate_pour_points(
            huc12_fc,
            flowlines_fc,
            pourpoints_gdb
        )
    )

    utils.msg(
        "Extracting DEM elevations..."
    )

    z_points = sample_dem(
        candidate_points,
        dem,
        pourpoints_gdb
    )

    utils.msg(
        "Selecting lowest elevation point per HU12..."
    )

    final_pourpoints = os.path.join(
        pourpoints_gdb,
        "PourPoints"
    )

    create_final_pour_points(
        z_points,
        final_pourpoints
    )

    utils.separator()

    utils.msg(
        "Pour point generation completed successfully."
    )

    utils.separator()


if __name__ == "__main__":
    main()
