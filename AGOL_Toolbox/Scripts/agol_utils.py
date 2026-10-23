"""
Shared AGOL toolbox utilities.
"""

import arcpy
import os
import sys

SCRIPT_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(
        0,
        SCRIPT_DIR
    )

from agol_config import PROJECTS


# =============================================================================
# CONFIG
# =============================================================================

def get_project_services(project):

    if project not in PROJECTS:

        raise ValueError(
            f"Unknown project: {project}"
        )

    return PROJECTS[project]


# =============================================================================
# COUNTS
# =============================================================================

def get_count(dataset):

    return int(
        arcpy.management.GetCount(
            dataset
        ).getOutput(0)
    )


# =============================================================================
# FIELD MAPPINGS
# =============================================================================

def build_field_mappings(source_fc):

    field_mappings = arcpy.FieldMappings()

    field_mappings.addTable(
        source_fc
    )

    if "Desc" not in [
        f.name
        for f in arcpy.ListFields(
            source_fc
        )
    ]:
        return field_mappings

    for i in reversed(
            range(
                field_mappings.fieldCount
            )
    ):

        fmap = field_mappings.getFieldMap(i)

        if (
                fmap.outputField.name
                == "Desc_"
        ):
            field_mappings.removeFieldMap(
                i
            )

    fmap = arcpy.FieldMap()

    fmap.addInputField(
        source_fc,
        "Desc"
    )

    output_field = fmap.outputField

    output_field.name = "Desc_"
    output_field.aliasName = "Desc"

    fmap.outputField = output_field

    field_mappings.addFieldMap(
        fmap
    )

    return field_mappings


# =============================================================================
# APPEND
# =============================================================================

# def clear_service(
#         service_url):
#
#     record_count = int(
#         arcpy.management.GetCount(
#             service_url
#         ).getOutput(0)
#     )
#
#     if record_count == 0:
#         return
#
#     arcpy.management.DeleteRows(
#         service_url
#     )

def validate_service(service_url):

    try:

        count = int(
            arcpy.management.GetCount(
                service_url
            ).getOutput(0)
        )

        return True

    except Exception:

        return False

def append_to_service(
        source_fc,
        service_url):

    field_mappings = (
        build_field_mappings(
            source_fc
        )
    )

    arcpy.management.Append(
        source_fc,
        service_url,
        "NO_TEST",
        field_mappings
    )

# =============================================================================
# REVIEW LAYER STUFF
# =============================================================================

def export_review_layer(
        service_url,
        output_gdb,
        output_name):

    arcpy.conversion.FeatureClassToFeatureClass(
        service_url,
        output_gdb,
        output_name
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
            "TruncateTable failed. "
            "Using DeleteRows."
        )

        arcpy.management.DeleteRows(
            service_url
        )