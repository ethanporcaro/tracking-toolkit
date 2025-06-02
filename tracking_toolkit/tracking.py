import datetime
import queue
import threading
from typing import Generator

import bpy
import bpy_extras
import openvr
from mathutils import Matrix

from .properties import OVRContext, OVRTracker, OVRInput

# Shared variables

pose_queue = queue.Queue()
polling_thread = None
stop_thread_flag = threading.Event()

data_buffer = []
buffer_lock = threading.Lock()

action_sets = []
action_handles = {}


def init_handles():
    vr_ipt = openvr.VRInput()

    global action_sets
    action_sets = (openvr.VRActiveActionSet_t * 1)()
    action_set = action_sets[0]
    action_set.ulActionSet = vr_ipt.getActionSetHandle("/actions/legacy")

    global action_handles
    action_handles = {
        "l_joystick": vr_ipt.getActionHandle("/actions/legacy/in/Left_Axis0_Value"),
        "r_joystick": vr_ipt.getActionHandle("/actions/legacy/in/Right_Axis1_Value"),

        "l_trigger": vr_ipt.getActionHandle("/actions/legacy/in/Left_Axis1_Value"),
        "r_trigger": vr_ipt.getActionHandle("/actions/legacy/in/Right_Axis1_Value"),

        "l_grip": vr_ipt.getActionHandle("/actions/legacy/in/Left_Axis2_Value"),
        "r_grip": vr_ipt.getActionHandle("/actions/legacy/in/Right_Axis2_Value"),

        "r_a": vr_ipt.getActionHandle("/actions/legacy/in/Right_A_Press"),
        "l_a": vr_ipt.getActionHandle("/actions/legacy/in/Left_A_Press"),

        "l_b": vr_ipt.getActionHandle("/actions/legacy/in/Left_ApplicationMenu_Press"),
        "r_b": vr_ipt.getActionHandle("/actions/legacy/in/Right_ApplicationMenu_Press")
    }

    print("Initialized OpenVR action handles")


def _handle_input(ovr_context: OVRContext):
    l_ipt = ovr_context.l_input
    r_ipt = ovr_context.r_input


def _get_input(ovr_context: OVRContext):
    if not (action_handles and action_sets):
        return

    vr_ipt = openvr.VRInput()
    l_ipt: OVRInput = ovr_context.l_input
    r_ipt: OVRInput = ovr_context.r_input

    vr_ipt.updateActionState(action_sets)

    def _make_vector(action_data):
        return action_data.x, action_data.x

    # Axis values
    l_ipt.joystick_position = _make_vector(vr_ipt.getAnalogActionData(action_handles["l_joystick"], 0))
    r_ipt.joystick_position = _make_vector(vr_ipt.getAnalogActionData(action_handles["r_joystick"], 0))

    l_ipt.trigger_strength = vr_ipt.getAnalogActionData(action_handles["l_trigger"], 0).x
    r_ipt.trigger_strength = vr_ipt.getAnalogActionData(action_handles["r_trigger"], 0).x

    # l_ipt.grip_strength = vr_ipt.getAnalogActionData(action_handles["l_grip"], 0).x
    # r_ipt.grip_strength = vr_ipt.getAnalogActionData(action_handles["r_grip"], 0).x

    l_ipt.a_button = vr_ipt.getDigitalActionData(action_handles["l_a"], 0).bState
    r_ipt.a_button = vr_ipt.getDigitalActionData(action_handles["r_a"], 0).bState

    l_ipt.b_button = vr_ipt.getDigitalActionData(action_handles["l_b"], 0).bState
    r_ipt.b_button = vr_ipt.getDigitalActionData(action_handles["r_b"], 0).bState


def _get_poses(ovr_context: OVRContext) -> Generator[tuple[datetime.datetime, OVRTracker, Matrix], None, None]:
    system = openvr.VRSystem()
    poses, _ = openvr.VRCompositor().waitGetPoses([], None)
    time = datetime.datetime.now()

    for tracker in ovr_context.trackers:
        if not bool(system.isTrackedDeviceConnected(tracker.index)):
            continue

        absolute_pose = poses[tracker.index].mDeviceToAbsoluteTracking

        mat = Matrix([list(absolute_pose[0]), list(absolute_pose[1]), list(absolute_pose[2]), [0, 0, 0, 1]])
        mat_world = bpy_extras.io_utils.axis_conversion("Z", "Y", "Y", "Z").to_4x4()
        mat_world = mat_world @ mat

        # Apply scale
        root = bpy.data.objects.get("OVR Root")
        if root:
            mat_world = mat_world @ Matrix.Scale(root.scale.length, 4)

        yield time, tracker, mat_world


