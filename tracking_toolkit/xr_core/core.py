import ctypes
import time

import bpy
import bpy_extras
import glfw
import gpu
import mathutils
import xr
from xr.utils.gl import ContextObject
from xr.utils.gl.glfw_util import GLFWSharedOffscreenContextProvider, GLFWOffscreenContextProvider

from .actions import default_action_data, vive_tracker_action_data


def _pose_to_mat(pose):
    loc = mathutils.Vector(pose.position.as_numpy())
    rot = mathutils.Quaternion((
        pose.orientation.w,
        pose.orientation.x,
        pose.orientation.y,
        pose.orientation.z
    ))
    mat = mathutils.Matrix.LocRotScale(loc, rot, (1, 1, 1))
    # Convert OpenXR to Blender spaces.
    mat_world = bpy_extras.io_utils.axis_conversion("-Z", "Y", "Y", "Z").to_4x4()
    return mat_world @ mat


context: ContextObject | None = None
spaces = {}


def start_xr():
    print("Starting XR Tracking")

    available_extensions = xr.enumerate_instance_extension_properties()

    enabled_extensions = [xr.KHR_OPENGL_ENABLE_EXTENSION_NAME]

    use_vive_trackers = xr.HTCX_VIVE_TRACKER_INTERACTION_EXTENSION_NAME in available_extensions
    if use_vive_trackers:
        print("Using Vive trackers")
        enabled_extensions.append(xr.HTCX_VIVE_TRACKER_INTERACTION_EXTENSION_NAME)

    global context

    # Avoid conflicting with Blender's OpenGL.
    if gpu.platform.backend_type_get() == "OPENGL":
        provider = GLFWSharedOffscreenContextProvider(glfw.get_current_context())
    else:
        provider = GLFWOffscreenContextProvider()

    context = ContextObject(
        context_provider=provider,
        instance_create_info=xr.InstanceCreateInfo(enabled_extension_names=enabled_extensions),
        session_create_info=xr.SessionCreateInfo()  # We need to reinitialize the default parameter.
    )
    context.__enter__()

    # Save the runtime's name.
    properties = xr.get_instance_properties(context.instance)
    runtime_name = properties.runtime_name.decode()
    bpy.context.scene.XRContext.runtime = runtime_name
    print(f"Using {runtime_name} as OpenXR runtime.")

    # Setup actions
    action_data = default_action_data.copy()
    if use_vive_trackers:
        action_data.extend(vive_tracker_action_data)

    paths = [xr.string_to_path(context.instance, data.action_path) for data in action_data]
    action = xr.create_action(
        action_set=context.default_action_set,
        create_info=xr.ActionCreateInfo(
            action_type=xr.ActionType.POSE_INPUT,
            action_name="tracker_pose",
            localized_action_name="Tracker Pose",
            count_subaction_paths=len(paths),
            subaction_paths=paths,
        )
    )

    # Controller suggested bindings
    suggested_bindings = [xr.ActionSuggestedBinding(
        action=action,
        binding=xr.string_to_path(
            instance=context.instance,
            path_string=data.action_path + data.subaction_path,
        )
    ) for data in default_action_data]

    xr.suggest_interaction_profile_bindings(
        instance=context.instance,
        suggested_bindings=xr.InteractionProfileSuggestedBinding(
            interaction_profile=xr.string_to_path(
                context.instance,
                "/interaction_profiles/khr/simple_controller"
            ),
            count_suggested_bindings=len(suggested_bindings),
            suggested_bindings=suggested_bindings,
        )
    )

    # Vive tracker suggested bindings
    if use_vive_trackers:
        suggested_bindings = [xr.ActionSuggestedBinding(
            action=action,
            binding=xr.string_to_path(
                instance=context.instance,
                path_string=data.action_path + data.subaction_path,
            )
        ) for data in vive_tracker_action_data]

        xr.suggest_interaction_profile_bindings(
            instance=context.instance,
            suggested_bindings=xr.InteractionProfileSuggestedBinding(
                interaction_profile=xr.string_to_path(
                    context.instance,
                    "/interaction_profiles/htc/vive_tracker_htcx"
                ),
                count_suggested_bindings=len(suggested_bindings),
                suggested_bindings=suggested_bindings,
            )
        )

    # Create action spaces
    global spaces
    for data in action_data:
        spaces[data.name] = xr.create_action_space(
            session=context.session,
            create_info=xr.ActionSpaceCreateInfo(
                action=action,
                subaction_path=xr.string_to_path(context.instance, data.action_path)
            )
        )

    # Attach action sets.
    xr.attach_session_action_sets(
        session=context.session,
        attach_info=xr.SessionActionSetsAttachInfo(
            count_action_sets=len(context.action_sets),
            action_sets=(xr.ActionSet * len(context.action_sets))(*context.action_sets)
        ),
    )


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
            xr.begin_frame(context.session)
            context.render_layers = []
            context.graphics.make_current()

            xr.end_frame(
                context.session,
                frame_end_info=xr.FrameEndInfo(
                    display_time=frame_state.predicted_display_time,
                    environment_blend_mode=context.environment_blend_mode,
                    layers=context.render_layers,
                )
            )

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
                time=frame_state.predicted_display_time,
            )

            if space_location.location_flags & xr.SPACE_LOCATION_POSITION_VALID_BIT:
                poses[space_name] = _pose_to_mat(space_location.pose)

        # Get HMD pose
        view_state, views = xr.locate_views(
            session=context.session,
            view_locate_info=xr.ViewLocateInfo(
                view_configuration_type=context.view_configuration_type,
                display_time=frame_state.predicted_display_time,
                space=context.space,
            )
        )
        poses["head"] = _pose_to_mat(views[xr.utils.Eye.LEFT.value].pose)

        if len(poses) == 0:
            return None

        return poses

    return None


def stop_xr():
    global context

    if not context:
        return

    context.__exit__(None, None, None)

    print("XR Tracking Stopped")
