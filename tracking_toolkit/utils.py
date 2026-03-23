import os
import re

import bpy
from bpy_extras import anim_utils
from mathutils import Vector


def get_context() -> "XRContext":
    """
    Get the shared XRContext properties instance.
    """
    # noinspection PyUnresolvedReferences
    return bpy.context.scene.XRContext


class TempModeContext:
    """
    Context class for temporarily setting mode, then restoring it after.
    """

    def __init__(self, mode):
        self.mode = mode

    def __enter__(self):
        # Set to object mode while keeping track of the previous one.
        self.prev_obj = bpy.context.object

        if self.prev_obj:
            self.prev_mode = self.prev_obj.mode
            bpy.ops.object.mode_set(mode=self.mode)

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore the previous selection and mode.
        try:
            if self.prev_obj:
                # Restore selection.
                select_obj(self.prev_obj)

                # We can only guarantee safety in modes like edit or pose when an object is selected.
                bpy.ops.object.mode_set(mode=self.prev_mode)

        except ReferenceError:
            pass


def delete_recursive(obj: bpy.types.Object):
    """
    Recursively delete an object and its children.
    """
    with TempModeContext("OBJECT"):
        for child in obj.children:
            delete_recursive(child)
        bpy.data.objects.remove(obj, do_unlink=True)


def select_obj(target_obj: bpy.types.Object, only: bool = False):
    """
    Select an object. Optionally deselect all others.
    """
    if only:
        bpy.ops.object.select_all(action="DESELECT")
    target_obj.select_set(True)
    bpy.context.view_layer.objects.active = target_obj


def _ensure_widgets() -> tuple[bpy.types.Object, bpy.types.Object]:
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

    with TempModeContext("OBJECT"):
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


def ensure_bone(
    arm: bpy.types.Object, name: str, small: bool = False
) -> bpy.types.Object:
    """
    Create or return a bone for an armature with a certain name.
    """
    assert bpy.context.object == arm, "Armature must be selected to ensure bone."
    with TempModeContext("EDIT"):
        edit_bones = arm.data.edit_bones
        bone = edit_bones.get(name)
        if not bone:
            bone = edit_bones.new(name)
        bone.head = Vector((0, 0, 0))

        if small:
            bone.tail = Vector((0, 0.2, 0))
        else:
            bone.tail = Vector((0, 1, 0))

        return bone


def ensure_empty(name):
    """
    Create or return an empty with a certain name.
    """
    with TempModeContext("OBJECT"):
        empty = bpy.data.objects.get(name)
        if not empty:
            empty = bpy.data.objects.new(name, None)
            bpy.context.scene.collection.objects.link(empty)

        # Set up rotation modes.
        empty.rotation_mode = "QUATERNION"

        return empty


def create_bone_references():
    print("Creating bone references.")

    xr_context = get_context()

    with TempModeContext("OBJECT"):
        # Ensure the armature exists.
        arm = bpy.data.objects.get("XR Trackers")
        if not arm:
            arm_data = bpy.data.armatures.new("XR Trackers")
            arm = bpy.data.objects.new("XR Trackers", arm_data)
            bpy.context.scene.collection.objects.link(arm)
        select_obj(arm)

        # Root bone.
        ensure_bone(arm, "root", small=True)

        # Create bones for each tracker.
        for tracker in xr_context.trackers:
            role_string = tracker.naming.role_string
            nickname = tracker.naming.nickname

            # Create bones.

            with TempModeContext("EDIT"):
                # Get root bone again in case the old reference broke during mode change.
                root = arm.data.edit_bones.get("root")

                tracker_bone = ensure_bone(arm, nickname)
                tracker_bone.parent = root

                offset_bone = ensure_bone(arm, f"{nickname} Offset")
                offset_bone.parent = tracker_bone

            # Set shape.

            # Make sure widgets exist.
            tracker_obj, offset_obj = _ensure_widgets()

            pose_bones = arm.pose.bones

            tracker_pose_bone = pose_bones.get(nickname)
            tracker_pose_bone.custom_shape = tracker_obj
            tracker_pose_bone.color.palette = "THEME01"
            tracker_pose_bone["role_string"] = role_string
            tracker_pose_bone["ref_type"] = "tracker"

            offset_pose_bone = pose_bones.get(f"{nickname} Offset")
            offset_pose_bone.custom_shape = offset_obj
            offset_pose_bone.color.palette = "THEME03"
            offset_pose_bone.custom_shape_wire_width = 3
            offset_pose_bone["role_string"] = role_string
            offset_pose_bone["ref_type"] = "offset"


