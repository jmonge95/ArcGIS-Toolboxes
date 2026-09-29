import arcpy
import os
import datetime
import shutil

# TBX Tool Parameters
huc8 = arcpy.GetParameterAsText(0)
hu_name = arcpy.GetParameterAsText(1)

# Constants - Change as needed for new projects
agol_url = "https://services2.arcgis.com/AcNHAIhTDPOJkhQF/arcgis/rest/services/Client_Review_Layers_MiHydro/FeatureServer"
backup_folder = r"W:\2023_MI_Statewide_EDH\14_Edits\!Client_Review_Snapshot_Backups"
template_gdb_path = r"W:\2023_MI_Statewide_EDH\14_Edits\z_MI_ClientReview_TEMPLATE\TEMPLATE_ClientReviewLayers_NV5.gdb"
main_edits_folder = r"W:\2023_MI_Statewide_EDH\14_Edits"

# Gather YYYYMMDD for standard naming conventions
today_str = datetime.datetime.now().strftime("%Y%m%d")
downloaded_gdb_name = f"Client_Review_Layers_MiHydro_{today_str}.gdb"
downloaded_gdb_path = os.path.join(backup_folder, downloaded_gdb_name)

# Automatically gather AGOL credentials from Active Session
portal_url = arcpy.GetActivePortalURL()
arcpy.AddMessage(f"Using active portal session: {portal_url}")

## ETL From AGOL to Analytics Drive
# Create the output file geodatabase
if not arcpy.Exists(downloaded_gdb_path):
    arcpy.management.CreateFileGDB(backup_folder, f"Client_Review_Layers_MiHydro_{today_str}")
    arcpy.AddMessage(f"Created file geodatabase: {downloaded_gdb_path}")

# Export each layer from AGOL into the new GDB
layer_indices = [0, 1, 2]
layer_names = ["Point", "Polygon", "Line"]

for idx, name in zip(layer_indices, layer_names):
    layer_url = f"{agol_url}/{idx}"
    try:
        arcpy.conversion.FeatureClassToFeatureClass(layer_url, downloaded_gdb_path, f"Client_Review_{name}_MiHydro")
        arcpy.AddMessage(f"Exported {layer_url} to {downloaded_gdb_path}")
    except Exception as e:
        arcpy.AddWarning(f"Failed to export layer {layer_url}: {e}")

# Create HUC8 Edits folder
huc8_folder = os.path.join(main_edits_folder, huc8)
os.makedirs(huc8_folder, exist_ok=True)

# Copy and rename template GDB using standard naming convention
hu_name_clean = hu_name.replace(" ", "_")
new_gdb_name = f"{hu_name_clean}_{huc8}_ClientReviewLayers_NV5.gdb"
new_gdb_path = os.path.join(huc8_folder, new_gdb_name)
shutil.copytree(template_gdb_path, new_gdb_path)
arcpy.AddMessage(f"Template Client Review GDB created for {hu_name}")

# Select HUC8
huc8_layer = "2023_MI_Statewide_EDH_WBDHU8"
arcpy.management.SelectLayerByAttribute(huc8_layer, "NEW_SELECTION", f"huc8 = '{huc8}'")

# Append features from downloaded GDB to Edits GDB
for ftype in layer_names:
    source_fc = os.path.join(downloaded_gdb_path, f"Client_Review_{ftype}_MiHydro")
    target_fc = os.path.join(new_gdb_path, f"Client_Review_{ftype}_NV5")

    arcpy.management.MakeFeatureLayer(source_fc, f"src_{ftype}")
    arcpy.management.SelectLayerByLocation(f"src_{ftype}", "INTERSECT", huc8_layer)

    count = int(arcpy.management.GetCount(f"src_{ftype}")[0])
    if count > 0:
        arcpy.AddMessage(f"Features selected in Client_Review_{ftype}_MiHydro, performing append")
        arcpy.management.Append(f"src_{ftype}", target_fc, "NO_TEST")
    else:
        arcpy.AddWarning(f"No features selected in Client_Review_{ftype}_MiHydro")

arcpy.AddMessage(f"Client Review Layers for {hu_name} are ready for review")

## Cleanup web reviewer layers
# Get current map info
aprx = arcpy.mp.ArcGISProject("CURRENT")
map_obj = aprx.activeMap

# Cleanup web reviewer layers
for ftype in layer_names:
    layer_name = f"Client Review {ftype}_MiHydro"
    
    # Try to get the layer object from the map
    layer = next((lyr for lyr in map_obj.listLayers() if lyr.name == layer_name), None)
    
    if layer:
        try:
            arcpy.management.SelectLayerByLocation(layer, "INTERSECT", huc8_layer)
            arcpy.management.DeleteFeatures(layer)
            arcpy.AddMessage(f"Deleted intersecting features from {layer_name}")
        except Exception as e:
            arcpy.AddWarning(f"Failed to delete features from {layer_name}: {e}")
    else:
        arcpy.AddWarning(f"Layer '{layer_name}' not found in the active map.")


arcpy.AddMessage("Web reviewer cleanup complete")
