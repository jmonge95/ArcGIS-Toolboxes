import arcpy
import math
import os
import networkx as nx

from collections import defaultdict, deque


def normalize_huc(value):
    """ HUC12 can be stored as text or numeric, compare everything as text """

    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    value = str(value).strip()
    return value if value else None


def node_key(x, y, decimals=4):
    """ Round coordinates so nodes that should be coincident but differ by float noise or tolerance """

    return round(x, decimals), round(y, decimals)


def build_graph(fc, huc_field):
    """ Build directed graph from line start and end points with OID and HUC12 stored in edges """

    graph = nx.MultiDiGraph()

    with arcpy.da.SearchCursor(fc, ["OID@", "SHAPE@", huc_field]) as cursor:
        for oid, shape, huc in cursor:
            if shape is None:
                continue
            start = node_key(shape.firstPoint.X, shape.firstPoint.Y)
            end = node_key(shape.lastPoint.X, shape.lastPoint.Y)
            graph.add_edge(start, end, oid=oid, huc=normalize_huc(huc))

    return graph


def verify_starts(graph, pour_points_fc, streams_fc, spatial_ref, pour_points_huc_fld, tolerance):
    """ Starts are HUC12 pour points with their HUC12 in pour_points_huc_fld. Each is verified to sit on the end
     node or edge of a line of its HUC12, and the trace begins from that line's end node. Start coordinates
     are read in the streams spatial reference so they match the graph nodes. Starts that fail
     verification are returned as untraced QC rows instead of being traced """

    # Get all lines within tolerance to account for matching edges and snapping tolerance errors
    near_table = arcpy.GenerateNearTable_analysis(
        pour_points_fc, streams_fc, "memory/start_near", search_radius=str(tolerance), closest="ALL", closest_count=0
    )
    start_lines = defaultdict(list)
    with arcpy.da.SearchCursor(near_table, ["IN_FID", "NEAR_FID", "NEAR_DIST"]) as cursor:
        for in_fid, near_fid, near_dist in cursor:
            if near_dist <= tolerance:
                start_lines[in_fid].append((near_dist, near_fid))
    arcpy.Delete_management(near_table)

    line_info = {edge_attrs["oid"]: (end, edge_attrs["huc"]) for _, end, edge_attrs in graph.edges(data=True)}
    start_nodes = []
    unverified = []

    with arcpy.da.SearchCursor(pour_points_fc, ["OID@", "SHAPE@X", "SHAPE@Y", pour_points_huc_fld],
                               spatial_reference=spatial_ref) as cursor:
        for oid, x, y, huc in cursor:
            point = node_key(x, y)
            start_huc = normalize_huc(huc)
            # Check that huc12 value has been assigned to pour point
            if start_huc is None:
                arcpy.AddWarning(f"Start OID {oid} has no HUC12 value.")
                unverified.append((point, None, None, "Pour point HUC12 missing"))
                continue

            # Get the lines whose pour point is snapped within tolerance
            candidates = [(dist, fid) for dist, fid in start_lines.get(oid, []) if fid in line_info]
            if not candidates:
                arcpy.AddWarning(f"Start OID {oid} ({start_huc}) is not snapped to a stream.")
                unverified.append((point, start_huc, None, "Start not snapped to stream"))
                continue

            # Use only lines of the pour point's own HUC12, other HUC12 lines meeting at the same node are ignored
            huc_lines = [(dist, fid) for dist, fid in candidates if line_info[fid][1] == start_huc]
            if not huc_lines:
                arcpy.AddWarning(f"Start OID {oid} ({start_huc}) is not on a line of its HUC12.")
                unverified.append((point, start_huc, None, "Pour point not on a line of its HUC12"))
                continue

            # Assign matching line's end point, or the end point of closest line the pour point sits on the edge of
            ending = [
                fid for _, fid in huc_lines
                if math.hypot(x - line_info[fid][0][0], y - line_info[fid][0][1]) <= tolerance
            ]
            end = line_info[ending[0] if ending else min(huc_lines)[1]][0]

            start_nodes.append((oid, end, start_huc))

    return start_nodes, unverified


def trace(graph, start, start_huc):
    """ BFS processed one level at a time so the first HUC12 change found is the shortest path by segment count,
     and ties at the same distance can be caught. Visited nodes are never expanded again so loops are ignored """

    visited = {start}
    queue = deque([start])

    while queue:
        found = set()
        for _ in range(len(queue)):
            node = queue.popleft()

            for successor, edges in graph[node].items():
                for edge_attrs in edges.values():
                    huc = edge_attrs["huc"]

                    # Stop on the first line with a different HUC12, null HUC12 lines are passed through
                    if huc is not None and huc != start_huc:
                        found.add(huc)
                        continue
                    if successor in visited:
                        continue

                    visited.add(successor)
                    queue.append(successor)

        if found:
            return found

    return set()


