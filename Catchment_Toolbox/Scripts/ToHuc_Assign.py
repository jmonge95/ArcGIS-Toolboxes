import arcpy
import os
import sys
import traceback
import networkx as nx

from collections import defaultdict, deque


def normalize_huc(value):
    # HUC12 can be stored as text or numeric, compare everything as text
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    value = str(value).strip()
    return value if value else None


def build_graph(fc, huc_field):
    # Build directed graph from line start and end points with OID and HUC12 stored in edges
    graph = nx.MultiDiGraph()

    with arcpy.da.SearchCursor(fc, ["OID@", "SHAPE@", huc_field]) as cursor:
        for oid, shape, huc in cursor:
            if shape is None:
                continue
            start = (shape.firstPoint.X, shape.firstPoint.Y)
            end = (shape.lastPoint.X, shape.lastPoint.Y)
            graph.add_edge(start, end, oid=oid, huc=normalize_huc(huc))

    return graph


def get_start_hucs(graph, start):
    # HUC12 of the line(s) leaving the start node
    hucs = set()
    for edges in graph[start].values():
        for edge_attrs in edges.values():
            if edge_attrs["huc"] is not None:
                hucs.add(edge_attrs["huc"])
    return hucs


def trace(graph, start, start_huc):
    # BFS processed one level at a time so the first HUC12 change found is the shortest path by segment count,
    # and ties at the same distance can be caught. Visited nodes are never expanded again so loops are ignored.
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


def check_snapped(streams, starts):
    try:
        # Create feature class with unsnapped start points
        starts_to_check = "starts_to_check"

        arcpy.AddMessage("Checking for starts not snapped to stream start vertices...")

        stream_start_points = arcpy.FeatureVerticesToPoints_management(streams, "memory/stream_starts", "START")

        # Run near analysis to find unsnapped starts
        arcpy.Near_analysis(
            in_features=starts,
            near_features=stream_start_points,
            location="NO_LOCATION",
            angle="NO_ANGLE",
            field_names="NEAR_FID NEAR_FID;NEAR_DIST NEAR_DIST",
            distance_unit="Meters",
        )

        starts_layer = arcpy.MakeFeatureLayer_management(starts, "starts_layer")
        unsnapped_starts_expression = "NEAR_DIST <> 0"
        arcpy.SelectLayerByAttribute_management(starts_layer, "NEW_SELECTION", unsnapped_starts_expression)

        unsnapped_starts = int(arcpy.GetCount_management(starts_layer).getOutput(0))

        if unsnapped_starts:
            arcpy.CopyFeatures_management(starts_layer, starts_to_check)
        else:
            if arcpy.Exists(starts_to_check):
                arcpy.Delete_management(starts_to_check)

        arcpy.Delete_management(stream_start_points)
        arcpy.Delete_management(starts_layer)

        if unsnapped_starts > 0:
            arcpy.AddError(
                "Invalid start flags found. Check and ensure points are snapped to the start vertex of a stream. \n"
                "Please check unsnapped error feature shape 'starts_to_check' in the QC geodatabase."
            )
            sys.exit(2)

    except arcpy.ExecuteError:
        arcpy.AddError(arcpy.GetMessages(2))
        traceb = traceback.format_exc()
        arcpy.AddError("ArcGIS error in checking start points. Please check data or parameters.")
        arcpy.AddError(traceb)

    except Exception as err:
        arcpy.AddError(f"A Python error occurred: {err}")
        traceb = traceback.format_exc()
        arcpy.AddError(traceb)


def export_qc_points(name, rows, spatial_ref):
    # Write QC points with the start and downstream HUC12 and the reason for review
    if not rows:
        if arcpy.Exists(name):
            arcpy.Delete_management(name)
        return False

    arcpy.CreateFeatureclass_management(arcpy.env.workspace, name, "POINT", spatial_reference=spatial_ref)
    arcpy.AddField_management(name, "Start_HUC", "TEXT", field_length=100)
    arcpy.AddField_management(name, "Down_HUC", "TEXT", field_length=100)
    arcpy.AddField_management(name, "Issue", "TEXT", field_length=100)

    with arcpy.da.InsertCursor(name, ["SHAPE@", "Start_HUC", "Down_HUC", "Issue"]) as insert_cursor:
        for (x, y), start_huc, down_huc, issue in rows:
            insert_cursor.insertRow([arcpy.Point(x, y), start_huc, down_huc, issue])

    return True


