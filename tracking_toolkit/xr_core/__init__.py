import ctypes

import mathutils
import bpy_extras

import xr
from xr.utils.gl import ContextObject
from xr.utils.gl.glfw_util import GLFWOffscreenContextProvider

from .actions import ActionData
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
    mat_world = bpy_extras.io_utils.axis_conversion("Z", "Y", "Y", "Z").to_4x4()
    return mat_world @ mat


def run_xr(check_break_fn):
    """
    Run XR tracking. Yields a pose or None. Optionally define a function for exit checks.
    :param check_break_fn: A function that returns a boolean. If the boolean is True, the XR session will stop.
    :return:
    """
    print("Starting XR Tracking")

    available_extensions = xr.enumerate_instance_extension_properties()

    enabled_extensions = [xr.KHR_OPENGL_ENABLE_EXTENSION_NAME]

    use_vive_trackers = xr.HTCX_VIVE_TRACKER_INTERACTION_EXTENSION_NAME in available_extensions
    if use_vive_trackers:
        print("Using Vive trackers")
        enabled_extensions.append(xr.HTCX_VIVE_TRACKER_INTERACTION_EXTENSION_NAME)

    with ContextObject(
            context_provider=GLFWOffscreenContextProvider(),
            instance_create_info=xr.InstanceCreateInfo(enabled_extension_names=enabled_extensions),
            session_create_info=xr.SessionCreateInfo()  # We need to reinitialize the default parameter.
    ) as context:
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
        spaces = {}
        for data in action_data:
            spaces[data.name] = xr.create_action_space(
                session=context.session,
                create_info=xr.ActionSpaceCreateInfo(
                    action=action,
                    subaction_path=xr.string_to_path(context.instance, data.action_path)
                )
            )

        active_action_set = xr.ActiveActionSet(
            action_set=context.default_action_set,
            subaction_path=ctypes.c_uint64(xr.NULL_PATH),
        )

        # Main loop
        print("Entering tracking loop.")
        for frame_index, frame_state in enumerate(context.frame_loop()):
            # Check if we need to break
            if check_break_fn and check_break_fn():
                print("Requesting XR Exit")
                xr.request_exit_session(context.session)
                continue

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
                    continue

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
                    continue

                yield poses
                continue

            yield None

    print("XR Tracking Stopped")


# Test function
def main():
    should_break = False
    for i, pose in enumerate(run_xr(lambda: should_break)):
        print(i, pose)

        if i > 20:
            should_break = True


if __name__ == "__main__":
    main()
