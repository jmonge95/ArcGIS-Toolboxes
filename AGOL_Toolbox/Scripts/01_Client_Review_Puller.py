"""
Client_Review_Puller.py

AGOL Toolbox

Purpose
-------
Pull Client Review markup layers from AGOL,
archive them, load them into a production
review geodatabase, and optionally clear
AGOL review/EDH services.

Parameters
----------
0 - Project
1 - Backup Folder
2 - Production Folder
3 - Clear AGOL Layers
"""

import os
import shutil
import datetime
import arcpy

from agol_config import (
    get_project,
    get_review_services,
    get_edh_services
)

arcpy.env.overwriteOutput = True


# =============================================================================
# PORTAL VALIDATION
# =============================================================================

def verify_portal():

    portal = arcpy.GetActivePortalURL()

    if not portal:

        raise RuntimeError(
            "No active ArcGIS Online connection found."
        )

    arcpy.AddMessage(
        f"Connected Portal: {portal}"
    )


# =============================================================================
# HELPERS
# =============================================================================

def get_count(dataset):

    return int(
        arcpy.management.GetCount(
            dataset
        ).getOutput(0)
    )


def clear_service(service_url):

    count = get_count(
        service_url
    )

    if count == 0:
        return

    try:

        arcpy.management.TruncateTable(
            service_url
        )

    except arcpy.ExecuteError:

        arcpy.AddWarning(
            "TruncateTable not supported. "
            "Using DeleteRows instead."
        )

        arcpy.management.DeleteRows(
            service_url
        )

def append_feedback_data(
        source_fc,
        target_fc):

    if not arcpy.Exists(
            source_fc):
        return

    count = int(
        arcpy.management.GetCount(
            source_fc
        ).getOutput(0)
    )

    if count == 0:
        return

    arcpy.management.Append(
        source_fc,
        target_fc,
        "NO_TEST"
    )

    arcpy.AddMessage(
        f"Appended {count:,} "
        f"feedback features."
    )


# =============================================================================
# EXPORT REVIEW LAYERS
# =============================================================================

def export_review_layer(
        service_url,
        output_gdb,
        output_name):

    arcpy.AddMessage(
        f"Exporting {output_name}..."
    )

    arcpy.conversion.FeatureClassToFeatureClass(
        service_url,
        output_gdb,
        output_name
    )


# =============================================================================
# APPEND REVIEW DATA
# =============================================================================

def append_review_data(
        source_fc,
        target_fc,
        work_unit_boundary,
        where_clause=None):

    source_count = get_count(
        source_fc
    )

    if source_count == 0:

        arcpy.AddWarning(
            f"{os.path.basename(source_fc)} "
            f"contains no features."
        )

        return

    layer_name = (
        f"lyr_{os.path.basename(source_fc)}"
    )

    arcpy.management.MakeFeatureLayer(
        source_fc,
        layer_name
    )

    if where_clause:

        arcpy.management.SelectLayerByAttribute(
            layer_name,
            "NEW_SELECTION",
            where_clause
        )

        arcpy.management.SelectLayerByLocation(
            layer_name,
            "INTERSECT",
            work_unit_boundary,
            None,
            "SUBSET_SELECTION"
        )

    else:

        arcpy.management.SelectLayerByLocation(
            layer_name,
            "INTERSECT",
            work_unit_boundary
        )

    arcpy.management.SelectLayerByLocation(
        layer_name,
        "INTERSECT",
        work_unit_boundary
    )

    selected_count = int(
        arcpy.management.GetCount(
            layer_name
        ).getOutput(0)
    )

    if selected_count == 0:

        arcpy.AddWarning(
            f"No features intersect the "
            f"Work Unit Boundary in "
            f"{os.path.basename(source_fc)}."
        )

        return

    arcpy.management.Append(
        layer_name,
        target_fc,
        "NO_TEST"
    )

    arcpy.AddMessage(
        f"Appended {selected_count:,} "
        f"features from "
        f"{os.path.basename(source_fc)}."
    )


# =============================================================================
# MAIN
# =============================================================================