def export_qc_points(name, rows, spatial_ref):
    """ Write QC points with the start and downstream HUC12 and the reason for review """

    qc_points = arcpy.CreateFeatureclass_management(arcpy.env.workspace, name, "POINT", spatial_reference=spatial_ref)
    arcpy.AddField_management(qc_points, "Start_HUC", "TEXT", field_length=100)
    arcpy.AddField_management(qc_points, "Down_HUC", "TEXT", field_length=100)
    arcpy.AddField_management(qc_points, "Issue", "TEXT", field_length=100)

    with arcpy.da.InsertCursor(qc_points, ["SHAPE@", "Start_HUC", "Down_HUC", "Issue"]) as insert_cursor:
        for (x, y), start_huc, down_huc, issue in rows:
            insert_cursor.insertRow([arcpy.Point(x, y), start_huc, down_huc, issue])

    return qc_points


def output_qc(untraced, conflicts, spatial_ref):
    """ Output QC shapes to fix, returns True if any errors were found """

    errors_found = False

    untraced_pts = export_qc_points("QC_Untraced_Points", untraced, spatial_ref)
    untraced_count = int(arcpy.management.GetCount(untraced_pts)[0])

    if untraced_count:
        arcpy.AddWarning(f"{untraced_count} untraced start points found, check QC_Untraced_Points!")
        errors_found = True
    else:
        arcpy.AddMessage("No untraced starts found.")
        arcpy.management.Delete(untraced_pts)

    conflict_pts = export_qc_points("QC_Conflict_Points", conflicts, spatial_ref)
    conflict_count = int(arcpy.management.GetCount(conflict_pts)[0])

    if conflict_count:
        arcpy.AddWarning(f"{conflict_count} conflicting start points found, check QC_Conflict_Points! "
                         f"These HUC12s are not updated.")
        errors_found = True
    else:
        arcpy.AddMessage("No conflicting starts found.")
        arcpy.management.Delete(conflict_pts)

    return errors_found


