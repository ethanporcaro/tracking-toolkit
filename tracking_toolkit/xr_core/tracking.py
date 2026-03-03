import datetime

import bpy
import bpy_extras
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
        preferences = bpy.context.preferences.addons[base_package].preferences

        for i, tracker_name in enumerate(poses.keys()):
            # Don't touch existing.
            if tracker_name in current_trackers:
                continue

            # Check if nickname is in preference already.
            nickname = tracker_name
            for n in preferences.nicknames:
                if tracker_name == n.real_name:
                    nickname = n.nickname

            print(f"Adding new tracker: {nickname} ({tracker_name})")

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

    # Calculate recording FPS.
    # It may be a good idea to move this math outside the timer.

    preferences = bpy.context.preferences.addons[base_package].preferences
    if preferences.record_at_scene_fps:
        framerate = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    else:
        framerate = preferences.record_custom_fps

    return 1.0 / framerate


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

    xr_context = bpy.context.scene.XRContext
    trackers = xr_context.trackers

    for pose_name in pose_data.keys():
        pose = pose_data[pose_name]

        # Apply bone transforms.
        if xr_context.use_bones:
            armature = bpy.data.objects.get("XR Trackers")
            if not armature:
                return

            bones = armature.pose.bones
            for tracker in trackers:
                if tracker.name != pose_name:
                    continue

                tracker_bone = bones.get(tracker.nickname)
                if not tracker_bone:
                    continue

                tracker_bone.matrix = pose

        # Apply empty transforms.
        else:
            # Get the tracker object.
            tracker_obj = None
            for tracker in trackers:
                if tracker.name == pose_name:
                    tracker_obj = bpy.data.objects.get(tracker.nickname)
                    break

            if not tracker_obj:
                continue  # TODO: Error

            tracker_obj.matrix_world = pose


def _pose_vis_timer():
    _apply_poses()
    return 1.0 / 60  # 60hz


def _insert_action():
    xr_context = bpy.context.scene.XRContext
    preferences = bpy.context.preferences.addons[base_package].preferences

    pose_data = _get_buffer()

    num_samples = len(pose_data)
    if num_samples == 0:
        print(f"OpenXR Found no samples to process")
        return

    # Calculate recording FPS.
    scene_fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    record_fps = scene_fps if preferences.record_at_scene_fps else preferences.record_custom_fps

    start_time = pose_data[0][0]
    end_time = pose_data[-1][0]
    total_duration = (end_time - start_time).total_seconds()
    total_frames = round(total_duration * record_fps)
    source_times = [(t - start_time).total_seconds() for t, _ in pose_data]

    # The samples might not be at the correct interval. Here, we go through each frame and linearly interpolate.

    print("OpenXR Converting samples...")
    print(f"Frames: {total_frames}")
    print(f"Samples: {len(pose_data)}")
    print(f"Duration: {total_duration}")

    animation_data = {}
    current_time = 0
    frame = 0
    min_index = 0  # Checkpoint the "closest index" to avoid recalculations.

    while current_time <= total_duration:
        # Get closest sample.

        closest_idx = None
        for i in range(min_index, len(source_times)):
            if source_times[i] >= current_time:
                closest_idx = i
                min_index = i
                break

        if closest_idx is None:
            break  # We reached the end.

        # Interpolate the poses to be even with the framerate.
        # This is because the Blender timer might not have gone off at the correct interval.

        # Calculate lerp factor.
        if closest_idx == 0:
            prev_sample = pose_data[0][1]
            next_sample = pose_data[0][1]
            factor = 0
        else:
            prev_time = source_times[closest_idx - 1]
            next_time = source_times[closest_idx]

            if prev_time != next_time:  # Prevent division by 0.
                factor = (current_time - prev_time) / (next_time - prev_time)

            prev_sample = pose_data[closest_idx - 1][1]
            next_sample = pose_data[closest_idx][1]

        for name, next_pose in next_sample.items():
            # Get the tracker.
            tracker_data = None
            for tracker in bpy.context.scene.XRContext.trackers:
                if tracker.name == name:
                    tracker_data = tracker
                    break

            if not tracker_data:
                continue

            # Initialize data structure for this object if it's the first time we see it.
            if name not in animation_data:
                animation_data[name] = {
                    "tracker": tracker_data,
                    "frames": [],
                    "locs": [],
                    "rots": [],
                    "scales": []
                }

            # Lerp pose.

            if name not in prev_sample:
                continue
            prev_pose = prev_sample[name]

            loc0, rot0, sca0 = prev_pose.decompose()
            loc1, rot1, sca1 = next_pose.decompose()

            loc_final = loc0.lerp(loc1, factor)
            rot_final = rot0.slerp(rot1, factor)  # Slerp for rotation.
            sca_final = sca0.lerp(sca1, factor)

            lerp_pose = mathutils.Matrix.LocRotScale(loc_final, rot_final, sca_final)

            # Decompose and add to data structure

            # Inverse calculation from Blender space back to OpenXR space.
            # I don't quite know why this is needed, but it has to do with the way bone transformations are handled.
            if xr_context.use_bones:
                mat_world = bpy_extras.io_utils.axis_conversion(
                    "-Z", "Y", "Y", "Z"
                ).to_4x4().inverted()
                lerp_pose = mat_world @ lerp_pose

            # Decompose the matrix and append data.
            loc, rot, scale = lerp_pose.decompose()

            data = animation_data[name]
            data["frames"].append(frame)
            data["locs"].extend(loc)
            data["rots"].extend(rot)
            data["scales"].extend(scale)

        # Increment.
        current_time += 1 / record_fps
        frame += 1 * (scene_fps / record_fps)  # Compensate for difference in scene and record fps

    # Now insert or replace the data
    print("OpenXR Inserting data...")

    time_string = start_time.strftime("%Y/%m/%d_%H:%M:%S")

    # Keep track of armature creation, so it only happens once in the loop.
    has_created_armature_action = False

    for tracker_name, data in animation_data.items():
        print(">", tracker_name)

        tracker = data["tracker"]
        num_keys = len(data["frames"])

        if xr_context.use_bones:
            animated_obj = bpy.data.objects.get("XR Trackers")
        else:
            animated_obj = bpy.data.objects.get(tracker.nickname)  # Empty object references.

        if not animated_obj:
            continue  # TODO: Error

        # Create animation data if unavailable.
        if not animated_obj.animation_data:
            animated_obj.animation_data_create()

        # Create new actions.
        if not xr_context.use_bones or (xr_context.use_bones and not has_created_armature_action):
            # If an action already exists, push it to a new track and mute it.
            existing_action = animated_obj.animation_data.action
            if existing_action:
                track = animated_obj.animation_data.nla_tracks.new()
                track.name = existing_action.name
                track.strips.new(existing_action.name, int(existing_action.frame_range[0]), existing_action)
                track.mute = True

            # Create a new action.
            action = bpy.data.actions.new(name=f"{time_string}-{animated_obj.name}")
            animated_obj.animation_data.action = action

            # If using bones, mark action as created so we don't repeat it next iteration.
            if xr_context.use_bones:
                has_created_armature_action = True

        # Map the F-Curve data_path and array_index to our collected data.
        if xr_context.use_bones:
            data_path_prefix = f'pose.bones["{tracker.nickname}"]'
            fcurve_props = [
                (f"{data_path_prefix}.location", 3, data["locs"]),
                (f"{data_path_prefix}.rotation_quaternion", 4, data["rots"]),
                (f"{data_path_prefix}.scale", 3, data["scales"])
            ]

        else:
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

        # Select the first action slot.
        # Otherwise, the new keyframes will not show.
        action_slot = action.slots[0]
        animated_obj.animation_data.action_slot = action_slot

    print("Done")


