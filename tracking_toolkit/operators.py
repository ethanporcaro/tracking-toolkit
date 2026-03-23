import bpy

from .utils import create_bone_references, create_empty_references
from .xr_core.tracking import (
    start_recording,
    stop_recording,
    start_preview,
    stop_preview,
    get_context,
)


class ToggleRecordOperator(bpy.types.Operator):
    bl_idname = "id.toggle_recording"
    bl_label = "Toggle OpenXR recording"

    def execute(self, context):
        xr_context = get_context()

        # Double check state, though this should have been checked before
        if not xr_context.enabled:
            return {"FINISHED"}

        if xr_context.recording:
            stop_recording()
        else:
            start_recording()

        return {"FINISHED"}


class ToggleActiveOperator(bpy.types.Operator):
    bl_idname = "id.toggle_active"
    bl_label = "Toggle OpenXR's tracking state"

    def execute(self, context):
        if get_context().enabled:
            stop_preview()
        else:
            start_preview()

        return {"FINISHED"}


class CreateRefsOperator(bpy.types.Operator):
    bl_idname = "id.add_tracker_res"
    bl_label = "Create tracker target references"
    bl_options = {"UNDO"}

    @staticmethod
    def execute(self, context):
        xr_context = get_context()

        # Temporarily disable XR.
        should_reenable = xr_context.enabled
        if xr_context.enabled:
            stop_preview()

        # Create references.
        if xr_context.use_bones:
            create_bone_references()
        else:
            create_empty_references()

        if should_reenable:
            start_preview()

        print("Done")
        return {"FINISHED"}
