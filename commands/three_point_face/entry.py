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
def thisComponent():
    if design.activeComponent == None:
        return design.rootComponent
    return design.activeComponent or design.rootComponent

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
    futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate, local_handlers=local_handlers)

    inputs = args.command.commandInputs

    # Create some text boxes for your user interface
    title_box = inputs.addTextBoxCommandInput('title_box', '', 'Select three vertices', 1, True)
    title_box.isFullWidth = True

    # Create a selection input, apply filters and set the selection limits
    selection_input = inputs.addSelectionInput('selection_input', 'Face corners', 'Select 3 vertices')
    selection_input.addSelectionFilter('Vertices')
    selection_input.setSelectionLimits(3, 3)

    thickness_input = inputs.addValueInput('thickness_input', 'Thickness', 'mm', adsk.core.ValueInput.createByReal(mm(1)))

    offset_input = inputs.addValueInput('offset_input', 'Offset', 'mm', adsk.core.ValueInput.createByReal(mm(0.0)))

    taper_angle = inputs.addAngleValueCommandInput('taper_angle', 'Taper angle', adsk.core.ValueInput.createByReal(deg(0.0)))

    extrude_direction = inputs.addDirectionCommandInput('extrude_direction', 'Direction flipped?')
    extrude_direction.setManipulator(adsk.core.Point3D.create(0, 0, 0), pointToVec3D(Point(0, 1, 0)))

def command_validate(args: adsk.core.ValidateInputsEventArgs):
    # futil.log(f'{CMD_NAME} Command Validate Event with {args}')

    inputs = args.inputs
    selection_input: adsk.core.SelectionCommandInput = inputs.itemById('selection_input')
    thickness_input: adsk.core.SelectionCommandInput = inputs.itemById('thickness_input')
    offset_input: adsk.core.SelectionCommandInput = inputs.itemById('offset_input')

    if selection_input.selectionCount < 3:
        args.areInputsValid = False
        return

    args.areInputsValid = True

def command_preview(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Preview Event')
    inputs = args.command.commandInputs
    createExtrudeFromInputs(inputs)

def createPlaneFromInputs(inputs: adsk.core.CommandInputs):
    selection_input: adsk.core.SelectionCommandInput = inputs.itemById('selection_input')
    offset_input: adsk.core.SelectionCommandInput = inputs.itemById('offset_input')
    extrude_direction: adsk.core.SelectionCommandInput = inputs.itemById('extrude_direction')

    # and then create a plane from those vectors
    constructionPlanes = thisComponent().constructionPlanes
    futil.log(f'Creating plane in {thisComponent().name} Construction Planes collection with {len(constructionPlanes)} planes)')
    inputPlane = constructionPlanes.createInput()
    inputPlane.setByThreePoints(facePoints[0], facePoints[1], facePoints[2])
    # inputPlane.isVisible = False
    
    thisPlane = constructionPlanes.add(inputPlane)
    if offset_input.value > 0:
        offsetPlane = constructionPlanes.createInput()
        offsetValue = offset_input.value * -1 if extrude_direction.isDirectionFlipped else offset_input.value
        offsetPlane.setByOffset(thisPlane, adsk.core.ValueInput.createByReal(offsetValue))
        offsetPlane.isVisible = False
        thisPlane = constructionPlanes.add(offsetPlane)

    # planeInput.setByOffset(facePoints[0], adsk.core.ValueInput.createByReal(offset_input.value))
    return thisPlane

def createProfileFromInputs(inputs: adsk.core.CommandInputs, thisPlane: adsk.fusion.ConstructionPlane):
    # Create a sketch and project the points onto it
    faceSketch = thisComponent().sketches.add(thisPlane)
    faceSketchPoint0 = faceSketch.project(facePoints[0])[0]
    faceSketchPoint1 = faceSketch.project(facePoints[1])[0]
    faceSketchPoint2 = faceSketch.project(facePoints[2])[0]

    # Create lines between the three points
    faceSketchLines = faceSketch.sketchCurves.sketchLines
    faceSketchLines.addByTwoPoints(faceSketchPoint0, faceSketchPoint1)
    faceSketchLines.addByTwoPoints(faceSketchPoint1, faceSketchPoint2)
    faceSketchLines.addByTwoPoints(faceSketchPoint2, faceSketchPoint0)
    faceSketch.isVisible = True
    return faceSketch

def createExtrudeFromSketch(inputs: adsk.core.CommandInputs, faceSketch: adsk.fusion.Sketch):
    # Extrude the sketch
    thickness_input: adsk.core.SelectionCommandInput = inputs.itemById('thickness_input')
    extrude_direction: adsk.core.SelectionCommandInput = inputs.itemById('extrude_direction')
    taper_angle: adsk.core.SelectionCommandInput = inputs.itemById('taper_angle')

    # Create surface from the sketch
    profile = faceSketch.profiles[0]
    extrudes = thisComponent().features.extrudeFeatures

    distanceExtentDefinition = adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByReal(thickness_input.value))

    extrudeBodyInput:adks.fusion.ExtrudeFeatureInput = extrudes.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    
    direction = adsk.fusion.ExtentDirections.NegativeExtentDirection if extrude_direction.isDirectionFlipped else adsk.fusion.ExtentDirections.PositiveExtentDirection

    extrudeBodyInput.setOneSideExtent(distanceExtentDefinition, direction)

    extrudeBodyInput.isSolid = True
    # extrudeBodyInput.isSymmetric = True
    extrudes.add(extrudeBodyInput)
    return extrudeBodyInput

