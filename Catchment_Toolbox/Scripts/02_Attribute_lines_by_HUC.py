"""
02_Attribute_Lines_By_HUC.py

Catchment Toolbox

Purpose:
    Traces EDH flowlines upstream from each
    QA/QC'd HU12 pour point and exports
    one flowline feature class per HU12.

Parameter:
    0 - User Workspace
"""

import os
import arcpy
import catchment_utils as utils

# =============================================================================
# OUTPUT GDB
# =============================================================================

def create_output_gdb(user_workspace):

    output_gdb = utils.get_flowlines_by_huc_gdb(
        user_workspace
    )

    if arcpy.Exists(output_gdb):
        arcpy.management.Delete(
            output_gdb
        )

    arcpy.management.CreateFileGDB(
        os.path.dirname(output_gdb),
        os.path.basename(output_gdb)
    )

    return output_gdb

# =============================================================================
# TRACE NETWORK
# =============================================================================

def build_trace_network(
        flowlines_fc,
        scratch_gdb):
    """
    Create trace network in Scratch.gdb.
    """

    utils.msg(
        "Creating trace network..."
    )

    trace_fd = os.path.join(
        scratch_gdb,
        "Flowline_Trace"
    )

    utils.delete_if_exists(
        trace_fd
    )

    sr = arcpy.Describe(
        flowlines_fc
    ).spatialReference

    root_trace_flowlines = os.path.join(
        scratch_gdb,
        "Trace_Flowlines"
    )

    utils.delete_if_exists(
        root_trace_flowlines
    )

    arcpy.management.CreateFeatureDataset(
        scratch_gdb,
        "Flowline_Trace",
        sr
    )

    trace_flowlines = os.path.join(
        trace_fd,
        "HUC_Trace_Flowlines"
    )

    arcpy.management.CopyFeatures(
        flowlines_fc,
        trace_flowlines
    )

    arcpy.tn.CreateTraceNetwork(
        trace_fd,
        "TraceNetwork",
        "",
        "HUC_Trace_Flowlines SIMPLE_EDGE"
    )

    trace_network = os.path.join(
        trace_fd,
        "TraceNetwork"
    )

    arcpy.tn.EnableNetworkTopology(
        trace_network
    )

    return (
        trace_fd,
        trace_network,
        trace_flowlines
    )

# =============================================================================
# TRACE EACH HUC12
# =============================================================================

def trace_huc12s(
        pourpoints_fc,
        trace_network,
        trace_fd,
        trace_flowlines,
        output_gdb):
    """
    Trace flowlines for each HUC12.
    """

    utils.msg(
        "Creating HUC12 traces..."
    )

    huc12_values = sorted(
        {
            row[0]
            for row in arcpy.da.SearchCursor(
            pourpoints_fc,
            ["HUC12"]
        )
            if row[0]
        }
    )

    for huc12 in huc12_values:

        utils.msg(
            f"Tracing {huc12}"
        )

        start_pts = os.path.join(
            trace_fd,
            "start_pts"
        )

        stop_pts = os.path.join(
            trace_fd,
            "stop_pts"
        )

        utils.delete_if_exists(
            start_pts
        )

        utils.delete_if_exists(
            stop_pts
        )

        huc_field = arcpy.AddFieldDelimiters(
            pourpoints_fc,
            "HUC12"
        )

        start_sql = (
            f"{huc_field} = '{huc12}'"
        )

        stop_sql = (
            f"{huc_field} <> '{huc12}'"
        )

        arcpy.analysis.Select(
            pourpoints_fc,
            start_pts,
            start_sql
        )

        arcpy.analysis.Select(
            pourpoints_fc,
            stop_pts,
            stop_sql
        )

        trace_result = arcpy.tn.Trace(
            in_trace_network=trace_network,
            trace_type="UPSTREAM",
            starting_points=start_pts,
            barriers=stop_pts,
            include_barriers="EXCLUDE_BARRIERS",
            result_types="NETWORK_LAYERS",
            out_network_layer="TRACED"
        )

        traced_lines = "TRACED/HUC_Trace_Flowlines"

        output_fc = os.path.join(
            output_gdb,
            f"HU_{huc12}"
        )

        utils.delete_if_exists(
            output_fc
        )

        arcpy.management.MakeFeatureLayer(
            "TRACED/HUC_Trace_Flowlines",
            "traced_lines_lyr"
        )

        arcpy.management.CopyFeatures(
            "traced_lines_lyr",
            output_fc
        )

        field_names = [
            f.name
            for f in arcpy.ListFields(
                output_fc
            )
        ]

        if "HUC12" not in field_names:
            arcpy.management.AddField(
                output_fc,
                "HUC12",
                "TEXT",
                field_length=12
            )

        arcpy.management.CalculateField(
            output_fc,
            "HUC12",
            f'"{huc12}"',
            "PYTHON3"
        )

        utils.delete_if_exists(
            start_pts
        )

        utils.delete_if_exists(
            stop_pts
        )

