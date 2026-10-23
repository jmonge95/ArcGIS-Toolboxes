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
        target_fc):

    source_count = get_count(
        source_fc
    )

    if source_count == 0:

        arcpy.AddWarning(
            f"{os.path.basename(source_fc)} "
            f"contains no features."
        )

        return

    arcpy.management.Append(
        source_fc,
        target_fc,
        "NO_TEST"
    )

    arcpy.AddMessage(
        f"Appended {source_count:,} features."
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

    clear_agol = (
        arcpy.GetParameter(3)
    )

    verify_portal()

    project_config = (
        get_project(project)
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
        "Client_Review_Point_NV5"
    )

    target_lines = os.path.join(
        production_gdb_path,
        "Client_Review_Line_NV5"
    )

    target_polygons = os.path.join(
        production_gdb_path,
        "Client_Review_Polygon_NV5"
    )

    append_review_data(
        source_points,
        target_points
    )

    append_review_data(
        source_lines,
        target_lines
    )

    append_review_data(
        source_polygons,
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

    arcpy.AddMessage(
        "=" * 60
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