import bpy
import bpy_extras
import openvr
from mathutils import Matrix

from .properties import OVRContext


def load_trackers(ovr_context: OVRContext, reset=False):
    system = openvr.VRSystem()

    if reset:
        ovr_context.trackers.clear()

    for i in range(openvr.k_unMaxTrackedDeviceCount):
        if system.getTrackedDeviceClass(i) == openvr.TrackedDeviceClass_Invalid:
            continue

        tracker_serial = system.getStringTrackedDeviceProperty(i, openvr.Prop_SerialNumber_String)
        matches = [tracker for tracker in ovr_context.trackers if tracker.serial == tracker_serial]
        assert len(matches) < 2, "No two trackers should have the same serial number!"

        # Existing tracker
        if len(matches) == 1:
            tracker = matches[0]
        else:
            tracker = ovr_context.trackers.add()
            tracker.name = tracker_serial
            tracker.serial = tracker_serial
            tracker.type = str(system.getTrackedDeviceClass(i))

        tracker.index = i  # Just in case, do it for both existing and non-existing
        tracker.connected = bool(system.isTrackedDeviceConnected(i))


def track_trackers(ovr_context: OVRContext):
    system = openvr.VRSystem()
    poses, _ = openvr.VRCompositor().waitGetPoses([], None)

    for tracker in ovr_context.trackers:
        tracker.connected = bool(system.isTrackedDeviceConnected(tracker.index))
        if not tracker.connected:
            continue

        absolute_pose = poses[tracker.index].mDeviceToAbsoluteTracking

        mat = Matrix([list(absolute_pose[0]), list(absolute_pose[1]), list(absolute_pose[2]), [0, 0, 0, 1]])
        mat_world = bpy_extras.io_utils.axis_conversion("Z", "Y", "Y", "Z").to_4x4()
        mat_world = mat_world @ mat

        # Apply scale
        root = bpy.data.objects.get("OVR Root")
        if root:
            mat_world.translation = mat_world.translation * (root.scale * 2)
            mat_world = mat_world @ Matrix.Scale(root.scale.length, 4)

        # Apply
        tracker_obj = bpy.data.objects.get(tracker.name)

        # If it doesn't exist, resync the trackers.
        if not tracker_obj:
            load_trackers(ovr_context)
            continue  # We'll catch it next time around

        tracker_obj.matrix_world = mat_world

        if bpy.context.scene.tool_settings.use_keyframe_insert_auto:
            tracker_obj.keyframe_insert("location")
            tracker_obj.keyframe_insert("rotation_euler")
            tracker_obj.keyframe_insert("scale")
