import datetime
from collections import defaultdict

import bpy
import mathutils
from bpy_extras import anim_utils

from .preferences import get_preferences, PreferenceInputMapping
from .protocol import start_xr, tick_xr, stop_xr, is_xr_running, PoseData
from .utils import get_context, get_state

# Shared variables
data_buffer = []
armed_triggers = []
initial_poses = {}


def _update_tracker_list(poses: dict[str, PoseData]):
    global initial_poses
    xr_context = get_context()
    is_running = is_xr_running()

    if not is_running:
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

            # Only add if the tracker has moved from its initial position.
            loc = poses[role_string].pose.to_translation()

            if role_string not in initial_poses:
                # Sometimes disconnected trackers start at 0 then jump to some fixed position.
                # Don't treat that jump as movement.
                if loc.length == 0:
                    continue

                initial_poses[role_string] = loc.copy()
                continue

            distance = (loc - initial_poses[role_string]).length
            if distance < 0.001:
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
            tracker.index = i


def _xr_tick_timer():
    global data_buffer

    poses = tick_xr()
    if poses:
        _update_tracker_list(poses)
        data_buffer.append([datetime.datetime.now(), poses])

    return 1.0 / 90  # 90fps just for preview.


def _clear_buffer():
    global data_buffer
    global initial_poses
    data_buffer.clear()
    initial_poses.clear()


def _get_buffer() -> list[tuple[datetime.datetime, dict[str, PoseData]]]:
    global data_buffer
    return data_buffer.copy()


def _get_latest_data() -> dict[str, PoseData] | None:
    global data_buffer
    if len(data_buffer) == 0:
        return None

    return data_buffer[-1][1]


def _handle_actions(role_string: str, pose_data: PoseData):
    """
    Handle the events triggered by actions. The mapping is stored in the preferences menu.
    """

    # Calculate leaped values.

    # Map data to preference key names.
    data = {
        "Trigger": pose_data.trigger,
        "A": pose_data.button_a,
        "B": pose_data.button_b,
        "X": pose_data.button_x,
        "Y": pose_data.button_y,
    }

    # Check actions.

    xr_state = get_state()
    preferences = get_preferences()
    map_: PreferenceInputMapping = preferences.input_mapping

    def _check_input(action_name: str) -> bool:
        """
        Utility to check if an action trigger is met.
        """
        role_prop = getattr(map_, f"{action_name}_role", None)
        ipt_prop = getattr(map_, f"{action_name}_input", None)

        if not role_prop or not ipt_prop:
            return False

        if role_prop != role_string:
            return False

        value = data.get(ipt_prop)
        if value is None:
            return False

        is_pressed = float(value) >= 0.9

        # Check if the trigger is armed.
        # This means that it was held before.
        # If it is no longer held, that triggers the event.
        global armed_triggers

        is_armed = action_name in armed_triggers

        # If pressed and unarmed, arm the event.
        if is_pressed:
            if not is_armed:
                armed_triggers.append(action_name)

        # If not pressed, and was armed before, fire event and disarm.
        else:
            if is_armed:
                print(f"Triggered {action_name}!")
                armed_triggers.remove(action_name)
                return True

        return False

    if _check_input("toggle_capture"):
        bpy.ops.screen.animation_pause()
        if xr_state.recording:
            stop_recording()
        else:
            bpy.context.scene.frame_set(0)
            start_recording()

    # Capture the current pose to the current keyframe.
    if _check_input("single_capture"):
        if not xr_state.recording:
            _insert_keyframe(_get_latest_data())

    if _check_input("frame_forward"):
        if not xr_state.recording:
            bpy.context.scene.frame_current += 1

    if _check_input("frame_backward"):
        if not xr_state.recording:
            bpy.context.scene.frame_current -= 1

    if _check_input("playback"):
        if not xr_state.recording:
            if bpy.context.screen.is_animation_playing:
                bpy.ops.screen.animation_pause()
            else:
                if map_.playback_restart:
                    bpy.context.scene.frame_set(0)
                bpy.ops.screen.animation_play()


def _apply_poses():
    pose_data = _get_latest_data()
    if not pose_data:
        return

    xr_context = get_context()

    for role_string in pose_data.keys():
        data = pose_data[role_string]

        _handle_actions(role_string, data)

        # Don't preview when playing, since a previous recording may interfere.
        if bpy.context.screen.is_animation_playing:
            return

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

                bone.matrix = data.pose

        # Apply empty transforms.
        else:
            for obj in bpy.data.objects:
                if not obj.get("role_string") == role_string:
                    continue

                if not obj.get("ref_type") == "tracker":
                    continue

                obj.matrix_world = data.pose


def _pose_vis_timer():
    _apply_poses()
    return 1.0 / 90  # 90fps.


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