def main(pour_points_fc, streams_fc, huc_polys_fc, qc_workspace, pour_points_huc_fld, stream_huc_fld, poly_huc_fld,
         poly_tohuc_fld, overwrite_tohuc, tolerance):
    arcpy.AddMessage("HUC12 downstream trace beginning processing...")

    # Arcpy environment settings
    arcpy.env.overwriteOutput = True
    arcpy.env.workspace = qc_workspace
    spatial_ref = arcpy.Describe(streams_fc).spatialReference

    # Check if there is a selection in the starts, and modify the starts to only use selected values
    arcpy.AddMessage("Checking for map and start selection....")
    trace_points = pour_points_fc
    starts_basename = os.path.basename(pour_points_fc).lower()
    try:
        project = arcpy.mp.ArcGISProject("CURRENT")
        active_map = project.activeMap
        for layer in active_map.listLayers():
            layer_name = layer.name.lower()
            if layer.supports("DATASOURCE"):
                layer_source_basename = os.path.basename(layer.dataSource).lower()
            else:
                layer_source_basename = ""
            if layer_name == starts_basename or layer_source_basename == starts_basename:
                selected_features = layer.getSelectionSet()
                if selected_features:
                    arcpy.AddMessage("Using selected starts only as start points for trace.")
                    trace_points = arcpy.CopyFeatures_management(layer, "memory/starts_selected")
                break
    except Exception:
        arcpy.AddMessage("No map found open, skipping start selection check.")

    # Build directed graph
    arcpy.AddMessage("Building directional graph from streams...")
    graph = build_graph(streams_fc, stream_huc_fld)
    arcpy.AddMessage("Directional graph built from streams.")

    # Collect start nodes, starts that fail verification go straight to untraced QC
    arcpy.AddMessage("Resolving start nodes from streams...")
    start_nodes, untraced = verify_starts(graph, trace_points, streams_fc, spatial_ref, pour_points_huc_fld, tolerance)
    total_starts = len(start_nodes)

    # Trace downstream from each start until the HUC12 changes
    arcpy.AddMessage("Beginning tracing of starts downstream...")
    results = defaultdict(list)
    conflicts = []
    conflict_hucs = set()
    for i, (oid, start_node, start_huc) in enumerate(start_nodes, start=1):
        arcpy.AddMessage(f"Tracing start {i}/{total_starts}: HUC12 {start_huc} (OID {oid})")

        found = trace(graph, start_node, start_huc)
        if not found:
            arcpy.AddWarning(f"No different HUC12 found downstream of start OID {oid} ({start_huc}).")
            untraced.append((start_node, start_huc, None, "No downstream HUC12 found"))
            continue
        if len(found) > 1:
            arcpy.AddWarning(f"Start OID {oid} ({start_huc}) reaches multiple HUC12s at equal distance: {sorted(found)}")
            conflicts.append((start_node, start_huc, ", ".join(sorted(found)), "Tie at equal distance"))
            conflict_hucs.add(start_huc)
            continue

        down_huc = next(iter(found))
        arcpy.AddMessage(f"  {start_huc} -> {down_huc}")
        results[start_huc].append((down_huc, start_node))
    arcpy.AddMessage("Tracing of starts downstream complete.")

    # Resolve one downstream HUC12 per starting HUC12, multiple starts in the same HUC12 must agree
    arcpy.AddMessage("Checking for conflicting downstream HUC12s...")
    assignments = {}
    for huc12, huc_traces in results.items():
        traced_down_hucs = {trace_result[0] for trace_result in huc_traces}
        if len(traced_down_hucs) > 1:
            arcpy.AddWarning(f"Starts in {huc12} disagree on downstream HUC12: {sorted(traced_down_hucs)}")
            for traced_huc, traced_node in huc_traces:
                conflicts.append((traced_node, huc12, traced_huc, "Starts in same HUC12 disagree"))
            conflict_hucs.add(huc12)
        elif huc12 not in conflict_hucs:
            assignments[huc12] = huc_traces[0][0]

    # Output QC shapes to fix
    errors_found = output_qc(untraced, conflicts, spatial_ref)

    # Check if ToHUC field exists in HUC12 polygons, add if missing
    poly_fields = {field.name.lower(): field for field in arcpy.ListFields(huc_polys_fc)}
    if poly_tohuc_fld.lower() not in poly_fields:
        arcpy.AddMessage(f"{poly_tohuc_fld} not found in HUC12 polygons, adding {poly_tohuc_fld} to fields")
        arcpy.AddField_management(huc_polys_fc, poly_tohuc_fld, "TEXT", field_length=12)
        tohuc_type = "String"
    else:
        tohuc_type = poly_fields[poly_tohuc_fld.lower()].type

    # Transfer downstream HUC12 to the polygon matching the starting HUC12
    arcpy.AddMessage("Transferring downstream HUC12 to HUC12 polygons...")
    updated = 0
    matched = set()
    if assignments:
        with arcpy.da.UpdateCursor(huc_polys_fc, [poly_huc_fld, poly_tohuc_fld]) as cursor:
            for huc, tohuc in cursor:
                key = normalize_huc(huc)
                if key not in assignments:
                    continue
                matched.add(key)
                if tohuc not in (None, "") and not overwrite_tohuc:
                    continue
                value = assignments[key] if tohuc_type == "String" else int(assignments[key])
                cursor.updateRow([huc, value])
                updated += 1

    for missing in sorted(set(assignments) - matched):
        arcpy.AddWarning(f"No HUC12 polygon found for {missing}")

    arcpy.AddMessage(f"{updated} HUC12 polygons updated.")

    if errors_found:
        arcpy.AddWarning("Some starts were not transferred due to errors, check QC shapes in the QC geodatabase!")

    arcpy.AddMessage("HUC12 downstream trace finished processing!")

    return


if __name__ == "__main__":
    # Use toolbox parameters when run as a script tool, otherwise fall back to the paths below
    if arcpy.GetParameterAsText(0):
        pour_points = arcpy.GetParameterAsText(0)
        streams = arcpy.GetParameterAsText(1)
        huc_polys = arcpy.GetParameterAsText(2)
        qc_gdb = arcpy.GetParameterAsText(3)
        stream_huc_field = arcpy.GetParameterAsText(4)
        poly_huc_field = arcpy.GetParameterAsText(5)
        poly_tohuc_field = arcpy.GetParameterAsText(6)
        overwrite_existing = arcpy.GetParameter(7)
        snap_tolerance = arcpy.GetParameter(8)
        pour_points_huc_field = arcpy.GetParameterAsText(9)
    else:
        pour_points = r""
        streams = r""
        huc_polys = r""
        qc_gdb = r""

        pour_points_huc_field = "HUC12"
        stream_huc_field = "HUC12"
        poly_huc_field = "HUC12"
        poly_tohuc_field = "ToHUC"
        overwrite_existing = True
        snap_tolerance = 0.001  # in streams map units

    main(pour_points, streams, huc_polys, qc_gdb, pour_points_huc_field, stream_huc_field, poly_huc_field,
         poly_tohuc_field, overwrite_existing, snap_tolerance)