def createFaceFromSketch(inputs: adsk.core.CommandInputs, faceSketch: adsk.fusion.Sketch):
    # Extrude the sketch
    thickness_input: adsk.core.SelectionCommandInput = inputs.itemById('thickness_input')

    # Create surface from the sketch
    profile = faceSketch.profiles[0]
    openProfile = thisComponent().createOpenProfile(faceSketch.sketchCurves.sketchLines[0], True)
    extrudes = thisComponent().features.extrudeFeatures

    # Body Extrude
    extrudeBodyInput:adks.fusion.ExtrudeFeatureInput = extrudes.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    extrudeBodyInput.setDistanceExtent(False, adsk.core.ValueInput.createByReal(thickness_input.value))
    extrudeBodyInput.isSolid = True
    extrude = extrudes.add(extrudeBodyInput)

    # # Face Extrude
    # extrudeFaceInput:adks.fusion.ExtrudeFeatureInput = extrudes.createInput(openProfile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    # extrudeFaceInput.setDistanceExtent(False, adsk.core.ValueInput.createByReal(thickness_input.value))
    # extrudeFaceInput.isSolid = False
    # extrude = extrudes.add(extrudeFaceInput)

    body = extrude.bodies[0]

    # Create input for offset feature
    inputEntities = adsk.core.ObjectCollection.create()
    inputEntities.add(body.faces[4])

    distance = adsk.core.ValueInput.createByReal(0.0)

    offsetFeatures = thisComponent().features.offsetFeatures
    offsetInput = offsetFeatures.createInput(inputEntities, distance, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)

    offset = offsetFeatures.add(offsetInput)
    # Delete the source body
    extrude.deleteMe()
    

def createExtrudeFromInputs(inputs: adsk.core.CommandInputs):
    # and then project the three vectors onto the sketch
    thisPlane = createPlaneFromInputs(inputs)
    # Create profile from the inputs
    faceSketch = createProfileFromInputs(inputs, thisPlane)
    # Extrude the sketch
    createFaceFromSketch(inputs, faceSketch)

# This function will be called when the user clicks the OK button in the command dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Execute Event')
    inputs = args.command.commandInputs
    createExtrudeFromInputs(inputs)
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
            facePoints.append(brepVertex)
            futil.log(f'User selected {selection_input.selectionCount} vertices and {len(facePoints)} facePoints')



# This function will be called when the user completes the command.
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    futil.log(f'{CMD_NAME} Command Destroy Event')
