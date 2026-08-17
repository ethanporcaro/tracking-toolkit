import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import bpy
import mathutils
from bpy.types import (
    XrActionMapBinding,
    XrActionMapItem,
    XrActionMap,
)

ACTION_SET_NAME = "tracking_toolkit"


@dataclass
class PoseData:
    pose: mathutils.Matrix
    trigger: float
    button_a: bool = False
    button_b: bool = False
    button_x: bool = False
    button_y: bool = False


@dataclass
class ActionData:
    name: str
    action_path: str
    subaction_path: str
    type: Literal["pose", "trigger", "button_a", "button_b", "button_x", "button_y"] = (
        "pose"
    )
    vendors: tuple[str, ...] | None = None


# Default actions.
default_action_data = [
    # Left Hand.
    ActionData(
        name="left_hand",
        action_path="/user/hand/left",
        subaction_path="/input/grip/pose",
    ),
    ActionData(
        name="left_hand_trigger",
        action_path="/user/hand/left",
        subaction_path="/input/trigger/value",
        type="trigger",
    ),
    ActionData(
        name="left_hand_a",
        action_path="/user/hand/left",
        subaction_path="/input/a/click",
        type="button_a",
        vendors=("index",),
    ),
    ActionData(
        name="left_hand_b",
        action_path="/user/hand/left",
        subaction_path="/input/b/click",
        type="button_b",
        vendors=("index",),
    ),
    ActionData(
        name="left_hand_x",
        action_path="/user/hand/left",
        subaction_path="/input/x/click",
        type="button_x",
        vendors=("oculus",),
    ),
    ActionData(
        name="left_hand_y",
        action_path="/user/hand/left",
        subaction_path="/input/y/click",
        type="button_y",
        vendors=("oculus",),
    ),
    # Right Hand.
    ActionData(
        name="right_hand",
        action_path="/user/hand/right",
        subaction_path="/input/grip/pose",
    ),
    ActionData(
        name="right_hand_trigger",
        action_path="/user/hand/right",
        subaction_path="/input/trigger/value",
        type="trigger",
    ),
    ActionData(
        name="right_hand_a",
        action_path="/user/hand/right",
        subaction_path="/input/a/click",
        type="button_a",
        vendors=("oculus", "index"),
    ),
    ActionData(
        name="right_hand_b",
        action_path="/user/hand/right",
        subaction_path="/input/b/click",
        type="button_b",
        vendors=("oculus", "index"),
    ),
]

# Vive tracker actions.
vive_role_strings = [
    "left_foot",
    "right_foot",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_knee",
    "right_knee",
    "left_wrist",  # Rev 3.
    "right_wrist",  # Rev 3.
    "left_ankle",  # Rev 3.
    "right_ankle",  # Rev 3.
    "waist",
    "chest",
    "camera",
    "keyboard",
]

vive_tracker_action_data = []
for role in vive_role_strings:
    vive_tracker_action_data.extend(
        [
            ActionData(
                name=role,
                action_path=f"/user/vive_tracker_htcx/role/{role}",
                subaction_path="/input/grip/pose",
            ),
            ActionData(
                name=f"{role}_trigger",
                action_path=f"/user/vive_tracker_htcx/role/{role}",
                subaction_path="/input/trigger/value",
                type="trigger",
            ),
        ]
    )

default_tracker_names = ["head", "left_hand", "right_hand", *vive_role_strings]


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


def _create_bindings(
    name: str,
    item: XrActionMapItem,
    interaction_profile: str,
    action_data: list[ActionData],
) -> XrActionMapBinding | None:
    for action_data_item in action_data:
        if action_data_item.type == item.name:
            item.user_paths.new(action_data_item.action_path)

    bindings = item.bindings.new(name, True)
    bindings.profile = interaction_profile

    for action_data_item in action_data:
        if action_data_item.type == item.name:
            bindings.component_paths.new(action_data_item.subaction_path)

    # Additional properties for float types.
    if item.type == "FLOAT":
        bindings.threshold = 0.3

    return bindings


def _add_bindings_for_profile(
    vendor: str,
    interaction_profile: str,
    action_map: XrActionMap,
    item: XrActionMapItem,
    action_data: list[ActionData],
):
    """Add bindings for a specific interaction profile to an existing action."""

    context = bpy.context
    session_state = bpy.context.window_manager.xr_session_state

    # Clear existing user_paths to rebuild them for this binding.
    while len(item.user_paths) > 0:
        item.user_paths.remove(item.user_paths[0])

    # Add user paths for this action type.
    paths_added = 0
    for action_data_item in action_data:
        if action_data_item.type == item.name:
            if action_data_item.vendors is None or vendor in action_data_item.vendors:
                item.user_paths.new(action_data_item.action_path)
                paths_added += 1

    if paths_added == 0:
        return True  # Nothing to bind for this vendor

    # Create the binding.
    bindings = item.bindings.new(f"{item.name}_{vendor}", True)
    bindings.profile = interaction_profile

    for action_data_item in action_data:
        if action_data_item.type == item.name:
            if action_data_item.vendors is None or vendor in action_data_item.vendors:
                bindings.component_paths.new(action_data_item.subaction_path)

    if item.type == "FLOAT":
        bindings.threshold = 0.3

    if not session_state.action_binding_create(context, action_map, item, bindings):
        print(f"Failed to add {vendor} {item.name} binding.")
        return False

    return True


