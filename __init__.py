# Dev reload
if "bpy" in locals():
    import sys
    print("Reloading Blender OpenVR Modules")
    prefix = __package__ + "."
    for name in sys.modules.copy():
        if name.startswith(prefix):
            print(f"Reloading {name}")
            del sys.modules[name]

from .blender_openvr.operators import (
    CreateRefsOperator,
    ResetTrackersOperator,
    ReloadTrackersOperator,
    ToggleActiveOperator,
    ToggleCalibrationOperator
)
from .blender_openvr.properties import (
    OVRContext,
    OVRTracker,
    OVRTarget,
    OVRTransform
)
from .blender_openvr.tracking import track_trackers
from .blender_openvr.ui import PANEL_UL_TrackerList, OpenVRPanel

import bpy
from bpy.app.handlers import persistent


@persistent
def on_frame(scene: bpy.types.Scene):
    """
    Handler for Blender frame play
    """
    ovr_context: OVRContext = scene.OVRContext
    if not ovr_context.enabled:
        return

    if ovr_context.calibration_stage != 0:
        return

    track_trackers(ovr_context)


def register():
    print("Loading Blender OpenVR")

    # Props
    bpy.utils.register_class(OVRTransform)
    bpy.utils.register_class(OVRTarget)
    bpy.utils.register_class(OVRTracker)
    bpy.utils.register_class(OVRContext)

    # Operators
    bpy.utils.register_class(ToggleCalibrationOperator)
    bpy.utils.register_class(ResetTrackersOperator)
    bpy.utils.register_class(ToggleActiveOperator)
    bpy.utils.register_class(CreateRefsOperator)
    bpy.utils.register_class(ReloadTrackersOperator)

    # Contexts
    bpy.types.Scene.OVRContext = bpy.props.PointerProperty(type=OVRContext)

    # Events
    bpy.app.handlers.frame_change_post.append(on_frame)

    # UI
    bpy.utils.register_class(PANEL_UL_TrackerList)
    bpy.utils.register_class(OpenVRPanel)


def unregister():
    print("Unloading Blender OpenVR...")

    # UI
    bpy.utils.unregister_class(PANEL_UL_TrackerList)
    bpy.utils.unregister_class(OpenVRPanel)

    # Events
    bpy.app.handlers.frame_change_post.remove(on_frame)

    # Contexts
    del bpy.types.Scene.OVRContext

    # Classes
    bpy.utils.unregister_class(ReloadTrackersOperator)
    bpy.utils.unregister_class(CreateRefsOperator)
    bpy.utils.unregister_class(ToggleActiveOperator)
    bpy.utils.unregister_class(ResetTrackersOperator)
    bpy.utils.unregister_class(ToggleCalibrationOperator)

    # Props
    bpy.utils.unregister_class(OVRContext)
    bpy.utils.unregister_class(OVRTracker)
    bpy.utils.unregister_class(OVRTarget)
    bpy.utils.unregister_class(OVRTransform)

    print("Unloaded Blender OpenVR")


if __name__ == "__main__":
    register()
