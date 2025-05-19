import bpy

from .. import __package__ as base_package


class OVRTransform(bpy.types.PropertyGroup):
    location: bpy.props.FloatVectorProperty(name="Location", default=(0, 0, 0))
    rotation: bpy.props.FloatVectorProperty(name="Rotation", default=(0, 0, 0))
    scale: bpy.props.FloatVectorProperty(name="Scale", default=(1, 1, 1))


class OVRTarget(bpy.types.PropertyGroup):
    object: bpy.props.StringProperty(name="Target object")
    transform: bpy.props.PointerProperty(type=OVRTransform)
    calibration_transform: bpy.props.PointerProperty(type=OVRTransform)


def tracker_name_change_callback(self: bpy.types.bpy_struct, context):
    tracker_ref = bpy.data.objects.get(self.prev_name)
    if not tracker_ref:
        return  # Not yet sure what to do here

    tracker_joint = bpy.data.objects.get(f"{self.prev_name} Joint")
    if not tracker_joint:
        return

    tracker_ref.name = self.name
    tracker_joint.name = f"{self.name} Joint"

    self.prev_name = self.name


class OVRTracker(bpy.types.PropertyGroup):
    index: bpy.props.IntProperty(name="OpenVR name")
    name: bpy.props.StringProperty(name="Tracker name", update=tracker_name_change_callback)
    prev_name: bpy.props.StringProperty(name="Tracker name before renaming")
    serial: bpy.props.StringProperty(name="Tracker serial string")
    type: bpy.props.StringProperty(name="Tracker type")

    connected: bpy.props.BoolProperty(name="Is tracker connected")

    target: bpy.props.PointerProperty(type=OVRTarget)
    joint: bpy.props.PointerProperty(type=OVRTarget)  # Joint offset


class OVRContext(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(name="OpenVR active", default=False)
    calibration_stage: bpy.props.IntProperty(name="Stage number of OpenVR Calibration", default=0)
    recording: bpy.props.BoolProperty(name="OpenVR recording", default=False)

    trackers: bpy.props.CollectionProperty(type=OVRTracker)
    selected_tracker: bpy.props.IntProperty(name="Selected tracker", default=0)

    offset: bpy.props.PointerProperty(type=OVRTransform, name="Tracker offset")

    record_start_frame: bpy.props.IntProperty(name="Recording start frame", default=0)


class Preferences(bpy.types.AddonPreferences):
    bl_idname = base_package

    steamvr_installation_path: bpy.props.StringProperty(
        name="SteamVR Installation Path",
        subtype="FILE_PATH",
        default="C:/Program Files (x86)/Steam/steamapps/common/SteamVR"
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Preferences for Tracking Toolkit")
        layout.prop(self, "steamvr_installation_path")