def _xr_countdown_timer():
    xr_context: XRContext = bpy.context.scene.XRContext

    if not xr_context.recording:
        print("OpenXR Countdown Canceled")
        return None

    xr_context.countdown -= 1

    # Update UI to show status.
    for area in bpy.context.screen.areas:
        area.tag_redraw()

    # Clear buffer, so the recorded data starts now.
    # Use < 1 in case it somehow goes negative.
    if xr_context.countdown < 1:
        print("OpenXR Recording Started")
        _clear_buffer()
        return None

    print(f"OpenXR recording starting in {xr_context.countdown}s")
    return 1


def start_recording():
    xr_context: XRContext = bpy.context.scene.XRContext

    # Get timer delay.
    delay_val = xr_context.timer
    if delay_val == "CUSTOM":
        delay = xr_context.timer_custom
    else:
        delay = int(delay_val)

    xr_context.countdown = delay + 1  # Add one since the value is decremented at the start of the timer.

    if not bpy.app.timers.is_registered(_xr_countdown_timer):
        bpy.app.timers.register(_xr_countdown_timer)

    xr_context.recording = True
    print("OpenXR Countdown Started")


def stop_recording():
    xr_context: XRContext = bpy.context.scene.XRContext

    xr_context.recording = False

    if xr_context.countdown > 0:
        return  # Recording was probably canceled.

    _insert_action()
    _clear_buffer()

    print("OpenXR Recording Stopped")


def start_preview():
    xr_context: XRContext = bpy.context.scene.XRContext

    xr_context.trackers.clear()  # Fresh state. They get updated later.

    _clear_buffer()
    start_xr()
    xr_context.enabled = True

    if not bpy.app.timers.is_registered(_xr_tick_timer):
        bpy.app.timers.register(_xr_tick_timer)

    if not bpy.app.timers.is_registered(_pose_vis_timer):
        bpy.app.timers.register(_pose_vis_timer)

    print("OpenXR Preview Started")


def stop_preview():
    if bpy.app.timers.is_registered(_xr_tick_timer):
        bpy.app.timers.unregister(_xr_tick_timer)

    if bpy.app.timers.is_registered(_pose_vis_timer):
        bpy.app.timers.unregister(_pose_vis_timer)

    if bpy.app.timers.is_registered(_xr_tick_timer):
        bpy.app.timers.unregister(_xr_tick_timer)

    stop_xr()
    _clear_buffer()

    bpy.context.scene.XRContext.enabled = False
    bpy.context.scene.XRContext.recording = False

    print("OpenXR Preview Stopped")
