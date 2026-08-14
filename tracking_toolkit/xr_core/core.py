import os
import sys
from pathlib import Path

import bpy
import mathutils

from .actions import default_action_data, vive_tracker_action_data


def _get_runtime_path() -> str:
    """Finds the absolute path to the active OpenXR runtime JSON manifest."""

    # Env var.
    if "XR_RUNTIME_JSON" in os.environ:
        return os.environ["XR_RUNTIME_JSON"]

    # Windows registry.
    if sys.platform == "win32":
        import winreg

        try:
            reg_path = r"SOFTWARE\Khronos\OpenXR\1"
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_READ
            ) as key:
                value, _ = winreg.QueryValueEx(key, "ActiveRuntime")
                return value
        except WindowsError:
            return ""

    # Linux.
    elif sys.platform.startswith("linux"):
        user_path = Path.home() / ".config" / "openxr" / "1" / "active_runtime.json"
        if user_path.is_file():
            return str(user_path)

        sys_path = Path("/etc/xdg/openxr/1/active_runtime.json")
        if sys_path.is_file():
            return str(sys_path)

    return ""


def _init_xr(*_):
    context = bpy.context
    session_state = bpy.context.window_manager.xr_session_state

    runtime_path = _get_runtime_path()
    print(f"OpenXR runtime path: {runtime_path}")

    # Check if SteamVR is present using the runtime path.
    # Ideally, bpy would expose the runtime name.
    # Crashes occur if the tracker interaction profile is enabled outside SteamVR.
    use_trackers = (
        "steamvr" in runtime_path.lower() or "steamxr" in runtime_path.lower()
    )
    if use_trackers:
        print("Enabling Vive trackers.")

    action_map = session_state.actionmaps.new(
        session_state, "tracking_toolkit_controller", True
    )
    if not session_state.action_set_create(context, action_map):
        print(f"Failed to create action set.")
        return

    item = action_map.actionmap_items.new("pose", True)
    if not item:
        print(f"Failed to create controller action item.")
        return
    item.type = "POSE"
    item.pose_is_controller_grip = True

    # Controllers.

    for data in default_action_data:
        item.user_paths.new(data.action_path)

    controller_binding = item.bindings.new("controllers", True)
    controller_binding.profile = "/interaction_profiles/khr/simple_controller"
    for data in default_action_data:
        controller_binding.component_paths.new(data.subaction_path)

    # Trackers.

    if use_trackers:
        for data in vive_tracker_action_data:
            item.user_paths.new(data.action_path)

        tracker_binding = item.bindings.new("trackers", True)
        tracker_binding.profile = "/interaction_profiles/htc/vive_tracker_htcx"
        for data in vive_tracker_action_data:
            tracker_binding.component_paths.new(data.subaction_path)

    # Create actions and bindings.

    if not session_state.action_create(context, action_map, item):
        print(f"Failed to create action.")
        return

    # Workaround, since the length of user_paths must equal the number of action paths when creating bindings.
    # However, the action_create call requires these to exist.
    # If we don't clear here, user_paths accumulates both the controller and tracker paths, which mismatches when
    # creating bindings.
    for path in item.user_paths:
        item.user_paths.remove(path)

    for data in default_action_data:
        item.user_paths.new(data.action_path)
    if not session_state.action_binding_create(
        context, action_map, item, controller_binding
    ):
        print(f"Failed to create controller binding.")
        return

    if use_trackers:
        # Same workaround here.
        for path in item.user_paths:
            item.user_paths.remove(path)

        for data in vive_tracker_action_data:
            item.user_paths.new(data.action_path)
        if not session_state.action_binding_create(
            context, action_map, item, tracker_binding
        ):
            print(f"Failed to create tracker binding.")
            return

    session_state.controller_pose_actions_set(
        context, action_map.name, item.name, item.name
    )
    session_state.active_action_set_set(context, action_map.name)

    print("OpenXR initialized.")


def start_xr():
    context = bpy.context
    session_state = bpy.context.window_manager.xr_session_state

    print("Starting XR Tracking")

    if _init_xr not in bpy.app.handlers.xr_session_start_pre:
        bpy.app.handlers.xr_session_start_pre.append(_init_xr)

    if session_state and session_state.is_running(context):
        return

    bpy.ops.wm.xr_session_toggle()

    print("Waiting to start...")


def tick_xr():
    context = bpy.context
    session_state = bpy.context.window_manager.xr_session_state
    if not session_state:
        return None

    poses = {}

    for i, data in enumerate([*default_action_data, *vive_tracker_action_data]):
        location = session_state.controller_grip_location_get(context, i)
        rotation = session_state.controller_grip_rotation_get(context, i)

        r_mat = mathutils.Matrix.Identity(3)
        r_mat.rotate(mathutils.Quaternion(mathutils.Vector(rotation)))
        r_mat.resize_4x4()
        l_mat = mathutils.Matrix.Translation(location)
        s_mat = mathutils.Matrix.Scale(1, 4)

        poses[data.name] = l_mat @ r_mat @ s_mat

    return poses


def stop_xr():
    context = bpy.context
    session_state = bpy.context.window_manager.xr_session_state

    if _init_xr in bpy.app.handlers.xr_session_start_pre:
        bpy.app.handlers.xr_session_start_pre.remove(_init_xr)

    if session_state and not session_state.is_running(context):
        return

    bpy.ops.wm.xr_session_toggle()

    print("XR Tracking Stopped")
