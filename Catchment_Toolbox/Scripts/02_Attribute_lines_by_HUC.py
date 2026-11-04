"""
02_Attribute_Lines_By_HUC_graph.py

Catchment Toolbox

Purpose:
    Traces EDH flowlines upstream from each
    QA/QC'd HU12 pour point and exports
    one flowline feature class per HU12.
    Traces run on an in memory networkx graph
    instead of a trace network.

Parameter:
    0 - User Workspace
"""

import math
import os
import arcpy
import networkx as nx
import catchment_utils as utils

from collections import defaultdict, deque

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
# FLOWLINE GRAPH
# =============================================================================

def node_key(x, y, decimals=4):
    """ Round coordinates so nodes that should be coincident but differ by float noise or tolerance """

    return round(x, decimals), round(y, decimals)


def build_flowline_graph(flowlines_fc):
    """ Build directed graph from flowline start and end points with OIDs stored in edges. Flow follows the
     digitized direction like the trace network, and lines only connect at their endpoints like simple edges """

    utils.msg("Building flowline graph...")

    graph = nx.MultiDiGraph()
    line_nodes = {}

    with arcpy.da.SearchCursor(flowlines_fc, ["OID@", "SHAPE@"]) as cursor:
        for oid, shape in cursor:
            if shape is None:
                continue
            start = node_key(shape.firstPoint.X, shape.firstPoint.Y)
            end = node_key(shape.lastPoint.X, shape.lastPoint.Y)
            graph.add_edge(start, end, oid=oid)
            line_nodes[oid] = (start, end)

    return graph, line_nodes


def locate_pour_points(pourpoints_fc, flowlines_fc, line_nodes, sr, tolerance):
    """ Locate each pour point on the flowlines within XY tolerance like trace network starting points and
     barriers. Points on a line endpoint are on that junction, points along a line are on that edge. Returns
     (OID, HUC12, junction node or None, edge OIDs) per pour point """

    near_table = arcpy.analysis.GenerateNearTable(
        pourpoints_fc, flowlines_fc, "memory/pourpoint_near", search_radius=str(tolerance), closest="ALL",
        closest_count=0
    )
    point_lines = defaultdict(list)
    with arcpy.da.SearchCursor(near_table, ["IN_FID", "NEAR_FID"]) as cursor:
        for in_fid, near_fid in cursor:
            if near_fid in line_nodes:
                point_lines[in_fid].append(near_fid)
    arcpy.management.Delete(near_table)

    locations = []
    with arcpy.da.SearchCursor(pourpoints_fc, ["OID@", "SHAPE@X", "SHAPE@Y", "HUC12"],
                               spatial_reference=sr) as cursor:
        for oid, x, y, huc12 in cursor:
            near_lines = point_lines.get(oid, [])
            junction = next(
                (node for fid in near_lines for node in line_nodes[fid]
                 if math.hypot(x - node[0], y - node[1]) <= tolerance),
                None
            )
            locations.append((oid, huc12, junction, [] if junction is not None else near_lines))

    return locations

# =============================================================================
# TRACE EACH HUC12
# =============================================================================

def trace_upstream(graph, line_nodes, starts, barrier_nodes, barrier_edges):
    """ Upstream BFS against the digitized direction like the trace network UPSTREAM trace with barriers excluded.
     A barrier on a junction stops the trace there, a barrier along a line stops the trace before that line and
     leaves it out. A barrier on a starting junction blocks that start, since the trace network does not ignore
     barriers at starting points by default. Returns the set of traced flowline OIDs """

    traced = set()
    visited = set()
    queue = deque()

    for junction, edge_oids in starts:
        if junction is not None:
            if junction not in barrier_nodes and junction not in visited:
                visited.add(junction)
                queue.append(junction)
            continue

        # Starting along a line includes that line, then continues from its upstream end
        for edge_oid in edge_oids:
            traced.add(edge_oid)
            upstream_end = line_nodes[edge_oid][0]
            if edge_oid in barrier_edges or upstream_end in barrier_nodes or upstream_end in visited:
                continue
            visited.add(upstream_end)
            queue.append(upstream_end)

    while queue:
        node = queue.popleft()

        for upstream_node, _, edge_attrs in graph.in_edges(node, data=True):
            if edge_attrs["oid"] in barrier_edges:
                continue
            traced.add(edge_attrs["oid"])
            if upstream_node in barrier_nodes or upstream_node in visited:
                continue
            visited.add(upstream_node)
            queue.append(upstream_node)

    return traced


def trace_huc12s(graph, line_nodes, locations):
    """ Trace flowlines upstream for each HUC12 from its pour points, with the pour points of every other HUC12 as
     barriers. Returns the traced flowline OIDs per HUC12 """

    utils.msg("Creating HUC12 traces...")

    huc12_values = sorted({location[1] for location in locations if location[1]})
    huc_oids = {}

    for huc12 in huc12_values:
        utils.msg(f"Tracing {huc12}")

        starts = [(location[2], location[3]) for location in locations if location[1] == huc12]

        # Null HUC12 pour points are not barriers, matching the HUC12 <> SQL used for the trace network barriers
        barrier_nodes = set()
        barrier_edges = set()
        for _, point_huc, junction, edge_oids in locations:
            if point_huc is None or point_huc == huc12:
                continue
            if junction is not None:
                barrier_nodes.add(junction)
            barrier_edges.update(edge_oids)

        traced = trace_upstream(graph, line_nodes, starts, barrier_nodes, barrier_edges)

        if not traced:
            located = [start for start in starts if start[0] is not None or start[1]]
            if not located:
                reason = "pour point is not on a flowline"
            elif all(start[0] in barrier_nodes for start in located):
                reason = "pour point shares a junction with another HUC12 pour point"
            else:
                reason = "no flowlines upstream of pour point"
            utils.warn(f"No flowlines traced for {huc12}, {reason}.")

        huc_oids[huc12] = traced

    return huc_oids

