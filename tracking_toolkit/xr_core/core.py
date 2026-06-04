import ctypes
import ctypes.wintypes
import time
from ctypes import pointer

import bpy
import gpu
import bpy_extras
import mathutils
import xr
from xr.utils.gl import ContextObject
from xr.utils.gl.glfw_util import GLFWOffscreenContextProvider
from dataclasses import dataclass

from .actions import default_action_data, vive_tracker_action_data


@dataclass
class PoseData:
    pose: mathutils.Matrix
    trigger: float
    grip: float
    thumbstick_x: float
    thumbstick_y: float
    button_a: float
    button_b: float
    button_x: float
    button_y: float


def _pose_to_mat(pose):
    loc = mathutils.Vector(pose.position.as_numpy())
    rot = mathutils.Quaternion(
        (pose.orientation.w, pose.orientation.x, pose.orientation.y, pose.orientation.z)
    )
    mat = mathutils.Matrix.LocRotScale(loc, rot, (1, 1, 1))
    # Convert OpenXR to Blender spaces.
    mat_world = bpy_extras.io_utils.axis_conversion("-Z", "Y", "Y", "Z").to_4x4()
    return mat_world @ mat


use_compatibility_mode = False
context: ContextObject | None = None
spaces = {}
action_data = default_action_data.copy()
action_trigger = None
action_squeeze = None
action_thumbstick_x = None
action_thumbstick_y = None
action_a_click = None
action_b_click = None
action_x_click = None
action_y_click = None


def _headless_enter(self):
    self.instance = xr.create_instance(
        create_info=self._instance_create_info,
    )
    self.system_id = xr.get_system(
        instance=self.instance,
        get_info=xr.SystemGetInfo(
            form_factor=self.form_factor,
        ),
    )
    self._session_create_info.system_id = self.system_id
    self._session_create_info.next = None
    self.session = xr.create_session(
        instance=self.instance,
        create_info=self._session_create_info,
    )
    self.space = xr.create_reference_space(
        session=self.session, create_info=self._reference_space_create_info
    )
    self.default_action_set = xr.create_action_set(
        instance=self.instance,
        create_info=xr.ActionSetCreateInfo(
            action_set_name="default_action_set",
            localized_action_set_name="Default Action Set",
            priority=0,
        ),
    )
    self.action_sets.append(self.default_action_set)
    return self


