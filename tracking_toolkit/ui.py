import bpy
from bl_ui.space_view3d_toolbar import View3DPanel

from .operators import (
    ToggleActiveOperator,
    ToggleCalibrationOperator,
    ReloadTrackersOperator,
    ResetTrackersOperator,
    CreateRefsOperator,
    ToggleRecordOperator
)
from .properties import OVRContext


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


class OpenVRPanel(View3DPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_openvr_menu"
    bl_label = "Tracking Toolkit"
    bl_category = "Track TK"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        ovr_context: OVRContext = context.scene.OVRContext

        layout.label(text="Tracking Toolkit")

        # Toggle active button
        # It's super annoying to have Blender not save the state of this button on save, so we just label it funny
        activate_label = "Disconnect/Reset OpenVR" if ovr_context.enabled else "Start/Connect OpenVR"
        layout.operator(ToggleActiveOperator.bl_idname, text=activate_label)

        if not ovr_context.enabled:
            return

        layout.label(text="Calibration:")

        # Toggle calibration button
        if ovr_context.calibration_stage == 1:
            calibrate_btn_label = "Continue to Offset"
            calibrate_hint = "Stage 1: Line up the opaque tracker models with the character"
        elif ovr_context.calibration_stage == 2:
            calibrate_btn_label = "Complete Calibration"
            calibrate_hint = "Stage 2: Offset the wireframe tracker models to correct the pose"
        else:
            calibrate_btn_label = "Start Calibration"
            calibrate_hint = "Calibration complete"

        layout.operator(ToggleCalibrationOperator.bl_idname, text=calibrate_btn_label)
        layout.label(text=calibrate_hint)

        # Tracker management
        layout.template_list(
            "PANEL_UL_TrackerList",
            "",
            ovr_context,
            "trackers",
            ovr_context,
            "selected_tracker",
            rows=len(ovr_context.trackers),
            type="DEFAULT"
        )

        layout.label(text="If you rename any trackers you will need to recreate empties!")
        layout.label(text="You will probably want to delete the old ones.")

        # Reload tracker button
        layout.operator(ReloadTrackersOperator.bl_idname, text="Reload Trackers")

        # Create empties
        layout.operator(CreateRefsOperator.bl_idname, text="Create References")

        # Reset names button
        layout.operator_context = "INVOKE_DEFAULT"
        layout.operator(ResetTrackersOperator.bl_idname, text="Trim And Reset All Trackers And Names")

        # Recording
        layout.label(text="Recording")

        start_record_label = "Start Recording"
        stop_record_label = "Stop Recording"
        active_record_label = stop_record_label if ovr_context.recording else start_record_label

        start_record_icon = "RECORD_OFF"
        stop_record_icon = "RECORD_ON"
        active_record_icon = stop_record_icon if ovr_context.recording else start_record_icon

        # I hate warnings (for icon type checking)
        # noinspection PyTypeChecker
        layout.operator(
            ToggleRecordOperator.bl_idname,
            text=active_record_label,
            icon=active_record_icon,
            depress=ovr_context.recording
        )
