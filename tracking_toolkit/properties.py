import bpy

from .. import __package__ as base_package


class XRTransform(bpy.types.PropertyGroup):
    location: bpy.props.FloatVectorProperty(name="Location", default=(0, 0, 0))
    rotation: bpy.props.FloatVectorProperty(name="Rotation", default=(0, 0, 0))
    scale: bpy.props.FloatVectorProperty(name="Scale", default=(1, 1, 1))


class XRTarget(bpy.types.PropertyGroup):
    object: bpy.props.PointerProperty(name="Target object", type=bpy.types.Object)
    transform: bpy.props.PointerProperty(type=XRTransform)


class XRTracker(bpy.types.PropertyGroup):
    index: bpy.props.IntProperty(name="OpenXR name")
    name: bpy.props.StringProperty(name="Tracker name")
    type: bpy.props.StringProperty(name="Tracker type")

    target: bpy.props.PointerProperty(type=XRTarget)
    joint: bpy.props.PointerProperty(type=XRTarget)  # Joint offset


class XRInput(bpy.types.PropertyGroup):
    joystick_position: bpy.props.FloatVectorProperty(name="Joystick position", size=2, default=(0, 0))

    grip_strength: bpy.props.FloatProperty(name="Grip strength", default=0)
    trigger_strength: bpy.props.FloatProperty(name="Trigger strength", default=0)

    a_button: bpy.props.BoolProperty(name="A pressed", default=False)
    b_button: bpy.props.BoolProperty(name="B pressed", default=False)


def tracker_joint_filter(_, obj: bpy.types.Object) -> bool:
    xr_context = bpy.context.scene.XRContext
    return any(obj.name == f"{tracker.name} Joint" for tracker in xr_context.trackers)


class XRArmatureJoints(bpy.types.PropertyGroup):
    head: bpy.props.PointerProperty(name="Head", type=bpy.types.Object, poll=tracker_joint_filter)
    chest: bpy.props.PointerProperty(name="Chest", type=bpy.types.Object, poll=tracker_joint_filter)
    hips: bpy.props.PointerProperty(name="Hips", type=bpy.types.Object, poll=tracker_joint_filter)

    r_hand: bpy.props.PointerProperty(name="Right hand", type=bpy.types.Object, poll=tracker_joint_filter)
    l_hand: bpy.props.PointerProperty(name="Left hand", type=bpy.types.Object, poll=tracker_joint_filter)

    r_elbow: bpy.props.PointerProperty(name="Right elbow", type=bpy.types.Object, poll=tracker_joint_filter)
    l_elbow: bpy.props.PointerProperty(name="Left elbow", type=bpy.types.Object, poll=tracker_joint_filter)

    r_foot: bpy.props.PointerProperty(name="Right foot", type=bpy.types.Object, poll=tracker_joint_filter)
    l_foot: bpy.props.PointerProperty(name="Left foot", type=bpy.types.Object, poll=tracker_joint_filter)

    r_knee: bpy.props.PointerProperty(name="Right knee", type=bpy.types.Object, poll=tracker_joint_filter)
    l_knee: bpy.props.PointerProperty(name="Left knee", type=bpy.types.Object, poll=tracker_joint_filter)


def selected_tracker_change_callback(self: "XRContext", context):
    selected_tracker = self.trackers[self.selected_tracker]

    obj = selected_tracker.joint.object
    if not obj:
        return

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj


class XRContext(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(name="OpenXR active", default=False)
    recording: bpy.props.BoolProperty(name="OpenXR recording", default=False)

    trackers: bpy.props.CollectionProperty(type=XRTracker)
    selected_tracker: bpy.props.IntProperty(name="Selected tracker", default=0, update=selected_tracker_change_callback)

    offset: bpy.props.PointerProperty(type=XRTransform, name="Tracker offset")

    record_start_frame: bpy.props.IntProperty(name="Recording start frame", default=0)

    l_input: bpy.props.PointerProperty(type=XRInput, name="Left controller input state")
    r_input: bpy.props.PointerProperty(type=XRInput, name="Right controller input state")

    armature_joints: bpy.props.PointerProperty(type=XRArmatureJoints, name="Armature Joints")


class Preferences(bpy.types.AddonPreferences):
    bl_idname = base_package

    steamvr_installation_path: bpy.props.StringProperty(
        name="SteamVR Installation Path",
        subtype="FILE_PATH",
        default="C:/Program Files (x86)/Steam/steamapps/common/SteamVR"
    )

    def draw(self, _):
        layout = self.layout
        layout.label(text="Preferences for Tracking Toolkit")
        layout.prop(self, "steamvr_installation_path")