def start_xr():
    print("Starting XR Tracking")

    global use_compatibility_mode
    use_compatibility_mode = gpu.platform.backend_type_get() == "OPENGL"

    available_extensions = xr.enumerate_instance_extension_properties()

    required_extensions = []

    # Headless mode must be supported to use Blender's OpenGL.
    # This is because the OpenXR OpenGL will conflict with Blender's and cause crashes.
    if use_compatibility_mode:
        if xr.MND_HEADLESS_EXTENSION_NAME not in available_extensions:
            raise RuntimeError(
                "Your runtime does not support headless mode. "
                "You must use Vulkan as Blender's Display Graphics Backend."
            )

        print("Using headless compatability mode.")

        required_extensions.extend(
            [
                xr.MND_HEADLESS_EXTENSION_NAME,
                xr.KHR_WIN32_CONVERT_PERFORMANCE_COUNTER_TIME_EXTENSION_NAME,
            ]
        )

    # Vulkan as Blender's backend is safe for wide compatibility.
    else:
        required_extensions.extend([xr.KHR_OPENGL_ENABLE_EXTENSION_NAME])

    for ext in required_extensions:
        if ext not in available_extensions:
            raise RuntimeError(f"Extension {ext} not supported by your runtime.")

    enabled_extensions = required_extensions.copy()

    use_vive_trackers = (
        xr.HTCX_VIVE_TRACKER_INTERACTION_EXTENSION_NAME in available_extensions
    )
    if use_vive_trackers:
        print("Using Vive trackers")
        enabled_extensions.append(xr.HTCX_VIVE_TRACKER_INTERACTION_EXTENSION_NAME)

    # Instantiate the headless context.

    global context

    context_obj = ContextObject
    provider = None

    # Headless context.
    if use_compatibility_mode:
        context_obj.__enter__ = _headless_enter

    # OpenGL context.
    else:
        provider = GLFWOffscreenContextProvider()

    context = context_obj(
        context_provider=provider,
        instance_create_info=xr.InstanceCreateInfo(
            enabled_extension_names=enabled_extensions
        ),
        session_create_info=xr.SessionCreateInfo(),  # We need to reinitialize the default parameter.
    )

    context.__enter__()

    # Save the runtime's name.
    properties = xr.get_instance_properties(context.instance)
    runtime_name = properties.runtime_name.decode()
    bpy.context.window_manager.XRState.runtime = runtime_name
    print(f"Using {runtime_name} as OpenXR runtime.")

    # Setup actions.

    global action_data
    action_data = default_action_data.copy()
    if use_vive_trackers:
        action_data.extend(vive_tracker_action_data)

    paths = [
        xr.string_to_path(context.instance, data.action_path) for data in action_data
    ]
    action = xr.create_action(
        action_set=context.default_action_set,
        create_info=xr.ActionCreateInfo(
            action_type=xr.ActionType.POSE_INPUT,
            action_name="tracker_pose",
            localized_action_name="Tracker Pose",
            count_subaction_paths=len(paths),
            subaction_paths=paths,
        ),
    )

    global action_trigger, action_squeeze
    global action_thumbstick_x, action_thumbstick_y, action_a_click, action_b_click, action_x_click, action_y_click
    action_trigger = xr.create_action(
        action_set=context.default_action_set,
        create_info=xr.ActionCreateInfo(
            action_type=xr.ActionType.FLOAT_INPUT,
            action_name="tracker_trigger",
            localized_action_name="Tracker Trigger",
            count_subaction_paths=len(paths),
            subaction_paths=paths,
        ),
    )
    action_squeeze = xr.create_action(
        action_set=context.default_action_set,
        create_info=xr.ActionCreateInfo(
            action_type=xr.ActionType.FLOAT_INPUT,
            action_name="tracker_squeeze",
            localized_action_name="Tracker Squeeze",
            count_subaction_paths=len(paths),
            subaction_paths=paths,
        ),
    )
    action_thumbstick_x = xr.create_action(
        action_set=context.default_action_set,
        create_info=xr.ActionCreateInfo(
            action_type=xr.ActionType.FLOAT_INPUT,
            action_name="tracker_thumbstick_x",
            localized_action_name="Tracker Thumbstick X",
            count_subaction_paths=len(paths),
            subaction_paths=paths,
        ),
    )
    action_thumbstick_y = xr.create_action(
        action_set=context.default_action_set,
        create_info=xr.ActionCreateInfo(
            action_type=xr.ActionType.FLOAT_INPUT,
            action_name="tracker_thumbstick_y",
            localized_action_name="Tracker Thumbstick Y",
            count_subaction_paths=len(paths),
            subaction_paths=paths,
        ),
    )
    action_a_click = xr.create_action(
        action_set=context.default_action_set,
        create_info=xr.ActionCreateInfo(
            action_type=xr.ActionType.BOOLEAN_INPUT,
            action_name="tracker_a_click",
            localized_action_name="Tracker A Click",
            count_subaction_paths=len(paths),
            subaction_paths=paths,
        ),
    )
    action_b_click = xr.create_action(
        action_set=context.default_action_set,
        create_info=xr.ActionCreateInfo(
            action_type=xr.ActionType.BOOLEAN_INPUT,
            action_name="tracker_b_click",
            localized_action_name="Tracker B Click",
            count_subaction_paths=len(paths),
            subaction_paths=paths,
        ),
    )
    action_x_click = xr.create_action(
        action_set=context.default_action_set,
        create_info=xr.ActionCreateInfo(
            action_type=xr.ActionType.BOOLEAN_INPUT,
            action_name="tracker_x_click",
            localized_action_name="Tracker X Click",
            count_subaction_paths=len(paths),
            subaction_paths=paths,
        ),
    )
    action_y_click = xr.create_action(
        action_set=context.default_action_set,
        create_info=xr.ActionCreateInfo(
            action_type=xr.ActionType.BOOLEAN_INPUT,
            action_name="tracker_y_click",
            localized_action_name="Tracker Y Click",
            count_subaction_paths=len(paths),
            subaction_paths=paths,
        ),
    )

    # Base controller suggested bindings.
    simple_bindings = [
        xr.ActionSuggestedBinding(
            action=action,
            binding=xr.string_to_path(
                instance=context.instance,
                path_string=data.action_path + data.subaction_path,
            ),
        )
        for data in default_action_data
    ]

    xr.suggest_interaction_profile_bindings(
        instance=context.instance,
        suggested_bindings=xr.InteractionProfileSuggestedBinding(
            interaction_profile=xr.string_to_path(
                context.instance, "/interaction_profiles/khr/simple_controller"
            ),
            count_suggested_bindings=len(simple_bindings),
            suggested_bindings=simple_bindings,
        ),
    )

    # Advanced controller bindings (trigger, squeeze, thumbsticks, buttons).
    oculus_bindings = list(simple_bindings)
    index_bindings = list(simple_bindings)
    for data in default_action_data:
        for bindings in [oculus_bindings, index_bindings]:
            bindings.extend(
                [
                    xr.ActionSuggestedBinding(
                        action=action_trigger,
                        binding=xr.string_to_path(
                            context.instance, data.action_path + "/input/trigger/value"
                        ),
                    ),
                    xr.ActionSuggestedBinding(
                        action=action_squeeze,
                        binding=xr.string_to_path(
                            context.instance, data.action_path + "/input/squeeze/value"
                        ),
                    ),
                    xr.ActionSuggestedBinding(
                        action=action_thumbstick_x,
                        binding=xr.string_to_path(
                            context.instance, data.action_path + "/input/thumbstick/x"
                        ),
                    ),
                    xr.ActionSuggestedBinding(
                        action=action_thumbstick_y,
                        binding=xr.string_to_path(
                            context.instance, data.action_path + "/input/thumbstick/y"
                        ),
                    ),
                ]
            )

        if data.name == "left_hand":
            oculus_bindings.extend(
                [
                    xr.ActionSuggestedBinding(
                        action=action_x_click,
                        binding=xr.string_to_path(
                            context.instance, data.action_path + "/input/x/click"
                        ),
                    ),
                    xr.ActionSuggestedBinding(
                        action=action_y_click,
                        binding=xr.string_to_path(
                            context.instance, data.action_path + "/input/y/click"
                        ),
                    ),
                ]
            )
            index_bindings.extend(
                [
                    xr.ActionSuggestedBinding(
                        action=action_a_click,
                        binding=xr.string_to_path(
                            context.instance, data.action_path + "/input/a/click"
                        ),
                    ),
                    xr.ActionSuggestedBinding(
                        action=action_b_click,
                        binding=xr.string_to_path(
                            context.instance, data.action_path + "/input/b/click"
                        ),
                    ),
                ]
            )
        elif data.name == "right_hand":
            for bindings in [oculus_bindings, index_bindings]:
                bindings.extend(
                    [
                        xr.ActionSuggestedBinding(
                            action=action_a_click,
                            binding=xr.string_to_path(
                                context.instance, data.action_path + "/input/a/click"
                            ),
                        ),
                        xr.ActionSuggestedBinding(
                            action=action_b_click,
                            binding=xr.string_to_path(
                                context.instance, data.action_path + "/input/b/click"
                            ),
                        ),
                    ]
                )

    try:
        xr.suggest_interaction_profile_bindings(
            instance=context.instance,
            suggested_bindings=xr.InteractionProfileSuggestedBinding(
                interaction_profile=xr.string_to_path(
                    context.instance, "/interaction_profiles/oculus/touch_controller"
                ),
                count_suggested_bindings=len(oculus_bindings),
                suggested_bindings=oculus_bindings,
            ),
        )
    except xr.exception.PathUnsupportedError:
        pass

    try:
        xr.suggest_interaction_profile_bindings(
            instance=context.instance,
            suggested_bindings=xr.InteractionProfileSuggestedBinding(
                interaction_profile=xr.string_to_path(
                    context.instance, "/interaction_profiles/valve/index_controller"
                ),
                count_suggested_bindings=len(index_bindings),
                suggested_bindings=index_bindings,
            ),
        )
    except xr.exception.PathUnsupportedError:
        pass

    # Vive tracker suggested bindings
    if use_vive_trackers:
        suggested_bindings = [
            xr.ActionSuggestedBinding(
                action=action,
                binding=xr.string_to_path(
                    instance=context.instance,
                    path_string=data.action_path + data.subaction_path,
                ),
            )
            for data in vive_tracker_action_data
        ]

        xr.suggest_interaction_profile_bindings(
            instance=context.instance,
            suggested_bindings=xr.InteractionProfileSuggestedBinding(
                interaction_profile=xr.string_to_path(
                    context.instance, "/interaction_profiles/htc/vive_tracker_htcx"
                ),
                count_suggested_bindings=len(suggested_bindings),
                suggested_bindings=suggested_bindings,
            ),
        )

    # Create action spaces
    global spaces
    for data in action_data:
        spaces[data.name] = xr.create_action_space(
            session=context.session,
            create_info=xr.ActionSpaceCreateInfo(
                action=action,
                subaction_path=xr.string_to_path(context.instance, data.action_path),
            ),
        )

    # Attach action sets.
    xr.attach_session_action_sets(
        session=context.session,
        attach_info=xr.SessionActionSetsAttachInfo(
            count_action_sets=len(context.action_sets),
            action_sets=pointer(context.default_action_set),
        ),
    )


