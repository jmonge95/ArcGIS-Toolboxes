import arcpy
import os
import datetime
import shutil

# TBX Tool Parameters
huc8 = arcpy.GetParameterAsText(0)     # Can be single or comma-separated - no spaces
hu_name = arcpy.GetParameterAsText(1)  # Can be single or comma-separated - no spaces

# ---------------------------------------------------------------------------
# Parse and clean multi-value inputs
# ---------------------------------------------------------------------------
# Split into lists
huc8_list = [h.strip() for h in huc8.split(",") if h.strip()]
hu_name_list = [n.strip() for n in hu_name.split(",") if n.strip()]

# Clean HU names for naming (spaces, dashes, commas → underscore)
hu_name_clean_list = [
    n.replace(" ", "_").replace("-", "_").replace(",", "_")
    for n in hu_name_list
]

# Clean HUC8 for naming (commas → underscore)
huc8_clean = "_".join(huc8_list)

# Build combined HU name for naming convention
hu_name_clean_combined = "_".join(hu_name_clean_list)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
agol_url = "https://services2.arcgis.com/AcNHAIhTDPOJkhQF/arcgis/rest/services/Client_Review_Layers_MiHydro/FeatureServer"
backup_folder = r"W:\2025_MI_UP_EDH\17_Edits\!_Client_Review_Snapshot_Backups"
template_gdb_path = r"W:\2023_MI_Statewide_EDH\14_Edits\z_MI_ClientReview_TEMPLATE\TEMPLATE_ClientReviewLayers_NV5.gdb"
main_edits_folder = r"W:\2025_MI_UP_EDH\17_Edits"

# Gather timestamp for naming

today_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
downloaded_gdb_name = f"Client_Review_Layers_MiHydro_{today_str}.gdb"
downloaded_gdb_path = os.path.join(backup_folder, downloaded_gdb_name)

# Automatically gather AGOL credentials from Active Session
portal_url = arcpy.GetActivePortalURL()
arcpy.AddMessage(f"Using active portal session: {portal_url}")

# ---------------------------------------------------------------------------
# ETL From AGOL to Backup GDB
# ---------------------------------------------------------------------------
if not arcpy.Exists(downloaded_gdb_path):
    arcpy.management.CreateFileGDB(backup_folder, f"Client_Review_Layers_MiHydro_{today_str}")
    arcpy.AddMessage(f"Created file geodatabase: {downloaded_gdb_path}")

layer_indices = [0, 1, 2]
layer_names = ["Point", "Polygon", "Line"]

for idx, name in zip(layer_indices, layer_names):
    layer_url = f"{agol_url}/{idx}"
    try:
        arcpy.conversion.FeatureClassToFeatureClass(
            layer_url,
            downloaded_gdb_path,
            f"Client_Review_{name}_MiHydro"
        )
        arcpy.AddMessage(f"Exported {layer_url} to {downloaded_gdb_path}")
    except Exception as e:
        arcpy.AddWarning(f"Failed to export layer {layer_url}: {e}")

# Create HUC8 Edits folder
huc8_folder = os.path.join(main_edits_folder, huc8_clean)
os.makedirs(huc8_folder, exist_ok=True)

# Copy and rename template GDB
new_gdb_name = f"{hu_name_clean_combined}_{huc8_clean}_ClientReviewLayers_NV5.gdb"
new_gdb_path = os.path.join(huc8_folder, new_gdb_name)
shutil.copytree(template_gdb_path, new_gdb_path)
arcpy.AddMessage(f"Template Client Review GDB created for {hu_name_clean_combined}")

# Select HUC8 features (supports multiple)
huc8_layer = "Michigan HU8 Boundaries"

# Build SQL IN clause
huc8_sql_list = [f"'{h}'" for h in huc8_list]
where_clause = f"HUC8 IN ({', '.join(huc8_sql_list)})"

arcpy.AddMessage(f"HUC8 SQL List: {huc8_sql_list}")
arcpy.AddMessage(f"WHERE clause being applied: {where_clause}")

arcpy.management.SelectLayerByAttribute(huc8_layer, "NEW_SELECTION", where_clause)

# Validate that all requested HUC8s were found
selected_huc8s = set()

with arcpy.da.SearchCursor(huc8_layer, ["HUC8"]) as cursor:
    for row in cursor:
        selected_huc8s.add(str(row[0]))

missing_huc8s = [h for h in huc8_list if h not in selected_huc8s]

