#  Copyright 2022 by Autodesk, Inc.
#  Permission to use, copy, modify, and distribute this software in object code form
#  for any purpose and without fee is hereby granted, provided that the above copyright
#  notice appears in all copies and that both that copyright notice and the limited
#  warranty and restricted rights notice below appear in all supporting documentation.
#
#  AUTODESK PROVIDES THIS PROGRAM "AS IS" AND WITH ALL FAULTS. AUTODESK SPECIFICALLY
#  DISCLAIMS ANY IMPLIED WARRANTY OF MERCHANTABILITY OR FITNESS FOR A PARTICULAR USE.
#  AUTODESK, INC. DOES NOT WARRANT THAT THE OPERATION OF THE PROGRAM WILL BE
#  UNINTERRUPTED OR ERROR FREE.

import adsk.core
import os
import io

import math
from ...lib import fusion360utils as futil
from ... import config
from dataclasses import dataclass
import csv 
# import yaml
from pathlib import Path

app = adsk.core.Application.get()
ui = app.userInterface

design:adsk.fusion.Design = adsk.fusion.Design.cast(app.activeProduct)
# if not design:
#     ui.messageBox('No active Fusion design', 'No Design')
#     return

# Get the root component of the active design.
rootComp = design.rootComponent

sketches = rootComp.sketches
onstructionPoints = rootComp.constructionPoints
constructionPlanes = rootComp.constructionPlanes

pointInput = onstructionPoints.createInput()

CMD_NAME = os.path.basename(os.path.dirname(__file__))
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_{CMD_NAME}'
CMD_Description = 'Face creation by the selection of three points.'
IS_PROMOTED = False

# Global variables by referencing values from /config.py
WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name

PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Holds references to event handlers
local_handlers = []
facePoints = []

@dataclass
class Point:
    x: float
    y: float
    z: float

@dataclass
class Angle3D:
    x: float
    y: float
    z: float
    
# For Yaml serialization
class Object(object):
    pass

def pointToVec3D(vec: Point):
    return adsk.core.Vector3D.create(mm(vec.x), mm(vec.y), mm(vec.z))

def mm(centimeters: float):
    return centimeters / 10.0

# Convert from degrees to radians
def deg(degrees: float):
   return degrees * math.pi / 180.0 

# Executed when add-in is run.
def start():
    # ******************************** Create Command Definition ********************************
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)

    # Add command created handler. The function passed here will be executed when the command is executed.
    futil.add_handler(cmd_def.commandCreated, command_created)

    # ******************************** Create Command Control ********************************
    # Get target workspace for the command.
    workspace = ui.workspaces.itemById(WORKSPACE_ID)

    # Get target toolbar tab for the command and create the tab if necessary.
    toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
    if toolbar_tab is None:
        toolbar_tab = workspace.toolbarTabs.add(TAB_ID, TAB_NAME)

    # Get target panel for the command and and create the panel if necessary.
    panel = toolbar_tab.toolbarPanels.itemById(PANEL_ID)
    if panel is None:
        panel = toolbar_tab.toolbarPanels.add(PANEL_ID, PANEL_NAME, PANEL_AFTER, False)

    # Create the command control, i.e. a button in the UI.
    control = panel.controls.addCommand(cmd_def)

    # Now you can set various options on the control such as promoting it to always be shown.
    control.isPromoted = IS_PROMOTED
    facePoints.clear()


# Executed when add-in is stopped.
def stop():
    # Get the various UI elements for this command
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    # Delete the button command control
    if command_control:
        command_control.deleteMe()

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()

    # Delete the panel if it is empty
    if panel.controls.count == 0:
        panel.deleteMe()

    # Delete the tab if it is empty
    if toolbar_tab.toolbarPanels.count == 0:
        toolbar_tab.deleteMe()

# Function to be called when a user clicks the corresponding button in the UI.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f'{CMD_NAME} Command Created Event')

    # Connect to the events that are needed by this command.
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)

    inputs = args.command.commandInputs

    # Create some text boxes for your user interface
    title_box = inputs.addTextBoxCommandInput('title_box', '', 'Select three vertices', 1, True)
    title_box.isFullWidth = True

    thickness_input = inputs.addValueInput('thickness_input', 'Thickness', 'mm', adsk.core.ValueInput.createByReal(mm(1.5)))

    offset_input = inputs.addValueInput('offset_input', 'Offset', 'mm', adsk.core.ValueInput.createByReal(mm(0.0)))

    # Create a selection input, apply filters and set the selection limits
    selection_input = inputs.addSelectionInput('selection_input', 'Face corners', 'Select 3 vertices')
    selection_input.addSelectionFilter('Vertices')
    selection_input.setSelectionLimits(3, 3)

    # selection_input.addSelection(rootComp.bRepBodies.item(0))


# This function will be called when the user clicks the OK button in the command dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Execute Event')

    inputs = args.command.commandInputs
    selection_input: adsk.core.SelectionCommandInput = inputs.itemById('selection_input')
    thickness_input: adsk.core.SelectionCommandInput = inputs.itemById('thickness_input')
    offset_input: adsk.core.SelectionCommandInput = inputs.itemById('offset_input')

    # and then create a plane from those vectors
    planeInput = constructionPlanes.createInput()
    planeInput.setByThreePoints(facePoints[0], facePoints[1], facePoints[2])
    planeInput.setByOffset(facePoints[0], adsk.core.ValueInput.createByReal(offset_input.value))
    thisPlane = constructionPlanes.add(planeInput)

    # and then project the three vectors onto the sketch

    # Create a sketch and project the points onto it
    faceSketch = sketches.add(thisPlane)
    faceSketchPoint0 = faceSketch.project(facePoints[0])[0]
    faceSketchPoint1 = faceSketch.project(facePoints[1])[0]
    faceSketchPoint2 = faceSketch.project(facePoints[2])[0]

    # Create a line between the three points
    faceSketchLines = faceSketch.sketchCurves.sketchLines
    faceSketchLines.addByTwoPoints(faceSketchPoint0, faceSketchPoint1)
    faceSketchLines.addByTwoPoints(faceSketchPoint1, faceSketchPoint2)
    faceSketchLines.addByTwoPoints(faceSketchPoint2, faceSketchPoint0)
    faceSketch.isVisible = True

    # Extrude the sketch
    extrudes = rootComp.features.extrudeFeatures
    extInput = extrudes.createInput(faceSketch.profiles.item(0), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    extInput.setDistanceExtent(False, adsk.core.ValueInput.createByReal(thickness_input.value))
    extInput.isSolid = True
    extInput.isSymmetric = True
    extrudes.add(extInput)

    facePoints.clear()
    
# This function will be called when the user changes anything in the command dialog.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs
    futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {inputs}')

    selection_input: adsk.core.SelectionCommandInput = inputs.itemById('selection_input')

    if changed_input.id == 'selection_input':
        if selection_input.selectionCount > 0:
            brepVertex = selection_input.selection(selection_input.selectionCount - 1).entity
            _3dPoint = brepVertex
            point = Point(_3dPoint.geometry.x, _3dPoint.geometry.y, _3dPoint.geometry.z)
            facePoints.append(_3dPoint)
            futil.log(f'User selected {point.x}, {point.y}, {point.z}')



# This function will be called when the user completes the command.
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    futil.log(f'{CMD_NAME} Command Destroy Event')
