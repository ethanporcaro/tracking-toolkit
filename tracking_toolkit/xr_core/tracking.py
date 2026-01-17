import datetime

import bpy
import mathutils
from bpy_extras import anim_utils

from .actions import vive_role_strings
from .core import start_xr, tick_xr, stop_xr
from ..properties import XRContext
from ... import __package__ as base_package

# Shared variables
data_buffer = []
should_stop = False


def _update_tracker_list(poses):
    xr_context: XRContext = bpy.context.scene.XRContext
    if not xr_context.enabled:
        return

    # Check if trackers changed
    new_trackers = poses.keys()
    current_trackers = [tracker.name for tracker in xr_context.trackers]
    if set(new_trackers) != set(current_trackers):
        print("Updating trackers")

        preferences = bpy.context.preferences.addons[base_package].preferences

        xr_context.trackers.clear()

        for i, tracker_name in enumerate(poses.keys()):
            # Check if nickname is in preference already.
            nickname = tracker_name
            for n in preferences.nicknames:
                if tracker_name == n.real_name:
                    nickname = n.nickname

            # Set up tracker property data.
            tracker = xr_context.trackers.add()
            tracker.name = tracker_name
            tracker.nickname = nickname
            tracker.prev_nickname = nickname
            tracker.type = (
                "tracker" if tracker_name in vive_role_strings else
                "hmd" if tracker_name == "head" else "controller"
            )
            tracker.index = i


def _xr_tick_timer():
    global data_buffer, should_stop

    poses = tick_xr()
    if poses:
        _update_tracker_list(poses)
        data_buffer.append([datetime.datetime.now(), poses])

    return 1.0 / 90  # 90hz


def _clear_buffer():
    global data_buffer
    data_buffer.clear()


def _get_buffer() -> list[tuple[datetime.datetime, dict[str, mathutils.Matrix]]]:
    global data_buffer
    return data_buffer.copy()


def _get_latest_poses() -> dict[str, mathutils.Matrix] | None:
    global data_buffer
    if len(data_buffer) == 0:
        return None

    return data_buffer[-1][1]


def _apply_poses():
    # Don't preview when playing, since a previous recording may interfere
    if bpy.context.screen.is_animation_playing:
        return

    pose_data = _get_latest_poses()
    if not pose_data:
        return

    trackers = bpy.context.scene.XRContext.trackers

    for pose_name in pose_data.keys():
        pose = pose_data[pose_name]

        # Get the tracker object.
        tracker_obj = None
        for tracker in trackers:
            if tracker.name == pose_name:
                tracker_obj = tracker.target.object
                break

        if not tracker_obj:
            continue

        tracker_obj.matrix_world = pose


def _pose_vis_timer():
    _apply_poses()
    return 1.0 / 60  # 60hz


def _insert_action():
    xr_context = bpy.context.scene.XRContext

    pose_data = _get_buffer()
    num_samples = len(pose_data)
    print(f"OpenXR Processing {num_samples} recorded samples")

    if num_samples == 0:
        print(f"OpenXR Found no samples to process")
        return

    # Frame and conversion math
    framerate = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    start_frame = xr_context.record_start_frame

    # Create object to store processed animation data
    animation_data = {}

    # Process samples into a large buffer, so we can efficiently apply it later
    print("OpenXR Converting samples...")
    for time, sample in pose_data:
        for name, pose in sample.items():
            # Get the tracker object.
            tracker_obj = None
            for tracker in bpy.context.scene.XRContext.trackers:
                if tracker.name == name:
                    tracker_obj = tracker.target.object
                    break

            if not tracker_obj:
                continue

            # Create animation data if it doesn't exist
            if tracker_obj.animation_data is None:
                tracker_obj.animation_data_create()

            # Initialize data structure for this object if it's the first time we see it.
            if name not in animation_data:
                animation_data[name] = {
                    "obj": tracker_obj,
                    "frames": [],
                    "locs": [],
                    "rots": [],
                    "scales": []
                }

            # Calculate frame number
            time_delta = time - pose_data[0][0]
            frame = start_frame + time_delta.total_seconds() * framerate

            # Decompose the matrix and append data
            loc, rot, scale = pose.decompose()

            data = animation_data[name]
            data["frames"].append(frame)
            data["locs"].extend(loc)
            data["rots"].extend(rot)
            data["scales"].extend(scale)

    # Now insert or replace the data
    print("OpenXR Inserting data...")
    for tracker_name, data in animation_data.items():
        print(">", tracker_name)

        tracker_obj = data["obj"]
        num_keys = len(data["frames"])

        # Create animation data and action
        if not tracker_obj.animation_data:
            tracker_obj.animation_data_create()

        action = tracker_obj.animation_data.action
        if not action:
            action = bpy.data.actions.new(name=f"{tracker_obj.name}_Action")
            tracker_obj.animation_data.action = action

        # Map the F-Curve data_path and array_index to our collected data.
        fcurve_props = [
            ("location", 3, data["locs"]),
            ("rotation_quaternion", 4, data["rots"]),
            ("scale", 3, data["scales"])
        ]

        for data_path, num_components, values in fcurve_props:
            for i in range(num_components):
                # Get or create the F-Curve
                if len(action.slots) > 0:
                    action_slot = action.slots[0]
                else:
                    action_slot = action.slots.new("OBJECT", "MOCAP")

                channelbag = anim_utils.action_ensure_channelbag_for_slot(action, action_slot)
                fcurve = channelbag.fcurves.find(data_path, index=i)
                if fcurve:
                    channelbag.fcurves.remove(fcurve)
                fcurve = channelbag.fcurves.new(data_path, index=i)

                # Fill with points
                fcurve.keyframe_points.add(num_keys)

                # Create the flattened list for foreach_set.
                # The format is [frame1, value1, frame2, value2, ...]

                # Initialize
                key_coords = [0.0] * (num_keys * 2)

                # We slice the values list to get the data for the current component (axis)
                component_values = values[i::num_components]

                key_coords[0::2] = data["frames"]
                key_coords[1::2] = component_values

                # Set all keyframe coordinates at once
                fcurve.keyframe_points.foreach_set("co", key_coords)

                # Update the fcurve to apply changes
                fcurve.update()

        # Select first action slot
        # Otherwise, the new keyframes will not show
        action_slot = action.slots[0]
        tracker_obj.animation_data.action_slot = action_slot

    print("Done")


def start_recording():
    _clear_buffer()

    print("OpenXR Recording Started")


def stop_recording():
    _insert_action()
    _clear_buffer()

    print("OpenXR Recording Stopped")


def start_preview():
    _clear_buffer()
    start_xr()

    if not bpy.app.timers.is_registered(_xr_tick_timer):
        bpy.app.timers.register(_xr_tick_timer)

    if not bpy.app.timers.is_registered(_pose_vis_timer):
        bpy.app.timers.register(_pose_vis_timer)

    print("OpenXR Preview Started")


def stop_preview():
    if bpy.app.timers.is_registered(_pose_vis_timer):
        bpy.app.timers.unregister(_pose_vis_timer)

    if bpy.app.timers.is_registered(_xr_tick_timer):
        bpy.app.timers.unregister(_xr_tick_timer)

    stop_xr()
    _clear_buffer()

    print("OpenXR Preview Stopped")
