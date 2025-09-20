import ctypes
import datetime
import platform
import queue
import threading

import bpy
import bpy_extras
import mathutils
import xr
import xr.ext.HTCX.vive_tracker_interaction as vive_tracker_interaction

from .properties import VRContext

# Shared variables

pose_queue = queue.Queue()
polling_thread = None
stop_thread_flag = threading.Event()

data_buffer = []
buffer_lock = threading.Lock()

# OpenXR
instance: xr.Instance
system: ctypes.c_uint
session: xr.Session

paths: list[xr.Path] = []
action_set: xr.ActionSet
action_spaces = []
base_space: xr.Space
view_reference_space: xr.Space

# Role strings from
# https://www.khronos.org/registry/OpenXR/specs/1.0/html/xrspec.html#XR_HTCX_vive_tracker_interaction
use_vive = False
role_strings = [
    "left_foot",
    "right_foot",
    "left_elbow",
    "right_elbow",
    "left_knee",
    "right_knee",
    "waist",
    "chest"
]
role_path_strings = [f"/user/vive_tracker_htcx/role/{role}" for role in role_strings]

# Platform specific
if platform.system() == "Windows":
    kernel32 = ctypes.WinDLL("kernel32")


def _getTimeFunc():
    """
    # See https://github.com/cmbruns/pyopenxr_examples/blob/main/xr_examples/headless.py
    """
    if platform.system() == "Windows":

        pxrConvertWin32PerformanceCounterToTimeKHR = ctypes.cast(
            xr.get_instance_proc_addr(
                instance=instance,
                name="xrConvertWin32PerformanceCounterToTimeKHR",
            ),
            xr.PFN_xrConvertWin32PerformanceCounterToTimeKHR,
        )

        import ctypes.wintypes as wintypes

        def _time_from_perf_counter(performance_counter: ctypes.wintypes.LARGE_INTEGER) -> xr.Time:
            xr_time = xr.Time()
            result = pxrConvertWin32PerformanceCounterToTimeKHR(
                instance,
                ctypes.pointer(performance_counter),
                ctypes.byref(xr_time),
            )
            result = xr.check_result(result)
            if result.is_exception():
                raise result
            return xr_time

        return _time_from_perf_counter

    # Linux
    else:
        pxrConvertTimespecTimeToTimeKHR = ctypes.cast(
            xr.get_instance_proc_addr(
                instance=instance,
                name="xrConvertTimespecTimeToTimeKHR",
            ),
            xr.PFN_xrConvertTimespecTimeToTimeKHR,
        )

        def _time_from_timespec(timespec_time: xr.timespec) -> xr.Time:
            xr_time = xr.Time()
            result = pxrConvertTimespecTimeToTimeKHR(
                instance,
                ctypes.pointer(timespec_time),
                ctypes.byref(xr_time),
            )
            result = xr.check_result(result)
            if result.is_exception():
                raise result
            return xr_time

        return _time_from_timespec


def _getXRTime():
    """
    # Headless needs a way to get time
    # This is cross-platform with Linux
    """

    if platform.system() == "Windows":

        import ctypes.wintypes as wintypes
        pc_time = ctypes.wintypes.LARGE_INTEGER()
        kernel32.QueryPerformanceCounter(ctypes.byref(pc_time))
        xr_time_now = _getTimeFunc()(pc_time)
    else:
        import time
        timespecTime = xr.timespec()
        time_float = time.clock_gettime(time.CLOCK_MONOTONIC)
        timespecTime.tv_sec = int(time_float)
        timespecTime.tv_nsec = int((time_float % 1) * 1e9)
        xr_time_now = _getTimeFunc()(timespecTime)

    return xr_time_now


def _get_tracker_paths() -> list[xr.Path]:
    """
    Get paths, just for Vive trackers
    """
    role_paths = (xr.Path * len(role_path_strings))(
        *[xr.string_to_path(instance, role_string) for role_string in role_path_strings],
    )
    return [xr.Path(path) for path in role_paths]


