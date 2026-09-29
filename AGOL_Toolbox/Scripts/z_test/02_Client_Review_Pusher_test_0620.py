import arcpy
import os
import datetime

# TBX tool parameters
huc8 = arcpy.GetParameterAsText(0)
hu_name = arcpy.GetParameterAsText(1)
input_gdb = arcpy.GetParameterAsText(2)
review_enddate = arcpy.GetParameterAsText(4)

# Clean HU name for messages
hu_name_clean = hu_name.replace(" ", "_").replace("-", "_")

# Get current map info
aprx = arcpy.mp.ArcGISProject("CURRENT")
map_obj = aprx.activeMap

# Feature class names and corresponding map layer names
feature_classes = ["Points", "Lines", "Polygons"]

# Append each feature class to the corresponding map layer
for fc_name in feature_classes:
    source_fc = os.path.join(input_gdb, fc_name)
    target_layer = next((lyr for lyr in map_obj.listLayers() if lyr.name == fc_name), None)

    if not arcpy.Exists(source_fc):
        arcpy.AddWarning(f"{fc_name} not found in input geodatabase, skipping append")
        continue

    count = int(arcpy.management.GetCount(source_fc)[0])
    if count == 0:
        arcpy.AddWarning(f"{fc_name} empty, skipping append")
        continue

    if target_layer:
        arcpy.AddMessage(f"Appending draft {fc_name} to web map layer")
        try:
            # Create field mappings
            field_mappings = arcpy.FieldMappings()
            field_mappings.addTable(source_fc)

            # Remove any existing mapping for 'Desc_'
            for i in reversed(range(field_mappings.fieldCount)):
                fmap = field_mappings.getFieldMap(i)
                if fmap.outputField.name == "Desc_":
                    field_mappings.removeFieldMap(i)

            # Create a new field map for Desc_ -> Desc
            fmap = arcpy.FieldMap()
            fmap.addInputField(source_fc, "Desc")
            output_field = fmap.outputField
            output_field.name = "Desc_"
            output_field.aliasName = "Desc"
            fmap.outputField = output_field
            field_mappings.addFieldMap(fmap)

            # Perform append with custom field mapping
            arcpy.management.Append(source_fc, target_layer, "NO_TEST", field_mappings)
            arcpy.AddMessage(f"{fc_name} appended successfully!")
        except Exception as e:
            arcpy.AddWarning(f"Failed to append {fc_name}: {e}")
    else:
        arcpy.AddWarning(f"Target layer '{fc_name}' not found in the map, skipping append")

#Final message
arcpy.AddMessage(
    f"Draft data for {hu_name_clean} successfully uploaded to AGOL, and other map settings have been updated. "
    "Proceed with setting up the application at "
    "https://nv5geospatial.maps.arcgis.com/apps/webappbuilder/index.html?id=4d731306a4b049a2b80c1effc1cd0e52"
)


# email template message


message = f"""Michigan EDH - {hu_name} ({huc8}) Draft Submission
Hello,

The draft EDH dataset for {hu_name} ({huc8}) has been loaded into the data reviewer, which can be accessed via this link.
Additionally, a copy of the geodatabase has been uploaded to the DTMB Sharepoint site.

We plan to pull the draft submission of {hu_name} EDH from the reviewer on COB {review_enddate}.

Thank you,
"""


#add message at end of tool
arcpy.AddMessage(message)


