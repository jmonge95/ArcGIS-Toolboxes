import arcpy
import os

# TBX tool parameters
huc8 = arcpy.GetParameterAsText(0)      # Can be single or comma-separated
hu_name = arcpy.GetParameterAsText(1)   # Can be single or comma-separated
input_gdb = arcpy.GetParameterAsText(2)
review_enddate = arcpy.GetParameterAsText(3)
append_query = arcpy.GetParameter(4)

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

# Combine cleaned HU names for naming
hu_name_clean_combined = "_".join(hu_name_clean_list)

# Clean HUC8 for naming (commas → underscore)
huc8_clean = huc8.replace(",", "_")

# Debug messages
arcpy.AddMessage(f"HU Name Clean Combined: {hu_name_clean_combined}")
arcpy.AddMessage(f"HUC8 Clean Combined: {huc8_clean}")

# ---------------------------------------------------------------------------
# Get current map
# ---------------------------------------------------------------------------
aprx = arcpy.mp.ArcGISProject("CURRENT")
map_obj = aprx.activeMap

# Feature class types
feature_classes = ["Points", "Lines", "Polygons"]

# ---------------------------------------------------------------------------
# Append features to appropriate layers
# ---------------------------------------------------------------------------
for fc_type in feature_classes:
    source_fc = os.path.join(input_gdb, fc_type)

    if not arcpy.Exists(source_fc):
        arcpy.AddWarning(f"{fc_type} not found in input geodatabase, skipping append")
        continue

    count = int(arcpy.management.GetCount(source_fc)[0])
    if count == 0:
        arcpy.AddWarning(f"{fc_type} is empty, skipping append")
        continue

    # Determine target layer
    if append_query:
        target_layer_name = f"{fc_type}_{hu_name_clean_combined}"
        target_layer = next((lyr for lyr in map_obj.listLayers() if lyr.name == target_layer_name), None)

        # If layer doesn't exist, create it from the base layer
        base_layer = next((lyr for lyr in map_obj.listLayers() if lyr.name == fc_type), None)
        if not target_layer and base_layer:
            existing_layer_names = [lyr.name for lyr in map_obj.listLayers()]
            map_obj.addLayer(base_layer)
            new_layers = [lyr for lyr in map_obj.listLayers() if lyr.name not in existing_layer_names]
            if new_layers:
                new_layer = new_layers[0]
                new_layer.name = target_layer_name
                target_layer = new_layer
                arcpy.AddMessage(f"Created new layer: {target_layer_name}")
            else:
                arcpy.AddWarning(f"Failed to identify newly added layer for {fc_type}")
    else:
        target_layer = next((lyr for lyr in map_obj.listLayers() if lyr.name == fc_type), None)

    if target_layer:
        arcpy.AddMessage(f"Appending {fc_type} to layer {target_layer.name}")
        try:
            # Create field mappings
            field_mappings = arcpy.FieldMappings()
            field_mappings.addTable(source_fc)

            # Remove existing mapping for 'Desc_'
            for i in reversed(range(field_mappings.fieldCount)):
                fmap = field_mappings.getFieldMap(i)
                if fmap.outputField.name == "Desc_":
                    field_mappings.removeFieldMap(i)

            # Create new field map for Desc -> Desc_
            fmap = arcpy.FieldMap()
            fmap.addInputField(source_fc, "Desc")
            output_field = fmap.outputField
            output_field.name = "Desc_"
            output_field.aliasName = "Desc"
            fmap.outputField = output_field
            field_mappings.addFieldMap(fmap)

            # Append with field mapping
            arcpy.management.Append(source_fc, target_layer, "NO_TEST", field_mappings)
            arcpy.AddMessage(f"{fc_type} appended successfully to {target_layer.name}")
        except Exception as e:
            arcpy.AddWarning(f"Failed to append {fc_type} to {target_layer.name}: {e}")
    else:
        arcpy.AddWarning(f"Target layer for {fc_type} not found in the map, skipping append")

# ---------------------------------------------------------------------------
# Email message
# ---------------------------------------------------------------------------
message = f"""SUBJECT: Michigan EDH - {hu_name} ({huc8}) Draft Submission
Hello,

The draft EDH dataset for {hu_name} ({huc8}) has been loaded into the data reviewer, which can be accessed via this link.
Additionally, a copy of the geodatabase has been uploaded to the DTMB Sharepoint site.

We plan to pull the draft submission of {hu_name} EDH from the reviewer on COB {review_enddate}.

Thank you,
"""

arcpy.AddMessage(message)
arcpy.AddMessage("Draft data upload complete.")