if missing_huc8s:
    msg = (
        f"The following HUC8 value(s) were not found in "
        f"'Michigan HU8 Boundaries': {', '.join(missing_huc8s)}. "
        f"Please review your input and rerun the tool."
    )
    arcpy.AddError(msg)
    raise Exception(msg)

arcpy.AddMessage(
    f"Validated {len(selected_huc8s)} HUC8(s) successfully."
)

# Append features from downloaded GDB to new GDB
for ftype in layer_names:
    source_fc = os.path.join(downloaded_gdb_path, f"Client_Review_{ftype}_MiHydro")
    target_fc = os.path.join(new_gdb_path, f"Client_Review_{ftype}_NV5")

    arcpy.management.MakeFeatureLayer(source_fc, f"src_{ftype}")
    arcpy.management.SelectLayerByLocation(f"src_{ftype}", "WITHIN_A_DISTANCE", huc8_layer, "500 Meters")

    count = int(arcpy.management.GetCount(f"src_{ftype}")[0])
    if count > 0:
        arcpy.AddMessage(f"Features selected in Client_Review_{ftype}_MiHydro, performing append")
        arcpy.management.Append(f"src_{ftype}", target_fc, "NO_TEST")
    else:
        arcpy.AddWarning(f"No features selected in Client_Review_{ftype}_MiHydro")

arcpy.AddMessage(f"Client Review Layers for {hu_name_clean_combined} are ready for review")

# ---------------------------------------------------------------------------
# Cleanup web reviewer layers
# ---------------------------------------------------------------------------
aprx = arcpy.mp.ArcGISProject("CURRENT")
map_obj = aprx.activeMap

# Clear definition query on HU8 boundaries
hu8_layer_obj = next((lyr for lyr in map_obj.listLayers() if lyr.name == "Michigan HU8 Boundaries"), None)

if hu8_layer_obj:
    try:
        hu8_layer_obj.definitionQuery = None
        arcpy.AddMessage("Cleared definition query on 'Michigan HU8 Boundaries'")
    except Exception as e:
        arcpy.AddWarning(f"Failed to clear definition query on 'Michigan HU8 Boundaries': {e}")
else:
    arcpy.AddWarning("Layer 'Michigan HU8 Boundaries' not found in the active map.")

# Cleanup web reviewer layers
for ftype in layer_names:
    layer_name = f"Client Review {ftype} MiHydro"
    layer = next((lyr for lyr in map_obj.listLayers() if lyr.name == layer_name), None)

    if layer:
        try:
            arcpy.management.SelectLayerByAttribute(
                layer,
                "CLEAR_SELECTION"
            )

            arcpy.management.SelectLayerByLocation(
                layer,
                "INTERSECT",
                huc8_layer
            )

            selected_count = int(arcpy.management.GetCount(layer)[0])

            if selected_count > 0:
                arcpy.management.DeleteFeatures(layer)

                arcpy.AddMessage(
                    f"Deleted {selected_count} intersecting features from {layer_name}"
                )
            else:
                arcpy.AddWarning(
                    f"No intersecting features found in {layer_name}"
                )

        except Exception as e:
            arcpy.AddWarning(
                f"Failed to delete features from {layer_name}: {e}"
            )
    else:
        arcpy.AddWarning(
            f"Layer '{layer_name}' not found in the active map."
        )

# Clear all features from Points, Lines, and Polygons layers
for layer_name in ["Points", "Lines", "Polygons"]:
    layer = next((lyr for lyr in map_obj.listLayers() if lyr.name == layer_name), None)

    if layer:
        try:
            before_count = int(arcpy.management.GetCount(layer)[0])

            # Explicitly select all features
            arcpy.management.SelectLayerByAttribute(
                layer,
                "NEW_SELECTION",
                "1=1"
            )

            selected_count = int(arcpy.management.GetCount(layer)[0])

            if selected_count > 0:
                arcpy.management.DeleteFeatures(layer)

            after_count = int(arcpy.management.GetCount(layer)[0])

            arcpy.AddMessage(
                f"Layer '{layer_name}': "
                f"Before={before_count}, "
                f"Selected={selected_count}, "
                f"After={after_count}"
            )

        except Exception as e:
            arcpy.AddWarning(
                f"Failed to delete features from layer '{layer_name}': {e}"
            )
    else:
        arcpy.AddWarning(f"Layer '{layer_name}' not found in the active map.")
