import os

import bpy

from .properties import XRContext
from .xr_core.tracking import start_recording, stop_recording, start_preview, stop_preview


class ToggleRecordOperator(bpy.types.Operator):
    bl_idname = "id.toggle_recording"
    bl_label = "Toggle OpenXR recording"

    def execute(self, context):
        xr_context: XRContext = context.scene.XRContext

        # Double check state, though this should have been checked before
        if not xr_context.enabled:
            return {"FINISHED"}

        xr_context.recording = not xr_context.recording
        if xr_context.recording:
            xr_context.record_start_frame = context.scene.frame_current
            start_recording()
        else:
            stop_recording()

        return {"FINISHED"}


class ToggleActiveOperator(bpy.types.Operator):
    bl_idname = "id.toggle_active"
    bl_label = "Toggle OpenXR's tracking state"

    def execute(self, context):
        xr_context: XRContext = context.scene.XRContext

        if xr_context.enabled:
            stop_preview()
        else:
            start_preview()

        xr_context.enabled = not xr_context.enabled
        return {"FINISHED"}


class CreateRefsOperator(bpy.types.Operator):
    bl_idname = "id.add_tracker_res"
    bl_label = "Create tracker target references"
    bl_options = {"UNDO"}

    def execute(self, context):
        xr_context: XRContext = context.scene.XRContext

        # Set to object mode while keeping track of the previous one
        prev_obj = bpy.context.object
        if prev_obj:
            prev_mode = prev_obj.mode
            if prev_mode != "OBJECT":  # Safe against linked library immutability
                bpy.ops.object.mode_set(mode="OBJECT")

        # Create root
        root_empty = bpy.data.objects.get("XR Root")
        if root_empty:
            bpy.data.objects.remove(root_empty)

        bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 0))
        root_empty = bpy.context.object
        root_empty.name = "XR Root"
        root_empty.empty_display_size = 0.1

        # Import models

        # Get model paths
        assets_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../assets")
        tracker_model_path = os.path.join(assets_path, "track-point.obj")
        offset_model_path = os.path.join(assets_path, "track-point-offset.obj")

        bpy.ops.wm.obj_import(filepath=tracker_model_path)
        tracker_model = bpy.context.object

        bpy.ops.wm.obj_import(filepath=offset_model_path)
        tracker_offset_model = bpy.context.object

        # Default reference transformations
        tracker_model.location = (0, 0, 0)
        tracker_model.rotation_euler = (0, 0, 0)

        tracker_offset_model.location = (0, 0, 0)
        tracker_offset_model.rotation_euler = (0, 0, 0)

        # Create references
        def select_model(target_model: bpy.types.Object):
            bpy.ops.object.select_all(action="DESELECT")
            target_model.select_set(True)
            bpy.context.view_layer.objects.active = target_model

        for tracker in xr_context.trackers:
            # Create new tracker empty if it doesn't exist
            tracker_name = tracker.nickname

            # Delete existing target
            tracker_target = bpy.data.objects.get(tracker_name)
            if tracker_target:
                bpy.data.objects.remove(tracker_target)

            # Create target
            select_model(tracker_model)
            bpy.ops.object.duplicate()

            tracker_target = bpy.context.object
            tracker_target.name = tracker_name

            tracker_target.show_name = True
            tracker_target.hide_render = True
            tracker_target.show_wire = True
            tracker_target.color = (1.0, 0.0, 0.0, 1.0)  # Red.

            # Create another empty as an offset.

            # Create one if it doesn't exist
            offset_name = f"{tracker_name} Offset"

            # Delete existing offset.
            tracker_offset = bpy.data.objects.get(offset_name)
            if tracker_offset:
                bpy.data.objects.remove(tracker_offset)

            # Create offset.
            select_model(tracker_offset_model)
            bpy.ops.object.duplicate()

            tracker_offset = bpy.context.object
            tracker_offset.name = offset_name

            tracker_offset.hide_render = True
            tracker_offset.show_wire = True
            tracker_offset.color = (0.0, 1.0, 0.0, 1.0)  # Green.

            # Assign objects
            tracker.target.object = tracker_target
            tracker.offset.object = tracker_offset

            # Set up parenting
            tracker_target.parent = root_empty
            tracker_offset.parent = tracker_target

            # Set up rotation modes
            tracker_target.rotation_mode = "QUATERNION"
            tracker_offset.rotation_mode = "QUATERNION"

        # Clean up
        bpy.data.objects.remove(tracker_model)
        bpy.data.objects.remove(tracker_offset_model)

        # Restore previous selection
        try:
            if prev_obj:
                prev_obj.select_set(True)
                bpy.context.view_layer.objects.active = prev_obj

                # I can't stand warnings, okay?
                # noinspection PyUnboundLocalVariable
                if bpy.context.object.mode != prev_mode:  # Safe against linked library immutability
                    bpy.ops.object.mode_set(mode=prev_mode)
        except ReferenceError:
            pass

        # Enable wireframe color display.
        context.space_data.shading.wireframe_color_type = "OBJECT"

        print("Done")
        return {"FINISHED"}