pc_time = ctypes.wintypes.LARGE_INTEGER()
kernel32 = ctypes.WinDLL("kernel32")


def _get_time() -> xr.Time:
    """
    Calculate timestamp from Windows performance counter, since we don't have info from a graphics API.
    """
    kernel32.QueryPerformanceCounter(ctypes.byref(pc_time))

    # Get native function.
    pxrConvertWin32PerformanceCounterToTimeKHR = ctypes.cast(
        xr.get_instance_proc_addr(
            instance=context.instance,
            name="xrConvertWin32PerformanceCounterToTimeKHR",
        ),
        xr.PFN_xrConvertWin32PerformanceCounterToTimeKHR,
    )

    # Query time.
    xr_time = xr.Time()
    result = pxrConvertWin32PerformanceCounterToTimeKHR(
        context.instance,
        ctypes.pointer(pc_time),
        ctypes.byref(xr_time),
    )
    result = xr.check_result(result)
    if result.is_exception():
        raise result

    return xr_time


def _poll_xr():
    context.exit_render_loop = False
    context.poll_xr_events()
    if context.exit_render_loop:
        return None

    if context.session_is_running:
        if context.session_state in (
            xr.SessionState.READY,
            xr.SessionState.SYNCHRONIZED,
            xr.SessionState.VISIBLE,
            xr.SessionState.FOCUSED,
        ):
            frame_state = xr.wait_frame(context.session)
            return frame_state
    else:
        # Throttle loop since xrWaitFrame won't be called.
        time.sleep(0.250)

    return None


