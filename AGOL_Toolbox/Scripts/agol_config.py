"""
agol_config.py

Project-specific ArcGIS Online service configuration
for the AGOL Toolbox.

Notes
-----
- Store Feature Service layer URLs only.
- Do NOT store AGOL tokens.
- Authentication is provided by the active
  ArcGIS Pro portal connection.
- Both the Client Review Pusher and Puller
  consume this configuration.
"""

# =============================================================================
# PROJECT SERVICE CONFIGURATION
# =============================================================================

PROJECTS = {

    # =====================================================================
    # MICHIGAN
    # =====================================================================

    "Michigan": {

        "display_name":
            "Michigan",

        # -------------------------------------------------------------
        # EDH Feature Services
        # -------------------------------------------------------------

        "edh_lines":
            "https://services2.arcgis.com/AcNHAIhTDPOJkhQF/ArcGIS/rest/services/TEMPLATE_SoM_EDH/FeatureServer/0",

        "edh_points":
            "https://services2.arcgis.com/AcNHAIhTDPOJkhQF/ArcGIS/rest/services/TEMPLATE_SoM_EDH/FeatureServer/1",

        "edh_polygons":
            "https://services2.arcgis.com/AcNHAIhTDPOJkhQF/ArcGIS/rest/services/TEMPLATE_SoM_EDH/FeatureServer/2",

        # -------------------------------------------------------------
        # Stakeholder Markup Feature Services
        # -------------------------------------------------------------

        "review_lines":
            "https://services2.arcgis.com/AcNHAIhTDPOJkhQF/ArcGIS/rest/services/Client_Review_Layers_MiHydro/FeatureServer/2",

        "review_points":
            "https://services2.arcgis.com/AcNHAIhTDPOJkhQF/ArcGIS/rest/services/Client_Review_Layers_MiHydro/FeatureServer/0",

        "review_polygons":
            "https://services2.arcgis.com/AcNHAIhTDPOJkhQF/ArcGIS/rest/services/Client_Review_Layers_MiHydro/FeatureServer/1",

        # -------------------------------------------------------------
        # Puller Configuration
        # -------------------------------------------------------------

        "template_gdb":
            r"W:\2023_MI_Statewide_EDH\14_Edits\z_MI_ClientReview_TEMPLATE\TEMPLATE_ClientReviewLayers_NV5.gdb",

        "download_name":
            "Client_Review_Layers_MiHydro",

        "target_review_points":
            "Client_Review_Point_NV5",

        "target_review_lines":
            "Client_Review_Line_NV5",

        "target_review_polygons":
            "Client_Review_Polygon_NV5",

        # -------------------------------------------------------------
        # Project-Specific Processing
        # -------------------------------------------------------------

        "apply_washd_filter":
            False
    },

    # =====================================================================
    # WASHINGTON
    # =====================================================================

    "Washington": {

        "display_name":
            "Washington",

        # -------------------------------------------------------------
        # EDH Feature Services
        # -------------------------------------------------------------

        "edh_lines":
            "https://services2.arcgis.com/AcNHAIhTDPOJkhQF/ArcGIS/rest/services/WA_Hydro_EDH_Reviewer_TEMPLATE/FeatureServer/0",

        "edh_points":
            "https://services2.arcgis.com/AcNHAIhTDPOJkhQF/ArcGIS/rest/services/WA_Hydro_EDH_Reviewer_TEMPLATE/FeatureServer/1",

        "edh_polygons":
            "https://services2.arcgis.com/AcNHAIhTDPOJkhQF/ArcGIS/rest/services/WA_Hydro_EDH_Reviewer_TEMPLATE/FeatureServer/2",

        # -------------------------------------------------------------
        # Stakeholder Markup Feature Services
        # -------------------------------------------------------------

        "review_lines":
            "https://services2.arcgis.com/AcNHAIhTDPOJkhQF/ArcGIS/rest/services/WASHD_FY24_Review_Layers/FeatureServer/0",

        "review_points":
            "https://services2.arcgis.com/AcNHAIhTDPOJkhQF/ArcGIS/rest/services/WASHD_FY24_Review_Layers/FeatureServer/2",

        "review_polygons":
            "https://services2.arcgis.com/AcNHAIhTDPOJkhQF/ArcGIS/rest/services/WASHD_FY24_Review_Layers/FeatureServer/1",

        # -------------------------------------------------------------
        # Puller Configuration
        # -------------------------------------------------------------

        "template_gdb":
            r"W:\2025_WA_EasternWA_FY26_EDH\17_Edits\z_TEMPLATE\00_AGOL_Prep\02_WASHD_Markups\HUC8_Review_Layers.gdb",

        "download_name":
            "Client_Review_Layers_WaHydro",

        "target_review_points":
            "Review_Points",

        "target_review_lines":
            "Review_Lines",

        "target_review_polygons":
            "Review_Polygons",

        # -------------------------------------------------------------
        # Washington-Specific Processing
        # -------------------------------------------------------------

        "apply_washd_filter":
            True,

        "washd_where_clause":
            "WASHD_Proceed NOT IN ('Unreviewed', 'No')"
    }
}


# =============================================================================
# PROJECT LIST
# =============================================================================

PROJECT_NAMES = sorted(
    PROJECTS.keys()
)


# =============================================================================
# CONFIG HELPERS
# =============================================================================

def get_project(project_name):
    """
    Return the configuration for a project.
    """

    if project_name not in PROJECTS:

        raise ValueError(
            f"Unknown project: "
            f"{project_name}"
        )

    return PROJECTS[
        project_name
    ]


def get_edh_services(project_name):
    """
    Return only EDH services.
    """

    project = get_project(
        project_name
    )

    return {

        "Lines":
            project["edh_lines"],

        "Points":
            project["edh_points"],

        "Polygons":
            project["edh_polygons"]
    }


def get_review_services(project_name):
    """
    Return only review services.
    """

    project = get_project(
        project_name
    )

    return {

        "Lines":
            project["review_lines"],

        "Points":
            project["review_points"],

        "Polygons":
            project["review_polygons"]
    }