def create_empty_references():
    print("Creating empty references.")

    xr_context = get_context()

    with TempModeContext("OBJECT"):
        # Create root

        root_empty = bpy.data.objects.get("XR Root")

        # Delete existing root.
        if root_empty:
            delete_recursive(root_empty)

        root_empty = ensure_empty("XR Root")
        root_empty.empty_display_size = 0.1

        # Create empties for each tracker.
        for tracker in xr_context.trackers:
            role_string = tracker.naming.role_string
            nickname = tracker.naming.nickname

            tracker_empty = ensure_empty(nickname)
            offset_empty = ensure_empty(f"{nickname} Offset")

            tracker_empty.parent = root_empty
            tracker_empty["role_string"] = role_string
            tracker_empty["ref_type"] = "tracker"

            offset_empty.parent = tracker_empty
            offset_empty["role_string"] = role_string
            offset_empty["ref_type"] = "offset"


def convert_bones_to_empties():
    """
    Converts bones to empties. Animation data is copied.
    """
    print("Converting bones to empties.")

    xr_context = get_context()

    arm = bpy.data.objects.get("XR Trackers")
    if not arm:
        # FIXME: This can probable be handled better.
        return

    # Create empties to convert data to.
    create_empty_references()

    animation_data = arm.animation_data
    if animation_data and animation_data.action:
        arm_action = animation_data.action

        for tracker in xr_context.trackers:
            nickname = tracker.naming.nickname

            bone = arm.pose.bones.get(nickname)
            if not bone:
                raise RuntimeError(f"Bone {nickname} does not exist.")

            empty = bpy.data.objects.get(nickname)
            if not empty:
                raise RuntimeError(f"Empty {nickname} does not exist.")

            empty.animation_data_create()

            # Copy action and rename channels.
            empty_action = arm_action.copy()
            empty_action.name = f"{nickname}_{arm_action.name}"

            fcurves = anim_utils.action_get_channelbag_for_slot(
                empty_action, empty_action.slots[0]
            ).fcurves
            for fcurve in fcurves:
                # Only get the fcurve for the current tracker's bone.
                if not fcurve.data_path.startswith(f'pose.bones["{nickname}"].'):
                    fcurves.remove(fcurve)
                    continue

                new_path = re.sub(r".+\.([^.]+)$", r"\1", fcurve.data_path)
                fcurve.data_path = new_path

            empty.animation_data.action = empty_action
            empty.animation_data.action_slot = empty_action.slots[0]

    # Delete bones.
    with TempModeContext("OBJECT"):
        root = bpy.data.objects.get("XR Trackers")
        if root:
            delete_recursive(root)


def convert_empties_to_bones():
    """
    Converts empties to bones. Animation data is copied.
    """
    print("Converting empties to bones.")

    xr_context = get_context()

    # Create empties to convert data to.
    create_bone_references()

    arm = bpy.data.objects.get("XR Trackers")
    if not arm:
        # This should be impossible.
        return

    arm.animation_data_create()

    for tracker in xr_context.trackers:
        nickname = tracker.naming.nickname

        empty = bpy.data.objects.get(nickname)
        if not empty:
            print(f"Empty {nickname} does not exist. Skipping.")
            continue

        animation_data = empty.animation_data
        if not animation_data:
            print(f"Empty {nickname} does have animation data. Skipping.")
            continue

        empty_action = animation_data.action
        if not empty_action:
            print(f"Empty {nickname} does have action. Skipping.")
            continue

        bone = arm.pose.bones.get(nickname)
        if not bone:
            raise RuntimeError(f"Bone {nickname} does not exist.")

        # On the first time, create the armature action.
        # We do it here since we know the action name now.
        arm_action = arm.animation_data.action
        if not arm_action:
            arm_action_name = empty_action.name.replace(f"{nickname}_", "")
            arm_action = bpy.data.actions.new(name=arm_action_name)
            arm.animation_data.action = arm_action
            arm.animation_data.action_slot = arm_action.slots.new("OBJECT", "MOCAP")

        # Get fcurves for arm and empty.
        # Add copy of empty fcurve to arm with the reformatted name.

        arm_fcurves = anim_utils.action_ensure_channelbag_for_slot(
            arm_action, arm_action.slots[0]
        ).fcurves

        empty_fcurves = anim_utils.action_get_channelbag_for_slot(
            empty_action, empty_action.slots[0]
        ).fcurves

        for empty_fcurve in empty_fcurves:
            new_path = f'pose.bones["{nickname}"].{empty_fcurve.data_path}'

            # Remove existing fcurve if present.
            arm_fcurve = arm_fcurves.find(new_path, index=empty_fcurve.array_index)
            if arm_fcurve:
                arm_fcurves.remove(arm_fcurve)

            arm_fcurve = arm_fcurves.new(
                data_path=new_path, index=empty_fcurve.array_index
            )

            # Copy over data.
            key_coords = []
            for kp in empty_fcurve.keyframe_points:
                key_coords.append(kp.co[0])  # Time.
                key_coords.append(kp.co[1])  # Value.

            arm_fcurve.keyframe_points.add(len(key_coords) // 2)
            arm_fcurve.keyframe_points.foreach_set("co", key_coords)
            arm_fcurve.update()

    # Delete empties.
    with TempModeContext("OBJECT"):
        root = bpy.data.objects.get("XR Root")
        if root:
            delete_recursive(root)
