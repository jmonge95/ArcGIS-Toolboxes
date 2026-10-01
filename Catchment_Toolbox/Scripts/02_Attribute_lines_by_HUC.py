import arcpy, os, time
from scripts import mdl_01_Split_PourPoints_HU12, mdl_02_Trace_Network_GBD, mdl_03_Trace_HU12, \
    mdl_04_Name_lines_by_HU12, mdl_05_Merge_Lines

start_time = time.time()

"""
Part 2

This script should be run after the pour points from Part 1 have been reviewed.
It will use the pour points from each HUC12 as a starting point for an upstream trace used to assign HUC12 attributions.
The attributions will then be used to group lines into watersheds based on flow information in the flow direction raster.


Inputs: Final EDH flowlines, Edited pour points, digital elevation model, workspace folder
Output: Attributed flowline network
        - "<workspace>/02_Attribution/OUTPUT_Flowlines_by_HU12.shp"
"""

""" BEGIN CHANGING INPUTS """

workspace = r"W:\2025_MA_Narragansett_D25_H\18_WBD\catchment\01_Generate_PourPoints\02_Attribution"
PPs = r"W:\2025_MA_Narragansett_D25_H\18_WBD\catchment\01_Generate_PourPoints\01_Pour_points\07_PourPoints_to_edit.shp"
DEM = r"W:\2025_MA_Narragansett_D25_H\18_WBD\catchment\00_EDH_Inputs\301183_source_dem.tif"
flowlines = r"W:\2025_MA_Narragansett_D25_H\18_WBD\catchment\00_EDH_Inputs\301183_edh.gdb\Lines"

""" END CHANGING INPUTS """

mdl_01_Split_PourPoints_HU12.split_pourpoints(workspace, PPs)
mdl_02_Trace_Network_GBD.geom_network_gbd(flowlines, workspace)
mdl_03_Trace_HU12.trace_HU12(workspace)
mdl_04_Name_lines_by_HU12.name_lines(workspace)
mdl_05_Merge_Lines.merge_flowlines(workspace)

# Calculate time
end_time = time.time()
total_time = end_time - start_time
print("Done!\nProcess time: {} minutes".format(total_time / 60))
