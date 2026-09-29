import arcpy, time, os
start_time = time.time()


"""
Part 1

This script will create the pour points that will be used for the upstream tracing of HUC12's in Part 2.
It is important to QC the resulting points shapefile before moving on to the next script "Attribute_lines_by_HUC12.py".


Inputs: Final EDH flowlines, original NHD WBDHU12 polygons, digital elevation model, workspace folder
Output: Rough draft of pour points for editing
        - "<outfolder>/01_Pour_points/07_PourPoints_to_edit.shp"

Tool should ignore "Frontal HUs" - and a separate tool should create LEP for frontal units and identify PPs for those front units by using LEPs that intersect
"""




""" BEGIN CHANGING INPUTS """

outfolder = r"W:\2025_MA_Narragansett_D25_H\18_WBD\catchment\01_Generate_PourPoints"
flowlines = r"W:\2025_MA_Narragansett_D25_H\18_WBD\catchment\00_EDH_Inputs\301183_edh.gdb\Lines"
HUC_shapes = r"W:\2025_MA_Narragansett_D25_H\18_WBD\catchment\00_EDH_Inputs\MA_Narragansett_D25_H_HU12s.shp"
DEM = r"W:\2025_MA_Narragansett_D25_H\18_WBD\catchment\00_EDH_Inputs\301183_source_dem.tif"

""" END CHANGING INPUTS """









workspace = os.path.join(outfolder, '01_Pour_points')
try:
    os.mkdir(workspace)
except:
    pass
try:
    os.mkdir(os.path.join(outfolder, '02_Attribution'))
except:
    pass



arcpy.env.workspace = workspace
arcpy.env.overwriteOutput = True

spatial_ref = arcpy.Describe(flowlines).spatialReference

arcpy.management.PolygonToLine(HUC_shapes, "01_WBDHU12_Lines.shp", "IDENTIFY_NEIGHBORS")

arcpy.analysis.Intersect(["01_WBDHU12_Lines.shp", flowlines], "02_Flowline_WBD_IntPts.shp", output_type="POINT")

arcpy.analysis.Buffer(HUC_shapes, "03_Flowline_WBD_IntPts_Buffered.shp", "1 Meters", dissolve_option="NONE")

arcpy.analysis.Intersect(["03_Flowline_WBD_IntPts_Buffered.shp", "02_Flowline_WBD_IntPts.shp"], "04_Flowline_WBD_IntPts_Int.shp", output_type="POINT")

arcpy.management.MultipartToSinglepart("04_Flowline_WBD_IntPts_Int.shp", "05_Flowline_WBD_IntPts_Int_SP.shp")

arcpy.CheckOutExtension("Spatial")
arcpy.sa.ExtractValuesToPoints("05_Flowline_WBD_IntPts_Int_SP.shp", DEM, "06_Flowline_WBD_IntPts_Int_SPZ.shp")

arcpy.analysis.Statistics("06_Flowline_WBD_IntPts_Int_SPZ.shp", "06_Flowline_WBD_IntPts_Int_SPZ_Stats.dbf", statistics_fields=[["RasterValu", "MIN"]], case_field="HUC12")

arcpy.management.JoinField("06_Flowline_WBD_IntPts_Int_SPZ.shp", "HUC12", "06_Flowline_WBD_IntPts_Int_SPZ_Stats.dbf", "HUC12")

# The MINRaster selection did not work correctly in one case...QC? Can go back to using MIN_Raster?
arcpy.management.AddField("06_Flowline_WBD_IntPts_Int_SPZ.shp", "MINRaster", "FLOAT")

arcpy.management.CalculateField("06_Flowline_WBD_IntPts_Int_SPZ.shp", "MINRaster", expression="!MIN_Raster!", expression_type="PYTHON")

where_clause = "RasterValu = MINRaster"
arcpy.management.MakeFeatureLayer("06_Flowline_WBD_IntPts_Int_SPZ.shp", "07_PourPoints_to_edit_unproj", where_clause)

arcpy.management.Project(in_dataset='07_PourPoints_to_edit_unproj', out_dataset='07_PourPoints_to_edit', out_coor_system=spatial_ref)



# Calculate time
end_time = time.time()
total_time = end_time - start_time
print("Done!\nProcess time: {} seconds".format(total_time))