def _get_controller_paths() -> ctypes.Array[xr.Path]:
    """
    Get paths for controllers
    """
    controller_paths = (xr.Path * 2)(  # noqa
        xr.string_to_path(instance, "/user/hand/left"),
        xr.string_to_path(instance, "/user/hand/right"),
    )
    return controller_paths


def _init_actions():
    """
    Create reference space, action set, and actions
    """

    global base_space
    base_space = xr.create_reference_space(
        session=session,
        create_info=xr.ReferenceSpaceCreateInfo(
            reference_space_type=xr.ReferenceSpaceType.STAGE,
        )
    )

    global view_reference_space
    view_reference_space = xr.create_reference_space(
        session=session,
        create_info=xr.ReferenceSpaceCreateInfo(
            reference_space_type=xr.ReferenceSpaceType.VIEW,
        )
    )

    global action_set
    action_set = xr.create_action_set(
        instance=instance,
        create_info=xr.ActionSetCreateInfo(
            action_set_name="default_action_set",
            localized_action_set_name="Default Action Set",
            priority=0,
        ),
    )

    global paths
    paths = []

    if use_vive:
        tracker_paths = _get_tracker_paths()
        paths.extend(tracker_paths)

    controller_paths = _get_controller_paths()
    paths.extend(controller_paths)

    pose_action = xr.create_action(
        action_set=action_set,
        create_info=xr.ActionCreateInfo(
            action_type=xr.ActionType.POSE_INPUT,
            action_name="device_pose",
            localized_action_name="Device Pose",
            count_subaction_paths=len(paths),
            subaction_paths=paths,
        ),
    )

    # Add Vive trackers
    if use_vive:
        suggested_binding_paths = (xr.ActionSuggestedBinding * len(role_path_strings))(
            *[xr.ActionSuggestedBinding(
                pose_action,
                xr.string_to_path(instance, f"{role_path_string}/input/grip/pose"))
                for role_path_string in role_path_strings],
        )
        xr.suggest_interaction_profile_bindings(
            instance=instance,
            suggested_bindings=xr.InteractionProfileSuggestedBinding(
                interaction_profile=xr.string_to_path(instance, "/interaction_profiles/htc/vive_tracker_htcx"),
                count_suggested_bindings=len(suggested_binding_paths),
                suggested_bindings=suggested_binding_paths,
            )
        )

    # Add controllers

    suggested_bindings = (xr.ActionSuggestedBinding * 2)(
        xr.ActionSuggestedBinding(
            action=pose_action,
            binding=xr.string_to_path(instance, "/user/hand/left/input/grip/pose"),
        ),
        xr.ActionSuggestedBinding(
            action=pose_action,
            binding=xr.string_to_path(instance, "/user/hand/right/input/grip/pose"),
        ),
    )
    xr.suggest_interaction_profile_bindings(
        instance=instance,
        suggested_bindings=xr.InteractionProfileSuggestedBinding(
            interaction_profile=xr.string_to_path(instance, "/interaction_profiles/htc/vive_controller"),
            count_suggested_bindings=len(suggested_bindings),
            suggested_bindings=suggested_bindings,
        )
    )

    # Create spaces for both trackers and controllers

    global action_spaces
    for path in paths:
        action_space = xr.create_action_space(
            session=session,
            create_info=xr.ActionSpaceCreateInfo(
                action=pose_action,
                subaction_path=path,
            )
        )
        action_spaces.append(action_space)

    # Attach action set to session
    action_sets = [action_set, ]
    xr.attach_session_action_sets(
        session=session,
        attach_info=xr.SessionActionSetsAttachInfo(
            count_action_sets=len(action_sets),
            action_sets=(xr.ActionSet * len(action_sets))(*action_sets)
        ),
    )