# =============================================================================
# WRITE OUTPUTS
# =============================================================================

def write_huc12_flowlines(flowlines_fc, huc_oids, output_gdb, sr):
    """ Write the traced flowlines of every HUC12 to the merged feature class in one pass over the flowlines, then
     select each HUC12 into its own HU_ feature class. Flowlines traced by more than one HUC12 are written once per
     HUC12 like the trace network outputs, so the identical flowline QC still catches them """

    utils.msg("Writing HUC12 flowlines...")

    if not huc_oids:
        raise ValueError("No HUC12 flowline feature classes found.")

    merged_fc = os.path.join(output_gdb, "MERGED_Flowlines_by_HU12")
    utils.delete_if_exists(merged_fc)
    arcpy.management.CreateFeatureclass(
        output_gdb, "MERGED_Flowlines_by_HU12", "POLYLINE", template=flowlines_fc, has_m="SAME_AS_TEMPLATE",
        has_z="SAME_AS_TEMPLATE", spatial_reference=sr
    )

    # Copy every editable attribute, HUC12 is added when the flowlines do not already have it
    copy_fields = [field.name for field in arcpy.ListFields(flowlines_fc)
                   if field.editable and field.type not in ("OID", "Geometry", "GlobalID")]
    huc_field = next((name for name in copy_fields if name.upper() == "HUC12"), None)
    if huc_field is None:
        huc_field = "HUC12"
        arcpy.management.AddField(merged_fc, huc_field, "TEXT", field_length=12)
        insert_fields = ["SHAPE@"] + copy_fields + [huc_field]
    else:
        insert_fields = ["SHAPE@"] + copy_fields
    huc_index = insert_fields.index(huc_field)
    huc_padding = [None] * (len(insert_fields) - len(copy_fields) - 1)

    oid_hucs = defaultdict(list)
    for traced_huc in sorted(huc_oids):
        for traced_oid in huc_oids[traced_huc]:
            oid_hucs[traced_oid].append(traced_huc)

    with arcpy.da.SearchCursor(flowlines_fc, ["OID@", "SHAPE@"] + copy_fields) as search_cursor, \
            arcpy.da.InsertCursor(merged_fc, insert_fields) as insert_cursor:
        for source_row in search_cursor:
            for row_huc in oid_hucs.get(source_row[0], []):
                merged_row = list(source_row[1:]) + huc_padding
                merged_row[huc_index] = row_huc
                insert_cursor.insertRow(merged_row)

    # Index HUC12 so each HU_ selection does not scan the whole merged feature class
    arcpy.management.AddIndex(merged_fc, huc_field, "HUC12_IDX")
    huc_sql_field = arcpy.AddFieldDelimiters(merged_fc, huc_field)
    for huc12 in sorted(huc_oids):
        output_fc = os.path.join(output_gdb, f"HU_{huc12}")
        utils.delete_if_exists(output_fc)
        arcpy.analysis.Select(merged_fc, output_fc, f"{huc_sql_field} = '{huc12}'")

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
        ).getOutput(0)
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

        utils.delete_if_exists(
            identical_table
        )

        utils.delete_if_exists(
            duplicate_fc
        )

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
        ).getOutput(0)
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

        utils.delete_if_exists(
            untraced_fc
        )

        utils.msg(
            "All source flowlines were attributed."
        )

# =============================================================================
# MAIN
# =============================================================================

def main(user_workspace):

    arcpy.env.overwriteOutput = True

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

    output_gdb = (
        create_output_gdb(
            user_workspace
        )
    )

    # Trace network topology connects within the XY tolerance, so pour points are located with it too
    sr = arcpy.Describe(flowlines_fc).spatialReference
    tolerance = sr.XYTolerance

    graph, line_nodes = build_flowline_graph(flowlines_fc)

    locations = locate_pour_points(pourpoints_fc, flowlines_fc, line_nodes, sr, tolerance)

    huc_oids = trace_huc12s(graph, line_nodes, locations)

    merged_fc = write_huc12_flowlines(flowlines_fc, huc_oids, output_gdb, sr)

    validate_identical_lines(
        merged_fc
    )

    validate_trace_coverage(
        flowlines_fc,
        merged_fc,
        output_gdb
    )

    utils.separator()

    utils.msg(
        "Flowline attribution completed successfully."
    )

    utils.separator()

if __name__ == "__main__":
    # Use toolbox parameter when run as a script tool, otherwise fall back to the path below
    if arcpy.GetParameterAsText(0):
        workspace_path = arcpy.GetParameterAsText(0)
    else:
        workspace_path = r""

    main(workspace_path)