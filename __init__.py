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
    ToggleCalibrationOperator,
    ToggleRecordOperator
)
from .tracking_toolkit.properties import (
    OVRContext,
    OVRTracker,
    OVRTarget,
    OVRTransform,
    OVRInput,
    Preferences
)
from .tracking_toolkit.tracking import stop_preview
from .tracking_toolkit.ui import PANEL_UL_TrackerList, OpenVRPanel


def scene_update_callback(scene: bpy.types.Scene, depsgraph):
    selected = [obj for obj in scene.objects if obj.select_get()]
    if not selected:
        return

    ovr_context = scene.OVRContext

    active = selected[-1].name
    for tracker in ovr_context.trackers:
        if tracker.target.object and (tracker.target.object.name == active or tracker.joint.object.name == active):
            if ovr_context.selected_tracker != tracker.index:
                ovr_context.selected_tracker = tracker.index


def register():
    print("Loading Tracking Toolkit")

    # Props
    bpy.utils.register_class(Preferences)
    bpy.utils.register_class(OVRTransform)
    bpy.utils.register_class(OVRTarget)
    bpy.utils.register_class(OVRTracker)
    bpy.utils.register_class(OVRInput)
    bpy.utils.register_class(OVRContext)

    # Operators
    bpy.utils.register_class(ToggleCalibrationOperator)
    bpy.utils.register_class(ToggleActiveOperator)
    bpy.utils.register_class(CreateRefsOperator)
    bpy.utils.register_class(ToggleRecordOperator)

    # Contexts
    bpy.types.Scene.OVRContext = bpy.props.PointerProperty(type=OVRContext)

    # UI
    bpy.utils.register_class(PANEL_UL_TrackerList)
    bpy.utils.register_class(OpenVRPanel)

    # Handlers
    bpy.app.handlers.depsgraph_update_post.clear()
    bpy.app.handlers.depsgraph_update_post.append(scene_update_callback)


def unregister():
    print("Unloading Tracking Toolkit...")

    stop_preview()

    # UI
    bpy.utils.unregister_class(PANEL_UL_TrackerList)
    bpy.utils.unregister_class(OpenVRPanel)

    # Contexts
    del bpy.types.Scene.OVRContext

    # Classes
    bpy.utils.unregister_class(ToggleRecordOperator)
    bpy.utils.unregister_class(CreateRefsOperator)
    bpy.utils.unregister_class(ToggleActiveOperator)
    bpy.utils.unregister_class(ToggleCalibrationOperator)

    # Props
    bpy.utils.unregister_class(OVRContext)
    bpy.utils.unregister_class(OVRInput)
    bpy.utils.unregister_class(OVRTracker)
    bpy.utils.unregister_class(OVRTarget)
    bpy.utils.unregister_class(OVRTransform)
    bpy.utils.unregister_class(Preferences)

    # Handlers
    bpy.app.handlers.depsgraph_update_post.clear()

    print("Unloaded Tracking Toolkit")


if __name__ == "__main__":
    register()