def main(starts_fc, streams, huc_polys, qc_gdb, stream_huc_field, poly_huc_field, poly_tohuc_field,
         overwrite_existing):
    arcpy.AddMessage("HUC12 downstream trace beginning processing...")

    # Arcpy environment settings
    arcpy.env.overwriteOutput = True
    arcpy.env.workspace = qc_gdb
    starts = starts_fc
    spatial_ref = arcpy.Describe(streams).spatialReference

    # Check if there is a selection in the starts, and modify the starts to only use selected values
    arcpy.AddMessage("Checking for map and start selection....")
    starts_basename = os.path.basename(starts_fc).lower()
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
                    starts = arcpy.CopyFeatures_management(layer, "memory/starts_selected")
                break
    except Exception:
        arcpy.AddMessage("No map found open, skipping start selection check.")

    # Check starts are properly snapped
    check_snapped(streams, starts)
    arcpy.AddMessage("Starts are snapped to streams.")

    # Build directed graph
    arcpy.AddMessage("Building directional graph from streams...")
    graph = build_graph(streams, stream_huc_field)
    arcpy.AddMessage("Directional graph built from streams.")

    # Collect start nodes
    start_nodes = []
    with arcpy.da.SearchCursor(starts, ["OID@", "SHAPE@X", "SHAPE@Y"]) as cursor:
        for oid, x, y in cursor:
            start_nodes.append((oid, (x, y)))
    total_starts = len(start_nodes)

    # Trace downstream from each start until the HUC12 changes
    arcpy.AddMessage("Beginning tracing of starts downstream...")
    results = defaultdict(list)
    untraced = []
    conflicts = []
    conflict_hucs = set()
    for i, (oid, start) in enumerate(start_nodes, start=1):
        arcpy.AddMessage(f"Tracing start {i}/{total_starts}: OID {oid}")

        if start not in graph:
            arcpy.AddWarning(f"Start OID {oid} not found as a stream node.")
            untraced.append((start, None, None, "Start not on stream node"))
            continue

        start_hucs = get_start_hucs(graph, start)
        if len(start_hucs) != 1:
            arcpy.AddWarning(f"Start OID {oid} has {len(start_hucs)} HUC12 values on its starting line(s).")
            untraced.append((start, ", ".join(sorted(start_hucs)) or None, None, "Starting HUC12 missing or ambiguous"))
            continue
        start_huc = next(iter(start_hucs))

        found = trace(graph, start, start_huc)
        if not found:
            arcpy.AddWarning(f"No different HUC12 found downstream of start OID {oid} ({start_huc}).")
            untraced.append((start, start_huc, None, "No downstream HUC12 found"))
            continue
        if len(found) > 1:
            arcpy.AddWarning(f"Start OID {oid} ({start_huc}) reaches multiple HUC12s at equal distance: {sorted(found)}")
            conflicts.append((start, start_huc, ", ".join(sorted(found)), "Tie at equal distance"))
            conflict_hucs.add(start_huc)
            continue

        results[start_huc].append((next(iter(found)), start))
    arcpy.AddMessage("Tracing of starts downstream complete.")

    # Resolve one downstream HUC12 per starting HUC12, multiple starts in the same HUC12 must agree
    arcpy.AddMessage("Checking for conflicting downstream HUC12s...")
    for start_huc, traces in results.items():
        down_hucs = {down_huc for down_huc, _ in traces}
        if len(down_hucs) > 1:
            arcpy.AddWarning(f"Starts in {start_huc} disagree on downstream HUC12: {sorted(down_hucs)}")
            for down_huc, start in traces:
                conflicts.append((start, start_huc, down_huc, "Starts in same HUC12 disagree"))
            conflict_hucs.add(start_huc)

    assignments = {
        start_huc: traces[0][0] for start_huc, traces in results.items() if start_huc not in conflict_hucs
    }

    # Output QC shapes to fix
    errors_found = False
    if export_qc_points("QC_Untraced_Points", untraced, spatial_ref):
        arcpy.AddMessage("Untraced start points exported as QC_Untraced_Points")
        errors_found = True
    else:
        arcpy.AddMessage("No untraced starts found.")

    if export_qc_points("QC_Conflict_Points", conflicts, spatial_ref):
        arcpy.AddMessage("Conflicting start points exported as QC_Conflict_Points, these HUC12s are not updated.")
        errors_found = True
    else:
        arcpy.AddMessage("No conflicting starts found.")

    # Check if ToHUC field exists in HUC12 polygons, add if missing
    poly_fields = {field.name.lower(): field for field in arcpy.ListFields(huc_polys)}
    if poly_tohuc_field.lower() not in poly_fields:
        arcpy.AddMessage(f"{poly_tohuc_field} not found in HUC12 polygons, adding {poly_tohuc_field} to fields")
        arcpy.AddField_management(huc_polys, poly_tohuc_field, "TEXT", field_length=12)
        tohuc_type = "String"
    else:
        tohuc_type = poly_fields[poly_tohuc_field.lower()].type

    # Transfer downstream HUC12 to the polygon matching the starting HUC12
    arcpy.AddMessage("Transferring downstream HUC12 to HUC12 polygons...")
    updated = 0
    matched = set()
    if assignments:
        with arcpy.da.UpdateCursor(huc_polys, [poly_huc_field, poly_tohuc_field]) as cursor:
            for huc, tohuc in cursor:
                key = normalize_huc(huc)
                if key not in assignments:
                    continue
                matched.add(key)
                if tohuc not in (None, "") and not overwrite_existing:
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
        starts_fc = arcpy.GetParameterAsText(0)
        streams = arcpy.GetParameterAsText(1)
        huc_polys = arcpy.GetParameterAsText(2)
        qc_gdb = arcpy.GetParameterAsText(3)
        stream_huc_field = arcpy.GetParameterAsText(4)
        poly_huc_field = arcpy.GetParameterAsText(5)
        poly_tohuc_field = arcpy.GetParameterAsText(6)
        overwrite_existing = arcpy.GetParameter(7)
    else:
        starts_fc = r""
        streams = r""
        huc_polys = r""
        qc_gdb = r""

        stream_huc_field = "HUC12"
        poly_huc_field = "HUC12"
        poly_tohuc_field = "ToHUC"
        overwrite_existing = True

    main(starts_fc, streams, huc_polys, qc_gdb, stream_huc_field, poly_huc_field, poly_tohuc_field,
         overwrite_existing)