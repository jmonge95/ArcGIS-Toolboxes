import arcpy
import math
import os
import networkx as nx

from collections import defaultdict, deque

CLOSED_BASIN = "CLOSED BASIN"


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
    mismatched = []

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
                line_hucs = sorted({str(line_info[fid][1]) for _, fid in candidates})
                mismatched.append((oid, point, start_huc, line_hucs))
                continue

            # Assign matching line's end point, or the end point of closest line the pour point sits on the edge of
            ending = [
                fid for _, fid in huc_lines
                if math.hypot(x - line_info[fid][0][0], y - line_info[fid][0][1]) <= tolerance
            ]
            end = line_info[ending[0] if ending else min(huc_lines)[1]][0]

            start_nodes.append((oid, end, start_huc))

    # Report pour points not on a line of their HUC12, and if another pour point of that HUC12 will be traced instead
    verified_hucs = {node_info[2] for node_info in start_nodes}
    for mismatch_oid, mismatch_point, mismatch_huc, line_hucs in mismatched:
        if mismatch_huc in verified_hucs:
            arcpy.AddWarning(f"Start OID {mismatch_oid} ({mismatch_huc}) is on a line of HUC12 {', '.join(line_hucs)}, "
                             f"HUC12 will be traced from another pour point.")
            issue = "Pour point not on a line of its HUC12, traced from another pour point of the same HUC12"
        else:
            arcpy.AddWarning(f"Start OID {mismatch_oid} ({mismatch_huc}) is on a line of HUC12 {', '.join(line_hucs)}, "
                             f"no other pour point to trace HUC12.")
            issue = "Pour point not on a line of its HUC12, no other pour point to trace HUC12"
        unverified.append((mismatch_point, mismatch_huc, None, issue))

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


def get_wbd(huc_polys_fc, spatial_ref):
    """ Dissolve HUC12 polygons into the WBD extent in the streams spatial reference, returns it and its boundary """

    wbd_dissolve = arcpy.management.Dissolve(huc_polys_fc, "memory/wbd_dissolve")
    with arcpy.da.SearchCursor(wbd_dissolve, ["SHAPE@"], spatial_reference=spatial_ref) as cursor:
        wbd_geom = next(cursor)[0]
    arcpy.management.Delete(wbd_dissolve)

    return wbd_geom, wbd_geom.boundary()


def within_wbd(wbd_geom, wbd_boundary, node, spatial_ref, tolerance):
    """ Sink is completely within the WBD when it is inside it and farther than tolerance from its boundary,
     sinks at the WBD edge are network outlets rather than closed basins """

    node_geom = arcpy.PointGeometry(arcpy.Point(node[0], node[1]), spatial_ref)
    return wbd_geom.contains(node_geom) and wbd_boundary.distanceTo(node_geom) > tolerance


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


