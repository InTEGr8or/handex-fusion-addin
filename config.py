# Application Global Variables
# This module serves as a way to share variables across different
# modules (global variables).

import os

# Flag that indicates to run in Debug mode or not. When running in Debug mode
# more information is written to the Text Command window. Generally, it's useful
# to set this to True while developing an add-in and set it to False when you
# are ready to distribute it.
DEBUG = True


# Gets the name of the add-in from the name of the folder the py file is in.
# This is used when defining unique internal names for various UI elements 
# that need a unique name. It's also recommended to use a company name as 
# part of the ID to better ensure the ID is unique.
ADDIN_NAME = os.path.basename(os.path.dirname(__file__))
COMPANY_NAME = 'Handex'

# Palettes
sample_palette_id = f'{COMPANY_NAME}_{ADDIN_NAME}_palette_id'


# Add tabs and panels to the UI using the following constants
design_workspace = 'FusionSolidEnvironment'
tools_tab_id = "ToolsTab"
my_tab_name = "Handex"  # Only used if creating a custom Tab

my_panel_id = f'{ADDIN_NAME}_panel_2'
my_panel_name = ADDIN_NAME
my_panel_after = ''