def tick_xr():
    active_action_set = xr.ActiveActionSet(
        action_set=context.default_action_set,
        subaction_path=ctypes.c_uint64(xr.NULL_PATH),
    )

    frame_state = _poll_xr()

    xr.begin_frame(context.session)

    # Headless 'frame'.
    if use_compatibility_mode:
        xr_time = _get_time()

        xr.end_frame(
            context.session,
            frame_end_info=xr.FrameEndInfo(
                display_time=xr_time,
            ),
        )

    # OpenGL frame.
    else:
        xr_time = frame_state.predicted_display_time

        context.render_layers = []
        context.graphics.make_current()
        xr.end_frame(
            context.session,
            frame_end_info=xr.FrameEndInfo(
                display_time=xr_time,
                environment_blend_mode=context.environment_blend_mode,
                layers=context.render_layers,
            ),
        )

    if context.session_state == xr.SessionState.FOCUSED:
        try:
            xr.sync_actions(
                session=context.session,
                sync_info=xr.ActionsSyncInfo(
                    count_active_action_sets=1,
                    active_action_sets=[active_action_set],
                ),
            )
        except Exception as e:
            print(f"XR exception occurred: {e}. Skipping frame.")
            return None

        poses = {}
        for space_name in spaces.keys():
            space = spaces[space_name]
            space_location = xr.locate_space(
                space=space,
                base_space=context.space,
                time=xr_time,
            )

            if space_location.location_flags & xr.SPACE_LOCATION_POSITION_VALID_BIT:
                # Get float state for trigger and squeeze
                subaction_path = xr.string_to_path(
                    context.instance,
                    [d.action_path for d in action_data if d.name == space_name][0],
                )

                def get_float(action) -> float:
                    try:
                        state = xr.get_action_state_float(
                            session=context.session,
                            get_info=xr.ActionStateGetInfo(
                                action=action, subaction_path=subaction_path
                            ),
                        )
                        return state.current_state if state.is_active else 0.0
                    except xr.XrException:
                        return 0.0

                def get_bool(action) -> float:
                    try:
                        state = xr.get_action_state_boolean(
                            session=context.session,
                            get_info=xr.ActionStateGetInfo(
                                action=action, subaction_path=subaction_path
                            ),
                        )
                        return float(state.current_state) if state.is_active else 0.0
                    except xr.XrException:
                        return 0.0

                poses[space_name] = PoseData(
                    pose=_pose_to_mat(space_location.pose),
                    trigger=get_float(action_trigger),
                    grip=get_float(action_squeeze),
                    thumbstick_x=get_float(action_thumbstick_x),
                    thumbstick_y=get_float(action_thumbstick_y),
                    button_a=get_bool(action_a_click),
                    button_b=get_bool(action_b_click),
                    button_x=get_bool(action_x_click),
                    button_y=get_bool(action_y_click),
                )

        # Get HMD pose
        view_state, views = xr.locate_views(
            session=context.session,
            view_locate_info=xr.ViewLocateInfo(
                view_configuration_type=context.view_configuration_type,
                display_time=xr_time,
                space=context.space,
            ),
        )
        poses["head"] = PoseData(
            pose=_pose_to_mat(views[xr.utils.Eye.LEFT.value].pose),
            trigger=0.0,
            grip=0.0,
            thumbstick_x=0.0,
            thumbstick_y=0.0,
            button_a=0.0,
            button_b=0.0,
            button_x=0.0,
            button_y=0.0,
        )

        if len(poses) == 0:
            return None

        return poses

    # Delay to avoid overloading system.
    time.sleep(0.001)

    return None


def stop_xr():
    global context

    if not context:
        return

    context.__exit__(None, None, None)

    print("XR Tracking Stopped")