def export_unassigned_hucs(huc_polys_fc, poly_huc_fld, assigned, unassigned_reasons, report_no_pour_point):
    """ Write HUC12 polygons not assigned a ToHUC with the reasons they were not, returns the QC feature class.
     HUC12s without a pour point are only reported when all pour points were traced, not a selection """

    qc_polys = arcpy.CreateFeatureclass_management(arcpy.env.workspace, "QC_Unassigned_HUC12", "POLYGON",
                                                   spatial_reference=arcpy.Describe(huc_polys_fc).spatialReference)
    arcpy.AddField_management(qc_polys, "HUC12", "TEXT", field_length=20)
    arcpy.AddField_management(qc_polys, "Reason", "TEXT", field_length=255)

    with arcpy.da.SearchCursor(huc_polys_fc, ["SHAPE@", poly_huc_fld]) as search_cursor, \
            arcpy.da.InsertCursor(qc_polys, ["SHAPE@", "HUC12", "Reason"]) as insert_cursor:
        for shape, huc in search_cursor:
            key = normalize_huc(huc)
            if key in assigned:
                continue
            if key is None:
                reason = "HUC12 polygon has no HUC12 value"
            elif key in unassigned_reasons:
                reason = "; ".join(sorted(unassigned_reasons[key]))
            elif report_no_pour_point:
                reason = "No pour point for HUC12"
            else:
                continue
            arcpy.AddMessage(f"  {key} not assigned: {reason}")
            insert_cursor.insertRow([shape, key, reason[:255]])

    return qc_polys


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
    selection_used = False
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
                    selection_used = True
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
    sinks = []
    for i, (oid, start_node, start_huc) in enumerate(start_nodes, start=1):
        arcpy.AddMessage(f"Tracing start {i}/{total_starts}: HUC12 {start_huc} (OID {oid})")

        # Nothing flows out of the pour point line, checked against the WBD after tracing
        if graph.out_degree(start_node) == 0:
            sinks.append((oid, start_node, start_huc))
            continue

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

    # Sinks completely within the WBD are closed basins, sinks on the WBD boundary keep their existing ToHUC
    closed_basins = []
    if sinks:
        arcpy.AddMessage("Checking sinks against the WBD boundary...")
        wbd_geom, wbd_boundary = get_wbd(huc_polys_fc, spatial_ref)
        for sink_oid, sink_node, sink_huc in sinks:
            if within_wbd(wbd_geom, wbd_boundary, sink_node, spatial_ref, tolerance):
                arcpy.AddWarning(f"Start OID {sink_oid} ({sink_huc}) ends at a sink within the WBD, "
                                 f"possible closed basin.")
                results[sink_huc].append((CLOSED_BASIN, sink_node))
                closed_basins.append((sink_node, sink_huc))
            else:
                arcpy.AddWarning(f"Start OID {sink_oid} ({sink_huc}) ends at a sink on the WBD boundary, "
                                 f"existing ToHUC kept.")
                untraced.append((sink_node, sink_huc, None, "Sink on WBD boundary, existing ToHUC kept"))

    # Resolve one downstream HUC12 per starting HUC12, only different downstream HUC12s conflict
    arcpy.AddMessage("Checking for conflicting downstream HUC12s...")
    assignments = {}
    for huc12, huc_traces in results.items():
        # A downstream HUC12 from any pour point is the outlet, CLOSED BASIN only applies when none was found
        outlet_hucs = {trace_result[0] for trace_result in huc_traces} - {CLOSED_BASIN}
        if len(outlet_hucs) > 1:
            arcpy.AddWarning(f"Starts in {huc12} disagree on downstream HUC12: {sorted(outlet_hucs)}")
            for traced_huc, traced_node in huc_traces:
                if traced_huc in outlet_hucs:
                    conflicts.append((traced_node, huc12, traced_huc, "Starts in same HUC12 disagree"))
            conflict_hucs.add(huc12)
        elif huc12 not in conflict_hucs:
            assignments[huc12] = next(iter(outlet_hucs)) if outlet_hucs else CLOSED_BASIN

    # Closed basins are still flagged for review, including sinks in HUC12s whose outlet was traced elsewhere
    for basin_node, basin_huc in closed_basins:
        basin_assignment = assignments.get(basin_huc)
        if basin_assignment == CLOSED_BASIN:
            untraced.append(
                (basin_node, basin_huc, CLOSED_BASIN, "Possible closed basin within WBD, CLOSED BASIN assigned")
            )
        elif basin_assignment is not None:
            arcpy.AddMessage(f"Sink in {basin_huc} overridden, outlet traced to {basin_assignment} from another "
                             f"pour point.")
            untraced.append(
                (basin_node, basin_huc, basin_assignment, "Sink within WBD, outlet traced from another pour point")
            )
        else:
            untraced.append((basin_node, basin_huc, None, "Sink within WBD, HUC12 outlets conflict"))

    # Output QC shapes to fix
    errors_found = output_qc(untraced, conflicts, spatial_ref)

    # Reasons each HUC12 with a failed pour point was not assigned, HUC12s assigned anyway are skipped later
    unassigned_reasons = defaultdict(set)
    for qc_row in untraced + conflicts:
        if qc_row[1] is not None:
            unassigned_reasons[qc_row[1]].add(qc_row[3])

    # Check if ToHUC field exists in HUC12 polygons, add if missing
    poly_fields = {field.name.lower(): field for field in arcpy.ListFields(huc_polys_fc)}
    if poly_tohuc_fld.lower() not in poly_fields:
        arcpy.AddMessage(f"{poly_tohuc_fld} not found in HUC12 polygons, adding {poly_tohuc_fld} to fields")
        arcpy.AddField_management(huc_polys_fc, poly_tohuc_fld, "TEXT", field_length=12)
        tohuc_type = "String"
        tohuc_length = 12
    else:
        tohuc_type = poly_fields[poly_tohuc_fld.lower()].type
        tohuc_length = poly_fields[poly_tohuc_fld.lower()].length

    # Transfer downstream HUC12 to the polygon matching the starting HUC12
    arcpy.AddMessage("Transferring downstream HUC12 to HUC12 polygons...")
    updated = 0
    matched = set()
    assigned = set()
    if assignments:
        with arcpy.da.UpdateCursor(huc_polys_fc, [poly_huc_fld, poly_tohuc_fld]) as cursor:
            for huc, tohuc in cursor:
                key = normalize_huc(huc)
                if key not in assignments:
                    continue
                matched.add(key)
                if tohuc not in (None, "") and not overwrite_tohuc:
                    assigned.add(key)
                    continue
                value = assignments[key]
                if tohuc_type != "String" and not value.isdigit():
                    unassigned_reasons[key].add(f"{poly_tohuc_fld} field is numeric, cannot store {value}")
                    continue
                if tohuc_type == "String" and len(value) > tohuc_length:
                    unassigned_reasons[key].add(f"{poly_tohuc_fld} field too short to store {value}")
                    continue
                cursor.updateRow([huc, value if tohuc_type == "String" else int(value)])
                assigned.add(key)
                updated += 1

    for missing in sorted(set(assignments) - matched):
        arcpy.AddWarning(f"No HUC12 polygon found for {missing}")

    arcpy.AddMessage(f"{updated} HUC12 polygons updated.")

    # Report HUC12s not assigned a ToHUC and output them as QC polygons
    arcpy.AddMessage("Checking for unassigned HUC12s...")
    unassigned_polys = export_unassigned_hucs(huc_polys_fc, poly_huc_fld, assigned, unassigned_reasons,
                                              not selection_used)
    unassigned_count = int(arcpy.management.GetCount(unassigned_polys)[0])

    if unassigned_count:
        arcpy.AddWarning(f"{unassigned_count} HUC12s not assigned, check QC_Unassigned_HUC12!")
        errors_found = True
    else:
        arcpy.AddMessage("No unassigned HUC12s found.")
        arcpy.management.Delete(unassigned_polys)

    if errors_found:
        arcpy.AddWarning("Some starts or HUC12s need review, check QC shapes in the QC geodatabase!")

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

    main(pour_points, streams, huc_polys, qc_gdb, pour_points_huc_field, stream_huc_field, poly_huc_field, poly_tohuc_field,
         overwrite_existing, snap_tolerance)