# =============================================================================
# MERGE OUTPUTS
# =============================================================================

def merge_huc12_flowlines(
        output_gdb):
    """
    Merge all HU_* feature classes into a
    single output feature class.
    """

    utils.msg(
        "Merging HUC12 flowlines..."
    )

    arcpy.env.workspace = output_gdb

    feature_classes = arcpy.ListFeatureClasses(
        "HU_*"
    )

    if not feature_classes:

        raise ValueError(
            "No HUC12 flowline feature classes found."
        )

    merged_fc = os.path.join(
        output_gdb,
        "MERGED_Flowlines_by_HU12"
    )

    utils.delete_if_exists(
        merged_fc
    )

    arcpy.management.Merge(
        feature_classes,
        merged_fc
    )

    return merged_fc

# =============================================================================
# QC VALIDATION
# =============================================================================

def validate_identical_lines(
        merged_fc):
    """
    Check merged flowlines for
    identical geometries and
    create a feature class of
    duplicate lines.
    """

    utils.msg(
        "Checking for identical flowlines..."
    )

    output_gdb = os.path.dirname(
        merged_fc
    )

    identical_table = os.path.join(
        output_gdb,
        "QC_Identical_Flowlines_Tbl"
    )

    duplicate_fc = os.path.join(
        output_gdb,
        "QC_Identical_Flowlines"
    )

    utils.delete_if_exists(
        identical_table
    )

    utils.delete_if_exists(
        duplicate_fc
    )

    arcpy.management.FindIdentical(
        merged_fc,
        identical_table,
        ["Shape"],
        output_record_option="ONLY_DUPLICATES"
    )

    identical_count = int(
        arcpy.management.GetCount(
            identical_table
        )[0]
    )

    if identical_count > 0:

        oid_field = arcpy.Describe(
            merged_fc
        ).OIDFieldName

        oids = []

        with arcpy.da.SearchCursor(
                identical_table,
                ["IN_FID"]
        ) as cursor:

            for row in cursor:
                oids.append(
                    str(row[0])
                )

        where_clause = (
            f"{oid_field} IN "
            f"({','.join(oids)})"
        )

        arcpy.analysis.Select(
            merged_fc,
            duplicate_fc,
            where_clause
        )

        utils.warn(
            f"QC WARNING: "
            f"{identical_count} duplicate "
            f"flowline geometries found."
        )

        utils.warn(
            f"Review feature class: "
            f"{duplicate_fc}"
        )

    else:

        utils.msg(
            "No identical flowlines found."
        )

def validate_trace_coverage(
        source_lines,
        merged_fc,
        output_gdb):
    """
    Identify source EDH lines that were
    never attributed to a HUC12.
    """

    utils.msg(
        "Checking for untraced flowlines..."
    )

    untraced_fc = os.path.join(
        output_gdb,
        "QC_Untraced_Flowlines"
    )

    utils.delete_if_exists(
        untraced_fc
    )

    arcpy.analysis.Erase(
        source_lines,
        merged_fc,
        untraced_fc
    )

    untraced_count = int(
        arcpy.management.GetCount(
            untraced_fc
        )[0]
    )

    if untraced_count > 0:

        utils.warn(
            f"QC WARNING: "
            f"{untraced_count} source EDH lines "
            f"were not attributed to a HUC12."
        )

        utils.warn(
            f"Review feature class: "
            f"{untraced_fc}"
        )

    else:

        utils.msg(
            "All source flowlines were attributed."
        )

# =============================================================================
# MAIN
# =============================================================================

def main():

    arcpy.env.overwriteOutput = True

    user_workspace = (
        arcpy.GetParameterAsText(0)
    )

    utils.separator()

    utils.msg(
        "Catchment Toolbox - "
        "02 Attribute Lines By HUC"
    )

    utils.separator()

    pourpoints_fc = (
        utils.get_pourpoints_fc(
            user_workspace
        )
    )

    flowlines_fc = (
        utils.get_edh_lines(
            user_workspace
        )
    )

    scratch_gdb = (
        utils.get_scratch_gdb(
            user_workspace
        )
    )

    output_gdb = (
        create_output_gdb(
            user_workspace
        )
    )

    (
        trace_fd,
        trace_network,
        trace_flowlines
    ) = build_trace_network(
        flowlines_fc,
        scratch_gdb
    )

    trace_huc12s(
        pourpoints_fc,
        trace_network,
        trace_fd,
        trace_flowlines,
        output_gdb
    )

    merged_fc = merge_huc12_flowlines(
        output_gdb
    )

    validate_identical_lines(
        merged_fc
    )

    validate_trace_coverage(
        flowlines_fc,
        merged_fc,
        output_gdb
    )

    utils.delete_if_exists(
        trace_fd
    )

    utils.separator()

    utils.msg(
        "Flowline attribution completed successfully."
    )

    utils.separator()

if __name__ == "__main__":
    main()

