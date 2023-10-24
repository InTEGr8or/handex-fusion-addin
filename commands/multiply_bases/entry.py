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
CMD_Description = 'Multiply Bases by CSV transforms'
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
    outBody = Object()
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
            measuredAngle = app.measureManager.measureAngle(face, plane)
            outBody.positionOne = [math.degrees(a) for a in measuredAngle.positionOne.asArray()]

            outString += f'  Face{face.tempId}:\n'
            outString += f'    Area: {face.area}\n'
            outString += f'    Centroid: {[c*10 for c in face.centroid.asArray()]}\n'
            outString += f'    PositionOne: {str([math.degrees(a) for a in measuredAngle.positionOne.asArray()])}\n'
            outString += f'    PositionTwo: {str([math.degrees(a) for a in measuredAngle.positionTwo.asArray()])}\n'
            outString += f'    PositionThree: {str([math.degrees(a) for a in measuredAngle.positionThree.asArray()])}\n'
            outString += f'    measuredAngle: {str(math.degrees(measuredAngle.value))}\n'

            # Draw the measured angle on the face
            design.rootComponent.features.createSketch(measuredAngle.positionOne, measuredAngle.positionTwo, measuredAngle.positionThree)
            # TODO: Draw the xyz transform that would need to be applied to the face to make it parallel to the plane

            faceNormals:adsk.core.Vector3D = face.geometry.evaluator.getNormalAtPoint(face.centroid)
            for normal in faceNormals:
                if not isinstance(normal, bool):
                    outString += f'    Normals: {[ math.degrees(n) for n in normal.asArray()]}\n'
            outBody.faces.append(outFace)
    return outString, outBody

def create_finger_base(selected_body:adsk.fusion.BRepBody, finger_name:str, translate:Points, angles:Angle3D):
    futil.log(f'Creating {finger_name}')
    features = rootComp.features

    # Get the first sub component
    occs = rootComp.occurrences
    # subComp1 = occs.item(0).component
    subComp1 = rootComp

    # Get the first body in sub component 1  
    baseBody = subComp1.bRepBodies.item(0)
    
    # Copy/paste bodies
    subComp1.features.copyPasteBodies.add(selected_body)
    
    # Rename Body
    bodies = subComp1.bRepBodies
    selected_bodyCopy: adsk.fusion.BRepBody = subComp1.bRepBodies.item(bodies.count - 1)
    selected_bodyCopy.name = finger_name + "_generated"
    selected_bodyCopy.opacity = 0.5

    # Create a collection of entities for move
    bodies = adsk.core.ObjectCollection.create()
    bodies.add(selected_bodyCopy)    
    
    moveFeats = features.moveFeatures

    # Create a transform to do move
    futil.log("Translate: " + str(translate))
    vector = pointToVec3D(translate)
    transform = adsk.core.Matrix3D.create()
    transform.translation = vector
    # Create a move feature
    moveFeatureInput = moveFeats.createInput(bodies, transform)
    moveFeats.add(moveFeatureInput)

    # Pivot at center of translated body
    pivot = vector.asPoint()
    
    # Translate pivot for model
    # pivot.x = pivot.x + mm(5)
    pivot.y = pivot.y + mm(0.5)
    # pivot.z = pivot.z + mm(5)

    if angles.x != 0:
        # Rotate X
        axis = pointToVec3D(Points(1,0,0))
        transform = adsk.core.Matrix3D.create()
        transform.setToRotation(angle = deg(angles.x), axis = axis, origin = pivot)
        moveFeatureInput = moveFeats.createInput(bodies, transform)
        moveFeats.add(moveFeatureInput)    

    if angles.y != 0:
        # Rotate Y
        axis = pointToVec3D(Points(0,1,0))
        transform = adsk.core.Matrix3D.create()
        transform.setToRotation(angle = deg(angles.y), axis = axis, origin = pivot)
        moveFeatureInput = moveFeats.createInput(bodies, transform)
        moveFeats.add(moveFeatureInput)    

    if angles.z != 0:
        # Rotate Z
        axis = pointToVec3D(Points(0,0,1))
        transform = adsk.core.Matrix3D.create()
        transform.setToRotation(angle = deg(angles.z), axis = axis, origin = pivot)
        moveFeatureInput = moveFeats.createInput(bodies, transform)
        moveFeats.add(moveFeatureInput)    