def _init_vr_headless(extensions: list[str]):
    print("Initializing OpenXR with headless mode...")

    global instance
    instance = xr.create_instance(xr.InstanceCreateInfo(
        enabled_extension_names=extensions,
    ))

    global system
    system = xr.get_system(
        instance,
        xr.SystemGetInfo(form_factor=xr.FormFactor.HEAD_MOUNTED_DISPLAY)  # Doesn't matter for headless mode
    )

    global session
    session = xr.create_session(
        instance,
        xr.SessionCreateInfo(
            system_id=system,
            next=None,  # No GraphicsBinding structure is required here in HEADLESS mode
        ),
    )


def _init_vr_with_graphics(extensions: list[str]):
    print("Initializing OpenXR with graphics mode...")

    # Use high level context manager
    from xr.utils.gl import ContextObject
    from xr.utils.gl.glfw_util import GLFWOffscreenContextProvider

    with ContextObject(
            context_provider=GLFWOffscreenContextProvider(),
            instance_create_info=xr.InstanceCreateInfo(
                enabled_extension_names=extensions,
            ),
    ) as context:
        global instance, system, session, base_space, view_reference_space, action_set
        instance = context.instance
        system = context.system
        session = context.session
        base_space = context.space
        view_reference_space = context.view_reference_space
        action_set = context.default_action_set


def init_vr():
    print("Initializing OpenXR...")

    # Get supported extensions
    supported_extensions = [ext.extension_name.decode() for ext in xr.enumerate_instance_extension_properties()]
    print(f"Supported extensions: {supported_extensions}")

    extensions = []

    if xr.MND_HEADLESS_EXTENSION_NAME in supported_extensions and False:
        extensions.append(vive_tracker_interaction.EXTENSION_NAME)
    elif xr.KHR_OPENGL_ENABLE_EXTENSION_NAME in supported_extensions:
        extensions.append(xr.KHR_OPENGL_ENABLE_EXTENSION_NAME)
    else:
        raise ValueError("No supported graphics extension found. Your OpenXR runtime is incompatible.")

    if vive_tracker_interaction.EXTENSION_NAME in supported_extensions:
        print("Using Vive tracker interaction extension")
        extensions.append(vive_tracker_interaction.EXTENSION_NAME)

        global use_vive
        use_vive = True

    if platform.system() == "Windows":
        extensions.append(xr.KHR_WIN32_CONVERT_PERFORMANCE_COUNTER_TIME_EXTENSION_NAME)
    else:  # Linux
        extensions.append(xr.KHR_CONVERT_TIMESPEC_TIME_EXTENSION_NAME)

    if xr.MND_HEADLESS_EXTENSION_NAME in supported_extensions:
        # Headless mode
        _init_vr_headless(extensions)
    else:
        # Graphics mode
        _init_vr_with_graphics(extensions)

    _init_actions()

    print("Initialized OpenXR")


def request_exit():
    """
    Soft request exit. Only use this if OpenXR sucessfully initialized.
    """
    print("Requesting exit...")
    try:
        if session:
            try:
                xr.request_exit_session(session)
            except xr.exception.HandleInvalidError:
                print("Handle invalid. Force exiting OpenXR...")
                stop_vr()
        else:
            print("No session to request exit with")
    except NameError:
        print("No session to request exit with")


def stop_vr():
    """
    Hard exit VR. Unless called from an event loop, creating a new session may fail.
    """
    print("Stopping OpenXR...")

    action_spaces.clear()

    try:
        if session:
            xr.destroy_session(session)
        else:
            print("No session to destroy")
    except NameError:
        print("No session to destroy")

    try:
        if instance:
            xr.destroy_instance(instance)
        else:
            print("No instance to destroy")
    except NameError:
        print("No instance to destroy")

    print("Stopped OpenXR")


