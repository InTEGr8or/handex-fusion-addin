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

CMD_NAME = os.path.basename(os.path.dirname(__file__))
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_{CMD_NAME}'
CMD_Description = 'Measure Transforms'
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

@dataclass
class Points:
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

def pointToVec3D(vec: Points):
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


def describe_body(body:adsk.fusion.BRepBody, plane: adsk.fusion.ConstructionPlane = rootComp.xZConstructionPlane)->str:
    outString = ''
    outString = f'- {body.name}:\n'
    outBody:adsk.fusion.BRepBody = Object()
    outBody.name = body.name
    outBody.faces = []
    outBody.BRepFaces = []
    if isinstance(plane, adsk.fusion.BRepFace):
        futil.log(f'Comparing {body.name} to \n{plane.geometry}')
    else:
        futil.log(f'Comparing {body.name} to {plane.name}\n{plane.geometry}')
    for face in body.faces:
        if face.area > 0.5:
            outBody.BRepFaces.append(face)
            outFace = Object()
            outFace.tempId = face.tempId
            outFace.area = face.area
            outFace.centroid = [c*10 for c in face.centroid.asArray()]
            measure_faces(face, plane, outBody)
            outBody.faces.append(outFace)
    return outString, outBody

def measure_faces(face1:adsk.fusion.BRepFace, face2:adsk.fusion.BRepFace, outBody:adsk.fusion.BRepBody)->str:
    outString = ''
    outString += f'{face1.body.name} {face1.tempId} to {face2.body.name} {face2.tempId}:\n'
    outString += f'  - face1_to_face2_centroid_distance: {10 * face1.centroid.distanceTo(face2.centroid)}\n'

    measuredAngle = app.measureManager.measureAngle(face1, face2)
    if outBody:
        outBody.positionOne = [math.degrees(a) for a in measuredAngle.positionOne.asArray()]

    outString += f'  Face1 {face1.tempId}:\n'
    outString += f'    Area mm**2: {100 * face1.area}\n'
    outString += f'    Centroid coords: {[c * 10 for c in face1.centroid.asArray()]}\n'
    outString += f'  Face2 {face2.tempId}:\n'
    outString += f'    Area mm**2: {100 * face2.area}\n'
    outString += f'    Centroid coords: {[c * 10 for c in face2.centroid.asArray()]}\n'
    outString += f'  Measured Angle {measuredAngle.classType} {measuredAngle.objectType}:\n'
    outString += f'    PositionOne: {str([a for a in measuredAngle.positionOne.asArray()])}\n'
    outString += f'    PositionTwo: {str([a for a in measuredAngle.positionTwo.asArray()])}\n'
    outString += f'    PositionThree: {str([a for a in measuredAngle.positionThree.asArray()])}\n'
    outString += f'    measuredAngle: {str(math.degrees(measuredAngle.value))}\n'

    # Draw the measured angle on the face
    # TODO: Draw the xyz transform that would need to be applied to the face to make it parallel to the plane
    # design.rootComponent.features.createSketch(measuredAngle.positionOne, measuredAngle.positionTwo, measuredAngle.positionThree)

    faceNormals:adsk.core.Vector3D = face1.geometry.evaluator.getNormalAtPoint(face1.centroid)
    for normal in faceNormals:
        if not isinstance(normal, bool):
            outString += f'Face1 Normals: {[ math.degrees(n/2*math.pi) for n in normal.asArray()]}\n'

    faceNormals:adsk.core.Vector3D = face2.geometry.evaluator.getNormalAtPoint(face2.centroid)
    for normal in faceNormals:
        if not isinstance(normal, bool):
            outString += f'Face2 Normals: {[ math.degrees(n/2*math.pi) for n in normal.asArray()]}\n'
    
    sketchXy = rootComp.sketches.add(rootComp.xYConstructionPlane)
    sketchXy.project(face1)
    sketchXy.project(face2)
    
    return outString
    
# Function to be called when a user clicks the corresponding button in the UI.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f'{CMD_NAME} Command Created Event')

    # Connect to the events that are needed by this command.
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)

    inputs = args.command.commandInputs

    # Create some text boxes for your user interface
    title_box = inputs.addTextBoxCommandInput('title_box', '', 'Selected Items', 1, True)
    title_box.isFullWidth = True

    # Select object selection type

    # Compare from face
    base_selection = inputs.addSelectionInput('base_selection', 'Base Selection', 'Select Something')

    
    base_selection.addSelectionFilter('Faces')
    base_selection.setSelectionLimits(1, 1)

    # Compare to face
    comparison_selection = inputs.addSelectionInput('comparison_selection', 'Comparison Selection', 'Select Something')
    comparison_selection.addSelectionFilter('Faces')
    comparison_selection.setSelectionLimits(1, 1)

# This function will be called when the user clicks the OK button in the command dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Execute Event')

    inputs = args.command.commandInputs
    selection_input: adsk.core.SelectionCommandInput = inputs.itemById('selection_input')

    selection = selection_input.selection(0)
    selected_body = selection.entity
    
    my_path = os.path.abspath(os.path.dirname(__file__))
    path = os.path.join(my_path, "fingerTransforms.csv")

    bodies = rootComp.bRepBodies
    output = ""
    outBodies = []
    compareBodies = []

# This function will be called when the user changes anything in the command dialog.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs
    futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')

    base_selection: adsk.core.SelectionCommandInput = inputs.itemById('base_selection')
    comparison_selection: adsk.core.SelectionCommandInput = inputs.itemById('comparison_selection')

    if base_selection.selectionCount > 0 and comparison_selection.selectionCount > 0:
        selected_entity = base_selection.selection(0).entity
        compare_result:str = measure_faces(base_selection.selection(0).entity, comparison_selection.selection(0).entity, None)
        futil.log(compare_result)
    else:
        futil.log('No selection')

# This function will be called when the user completes the command.
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    futil.log(f'{CMD_NAME} Command Destroy Event')
