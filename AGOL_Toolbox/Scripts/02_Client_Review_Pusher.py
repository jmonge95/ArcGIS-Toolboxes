"""
Client_Review_Pusher.py

AGOL Toolbox

Purpose
-------
Push finalized hydrography datasets to the
ArcGIS Online Client Review feature services
for a selected project.

Requirements
------------
- User must be signed into ArcGIS Online
  through ArcGIS Pro.
- Input geodatabase must contain:
      Points
      Lines
      Polygons

Parameters
----------
0 - Project
1 - Hydrography Geodatabase
"""

import os
import arcpy
import sys

SCRIPT_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(
        0,
        SCRIPT_DIR
    )

from agol_config import (
    get_edh_services
)

arcpy.env.overwriteOutput = True


# =============================================================================
# PORTAL VALIDATION
# =============================================================================

def verify_portal():
    """
    Verify an active portal connection exists.
    """

    portal = arcpy.GetActivePortalURL()

    if not portal:

        raise RuntimeError(
            "No active ArcGIS Portal connection found. "
            "Please sign into ArcGIS Online before "
            "running this tool."
        )

    arcpy.AddMessage(
        f"Connected Portal: {portal}"
    )


# =============================================================================
# SERVICE VALIDATION
# =============================================================================

def validate_service(
        service_url,
        service_name):
    """
    Verify AGOL service is accessible.
    """

    try:

        count = int(
            arcpy.management.GetCount(
                service_url
            ).getOutput(0)
        )

        arcpy.AddMessage(
            f"Verified {service_name} "
            f"({count:,} existing records)"
        )

    except Exception as ex:

        raise RuntimeError(
            f"Unable to access AGOL service:\n"
            f"{service_name}\n\n"
            f"{service_url}\n\n"
            f"{str(ex)}"
        )


# =============================================================================
# INPUT VALIDATION
# =============================================================================

def validate_feature_class(
        feature_class):
    """
    Validate existence and record count.
    """

    if not arcpy.Exists(
            feature_class):
        return False

    count = int(
        arcpy.management.GetCount(
            feature_class
        ).getOutput(0)
    )

    return count > 0


def get_count(dataset):

    return int(
        arcpy.management.GetCount(
            dataset
        ).getOutput(0)
    )


# =============================================================================
# FIELD MAPPINGS
# =============================================================================

def build_field_mappings(
        source_fc,
        target_fc):
    """
    Build field mappings for append.

    Explicitly maps:

        Source: Desc
        Target: Desc_
    """

    field_mappings = arcpy.FieldMappings()

    field_mappings.addTable(
        source_fc
    )

    field_mappings.addTable(
        target_fc
    )

    source_fields = [
        f.name
        for f in arcpy.ListFields(
            source_fc
        )
    ]

    if "Desc" not in source_fields:

        arcpy.AddWarning(
            "Source field 'Desc' not found."
        )

        return field_mappings

    for i in range(
            field_mappings.fieldCount):

        fmap = field_mappings.getFieldMap(
            i
        )

        output_field = fmap.outputField

        if output_field.name == "Desc_":

            while fmap.inputFieldCount > 0:
                fmap.removeInputField(0)

            fmap.addInputField(
                source_fc,
                "Desc"
            )

            field_mappings.replaceFieldMap(
                i,
                fmap
            )

            arcpy.AddMessage(
                "Mapped Desc -> Desc_"
            )

            break

    return field_mappings


# =============================================================================
# AGOL OPERATIONS
# =============================================================================

def clear_service(
        service_url,
        service_name):
    """
    Remove existing records.
    """

    existing_count = get_count(
        service_url
    )

    if existing_count == 0:

        arcpy.AddMessage(
            f"{service_name}: already empty."
        )

        return

    arcpy.AddMessage(
        f"{service_name}: deleting "
        f"{existing_count:,} records..."
    )

    arcpy.management.DeleteRows(
        service_url
    )


def append_features(
        source_fc,
        service_url,
        service_name):
    """
    Append local features into AGOL.
    """

    source_count = get_count(
        source_fc
    )

    arcpy.AddMessage(
        f"{service_name}: appending "
        f"{source_count:,} features..."
    )

    field_mappings = (
        build_field_mappings(
            source_fc,
            service_url
        )
    )

    arcpy.management.Append(
        source_fc,
        service_url,
        "NO_TEST",
        field_mappings
    )

    new_count = get_count(
        service_url
    )

    arcpy.AddMessage(
        f"{service_name}: "
        f"{new_count:,} total records."
    )


# =============================================================================
# PUSH DATASET
# =============================================================================

def push_dataset(
        source_fc,
        service_url,
        dataset_name,
        push_mode):
    """
    Replace AGOL service contents.
    """

    arcpy.AddMessage(
        "-" * 60
    )

    arcpy.AddMessage(
        f"Processing {dataset_name}"
    )

    if (
            push_mode
            ==
            "Replace Existing Features"
    ):

        clear_service(
            service_url,
            dataset_name
        )

    else:

        arcpy.AddMessage(
            f"{dataset_name}: "
            f"append-only mode."
        )

    append_features(
        source_fc,
        service_url,
        dataset_name
    )

    arcpy.AddMessage(
        f"{dataset_name} complete."
    )


# =============================================================================
# MAIN
# =============================================================================

def main():
    project = (
        arcpy.GetParameterAsText(0)
    )

    hydro_gdb = (
        arcpy.GetParameterAsText(1)
    )

    push_mode = (
        arcpy.GetParameterAsText(2)
    )

    verify_portal()

    arcpy.AddMessage(
        f"Selected Project: "
        f"{project}"
    )

    arcpy.AddMessage(
        f"Push Mode: "
        f"{push_mode}"
    )

    services = get_edh_services(
        project
    )

    datasets = {

        "Points": (
            os.path.join(
                hydro_gdb,
                "Points"
            ),
            services["Points"]
        ),

        "Lines": (
            os.path.join(
                hydro_gdb,
                "Lines"
            ),
            services["Lines"]
        ),

        "Polygons": (
            os.path.join(
                hydro_gdb,
                "Polygons"
            ),
            services["Polygons"]
        )
    }

    arcpy.AddMessage(
        "Validating AGOL services..."
    )

    for dataset_name, (
            source_fc,
            service_url
    ) in datasets.items():

        validate_service(
            service_url,
            dataset_name
        )

    arcpy.AddMessage(
        "All services validated."
    )

    for dataset_name, (
            source_fc,
            service_url
    ) in datasets.items():

        if not validate_feature_class(
                source_fc):

            arcpy.AddWarning(
                f"{dataset_name} missing "
                f"or empty. Skipping."
            )

            continue

        push_dataset(
            source_fc,
            service_url,
            dataset_name,
            push_mode
        )

    arcpy.AddMessage(
        ""
    )

    arcpy.AddMessage(
        "=" * 60
    )

    arcpy.AddMessage(
        "Client Review Push Complete"
    )

    arcpy.AddMessage(
        "=" * 60
    )

# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    main()
