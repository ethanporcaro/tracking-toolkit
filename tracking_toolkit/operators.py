import os

import bpy
from mathutils import Vector

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

        return {"FINISHED"}


def delete_recursive(obj: bpy.types.Object):
    for child in obj.children:
        delete_recursive(child)
    bpy.data.objects.remove(obj, do_unlink=True)


def select_obj(target_obj: bpy.types.Object):
    bpy.ops.object.select_all(action="DESELECT")
    target_obj.select_set(True)
    bpy.context.view_layer.objects.active = target_obj


class CreateRefsOperator(bpy.types.Operator):
    bl_idname = "id.add_tracker_res"
    bl_label = "Create tracker target references"
    bl_options = {"UNDO"}

    def _ensure_widgets(self) -> tuple[bpy.types.Object, bpy.types.Object]:
        """
        Ensure custom shapes exist for tracker references.
        :returns: Tuple of (tracker_object, offset_object).
        """

        widget_collection = bpy.data.collections.get("TTK Widgets")
        if not widget_collection:
            widget_collection = bpy.data.collections.new(name="TTK Widgets")
            bpy.context.scene.collection.children.link(widget_collection)

        # Import shapes.

        assets_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../assets")
        tracker_model_path = os.path.join(assets_path, "track-point.obj")
        offset_model_path = os.path.join(assets_path, "track-point-offset.obj")

        tracker_obj = bpy.data.objects.get("TTK Tracker")
        offset_obj = bpy.data.objects.get("TTK Offset")

        if not tracker_obj:
            bpy.ops.wm.obj_import(filepath=tracker_model_path)
            tracker_obj = bpy.context.object
            tracker_obj.name = "TTK Tracker"

            tracker_obj.show_name = True
            tracker_obj.hide_render = True
            tracker_obj.show_wire = True
            tracker_obj.color = (1.0, 0.0, 0.0, 1.0)  # Red.

            bpy.context.collection.objects.unlink(tracker_obj)
            widget_collection.objects.link(tracker_obj)

        if not offset_obj:
            bpy.ops.wm.obj_import(filepath=offset_model_path)
            offset_obj = bpy.context.object
            offset_obj.name = "TTK Offset"

            offset_obj.hide_render = True
            offset_obj.show_wire = True
            offset_obj.color = (0.0, 1.0, 0.0, 1.0)  # Green.

            bpy.context.collection.objects.unlink(offset_obj)
            widget_collection.objects.link(offset_obj)

        # Default reference transformations
        tracker_obj.location = (0, 0, 0)
        tracker_obj.rotation_euler = (0, 0, 0)
        tracker_obj.scale = (1, 1, 1)

        offset_obj.location = (0, 0, 0)
        offset_obj.rotation_euler = (0, 0, 0)
        offset_obj.scale = (1, 1, 1)

        # Enable wireframe color display.
        bpy.context.space_data.shading.wireframe_color_type = "OBJECT"

        # Hide collection
        bpy.context.view_layer.layer_collection.children["TTK Widgets"].exclude = True

        return tracker_obj, offset_obj

    def execute(self, context):
        xr_context: XRContext = context.scene.XRContext

        # Temporarily disable XR.
        should_reenable = xr_context.enabled
        if xr_context.enabled:
            stop_preview()

        # Set to object mode while keeping track of the previous one
        prev_obj = bpy.context.object
        prev_mode = None
        if prev_obj:
            prev_mode = prev_obj.mode
            if prev_mode != "OBJECT":  # Safe against linked library immutability
                bpy.ops.object.mode_set(mode="OBJECT")

        # Bone references.
        if xr_context.use_bones:
            print("Creating bone references.")
            tracker_obj, offset_obj = self._ensure_widgets()

            arm = bpy.data.objects.get("XR Trackers")
            if not arm:
                arm_data = bpy.data.armatures.new("XR Trackers")
                arm = bpy.data.objects.new("XR Trackers", arm_data)
                context.scene.collection.objects.link(arm)

            select_obj(arm)
            bpy.ops.object.mode_set(mode="EDIT")

            def ensure_bone(name: str):
                edit_bones = arm.data.edit_bones
                _bone = edit_bones.get(name)
                if not _bone:
                    _bone = edit_bones.new(name)
                _bone.head = Vector((0, 0, 0))
                _bone.tail = Vector((0, 0, 1))
                return _bone

            # Root bone.
            root = ensure_bone("root")
            root.tail = Vector((0, 0, 0.2))

            # Create bones for each tracker.
            for tracker in xr_context.trackers:
                tracker_name = tracker.nickname

                # Create bone.

                bpy.ops.object.mode_set(mode="EDIT")

                tracker = ensure_bone(tracker_name)
                tracker.parent = root
                offset = ensure_bone(f"{tracker_name} Offset")
                offset.parent = root

                # Set shape.

                bpy.ops.object.mode_set(mode="OBJECT")
                pose_bones = arm.pose.bones

                tracker_pose_bone = pose_bones.get(tracker_name)
                tracker_pose_bone.custom_shape = tracker_obj
                tracker_pose_bone.color.palette = "THEME01"

                offset_pose_bone = pose_bones.get(f"{tracker_name} Offset")
                offset_pose_bone.custom_shape = offset_obj
                offset_pose_bone.color.palette = "THEME03"
                offset_pose_bone.custom_shape_wire_width = 3

                # Set up constraints.

                # Clear existing constraints
                for constraint in offset_pose_bone.constraints:
                    if constraint.name.startswith("TTK_"):
                        offset_pose_bone.constraints.remove(constraint)

                constraint_loc = offset_pose_bone.constraints.new("COPY_LOCATION")
                constraint_loc.name = "TTK_Loc"
                constraint_loc.target = arm
                constraint_loc.subtarget = tracker_pose_bone.name
                constraint_loc.use_offset = True

                constraint_rot = offset_pose_bone.constraints.new("COPY_ROTATION")
                constraint_rot.name = "TTK_Rot"
                constraint_rot.target = arm
                constraint_rot.subtarget = tracker_pose_bone.name

        # Empty references
        else:
            print("Creating empty references.")

            # Create root
            root_empty = bpy.data.objects.get("XR Root")

            # Delete existing root.
            if root_empty:
                delete_recursive(root_empty)

            bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 0))
            root_empty = bpy.context.object
            root_empty.name = "XR Root"
            root_empty.empty_display_size = 0.1

            def ensure_empty(name):
                # Create empty.
                _empty = bpy.data.objects.get(name)
                if not _empty:
                    _empty = bpy.data.objects.new(name, None)
                    context.scene.collection.objects.link(_empty)

                # Set up parenting.
                _empty.parent = root_empty

                # Set up rotation modes.
                _empty.rotation_mode = "QUATERNION"

                return _empty

            # Create empties for each tracker.
            for tracker in xr_context.trackers:
                tracker_name = tracker.nickname

                tracker_empty = ensure_empty(tracker_name)
                offset_empty = ensure_empty(f"{tracker_name} Offset")

                # Set up constraints.

                # Clear existing constraints
                for constraint in offset_empty.constraints:
                    if constraint.name.startswith("TTK_"):
                        offset_empty.constraints.remove(constraint)

                constraint_loc = offset_empty.constraints.new("COPY_LOCATION")
                constraint_loc.name = "TTK_Loc"
                constraint_loc.target = tracker_empty
                constraint_loc.use_offset = True

                constraint_rot = offset_empty.constraints.new("COPY_ROTATION")
                constraint_rot.name = "TTK_Rot"
                constraint_rot.target = tracker_empty

                # Assign objects
                tracker.target.object = tracker_empty
                tracker.offset.object = offset_empty

        # Restore the previous selection and mode.
        try:
            if prev_obj:
                prev_obj.select_set(True)
                bpy.context.view_layer.objects.active = prev_obj

                if bpy.context.object.mode != prev_mode:  # Safe against linked library immutability.
                    bpy.ops.object.mode_set(mode=prev_mode)
        except ReferenceError:
            pass

        if should_reenable:
            start_preview()

        print("Done")
        return {"FINISHED"}