def main():

    project = (
        arcpy.GetParameterAsText(0)
    )

    backup_folder = (
        arcpy.GetParameterAsText(1)
    )

    production_folder = (
        arcpy.GetParameterAsText(2)
    )

    work_unit_boundary = (
        arcpy.GetParameterAsText(3)
    )

    washd_initial_feedback_gdb = (
        arcpy.GetParameterAsText(4)
    )

    clear_agol = (
        arcpy.GetParameter(5)
    )

    verify_portal()

    project_config = (
        get_project(project)
    )

    where_clause = None

    if project_config.get(
            "apply_washd_filter",
            False
    ):
        where_clause = (
            project_config[
                "washd_where_clause"
            ]
        )

    review_services = (
        get_review_services(project)
    )

    edh_services = (
        get_edh_services(project)
    )

    timestamp = (
        datetime.datetime.now()
        .strftime("%Y%m%d_%H%M%S")
    )

    # =====================================================================
    # CREATE BACKUP GDB
    # =====================================================================

    downloaded_gdb_name = (
        f"{project_config['download_name']}"
        f"_{timestamp}.gdb"
    )

    downloaded_gdb_path = (
        os.path.join(
            backup_folder,
            downloaded_gdb_name
        )
    )

    arcpy.management.CreateFileGDB(
        backup_folder,
        downloaded_gdb_name.replace(
            ".gdb",
            ""
        )
    )

    arcpy.AddMessage(
        f"Created backup GDB:"
    )

    arcpy.AddMessage(
        downloaded_gdb_path
    )

    # =====================================================================
    # EXPORT REVIEW SERVICES
    # =====================================================================

    export_review_layer(
        review_services["Points"],
        downloaded_gdb_path,
        "Client_Review_Points"
    )

    export_review_layer(
        review_services["Lines"],
        downloaded_gdb_path,
        "Client_Review_Lines"
    )

    export_review_layer(
        review_services["Polygons"],
        downloaded_gdb_path,
        "Client_Review_Polygons"
    )

    # =====================================================================
    # CREATE PRODUCTION GDB
    # =====================================================================

    template_gdb = (
        project_config[
            "template_gdb"
        ]
    )

    production_gdb_name = (
        f"ClientReview_"
        f"{project}_"
        f"{timestamp}.gdb"
    )

    production_gdb_path = (
        os.path.join(
            production_folder,
            production_gdb_name
        )
    )

    shutil.copytree(
        template_gdb,
        production_gdb_path
    )

    arcpy.AddMessage(
        f"Created production GDB:"
    )

    arcpy.AddMessage(
        production_gdb_path
    )

    for fc in [

        project_config["target_review_points"],
        project_config["target_review_lines"],
        project_config["target_review_polygons"]

    ]:

        fc_path = os.path.join(
            production_gdb_path,
            fc
        )

        if not arcpy.Exists(fc_path):
            raise RuntimeError(
                f"Expected feature class not found:\n"
                f"{fc_path}"
            )

    # =====================================================================
    # APPEND REVIEW DATA
    # =====================================================================

    source_points = os.path.join(
        downloaded_gdb_path,
        "Client_Review_Points"
    )

    source_lines = os.path.join(
        downloaded_gdb_path,
        "Client_Review_Lines"
    )

    source_polygons = os.path.join(
        downloaded_gdb_path,
        "Client_Review_Polygons"
    )

    target_points = os.path.join(
        production_gdb_path,
        project_config["target_review_points"]
    )

    target_lines = os.path.join(
        production_gdb_path,
        project_config["target_review_lines"]
    )

    target_polygons = os.path.join(
        production_gdb_path,
        project_config["target_review_polygons"]
    )

    append_review_data(
        source_points,
        target_points,
        work_unit_boundary,
        where_clause
    )

    append_review_data(
        source_lines,
        target_lines,
        work_unit_boundary,
        where_clause
    )

    append_review_data(
        source_polygons,
        target_polygons,
        work_unit_boundary,
        where_clause
    )

    if (
            project == "Washington"
            and
            washd_initial_feedback_gdb
    ):
        arcpy.AddMessage(
            "Appending WASHD Initial Feedback..."
        )

        append_feedback_data(

            os.path.join(
                washd_initial_feedback_gdb,
                "Review_Points"
            ),

            target_points
        )

        append_feedback_data(

            os.path.join(
                washd_initial_feedback_gdb,
                "Review_Lines"
            ),

            target_lines
        )

        append_feedback_data(

            os.path.join(
                washd_initial_feedback_gdb,
                "Review_Polygons"
            ),

            target_polygons
        )

    # =====================================================================
    # OPTIONAL AGOL CLEANUP
    # =====================================================================

    if clear_agol:

        arcpy.AddMessage(
            "Clearing AGOL layers..."
        )

        services_to_clear = [

            review_services["Points"],
            review_services["Lines"],
            review_services["Polygons"],

            edh_services["Points"],
            edh_services["Lines"],
            edh_services["Polygons"]

        ]

        for service in services_to_clear:

            clear_service(
                service
            )

        arcpy.AddMessage(
            "AGOL cleanup complete."
        )

    # =====================================================================
    # COMPLETE
    # =====================================================================

    webmap_url = (
        "https://nv5geospatial.maps.arcgis.com/"
        "apps/mapviewer/index.html?webmap="
        f"{project_config['webmap_id']}"
    )
    
    arcpy.AddMessage(
        "=" * 60
    )

    arcpy.AddWarning("")
    arcpy.AddWarning(
        "MANUAL WEB MAP REVIEW REQUIRED"
    )
    arcpy.AddWarning(
        f"Open: {webmap_url}"
    )
    arcpy.AddWarning(
        "Refer to the SOP for required "
        "post-pull cleanup tasks."
    )

    arcpy.AddMessage(
        "Client Review Pull Complete"
    )

    arcpy.AddMessage(
        "=" * 60
    )


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    main()