def _convert_pose(space_location: xr.SpaceLocation, index: int, predicted_display_time: ctypes.c_uint64):
    if space_location.location_flags & xr.SPACE_LOCATION_POSITION_VALID_BIT:

        # Convert to Blender's coordinate system
        position = space_location.pose.position  # Vec3 equivalent
        position = mathutils.Vector((position.x, position.y, position.z))

        rotation = space_location.pose.orientation  # Vec4 equivalent (quaternion)
        rotation = mathutils.Quaternion((rotation.w, rotation.x, rotation.y, rotation.z))

        mat = rotation.to_matrix().to_4x4()
        mat.translation = position

        mat_world = (
            bpy_extras.io_utils.axis_conversion("Z", "Y", "Y", "Z")
            .to_4x4()
        )
        mat_world = mat_world @ mat

        # Apply scale
        root = bpy.data.objects.get("VR Root")
        if root:
            mat_world = mat_world @ mathutils.Matrix.Scale(root.scale.length, 4)

        if index >= len(paths):
            name = "HMD"
        else:
            name = xr.path_to_string(instance, paths[index])

        return datetime.datetime.fromtimestamp(predicted_display_time.value / 1e9), name, mat_world

    return None


def _get_poses(predicted_display_time):
    """
    Must only be called when the session state is FOCUSED
    """
    active_action_set = xr.ActiveActionSet(
        action_set=action_set,
        subaction_path=ctypes.c_uint64(xr.NULL_PATH),
    )
    xr.sync_actions(
        session=session,
        sync_info=xr.ActionsSyncInfo(
            active_action_sets=[active_action_set],
        ),
    )

    for index, space in enumerate(action_spaces):
        space_location = xr.locate_space(
            space=space,
            base_space=base_space,
            time=predicted_display_time,
        )
        converted = _convert_pose(space_location, index, predicted_display_time)
        if converted:
            yield converted

    # Get HMD pose
    hmd_location = xr.locate_space(
        space=view_reference_space,
        base_space=base_space,
        time=predicted_display_time,
    )
    converted = _convert_pose(hmd_location, len(action_spaces), predicted_display_time)
    if converted:
        yield converted


def _poll_events():
    session_state = xr.SessionState.UNKNOWN
    while True:
        try:
            event_buffer = xr.poll_event(instance)
            event_type = xr.StructureType(event_buffer.type)

            if event_type == xr.StructureType.EVENT_DATA_SESSION_STATE_CHANGED:
                event = ctypes.cast(
                    ctypes.byref(event_buffer),
                    ctypes.POINTER(xr.EventDataSessionStateChanged)).contents

                session_state = xr.SessionState(event.state)
                print(f"OpenXR session state changed to xr.SessionState.{session_state.name}")

                if session_state == xr.SessionState.READY:
                    xr.begin_session(
                        session,
                        xr.SessionBeginInfo(
                            primary_view_configuration_type=xr.ViewConfigurationType.PRIMARY_STEREO,
                        ),
                    )

                elif session_state == xr.SessionState.STOPPING:
                    stop_vr()
                    break

        except xr.EventUnavailable:
            break  # No events

    return session_state


def _vr_poll_thread_func():
    global pose_queue, stop_thread_flag, data_buffer, buffer_lock

    has_focus = False

    while not stop_thread_flag.is_set():
        state = _poll_events()

        if state == xr.SessionState.FOCUSED:
            has_focus = True
        if state == xr.SessionState.STOPPING:
            break

        if has_focus:
            pose_chunk = []
            for pose_data in _get_poses(_getXRTime()):
                pose_chunk.append(pose_data)

            with buffer_lock:
                data_buffer.append(pose_chunk)


def _clear_buffer():
    global data_buffer, buffer_lock
    with buffer_lock:
        data_buffer.clear()


def _get_buffer() -> list[list[tuple[datetime.datetime, str, mathutils.Matrix]]]:
    global data_buffer, buffer_lock

    with buffer_lock:
        buffer_copy = data_buffer.copy()

    return buffer_copy


def _get_latest_poses() -> list[tuple[datetime.datetime, str, mathutils.Matrix]] | None:
    global data_buffer, buffer_lock
    with buffer_lock:
        if len(data_buffer) == 0:
            return None

    return data_buffer[-1]


