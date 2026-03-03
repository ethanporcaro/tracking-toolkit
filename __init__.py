_needs_reload = "bpy" in locals()

import bpy

from .tracking_toolkit import (
    operators,
    preferences,
    properties,
    ui
)
from .tracking_toolkit.xr_core import (
    actions,
    tracking,
    core
)

if _needs_reload:
    import importlib

    operators = importlib.reload(operators)
    preferences = importlib.reload(preferences)
    properties = importlib.reload(properties)
    ui = importlib.reload(ui)
    actions = importlib.reload(actions)
    tracking = importlib.reload(tracking)
    core = importlib.reload(core)

    print("Tracking Toolkit Reloaded")


@bpy.app.handlers.persistent
def scene_update_callback(scene: bpy.types.Scene, _):
    """
    When a tracker object is selected in the scene, make it active in the list too.
    This does not work with bones.
    """
    xr_context = scene.XRContext
    if xr_context.use_bones:
        return

    selected = [obj for obj in scene.objects if obj.select_get()]
    if not selected:
        return

    active = selected[-1].name
    for tracker in xr_context.trackers:
        if tracker.nickname in [active, f"{active} Offset"]:
            if xr_context.selected_tracker != tracker.index:
                xr_context.selected_tracker = tracker.index


@bpy.app.handlers.persistent
def load_post_callback(_):
    """
    Stop XR whenever a new file is loaded.
    """
    tracking.stop_preview()


def register():
    print("Loading Tracking Toolkit...")

    # Prefs
    bpy.utils.register_class(preferences.ResetNicknamesOperator)
    bpy.utils.register_class(preferences.CUSTOM_PG_nicknames)
    bpy.utils.register_class(preferences.Preferences)
    preferences.initialize_preferences()

    # Props
    bpy.utils.register_class(properties.XRTransform)
    bpy.utils.register_class(properties.XRTarget)
    bpy.utils.register_class(properties.XRTracker)
    bpy.utils.register_class(properties.XRContext)

    # Operators
    bpy.utils.register_class(operators.ToggleActiveOperator)
    bpy.utils.register_class(operators.CreateRefsOperator)
    bpy.utils.register_class(operators.ToggleRecordOperator)

    # Contexts
    bpy.types.Scene.XRContext = bpy.props.PointerProperty(type=properties.XRContext)

    # UI
    bpy.utils.register_class(ui.PANEL_UL_TrackerList)
    bpy.utils.register_class(ui.RecorderPanel)

    # Handlers
    if scene_update_callback not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(scene_update_callback)
    if load_post_callback not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.load_post.append(load_post_callback)

    print("Loaded Tracking Toolkit")


def unregister():
    print("Unloading Tracking Toolkit...")

    tracking.stop_preview()

    # UI
    bpy.utils.unregister_class(ui.PANEL_UL_TrackerList)
    bpy.utils.unregister_class(ui.RecorderPanel)

    # Contexts
    del bpy.types.Scene.XRContext

    # Classes
    bpy.utils.unregister_class(operators.ToggleRecordOperator)
    bpy.utils.unregister_class(operators.CreateRefsOperator)
    bpy.utils.unregister_class(operators.ToggleActiveOperator)

    # Props
    bpy.utils.unregister_class(properties.XRContext)
    bpy.utils.unregister_class(properties.XRTracker)
    bpy.utils.unregister_class(properties.XRTarget)
    bpy.utils.unregister_class(properties.XRTransform)

    # Prefs
    bpy.utils.unregister_class(preferences.Preferences)
    bpy.utils.unregister_class(preferences.CUSTOM_PG_nicknames)
    bpy.utils.unregister_class(preferences.ResetNicknamesOperator)

    # Handlers
    if scene_update_callback in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(scene_update_callback)
    if load_post_callback in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(load_post_callback)

    print("Unloaded Tracking Toolkit")


if __name__ == "__main__":
    register()
