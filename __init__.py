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
    ToggleRecordOperator,
    BuildArmatureOperator
)
from .tracking_toolkit.properties import (
    VRContext,
    VRArmatureJoints,
    VRTracker,
    VRTarget,
    VRTransform,
    VRInput,
    Preferences
)
from .tracking_toolkit.vr import stop_preview, stop_vr
from .tracking_toolkit.ui import PANEL_UL_TrackerList, RecorderPanel, ArmaturePanel


def scene_update_callback(scene: bpy.types.Scene, depsgraph):
    selected = [obj for obj in scene.objects if obj.select_get()]
    if not selected:
        return

    vr_context = scene.VRContext

    active = selected[-1].name
    for tracker in vr_context.trackers:
        if tracker.target.object and (tracker.target.object.name == active or tracker.joint.object.name == active):
            if vr_context.selected_tracker != tracker.index:
                vr_context.selected_tracker = tracker.index


def register():
    print("Loading Tracking Toolkit")

    # Props
    bpy.utils.register_class(Preferences)
    bpy.utils.register_class(VRTransform)
    bpy.utils.register_class(VRTarget)
    bpy.utils.register_class(VRTracker)
    bpy.utils.register_class(VRInput)
    bpy.utils.register_class(VRArmatureJoints)
    bpy.utils.register_class(VRContext)

    # Operators
    bpy.utils.register_class(ToggleCalibrationOperator)
    bpy.utils.register_class(ToggleActiveOperator)
    bpy.utils.register_class(CreateRefsOperator)
    bpy.utils.register_class(ToggleRecordOperator)
    bpy.utils.register_class(BuildArmatureOperator)

    # Contexts
    bpy.types.Scene.VRContext = bpy.props.PointerProperty(type=VRContext)

    # UI
    bpy.utils.register_class(PANEL_UL_TrackerList)
    bpy.utils.register_class(RecorderPanel)
    bpy.utils.register_class(ArmaturePanel)

    # Handlers
    bpy.app.handlers.depsgraph_update_post.clear()
    bpy.app.handlers.depsgraph_update_post.append(scene_update_callback)


def unregister():
    print("Unloading Tracking Toolkit...")

    stop_vr()
    stop_preview()

    # UI
    bpy.utils.unregister_class(PANEL_UL_TrackerList)
    bpy.utils.unregister_class(RecorderPanel)
    bpy.utils.unregister_class(ArmaturePanel)

    # Contexts
    del bpy.types.Scene.VRContext

    # Classes
    bpy.utils.unregister_class(BuildArmatureOperator)
    bpy.utils.unregister_class(ToggleRecordOperator)
    bpy.utils.unregister_class(CreateRefsOperator)
    bpy.utils.unregister_class(ToggleActiveOperator)
    bpy.utils.unregister_class(ToggleCalibrationOperator)

    # Props
    bpy.utils.unregister_class(VRContext)
    bpy.utils.unregister_class(VRArmatureJoints)
    bpy.utils.unregister_class(VRInput)
    bpy.utils.unregister_class(VRTracker)
    bpy.utils.unregister_class(VRTarget)
    bpy.utils.unregister_class(VRTransform)
    bpy.utils.unregister_class(Preferences)

    # Handlers
    bpy.app.handlers.depsgraph_update_post.clear()

    print("Unloaded Tracking Toolkit")


if __name__ == "__main__":
    register()
