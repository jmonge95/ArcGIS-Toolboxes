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

TEMPLATE_DIRECTORY = (
    r"C:\Users\Jimmy.Monge\Documents\!Script_Copies"
    r"\!_Toolboxes\z_Pro_Workspaces"
    r"\Catchments_WBD\Workflow_Directory_TEMPLATE"
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

    msg("=" * 70)


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

def get_edh_gdb(workspace):

    return os.path.join(
        workspace,
        "00_EDH_Inputs",
        "EDH.gdb"
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

def get_dpa_fc(workspace):

    return os.path.join(
        get_inputs_gdb(workspace),
        "DPA"
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