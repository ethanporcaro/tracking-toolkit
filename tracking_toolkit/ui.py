import bpy
from bl_ui.space_view3d_toolbar import View3DPanel

from .operators import (
    ToggleActiveOperator,
    ToggleCalibrationOperator,
    CreateRefsOperator,
    ToggleRecordOperator,
    BuildArmatureOperator
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


class RecorderPanel(View3DPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_openvr_recorder_menu"
    bl_label = "Tracking Toolkit Recorder"
    bl_category = "Track TK"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        ovr_context: OVRContext = context.scene.OVRContext

        layout.label(text="Tracking Toolkit Recorder")

        # Toggle active button
        # It's super annoying to have Blender not save the state of this button on save, so we just label it funny
        activate_label = "Disconnect/Reset OpenVR" if ovr_context.enabled else "Start/Connect OpenVR"
        layout.operator(ToggleActiveOperator.bl_idname, text=activate_label)

        # Trackers
        layout.label(text="Manage Trackers")

        # Default armature
        layout.prop(ovr_context, "armature", placeholder="Default Armature")

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

        # Bone binding
        layout.label(text="Bone binding")
        layout.label(text="Note: you may want to use the Armature Tools panel instead")

        if ovr_context.selected_tracker and ovr_context.selected_tracker < len(ovr_context.trackers):
            selected_tracker = ovr_context.trackers[ovr_context.selected_tracker]

            layout.prop(selected_tracker, "armature", placeholder="Override Armature")
            layout.prop(selected_tracker, "bone", placeholder="Bound Bone")

        # Create empties
        layout.operator(CreateRefsOperator.bl_idname, text="Create References")

        # Show the rest if OpenVR is running
        if not ovr_context.enabled:
            return

        # Calibration
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


class ArmaturePanel(View3DPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_openvr_armature_menu"
    bl_label = "Armature Tools"
    bl_category = "Track TK"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        ovr_context: OVRContext = context.scene.OVRContext

        joints = ovr_context.armature_joints

        layout.prop(joints, "head")
        layout.prop(joints, "chest")
        layout.prop(joints, "hips")

        layout.prop(joints, "r_hand")
        layout.prop(joints, "l_hand")

        layout.prop(joints, "r_elbow")
        layout.prop(joints, "l_elbow")

        layout.prop(joints, "r_foot")
        layout.prop(joints, "l_foot")

        layout.prop(joints, "r_knee")
        layout.prop(joints, "l_knee")

        layout.operator(BuildArmatureOperator.bl_idname)
