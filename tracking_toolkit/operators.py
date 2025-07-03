import bpy
import openvr
from mathutils import Vector

from .properties import Preferences, OVRTransform, OVRContext
from .tracking import load_trackers, start_recording, stop_recording, start_preview, stop_preview, init_handles
from .. import __package__ as base_package


class BuildArmatureOperator(bpy.types.Operator):
    bl_idname = "id.build_armature"
    bl_label = "Build OpenVR armature"

    def execute(self, context):
        ovr_context: OVRContext = context.scene.OVRContext

        # Store selection and mode state
        prev_select = None
        if context.object:
            prev_select = context.object

            prev_mode = context.object.mode
            bpy.ops.object.mode_set(mode="OBJECT")
        else:
            prev_mode = "OBJECT"

        # Create armature
        armature_obj = context.scene.objects.get("OVR Armature")
        if not armature_obj:
            bpy.ops.object.armature_add(enter_editmode=True, align="WORLD", location=(0, 0, 0))
            armature_obj = context.object
            armature_obj.name = "OVR Armature"

        context.view_layer.objects.active = armature_obj
        bpy.ops.object.mode_set(mode="EDIT")

        armature_data = armature_obj.data
        armature_data.name = "OVR Armature Data"
        armature_data.show_names = True
        armature_data.display_type = "STICK"

        edit_bones = armature_data.edit_bones
        # Clear any default bone Blender might have added, or all bones if recreating
        for bone in list(edit_bones):  # Iterate over a copy as we are modifying the list
            edit_bones.remove(bone)

        def get_loc(obj_prop) -> Vector | None:
            if obj_prop:
                return obj_prop.matrix_world.translation.copy()  # Use a copy to prevent changing it
            return None

        joints = ovr_context.armature_joints

        foot_height = (get_loc(joints.l_foot).z + get_loc(joints.r_foot).z) / 2  # Average of feet
        float_height = foot_height

        # Offset floor
        foot_height = 0

        head_height = get_loc(joints.head).z - float_height

        hips_height = get_loc(joints.hips).z - float_height

        chest_height = (get_loc(joints.chest).z - float_height
                        if joints.chest
                        else (hips_height + head_height) / 2)  # If no chest, average hips and head
        knee_height = ((get_loc(joints.l_knee).z + get_loc(joints.r_knee).z) / 2 - float_height
                       if joints.l_knee and joints.r_knee
                       else (foot_height + hips_height) / 2)  # If no knees, average hips and feet

        neck_height = head_height - head_height / 8  # Person is 8 heads tall about

        # Skip elbow height since we are t-posing

        head_loc = Vector((0, 0, head_height))
        hips_loc = Vector((0, 0, hips_height))
        chest_loc = Vector((0, 0, chest_height))
        neck_loc = Vector((0, 0, neck_height))
        root_loc = Vector((0, 0, hips_height - 0.01))

        l_foot_loc = Vector((0.15, 0, foot_height))
        r_foot_loc = Vector((-0.15, 0, foot_height))

        half_height = head_height / 2  # Half of wingspan

        # Offset 0.1 since it's added back later for hand tips
        l_hand_loc = Vector((half_height - 0.1, 0, chest_height))
        r_hand_loc = Vector((-half_height + 0.1, 0, chest_height))

        elbow_offset = half_height / 2  # Elbows halfway between hands
        elbow_height = (chest_height + neck_height) / 2

        l_elbow_loc = Vector((elbow_offset, 0, elbow_height))
        r_elbow_loc = Vector((-elbow_offset, 0, elbow_height))

        l_knee_loc = Vector((0.15, -0.2, knee_height))
        r_knee_loc = Vector((-0.15, -0.2, knee_height))

        # Name, parent name, parent_obj, head_loc, tail_loc, head_obj
        bone_definitions = [
            ("root", None, joints.hips, root_loc, hips_loc),  # Root to hips
            ("spine", "root", joints.head, hips_loc, neck_loc),  # Hips to neck
            ("head", "spine", joints.head, chest_loc, head_loc),  # Chest to head

            # Arms and hands
            ("arm.l", "spine", joints.l_elbow, chest_loc, l_elbow_loc),  # Chest to elbow
            ("arm.r", "spine", joints.r_elbow, chest_loc, r_elbow_loc),  # Chest to elbow

            ("forearm.l", "arm.l", joints.l_hand, l_elbow_loc, l_hand_loc),  # Elbow to hand
            ("forearm.r", "arm.r", joints.r_hand, r_elbow_loc, r_hand_loc),  # Elbow to hand

            ("hand.l", "forearm.l", joints.l_hand, l_hand_loc, l_hand_loc + Vector((0.1, 0, 0))),  # Hand to hand tip
            ("hand.r", "forearm.r", joints.r_hand, r_hand_loc, r_hand_loc + Vector((-0.1, 0, 0))),  # Hand to hand tip

            # Legs and feet
            ("thigh.l", "root", joints.l_knee or joints.l_foot, hips_loc, l_knee_loc),  # Hips to knee
            ("thigh.r", "root", joints.r_knee or joints.r_foot, hips_loc, r_knee_loc),  # Hips to knee

            ("leg.l", "thigh.l", joints.l_foot, l_knee_loc, l_foot_loc),  # L foot to elbow
            ("leg.r", "thigh.r", joints.r_foot, r_knee_loc, r_foot_loc),  # R foot to elbo

            ("foot.l", "leg.l", joints.l_foot, l_foot_loc, l_foot_loc + Vector((0, -0.1, 0))),
            ("foot.r", "leg.r", joints.r_foot, r_foot_loc, r_foot_loc + Vector((0, -0.1, 0))),
        ]

        bones = {}

        for name, parent_name, _, head_loc, tail_loc in bone_definitions:
            bone = edit_bones.new(name)

            bone.head = head_loc
            bone.tail = tail_loc

            bones[name] = bone

            if parent_name:
                bone.parent = bones[parent_name]
                bone.use_connect = True

        # Add constraints
        bpy.ops.object.mode_set(mode="POSE")

        # FK for elbow or knee trackers (and spine)
        damped_track_bones = ["spine", "hand.l", "hand.r"]
        if joints.l_elbow and joints.r_elbow:
            damped_track_bones.extend(["forearm.l", "forearm.r", "arm.l", "arm.r"])

        if joints.l_knee and joints.r_knee:
            damped_track_bones.extend(["leg.l", "leg.r", "thigh.l", "thigh.r"])

        # Actually add
        for name, _, parent_obj, _, _ in bone_definitions:
            if parent_obj:
                pose_bone: bpy.types.PoseBone = armature_obj.pose.bones.get(name)
                if not pose_bone:
                    print(f"No bone for {name}")
                    continue

                # Clear existing
                for constraint in pose_bone.constraints:
                    pose_bone.constraints.remove(constraint)

                if name in ["root", "head"]:
                    # Location and rotation (no scale because it gets weird)
                    constraint_loc = pose_bone.constraints.new("COPY_LOCATION")
                    constraint_loc.name = "Tracker Binding Location"
                    constraint_loc.target = parent_obj

                    constraint_rot = pose_bone.constraints.new("COPY_ROTATION")
                    constraint_rot.name = "Tracker Binding Rotation"
                    constraint_rot.target = parent_obj

                if name in ["hand.l", "hand.r", "foot.r", "foot.l"]:
                    constraint = pose_bone.constraints.new("IK")
                    constraint.name = "Tracker Binding Child"
                    constraint.target = parent_obj
                    constraint.chain_count = 2
                    constraint.use_rotation = "hand" not in name  # Hands rely on damped track

                if name in damped_track_bones:
                    constraint = pose_bone.constraints.new("DAMPED_TRACK")
                    constraint.name = "Tracker Binding Track"
                    constraint.target = parent_obj

        # Restore mode
        if prev_select:
            context.view_layer.objects.active = prev_select
            prev_select.select_set(True)
        bpy.ops.object.mode_set(mode=prev_mode)

        return {"FINISHED"}


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