def _apply_poses():
    # Don't preview when playing, since a previous recording may interfere
    if bpy.context.screen.is_animation_playing:
        return

    pose_data = _get_latest_poses()
    if not pose_data:
        return

    for time, tracker_name, pose in pose_data:
        tracker_obj = bpy.data.objects.get(tracker_name)
        if not tracker_obj:
            continue

        tracker_obj.matrix_world = pose
        tracker_obj.scale = (1, 1, 1)


def _pose_vis_timer():
    _apply_poses()
    return 1.0 / 60  # 60hz


def _insert_action(vr_context: VRContext):
    pose_data = _get_buffer()
    num_samples = len(pose_data)
    print(f"Processing {num_samples} recorded samples")

    if num_samples == 0:
        print(f"Found no samples to process")
        return

    # Frame and conversion math
    take_start_time = pose_data[0][0][0]
    framerate = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    start_frame = vr_context.record_start_frame

    # Create object to store processed animation data
    animation_data = {}

    # Process samples into a large buffer, so we can efficiently apply it later
    print("Converting samples...")
    for sample in pose_data:
        for time, tracker_name, pose in sample:
            # Get object for tracker
            tracker_obj = bpy.data.objects.get(tracker_name)
            if not tracker_obj:
                continue

            # Create animation data if it doesn't exist
            if tracker_obj.animation_data is None:
                tracker_obj.animation_data_create()

            # Initialize data structure for this object if it's the first time we see it.
            if tracker_name not in animation_data:
                animation_data[tracker_name] = {
                    "obj": tracker_obj,
                    "frames": [],
                    "locs": [],
                    "rots": [],
                    "scales": []
                }

            # Calculate frame number
            time_delta = time - take_start_time
            frame = start_frame + time_delta.total_seconds() * framerate

            # Decompose the matrix and append data
            loc, rot, scale = pose.decompose()

            data = animation_data[tracker_name]
            data["frames"].append(frame)
            data["locs"].extend(loc)
            data["rots"].extend(rot)
            data["scales"].extend(scale)

    # Now insert or replace the data
    print("Inserting data...")
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
                fcurve = action.fcurves.find(data_path, index=i)
                if fcurve:
                    action.fcurves.remove(fcurve)
                fcurve = action.fcurves.new(data_path, index=i)

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

    print("Recording Started")


def stop_recording(vr_context: VRContext | None):
    _insert_action(vr_context)
    _clear_buffer()

    print("Recording Stopped")


def start_preview():
    global polling_thread, stop_thread_flag, data_buffer, buffer_lock

    stop_thread_flag.clear()
    polling_thread = threading.Thread(target=_vr_poll_thread_func)
    polling_thread.daemon = True  # Quit with Blender
    polling_thread.start()

    if not bpy.app.timers.is_registered(_pose_vis_timer):
        bpy.app.timers.register(_pose_vis_timer)

    print("Preview Started")


def stop_preview():
    global polling_thread, stop_thread_flag

    if bpy.app.timers.is_registered(_pose_vis_timer):
        bpy.app.timers.unregister(_pose_vis_timer)

    if polling_thread and polling_thread.is_alive():
        stop_thread_flag.set()
        polling_thread.join()

    polling_thread = None
    stop_thread_flag.clear()

    print("Preview Stopped")


def load_trackers(vr_context: VRContext):
    print("Loading Trackers")
    if len(paths) == 0:
        print("No Trackers Found")
        return

    vr_context.trackers.clear()

    for i, path in enumerate(paths):
        name = xr.path_to_string(instance, path)
        print(f"Found tracker: {name}")

        tracker = vr_context.trackers.add()
        tracker.name = name
        tracker.prev_name = name
        tracker.serial = name
        tracker.type = "tracker" if name.startswith("/user/vive_tracker_htcx/") else "controller"
        tracker.index = i

    # Add hmd
    tracker = vr_context.trackers.add()
    tracker.name = "HMD"
    tracker.prev_name = "HMD"
    tracker.serial = "HMD"
    tracker.type = "hmd"
    tracker.index = len(paths)