def _openvr_poll_thread_func(ovr_context: OVRContext):
    global pose_queue, stop_thread_flag, data_buffer, buffer_lock

    while not stop_thread_flag.is_set():
        pose_chunk = []
        for pose_data in _get_poses(ovr_context):
            pose_chunk.append(pose_data)

        with buffer_lock:
            data_buffer.append(pose_chunk)

        _get_input(ovr_context)
        _handle_input(ovr_context)


def _clear_buffer():
    global data_buffer, buffer_lock
    with buffer_lock:
        data_buffer.clear()


def _get_buffer() -> list[list[tuple[datetime.datetime, OVRTracker, Matrix]]]:
    global data_buffer, buffer_lock

    with buffer_lock:
        buffer_copy = data_buffer.copy()

    return buffer_copy


def _get_latest_poses() -> list[tuple[datetime.datetime, OVRTracker, Matrix]] | None:
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

    for time, tracker, pose in pose_data:
        tracker_obj = bpy.data.objects.get(tracker.name)
        if not tracker_obj:
            continue

        tracker_obj.matrix_world = pose
        tracker_obj.scale = (1, 1, 1)


def _pose_vis_timer():
    _apply_poses()
    return 1.0 / 60  # 60hz


def _insert_action(ovr_context: OVRContext):
    pose_data = _get_buffer()
    num_samples = len(pose_data)
    print(f"OpenVR Processing {num_samples} recorded samples")

    if num_samples == 0:
        return

    # Frame and conversion math
    take_start_time = pose_data[0][0][0]
    framerate = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    start_frame = ovr_context.record_start_frame

    # Clear previous frames, since we record in sub-frames and some may linger from last run
    for tracker in ovr_context.trackers:
        tracker_obj = bpy.data.objects.get(tracker.name)
        if tracker_obj.animation_data is None:
            continue

        action = tracker_obj.animation_data.action
        if not action:
            continue

        for curve in action.fcurves:
            action.fcurves.remove(curve)

    # Add new frames
    for sample in pose_data:
        for time, tracker, pose in sample:
            # Get object for tracker
            tracker_obj = bpy.data.objects.get(tracker.name)
            if not tracker_obj:
                continue

            # Create animation data if it doesn't exist
            if tracker_obj.animation_data is None:
                tracker_obj.animation_data_create()

            # Add frames (using subframe)
            time_delta = time - take_start_time
            frame = start_frame + time_delta.total_seconds() * framerate

            tracker_obj.matrix_world = pose
            tracker_obj.keyframe_insert("location", frame=frame)
            tracker_obj.keyframe_insert("rotation_euler", frame=frame)
            tracker_obj.keyframe_insert("scale", frame=frame)


def start_recording():
    _clear_buffer()

    print("OpenVR Recording Started")


def stop_recording(ovr_context: OVRContext | None):
    stop_preview()
    _insert_action(ovr_context)
    _clear_buffer()
    start_preview(ovr_context)

    print("OpenVR Recording Stopped")


def start_preview(ovr_context: OVRContext):
    global polling_thread, stop_thread_flag, data_buffer, buffer_lock

    stop_thread_flag.clear()
    polling_thread = threading.Thread(target=lambda: _openvr_poll_thread_func(ovr_context))
    polling_thread.daemon = True  # Quit with Blender
    polling_thread.start()

    if not bpy.app.timers.is_registered(_pose_vis_timer):
        bpy.app.timers.register(_pose_vis_timer)

    print("OpenVR Preview Started")


def stop_preview():
    global polling_thread, stop_thread_flag

    if bpy.app.timers.is_registered(_pose_vis_timer):
        bpy.app.timers.unregister(_pose_vis_timer)

    if polling_thread and polling_thread.is_alive():
        stop_thread_flag.set()
        polling_thread.join()

    polling_thread = None
    stop_thread_flag.clear()

    print("OpenVR Preview Stopped")


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
            tracker.index = i

        tracker.connected = bool(system.isTrackedDeviceConnected(i))  # Just in case, do it for both
