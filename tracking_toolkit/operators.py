import bpy

from .utils import (
    check_refs,
    create_bone_references,
    create_empty_references,
    get_context,
    get_state,
)
from .xr_core.tracking import (
    start_recording,
    stop_recording,
    start_preview,
    stop_preview,
)


class ToggleRecordOperator(bpy.types.Operator):
    bl_idname = "id.toggle_recording"
    bl_label = "Toggle OpenXR recording"

    def execute(self, context):
        xr_state = get_state()

        # Double check state, though this should have been checked before
        if not xr_state.enabled:
            return {"FINISHED"}

        if xr_state.recording:
            stop_recording()
        else:
            if not check_refs():
                self.report({"WARNING"}, "Not all references exist. Expect data loss.")

            start_recording()

        return {"FINISHED"}


class ToggleActiveOperator(bpy.types.Operator):
    bl_idname = "id.toggle_active"
    bl_label = "Toggle OpenXR's tracking state"

    def execute(self, context):
        if get_state().enabled:
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
        # Create references.
        if get_context().use_bones:
            create_bone_references()
        else:
            create_empty_references()

        print("Done")
        return {"FINISHED"}