# Function to be called when a user clicks the corresponding button in the UI.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f'{CMD_NAME} Command Created Event')

    # Connect to the events that are needed by this command.
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)

    inputs = args.command.commandInputs

    # Create some text boxes for your user interface
    title_box = inputs.addTextBoxCommandInput('title_box', '', 'Selected Item', 1, True)
    title_box.isFullWidth = True
    name_box = inputs.addTextBoxCommandInput('name_box', 'Name', 'Pick Something', 1, True)
    type_box = inputs.addTextBoxCommandInput('type_box', 'Type', 'Pick Something', 1, True)

    # Create a selection input, apply filters and set the selection limits
    selection_input = inputs.addSelectionInput('selection_input', 'Some Selection', 'Select Something')
    selection_input.addSelectionFilter('SolidBodies')
    selection_input.addSelectionFilter('RootComponents')
    selection_input.addSelectionFilter('Occurrences')
    selection_input.setSelectionLimits(1, 1)

    selection_input.addSelection(rootComp.bRepBodies.item(0))


# This function will be called when the user clicks the OK button in the command dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Execute Event')

    inputs = args.command.commandInputs
    selection_input: adsk.core.SelectionCommandInput = inputs.itemById('selection_input')

    selection = selection_input.selection(0)
    selected_body = selection.entity
    
    my_path = os.path.abspath(os.path.dirname(__file__))
    path = os.path.join(my_path, "fingerTransforms.csv")

    futil.log(f"Replicating {rootComp.name} {selected_body.name} to fingers")

    bodies = rootComp.bRepBodies
    output = ""
    outBodies = []
    compareBodies = []
    compareType = "thumb"
    for body in bodies:
        
        # Compare matching body faces 
        if compareType in body.name:
            outstring,outBody = describe_body(body)
            if len(compareBodies) > 0:
                futil.log(f"Comparing {compareType} Type")
                compareBody = compareBodies.pop()
                for compareBodyFace in compareBody.BRepFaces:
                    outString,outBody = describe_body(body, compareBodyFace)
                    output += outstring.replace(compareType, f"{compareType}_compare")
                    outBody.name = outBody.name + "_compare"
                    outBodies.append(outBody)
            else:
                futil.log(f"Adding {compareType} compare")
                compareBodies.append(outBody)
            
        if "-base" in body.name or "-source" in body.name:
            futil.log(f"Comparing base type {body.name}")
            outstring,outBody = describe_body(body)
            output += outstring
            outBodies.append(outBody)
            
        if "_generated" in body.name:
            futil.log(f"Comparing generated type {body.name}")
            outstring,outBody = describe_body(body)
            output += outstring
            outBodies.append(outBody)
    
    for body in reversed(bodies):
        if "_generated" in body.name:
            body.deleteMe()
    
    f = open(path.replace(".csv", f"{rootComp.name}.yaml"), "w")
    f.write(output)
    f.close()

    with open(path, "r") as csvfile:
        fingers = csv.DictReader(csvfile)
        for finger in fingers:
            create_finger_base(selected_body, finger["name"], 
                               translate = Points(float(finger["tx"]), float(finger["ty"]), float(finger["tz"])), 
                               angles = Angle3D(float(finger["rx"]), float(finger["ry"]), float(finger["rz"]))
                              )
    

# This function will be called when the user changes anything in the command dialog.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs
    futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')

    selection_input: adsk.core.SelectionCommandInput = inputs.itemById('selection_input')
    name_box: adsk.core.TextBoxCommandInput = inputs.itemById('name_box')
    type_box: adsk.core.TextBoxCommandInput = inputs.itemById('type_box')

    if changed_input.id == 'selection_input':
        if selection_input.selectionCount > 0:
            selected_entity = selection_input.selection(0).entity
            name_box.text = selected_entity.name
            type_box.text = selected_entity.objectType
        else:
            name_box.text = 'Pick Something'
            type_box.text = 'Pick Something'


# This function will be called when the user completes the command.
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    futil.log(f'{CMD_NAME} Command Destroy Event')
