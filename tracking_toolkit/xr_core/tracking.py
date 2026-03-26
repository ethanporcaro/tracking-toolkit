import datetime

import bpy
import mathutils
from bpy_extras import anim_utils

from .actions import vive_role_strings
from .core import start_xr, tick_xr, stop_xr
from ..preferences import get_preferences
from ..utils import get_context, get_state

# Shared variables
data_buffer = []
should_stop = False


def _update_tracker_list(poses):
    xr_context = get_context()
    xr_state = get_state()

    if not xr_state.enabled:
        return

    # Check if trackers changed.
    new_trackers = poses.keys()
    current_tracker_roles = [
        tracker.naming.role_string for tracker in xr_context.trackers
    ]
    if set(new_trackers) != set(current_tracker_roles):

        for i, role_string in enumerate(poses.keys()):
            # Don't touch existing.
            if role_string in current_tracker_roles:
                continue

            # Apply default nicknames to this new tracker.
            nickname = "unknown"
            for n in get_preferences().naming:
                if n.role_string == role_string:
                    nickname = str(n.nickname)

            print(f"Adding new tracker: {nickname} ({role_string})")

            # Set up tracker property data.
            tracker = xr_context.trackers.add()
            tracker.naming.role_string = role_string
            tracker.naming.nickname = nickname
            tracker.naming.prev_nickname = nickname
            tracker.type = (
                "tracker"
                if role_string in vive_role_strings
                else "hmd" if role_string == "head" else "controller"
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

    preferences = get_preferences()
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

    xr_context = get_context()

    for role_string in pose_data.keys():
        pose = pose_data[role_string]

        # Apply bone transforms.
        if xr_context.use_bones:
            armature = bpy.data.objects.get("XR Trackers")
            if not armature:
                return

            bones = armature.pose.bones
            for bone in bones:
                if not bone.get("role_string") == role_string:
                    continue

                if not bone.get("ref_type") == "tracker":
                    continue

                bone.matrix = pose

        # Apply empty transforms.
        else:
            for obj in bpy.data.objects:
                if not obj.get("role_string") == role_string:
                    continue

                if not obj.get("ref_type") == "tracker":
                    continue

                obj.matrix_world = pose


def _pose_vis_timer():
    _apply_poses()
    return 1.0 / 60  # 60hz


def _create_action(obj: bpy.types.Object, action_name: str):
    """
    Create a new action for an object.
    If an action already exists, it is pushed down onto an NLA track and muted.
    """

    # Create animation data if unavailable.
    if not obj.animation_data:
        obj.animation_data_create()

    # If an action already exists, push it to a new track and mute it.
    action = obj.animation_data.action
    if action:
        track = obj.animation_data.nla_tracks.new()
        track.name = action.name
        track.strips.new(action.name, int(action.frame_range[0]), action)
        track.mute = True

    # Create new action.
    action = bpy.data.actions.new(name=action_name)
    obj.animation_data.action = action

    # Create and select action slot.
    obj.animation_data.action_slot = action.slots.new("OBJECT", "MOCAP")

    return action


def _insert_action():
    xr_context = get_context()
    preferences = get_preferences()

    pose_data = _get_buffer()

    num_samples = len(pose_data)
    if num_samples == 0:
        print(f"OpenXR Found no samples to process")
        return

    # Calculate recording FPS.
    scene_fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    record_fps = (
        scene_fps if preferences.record_at_scene_fps else preferences.record_custom_fps
    )

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
        factor = 0
        if closest_idx == 0:
            prev_sample = pose_data[0][1]
            next_sample = pose_data[0][1]
        else:
            prev_time = source_times[closest_idx - 1]
            next_time = source_times[closest_idx]

            if prev_time != next_time:  # Prevent division by 0.
                factor = (current_time - prev_time) / (next_time - prev_time)

            prev_sample = pose_data[closest_idx - 1][1]
            next_sample = pose_data[closest_idx][1]

        for name, next_pose in next_sample.items():
            # Get the tracker.
            tracker_object = None
            for tracker in get_context().trackers:
                if tracker.naming.role_string == name:
                    tracker_object = tracker
                    break

            if not tracker_object:
                continue

            # Initialize data structure for this object if it's the first time we see it.
            if name not in animation_data:
                animation_data[name] = {
                    "tracker": tracker_object,
                    "frames": [],
                    "locs": [],
                    "rots": [],
                    "scales": [],
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

            # Decompose the matrix and append data.
            loc, rot, scale = lerp_pose.decompose()

            data = animation_data[name]
            data["frames"].append(frame)
            data["locs"].extend(loc)
            data["rots"].extend(rot)
            data["scales"].extend(scale)

        # Increment.
        current_time += 1 / record_fps
        frame += 1 * (
            scene_fps / record_fps
        )  # Compensate for difference in scene and record fps

    # Now insert or replace the data
    print("OpenXR Inserting data...")

    # Format SMPTE timecode.
    # Also calculate the frame based on the current microsecond/scene time.
    # The frame is truncated down.
    time_string = start_time.strftime("%H:%M:%S")
    second_offset = start_time.microsecond / (1000 * 1000)
    frame_offset = int(second_offset * record_fps)
    time_string += f":{frame_offset}"

    print(f"Using SMPTE timecode: {time_string}")

    action = None

    for tracker_name, data in animation_data.items():
        print(">", tracker_name)

        tracker = data["tracker"]
        nickname = tracker.naming.nickname
        num_keys = len(data["frames"])

        # Create actions.

        # When using bones, only one action is created for the entire armature.
        if xr_context.use_bones:
            if not action:  # We are in a loop, so ensure it's only created once.
                arm = bpy.data.objects.get("XR Trackers")
                if not arm:
                    raise ValueError("Could not find armature")  # FIXME: Handle this.

                action = _create_action(arm, time_string)

        # When using empties, create an action for each empty object.
        # The action name will be prefixed with the tracker name to prevent conflicts.
        else:
            empty = bpy.data.objects.get(nickname)
            action = _create_action(empty, f"{tracker_name}_{time_string}")

        # Determine the property names for the fcurve channels we will put animation data into.
        # Armature actions are handled a little differently.
        if xr_context.use_bones:
            data_path_prefix = f'pose.bones["{nickname}"]'
            fcurve_props = [
                (f"{data_path_prefix}.location", 3, data["locs"]),
                (f"{data_path_prefix}.rotation_quaternion", 4, data["rots"]),
                (f"{data_path_prefix}.scale", 3, data["scales"]),
            ]
        else:
            fcurve_props = [
                ("location", 3, data["locs"]),
                ("rotation_quaternion", 4, data["rots"]),
                ("scale", 3, data["scales"]),
            ]

        # Efficiently insert animation data by directly inserting it into the fcurves.
        for data_path, num_components, values in fcurve_props:
            # Loop over every component (eg x, y, z, etc.)/
            for i in range(num_components):
                # Get or create the F-Curve.
                channelbag = anim_utils.action_ensure_channelbag_for_slot(
                    action, action.slots[0]
                )
                fcurve = channelbag.fcurves.find(data_path, index=i)
                if fcurve:
                    channelbag.fcurves.remove(fcurve)
                fcurve = channelbag.fcurves.new(data_path, index=i)

                # Fill with points.
                fcurve.keyframe_points.add(num_keys)

                # Create the flattened list for foreach_set.
                # The format is [frame1, value1, frame2, value2, ...].

                # Allocate array elements.
                key_coords = [0.0] * (num_keys * 2)

                # We slice the values list to get the data for the current component (axis).
                component_values = values[i::num_components]

                key_coords[0::2] = data["frames"]  # Frame numbers on even elements.
                key_coords[1::2] = component_values  # Data values on odd elements.

                # Set all keyframe coordinates at once.
                fcurve.keyframe_points.foreach_set("co", key_coords)

                # Update the fcurve to apply changes.
                fcurve.update()

    print("Done")


def _xr_countdown_timer():
    xr_state = get_state()

    if not xr_state.recording:
        print("OpenXR Countdown Canceled")
        return None

    xr_state.countdown -= 1

    # Update UI to show status.
    for area in bpy.context.screen.areas:
        area.tag_redraw()

    # Clear buffer, so the recorded data starts now.
    # Use < 1 in case it somehow goes negative.
    if xr_state.countdown < 1:
        print("OpenXR Recording Started")
        _clear_buffer()
        return None

    print(f"OpenXR recording starting in {xr_state.countdown}s")
    return 1


def start_recording():
    xr_context = get_context()
    xr_state = get_state()

    # Get timer delay.
    delay_val = xr_context.timer
    if delay_val == "CUSTOM":
        delay = xr_context.timer_custom
    else:
        delay = int(delay_val)

    xr_state.countdown = (
        delay + 1
    )  # Add one since the value is decremented at the start of the timer.

    if not bpy.app.timers.is_registered(_xr_countdown_timer):
        bpy.app.timers.register(_xr_countdown_timer)

    xr_state.recording = True
    print("OpenXR Countdown Started")


def stop_recording():
    xr_state = get_state()

    xr_state.recording = False

    if xr_state.countdown > 0:
        return  # Recording was probably canceled.

    _insert_action()
    _clear_buffer()

    print("OpenXR Recording Stopped")


def start_preview():
    _clear_buffer()
    start_xr()
    get_state().enabled = True

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

    xr_state = get_state()
    xr_state.enabled = False
    xr_state.recording = False

    print("OpenXR Preview Stopped")
