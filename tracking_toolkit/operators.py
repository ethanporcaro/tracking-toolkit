import bpy
import openvr

from .properties import Preferences, OVRTransform, OVRContext
from .tracking import load_trackers, start_recording, stop_recording, start_preview, stop_preview, init_handles
from .. import __package__ as base_package


class ToggleRecordOperator(bpy.types.Operator):
    bl_idname = "id.toggle_recording"
    bl_label = "Toggle OpenVR recording"

    def execute(self, context):
        ovr_context: OVRContext = context.scene.OVRContext

        # Double check state, though this should have been checked before
        if not ovr_context.enabled:
            return {"FINISHED"}

        if ovr_context.calibration_stage != 0:
            return {"FINISHED"}

        ovr_context.recording = not ovr_context.recording
        if ovr_context.recording:
            ovr_context.record_start_frame = context.scene.frame_current
            start_preview(ovr_context)
            start_recording()
        else:
            stop_recording(ovr_context)

        return {"FINISHED"}


class ToggleCalibrationOperator(bpy.types.Operator):
    bl_idname = "id.toggle_calibration"
    bl_label = "Toggle OpenVR calibration"

    @staticmethod
    def obj_t_to_prop(obj: bpy.types.Object, prop: OVRTransform):
        prop.location = obj.location
        prop.rotation = obj.rotation_euler
        # Scale shouldn't be applicable to calibration, and OpenVR will sometimes provide non-1 scale factors.
        # Just keep it as is, since some armatures depend on scale and it causes issues.

    @staticmethod
    def prop_t_to_obj(prop: OVRTransform, obj: bpy.types.Object):
        obj.location = prop.location
        obj.rotation_euler = prop.rotation
        # Same as above, skip scale.

    def restore_calibration_transforms(self, ovr_context):
        # Restore transform of trackers
        for tracker in ovr_context.trackers:
            if not tracker.connected:
                continue

            tracker_name = tracker.name
            tracker_obj = bpy.data.objects.get(tracker_name)
            if not tracker_obj:
                continue

            # Save original transforms
            self.obj_t_to_prop(tracker_obj, tracker.target.transform)

            # Restore calibration transforms
            self.prop_t_to_obj(tracker.target.calibration_transform, tracker_obj)

    def save_calibration_transforms(self, ovr_context):
        # Save transform of trackers
        for tracker in ovr_context.trackers:
            if not tracker.connected:
                continue

            tracker_name = tracker.name
            tracker_obj = bpy.data.objects.get(tracker_name)
            if not tracker_obj:
                continue

            # Save calibration transforms
            self.obj_t_to_prop(tracker_obj, tracker.target.calibration_transform)

            # Restore original transforms
            self.prop_t_to_obj(tracker.target.transform, tracker_obj)

    @staticmethod
    def enable_rest():
        # Put all armatures in rest position
        for obj in bpy.context.scene.objects:
            if obj.type == "ARMATURE":
                obj.data.pose_position = "REST"
        return {"FINISHED"}

    @staticmethod
    def disable_rest():
        # Put all armatures in rest position
        for obj in bpy.context.scene.objects:
            if obj.type == "ARMATURE":
                obj.data.pose_position = "POSE"
        return {"FINISHED"}

    def execute(self, context):
        ovr_context: OVRContext = context.scene.OVRContext

        # Next stage
        ovr_context.calibration_stage += 1
        if ovr_context.calibration_stage > 2:
            ovr_context.calibration_stage = 0

        # Cycle through stages
        if ovr_context.calibration_stage == 0:  # Complete calibration
            self.save_calibration_transforms(ovr_context)
            self.disable_rest()
            start_preview(ovr_context)
        elif ovr_context.calibration_stage == 1:  # Tracker Alignment
            stop_preview()
            self.restore_calibration_transforms(ovr_context)
            self.enable_rest()
        elif ovr_context.calibration_stage == 2:  # Tracker Offsetting
            stop_preview()
            self.disable_rest()

        return {"FINISHED"}


class ToggleActiveOperator(bpy.types.Operator):
    bl_idname = "id.toggle_active"
    bl_label = "Toggle OpenVR's tracking state"

    def execute(self, context):
        ovr_context: OVRContext = context.scene.OVRContext
        if ovr_context.enabled:
            stop_preview()
            openvr.shutdown()
        else:
            openvr.init(openvr.VRApplication_Scene)
            init_handles()
            load_trackers(ovr_context)
            start_preview(ovr_context)

        ovr_context.enabled = not ovr_context.enabled
        return {"FINISHED"}


class ResetTrackersOperator(bpy.types.Operator):
    bl_idname = "id.reset_trackers"
    bl_label = "Are you sure you want to trim and reset ALL OpenVR Trackers?"
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        ovr_context: OVRContext = context.scene.OVRContext
        if ovr_context.enabled:
            load_trackers(ovr_context, reset=True)

        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class ReloadTrackersOperator(bpy.types.Operator):
    bl_idname = "id.reload_trackers"
    bl_label = "Reload OpenVR tracker list"

    def execute(self, context):
        ovr_context: OVRContext = context.scene.OVRContext
        if ovr_context.enabled:
            load_trackers(ovr_context)

        return {"FINISHED"}


