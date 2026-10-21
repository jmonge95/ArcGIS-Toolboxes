# catchment_utils.py

import os
import time
import arcpy


# =============================================================================
# GLOBAL CONFIGURATION
# =============================================================================

LOCALE_CRS = {
    "CONUS": 6350,
    "AK": 3338
}

WBD_HU12_URL = (
    "https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer/6"
)

WBD_HU10_URL = (
    "https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer/5"
)

WBD_HU8_URL = (
    "https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer/4"
)

WBD_Line_URL = (
    "https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer/0"
)

from pathlib import Path
TEMPLATE_DIRECTORY = str(
    Path(__file__).resolve().parent.parent
    / "Workflow_Directory_TEMPLATE"
)

# =============================================================================
# MESSAGING
# =============================================================================

def msg(text):

    timestamp = time.strftime("%H:%M:%S")

    arcpy.AddMessage(
        f"[{timestamp}] {text}"
    )


def warn(text):

    timestamp = time.strftime("%H:%M:%S")

    arcpy.AddWarning(
        f"[{timestamp}] {text}"
    )


def err(text):

    timestamp = time.strftime("%H:%M:%S")

    arcpy.AddError(
        f"[{timestamp}] {text}"
    )


def separator():

    arcpy.AddMessage("=" * 70)


# =============================================================================
# PROJECTIONS
# =============================================================================

def get_spatial_reference(locale):

    locale = locale.upper()

    if locale not in LOCALE_CRS:

        raise ValueError(
            f"Unsupported locale: {locale}"
        )

    return arcpy.SpatialReference(
        LOCALE_CRS[locale]
    )


# =============================================================================
# WORKSPACE PATHS
# =============================================================================

def get_inputs_gdb(workspace):

    return os.path.join(
        workspace,
        "00_EDH_Inputs",
        "Inputs.gdb"
    )


def get_input_folder(workspace):

    return os.path.join(
        workspace,
        "00_EDH_Inputs"
    )


def get_pourpoints_folder(workspace):

    return os.path.join(
        workspace,
        "01_PourPoints"
    )

def get_pourpoints_gdb(workspace):

    return os.path.join(
        workspace,
        "01_PourPoints",
        "PourPoints.gdb"
    )

def get_hrt_folder(workspace):

    return os.path.join(
        workspace,
        "02_HRT_Processing"
    )

def get_scratch_gdb(workspace):

    return os.path.join(
        workspace,
        "00_EDH_Inputs",
        "Scratch.gdb"
    )

# =============================================================================
# FEATURE CLASS HELPERS
# =============================================================================

def fc_exists(fc):

    return arcpy.Exists(fc)


def delete_if_exists(dataset):

    if arcpy.Exists(dataset):

        arcpy.management.Delete(
            dataset
        )


def get_count(dataset):

    return int(
        arcpy.management.GetCount(
            dataset
        )[0]
    )


# =============================================================================
# STANDARD PROJECT DATASETS
# =============================================================================

def get_iwub_fc(workspace):

    return os.path.join(
        get_inputs_gdb(workspace),
        "IWUB"
    )


def get_huc12_fc(workspace):

    return os.path.join(
        get_inputs_gdb(workspace),
        "Existing_WBDHU12"
    )


def get_huc10_fc(workspace):

    return os.path.join(
        get_inputs_gdb(workspace),
        "Existing_WBDHU10"
    )


def get_huc8_fc(workspace):

    return os.path.join(
        get_inputs_gdb(workspace),
        "Existing_WBDHU8"
    )

def get_wbd_lines_fc(user_workspace):

    return os.path.join(
        get_inputs_gdb(user_workspace),
        "Existing_WBDLines"
    )

def get_edh_gdb(user_workspace):

    input_folder = get_input_folder(
        user_workspace
    )

    for item in os.listdir(
            input_folder
    ):

        if (
                item.lower().endswith(".gdb")
                and item.lower() != "inputs.gdb"
                and item.lower() != "scratch.gdb"
        ):

            return os.path.join(
                input_folder,
                item
            )

    raise ValueError(
        "Project EDH geodatabase not found."
    )

def get_edh_lines(user_workspace):

    return os.path.join(
        get_edh_gdb(
            user_workspace
        ),
        "Lines"
    )

def get_edh_points(user_workspace):

    return os.path.join(
        get_edh_gdb(user_workspace),
        "Points"
    )

def get_edh_polygons(workspace):

    return os.path.join(
        get_edh_gdb(workspace),
        "Polygons"
    )

def get_flowlines_by_huc_gdb(
        workspace):

    return os.path.join(
        workspace,
        "01_PourPoints",
        "Flowlines_By_HUC.gdb"
    )

def get_pourpoints_fc(
        workspace):

    return os.path.join(
        get_pourpoints_gdb(
            workspace
        ),
        "PourPoints"
    )

def get_streams_folder(workspace):

    return os.path.join(
        workspace,
        "02_HRT_Processing",
        "B_Streams"
    )

def get_waterbodies_folder(workspace):

    return os.path.join(
        workspace,
        "02_HRT_Processing",
        "C_Waterbodies"
    )

def get_hrt_outputs_folder(
        user_workspace):

    return os.path.join(
        get_hrt_folder(
            user_workspace
        ),
        "E_Outputs"
    )

def get_cleanup_folder(
        user_workspace):

    return os.path.join(
        user_workspace,
        "03_Catchment_Cleanup"
    )

def get_cleanup_catchments_folder(
        user_workspace):

    return os.path.join(
        get_cleanup_folder(
            user_workspace
        ),
        "A_Cleaned_Catchments"
    )

def get_cleanup_qa_folder(
        user_workspace):

    return os.path.join(
        get_cleanup_folder(
            user_workspace
        ),
        "B_QA"
    )

def get_cleanup_temp_folder(
        user_workspace):

    return os.path.join(
        get_cleanup_folder(
            user_workspace
        ),
        "C_Temp"
    )

def cleanup(items):

    for item in items:

        delete_if_exists(
            item
        )

def get_merged_flowlines_fc(
        user_workspace):

    return os.path.join(
        get_flowlines_by_huc_gdb(
            user_workspace
        ),
        "MERGED_Flowlines_by_HU12"
    )

# =============================================================================
# REPAIR GEOMETRY
# =============================================================================

def repair_geometry(
        input_fc,
        label=None):
    """
    Perform both ESRI and OGC geometry validation.

    Runs:
        1. Repair Geometry (ESRI)
        2. Repair Geometry (OGC)

    Delete Null Geometry is enabled for both passes.

    Parameters
    ----------
    input_fc : str
        Input feature class.

    label : str, optional
        Friendly name for messaging.
    """

    if label is None:
        label = os.path.basename(input_fc)

    if not arcpy.Exists(input_fc):

        warn(
            f"Geometry repair skipped. "
            f"{label} does not exist."
        )

        return

    try:

        before_count = int(
            arcpy.management.GetCount(
                input_fc
            )[0]
        )

        arcpy.management.RepairGeometry(
            in_features=input_fc,
            delete_null="DELETE_NULL",
            validation_method="ESRI"
        )

        arcpy.management.RepairGeometry(
            in_features=input_fc,
            delete_null="DELETE_NULL",
            validation_method="OGC"
        )

        after_count = int(
            arcpy.management.GetCount(
                input_fc
            )[0]
        )

        removed_count = (
            before_count -
            after_count
        )

    except Exception as ex:

        warn(
            f"Geometry repair failed for "
            f"{label}: {str(ex)}"
        )