def _init_xr(*_):
    context = bpy.context
    session_state = bpy.context.window_manager.xr_session_state

    runtime_path = _get_runtime_path()
    print(f"OpenXR runtime path: {runtime_path}")

    use_trackers = (
        "steamvr" in runtime_path.lower() or "steamxr" in runtime_path.lower()
    )
    if use_trackers:
        print("Enabling Vive trackers.")

    action_map = session_state.actionmaps.new(session_state, ACTION_SET_NAME, True)
    if not session_state.action_set_create(context, action_map):
        print("Failed to create action set.")
        return

    # Create action map items.

    pose_item = action_map.actionmap_items.new("pose", True)
    if not pose_item:
        print(f"Failed to create controller pose action item.")
        return
    pose_item.type = "POSE"
    pose_item.pose_is_controller_grip = True

    trigger_item = action_map.actionmap_items.new("trigger", True)
    button_a_item = action_map.actionmap_items.new("button_a", True)
    button_b_item = action_map.actionmap_items.new("button_b", True)
    button_x_item = action_map.actionmap_items.new("button_x", True)
    button_y_item = action_map.actionmap_items.new("button_y", True)

    # Add user paths from action data and create actions.

    working_action_data = default_action_data.copy()
    if use_trackers:
        working_action_data.extend(vive_tracker_action_data)

    for action_data_item in working_action_data:
        item = action_map.actionmap_items.get(action_data_item.type)
        if item is None:
            print(f"Failed to find action item for {action_data_item.type}")
            continue
        item.user_paths.new(action_data_item.action_path)

    if not session_state.action_create(context, action_map, pose_item):
        print(f"Failed to create pose action.")
        return

    session_state.action_create(context, action_map, trigger_item)
    session_state.action_create(context, action_map, button_a_item)
    session_state.action_create(context, action_map, button_b_item)
    session_state.action_create(context, action_map, button_x_item)
    session_state.action_create(context, action_map, button_y_item)

    # Add bindings for multiple profiles.
    profiles = [
        ("oculus", "/interaction_profiles/oculus/touch_controller"),
        ("index", "/interaction_profiles/valve/index_controller"),
        ("vive", "/interaction_profiles/htc/vive_controller"),
        ("simple", "/interaction_profiles/khr/simple_controller"),
    ]

    for vendor, profile in profiles:
        _add_bindings_for_profile(
            vendor, profile, action_map, pose_item, default_action_data
        )
        if vendor == "simple":
            break

        _add_bindings_for_profile(
            vendor, profile, action_map, trigger_item, default_action_data
        )
        _add_bindings_for_profile(
            vendor, profile, action_map, button_a_item, default_action_data
        )
        _add_bindings_for_profile(
            vendor, profile, action_map, button_b_item, default_action_data
        )
        _add_bindings_for_profile(
            vendor, profile, action_map, button_x_item, default_action_data
        )
        _add_bindings_for_profile(
            vendor, profile, action_map, button_y_item, default_action_data
        )

    if use_trackers:
        _add_bindings_for_profile(
            "vive_tracker",
            "/interaction_profiles/htc/vive_tracker_htcx",
            action_map,
            pose_item,
            vive_tracker_action_data,
        )

    session_state.controller_pose_actions_set(
        context, action_map.name, pose_item.name, pose_item.name
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


def is_xr_running() -> bool:
    context = bpy.context
    session_state = bpy.context.window_manager.xr_session_state
    if not session_state:
        return False
    return session_state.is_running(context)


def tick_xr() -> dict[str, PoseData] | None:
    context = bpy.context
    session_state = bpy.context.window_manager.xr_session_state
    if not session_state:
        return None

    poses = {}

    def _create_mat(location_, rotation_):
        r_mat = mathutils.Matrix.Identity(3)
        r_mat.rotate(mathutils.Quaternion(mathutils.Vector(rotation_)))
        r_mat.resize_4x4()
        l_mat = mathutils.Matrix.Translation(location_)
        s_mat = mathutils.Matrix.Scale(1, 4)
        return l_mat @ r_mat @ s_mat

    pose_action_data = [
        data
        for data in [*default_action_data, *vive_tracker_action_data]
        if data.type == "pose"
    ]
    for i, data in enumerate(pose_action_data):
        location = session_state.controller_grip_location_get(context, i)
        rotation = session_state.controller_grip_rotation_get(context, i)

        pose = _create_mat(location, rotation)
        trigger = session_state.action_state_get(
            context, ACTION_SET_NAME, "trigger", data.action_path
        )[0]

        button_a = session_state.action_state_get(
            context, ACTION_SET_NAME, "button_a", data.action_path
        )[0]

        button_b = session_state.action_state_get(
            context, ACTION_SET_NAME, "button_b", data.action_path
        )[0]

        button_x = session_state.action_state_get(
            context, ACTION_SET_NAME, "button_x", data.action_path
        )[0]

        button_y = session_state.action_state_get(
            context, ACTION_SET_NAME, "button_y", data.action_path
        )[0]

        pose_data = PoseData(
            pose=pose,
            trigger=trigger,
            button_a=button_a,
            button_b=button_b,
            button_x=button_x,
            button_y=button_y,
        )
        poses[data.name] = pose_data

    # Add head pose.
    location = session_state.viewer_pose_location
    rotation = session_state.viewer_pose_rotation
    pose = _create_mat(location, rotation)
    pose_data = PoseData(
        pose=pose,
        trigger=0.0,
        button_a=False,
        button_b=False,
        button_x=False,
        button_y=False,
    )
    poses["head"] = pose_data

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


def get_default_tracker_names():
    return default_tracker_names