class CreateRefsOperator(bpy.types.Operator):
    bl_idname = "id.add_tracker_res"
    bl_label = "Create tracker target references"
    bl_options = {"UNDO"}

    def execute(self, context):
        ovr_context: OVRContext = context.scene.OVRContext

        # Set to object mode while keeping track of the previous one
        prev_obj = bpy.context.object
        if prev_obj:
            prev_mode = prev_obj.mode
            if prev_mode != "OBJECT":  # Safe against linked library immutability
                bpy.ops.object.mode_set(mode="OBJECT")

        # Create root
        root_empty = bpy.data.objects.get("OVR Root")
        if not root_empty:
            bpy.ops.object.empty_add(type="CUBE", location=(0, 0, 0))
            root_empty = bpy.context.object
            root_empty.name = "OVR Root"
            root_empty.empty_display_size = 0.1

        # Import models

        # Get model paths from preferences
        preferences: Preferences | None = context.preferences.addons[base_package].preferences

        install_dir = preferences.steamvr_installation_path
        tracker_model_path = (f"{install_dir}/drivers/htc/resources/rendermodels/"
                              "vr_tracker_vive_3_0/vr_tracker_vive_3_0.obj")
        controller_model_path = (f"{install_dir}/resources/rendermodels/"
                                 "vr_controller_vive_1_5/vr_controller_vive_1_5.obj")
        hmd_model_path = (f"{install_dir}/resources/rendermodels/"
                          "generic_hmd/generic_hmd.obj")

        try:
            bpy.ops.wm.obj_import(filepath=tracker_model_path)
            tracker_model = bpy.context.object

            bpy.ops.wm.obj_import(filepath=controller_model_path)
            controller_model = bpy.context.object

            bpy.ops.wm.obj_import(filepath=hmd_model_path)
            hmd_model = bpy.context.object
        except RuntimeError:
            self.report(
                {"ERROR"},
                "Could not import tracker models. Check your SteamVR path in the addon preferences."
            )
            return {"FINISHED"}

        tracker_model.location = (0, 0, 0)
        tracker_model.rotation_euler = (0, 0, 0)

        controller_model.location = (0, 0, 0)
        controller_model.rotation_euler = (0, 0, 0)

        hmd_model.location = (0, 0, 0)
        hmd_model.rotation_euler = (0, 0, 0)

        # Create references
        def select_model(target_model: bpy.types.Object):
            bpy.ops.object.select_all(action="DESELECT")
            target_model.select_set(True)
            bpy.context.view_layer.objects.active = target_model

        for tracker in ovr_context.trackers:
            # Create new tracker empty if it doesn't exist
            tracker_name = tracker.name

            # Chose correct model
            if tracker.type == str(openvr.TrackedDeviceClass_Controller):
                model = controller_model
            elif tracker.type == str(openvr.TrackedDeviceClass_HMD):
                model = hmd_model
            else:
                model = tracker_model

            tracker_target = bpy.data.objects.get(tracker_name)
            if not tracker_target:
                # Select render model and duplicate it
                select_model(model)

                bpy.ops.object.duplicate()

                tracker_target = bpy.context.object
                tracker_target.name = tracker_name

                tracker_target.show_name = True
                tracker_target.hide_render = True

            # Create another empty as a joint offset. This is useful when you use a "Copy Transforms" constraint but
            # the physical tracker doesn't align perfectly with a character's joint
            # Create one if it doesn't exist
            joint_name = f"{tracker_name} Joint"

            tracker_joint = bpy.data.objects.get(joint_name)
            if not tracker_joint:
                select_model(model)
                bpy.ops.object.duplicate()

                tracker_joint = bpy.context.object
                tracker_joint.name = joint_name

                tracker_joint.display_type = "WIRE"
                tracker_joint.show_in_front = True
                tracker_target.hide_render = True

            # Assign objects
            tracker.target.object = tracker_target
            tracker.joint.object = tracker_joint

            # Set up parenting
            tracker_target.parent = root_empty
            tracker_joint.parent = tracker_target

        # Clean up
        select_model(tracker_model)
        bpy.ops.object.delete()
        select_model(controller_model)
        bpy.ops.object.delete()
        select_model(hmd_model)
        bpy.ops.object.delete()

        # Restore previous selection
        if prev_obj:
            prev_obj.select_set(True)
            bpy.context.view_layer.objects.active = prev_obj

            # I can't stand warnings, okay?
            # noinspection PyUnboundLocalVariable
            if bpy.context.object.mode != prev_mode:  # Safe against linked library immutability
                bpy.ops.object.mode_set(mode=prev_mode)

        return {"FINISHED"}