class CreateRefsOperator(bpy.types.Operator):
    bl_idname = "id.add_tracker_res"
    bl_label = "Create tracker target references"
    bl_options = {"UNDO"}

    def execute(self, context):
        ovr_context: OVRContext = context.scene.OVRContext
        if not ovr_context.enabled:
            self.report(
                {"ERROR"},
                "OpenVR has not been connected yet"
            )
            return {"FINISHED"}

        # Set to object mode while keeping track of the previous one
        prev_obj = bpy.context.object
        if prev_obj:
            prev_mode = prev_obj.mode
            if prev_mode != "OBJECT":  # Safe against linked library immutability
                bpy.ops.object.mode_set(mode="OBJECT")

        # Create root
        root_empty = bpy.data.objects.get("OVR Root")
        if root_empty:
            bpy.data.objects.remove(root_empty)

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

        load_trackers(ovr_context)

        # Default reference transformations
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

            print(">", tracker_name)

            # Chose correct model
            if tracker.type == str(openvr.TrackedDeviceClass_Controller):
                model = controller_model
            elif tracker.type == str(openvr.TrackedDeviceClass_HMD):
                model = hmd_model
            else:
                model = tracker_model

            # Delete existing target
            tracker_target = bpy.data.objects.get(tracker_name)
            if tracker_target:
                bpy.data.objects.remove(tracker_target)

            # Create target
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

            # Delete existing joint
            tracker_joint = bpy.data.objects.get(joint_name)
            if tracker_joint:
                bpy.data.objects.remove(tracker_joint)

            # Create joint
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

            # Set up rotation modes
            tracker_target.rotation_mode = "QUATERNION"
            tracker_joint.rotation_mode = "QUATERNION"

        # Clean up
        bpy.data.objects.remove(tracker_model)
        bpy.data.objects.remove(controller_model)
        bpy.data.objects.remove(hmd_model)

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

        print("Done")
        return {"FINISHED"}
