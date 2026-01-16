_needs_reload = "bpy" in locals()

import bpy

from .tracking_toolkit import (
    operators,
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
    properties = importlib.reload(properties)
    ui = importlib.reload(ui)
    actions = importlib.reload(actions)
    tracking = importlib.reload(tracking)
    core = importlib.reload(core)

    print("Tracking Toolkit Reloaded")


def scene_update_callback(scene: bpy.types.Scene, _):
    selected = [obj for obj in scene.objects if obj.select_get()]
    if not selected:
        return

    xr_context = scene.XRContext

    active = selected[-1].name
    for tracker in xr_context.trackers:
        if tracker.target.object and (tracker.target.object.name == active or tracker.offset.object.name == active):
            if xr_context.selected_tracker != tracker.index:
                xr_context.selected_tracker = tracker.index


def register():
    print("Loading Tracking Toolkit...")

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
    bpy.app.handlers.depsgraph_update_post.clear()
    bpy.app.handlers.depsgraph_update_post.append(scene_update_callback)

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

    # Handlers
    bpy.app.handlers.depsgraph_update_post.clear()

    print("Unloaded Tracking Toolkit")


if __name__ == "__main__":
    register()
