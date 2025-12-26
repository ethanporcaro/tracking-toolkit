# Dev reload
if "bpy" in locals():
    import sys
    print("Reloading Tracking Toolkit Modules")
    prefix = __package__ + "."
    for name in sys.modules.copy():
        if name.startswith(prefix):
            print(f"Reloading {name}")
            del sys.modules[name]

import bpy

from .tracking_toolkit.operators import (
    CreateRefsOperator,
    ToggleActiveOperator,
    ToggleRecordOperator,
    BuildArmatureOperator
)
from .tracking_toolkit.properties import (
    XRContext,
    XRArmatureJoints,
    XRTracker,
    XRTarget,
    XRTransform
)
from .tracking_toolkit.ui import PANEL_UL_TrackerList, RecorderPanel, ArmaturePanel
from .tracking_toolkit.xr_core.tracking import stop_preview


def scene_update_callback(scene: bpy.types.Scene, _):
    selected = [obj for obj in scene.objects if obj.select_get()]
    if not selected:
        return

    xr_context = scene.XRContext

    active = selected[-1].name
    for tracker in xr_context.trackers:
        if tracker.target.object and (tracker.target.object.name == active or tracker.joint.object.name == active):
            if xr_context.selected_tracker != tracker.index:
                xr_context.selected_tracker = tracker.index


def register():
    print("Loading Tracking Toolkit")

    # Props
    bpy.utils.register_class(XRTransform)
    bpy.utils.register_class(XRTarget)
    bpy.utils.register_class(XRTracker)
    bpy.utils.register_class(XRArmatureJoints)
    bpy.utils.register_class(XRContext)

    # Operators
    bpy.utils.register_class(ToggleActiveOperator)
    bpy.utils.register_class(CreateRefsOperator)
    bpy.utils.register_class(ToggleRecordOperator)
    bpy.utils.register_class(BuildArmatureOperator)

    # Contexts

    # noinspection PyNoneFunctionAssignment
    bpy.types.Scene.XRContext = bpy.props.PointerProperty(type=XRContext)

    # UI
    bpy.utils.register_class(PANEL_UL_TrackerList)
    bpy.utils.register_class(RecorderPanel)
    bpy.utils.register_class(ArmaturePanel)

    # Handlers
    bpy.app.handlers.depsgraph_update_post.clear()
    bpy.app.handlers.depsgraph_update_post.append(scene_update_callback)


def unregister():
    print("Unloading Tracking Toolkit...")

    stop_preview()

    # UI
    bpy.utils.unregister_class(PANEL_UL_TrackerList)
    bpy.utils.unregister_class(RecorderPanel)
    bpy.utils.unregister_class(ArmaturePanel)

    # Contexts
    del bpy.types.Scene.XRContext

    # Classes
    bpy.utils.unregister_class(BuildArmatureOperator)
    bpy.utils.unregister_class(ToggleRecordOperator)
    bpy.utils.unregister_class(CreateRefsOperator)
    bpy.utils.unregister_class(ToggleActiveOperator)

    # Props
    bpy.utils.unregister_class(XRContext)
    bpy.utils.unregister_class(XRArmatureJoints)
    bpy.utils.unregister_class(XRTracker)
    bpy.utils.unregister_class(XRTarget)
    bpy.utils.unregister_class(XRTransform)

    # Handlers
    bpy.app.handlers.depsgraph_update_post.clear()

    print("Unloaded Tracking Toolkit")


if __name__ == "__main__":
    register()
