import bpy
from bl_ui.space_view3d_toolbar import View3DPanel

from .operators import (
    ToggleActiveOperator,
    CreateRefsOperator,
    ToggleRecordOperator
)
from .properties import XRContext


class PANEL_UL_TrackerList(bpy.types.UIList):
    def draw_item(
            self,
            context,
            layout,
            data,
            item,
            icon,
            active_data,
            active_property,
            index,
            flt_flag,
    ):
        selected_tracker = item
        layout.prop(selected_tracker, "name", text="", emboss=False, icon_value=icon)


class RecorderPanel(View3DPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_openxr_recorder_menu"
    bl_label = "Tracking Toolkit Recorder"
    bl_category = "Track TK"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        xr_context: XRContext = context.scene.XRContext

        layout.label(text="Tracking Toolkit Recorder")

        # Toggle active button
        # It's super annoying to have Blender not save the state of this button on save, so we just label it funny
        activate_label = "Disconnect/Reset OpenXR" if xr_context.enabled else "Start/Connect OpenXR"
        layout.operator(ToggleActiveOperator.bl_idname, text=activate_label)

        # Trackers
        layout.label(text="Manage Trackers")

        # Tracker management
        layout.template_list(
            "PANEL_UL_TrackerList",
            "",
            xr_context,
            "trackers",
            xr_context,
            "selected_tracker",
            rows=len(xr_context.trackers),
            type="DEFAULT"
        )

        # Create empties
        layout.operator(CreateRefsOperator.bl_idname, text="Create References")

        # Show the rest if OpenXr is running
        if not xr_context.enabled:
            return

        # Recording
        layout.label(text="Recording")

        # Make button big
        record_btn_row = layout.row()
        record_btn_row.scale_y = 2
        record_btn_row.alert = xr_context.recording

        start_record_label = "Start Recording"
        stop_record_label = "Stop Recording"
        active_record_label = stop_record_label if xr_context.recording else start_record_label

        start_record_icon = "RECORD_OFF"
        stop_record_icon = "RECORD_ON"
        active_record_icon = stop_record_icon if xr_context.recording else start_record_icon

        # I hate warnings (for icon type checking)
        # noinspection PyTypeChecker
        record_btn_row.operator(
            ToggleRecordOperator.bl_idname,
            text=active_record_label,
            icon=active_record_icon,
            depress=True,
        )