def _insert_keyframe(pose_data: dict[str, PoseData]):
    """Insert a single keyframe on the timeline."""

    xr_context = get_context()

    for name, data in pose_data.items():
        # Get the tracker.
        tracker_object = None
        for tracker in get_context().trackers:
            if tracker.naming.role_string == name:
                tracker_object = tracker
                break

        if not tracker_object:
            continue

        nickname = tracker_object.naming.nickname

        obj = None
        if xr_context.use_bones:
            arm = bpy.data.objects.get("XR Trackers")
            if not arm:
                print("Could not find armature. Data was not applied.")
                return

            bone = arm.pose.bones.get(nickname)
            if not bone:
                print(f"Could not find bone for {nickname}. Skipping.")
                continue

            obj = bone

        else:
            obj = bpy.data.objects.get(nickname)
            if not obj:
                print(f"No references found for {nickname}. Skipping.")
                continue

        def _insert_key(path: str, value):
            obj[path] = value
            obj.keyframe_insert(data_path=path)
            obj.rotation_mode = "QUATERNION"

        loc, rot, scale = data.pose.decompose()
        _insert_key("location", data.pose.translation)
        _insert_key("rotation_quaternion", rot)
        _insert_key("scale", scale)


def _insert_action(relative_time: bool = False):
    xr_context = get_context()
    preferences = get_preferences()

    pose_data = _get_buffer()

    num_samples = len(pose_data)
    if num_samples == 0:
        print(f"OpenXR Found no samples to process")
        return

    # Calculate recording FPS based on scene FPS and framerate type.
    scene_fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    record_rate_type = preferences.record_timing_type
    if record_rate_type == "FPS":
        record_fps = preferences.record_custom_fps
    elif record_rate_type == "Interval":
        record_fps = round(scene_fps / preferences.record_custom_interval, 2)
    else:
        record_fps = scene_fps

    start_time = pose_data[0][0]
    end_time = pose_data[-1][0]
    total_duration = (end_time - start_time).total_seconds()
    total_frames = round(total_duration * record_fps)
    source_times = [(t - start_time).total_seconds() for t, _ in pose_data]

    # The samples might not be at the correct interval. Here, we go through each frame and linearly interpolate.

    print(f"OpenXR Converting samples at {record_fps}fps...")
    print(f"Frames: {total_frames}")
    print(f"Samples: {len(pose_data)}")
    print(f"Duration: {total_duration}")

    animation_data = {}
    current_time = 0
    min_index = 0  # Checkpoint the "closest index" to avoid recalculations.

    if relative_time:
        frame = bpy.context.scene.frame_current
    else:
        frame = 0

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

        for name, next_pose_data in next_sample.items():
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
                    "extras": [],
                }

            # Lerp pose.

            if name not in prev_sample:
                continue
            prev_pose_data = prev_sample[name]

            loc0, rot0, sca0 = prev_pose_data.pose.decompose()
            loc1, rot1, sca1 = next_pose_data.pose.decompose()

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

            # Add controller inputs.
            if tracker_object.naming.role_string in ["left_hand", "right_hand"]:
                data["extras"].append(
                    {
                        "trigger": prev_pose_data.trigger,
                        "button_a": prev_pose_data.button_a,
                        "button_b": prev_pose_data.button_b,
                        "button_x": prev_pose_data.button_x,
                        "button_y": prev_pose_data.button_y,
                    }
                )

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
    frame_offset_str = str(int(second_offset * record_fps))

    # Pad to at least two digits.
    if len(frame_offset_str) == 1:
        frame_offset_str = f"0{frame_offset_str}"

    time_string += f":{frame_offset_str}"

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
                    print("Could not find armature. Data was not applied.")
                    continue

                action = _create_action(arm, time_string)

        # When using empties, create an action for each empty object.
        # The action name will be prefixed with the tracker name to prevent conflicts.
        else:
            empty = bpy.data.objects.get(nickname)
            if not empty:
                print(f"No references found for {nickname}. Skipping.")
                continue

            action = _create_action(empty, f"{nickname}_{time_string}")

        # Determine the property names for the fcurve channels we will put animation data into.
        # Armature actions are handled a little differently.
        data_path_prefix = ""
        if xr_context.use_bones:
            data_path_prefix = f'pose.bones["{nickname}"].'

        fcurve_props = [
            (f"{data_path_prefix}location", 3, data["locs"]),
            (f"{data_path_prefix}rotation_quaternion", 4, data["rots"]),
            (f"{data_path_prefix}scale", 3, data["scales"]),
        ]

        # If using bones, remove the trailing dot (.) since we use bracket indexing for custom properties.
        if xr_context.use_bones:
            data_path_prefix = f'pose.bones["{nickname}"]'

        # Add extra channels.
        extra_sample_map = defaultdict(list)
        for extra_sample in data["extras"]:
            for k, v in extra_sample.items():
                extra_sample_map[k].append(v)
        for k, buffer in extra_sample_map.items():
            fcurve_props.append((f'{data_path_prefix}["{k}"]', 1, buffer))

        # Make sure custom properties exist.
        for prop_name in extra_sample_map.keys():
            if xr_context.use_bones:
                arm = bpy.data.objects.get("XR Trackers")
                bone = arm.pose.bones.get(nickname)
                if not bone:
                    continue
                obj = bone
            else:
                empty = bpy.data.objects.get(nickname)
                if not empty:
                    continue
                obj = empty

            obj[prop_name] = 0.0

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
    xr_state.recording = False

    print("OpenXR Preview Stopped")
