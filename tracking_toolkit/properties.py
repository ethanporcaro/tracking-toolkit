import bpy

from .. import __package__ as base_package


class OVRTransform(bpy.types.PropertyGroup):
    location: bpy.props.FloatVectorProperty(name="Location", default=(0, 0, 0))
    rotation: bpy.props.FloatVectorProperty(name="Rotation", default=(0, 0, 0))
    scale: bpy.props.FloatVectorProperty(name="Scale", default=(1, 1, 1))


class OVRTarget(bpy.types.PropertyGroup):
    object: bpy.props.PointerProperty(name="Target object", type=bpy.types.Object)
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


def armature_filter(self: bpy.types.bpy_struct, obj: bpy.types.ID) -> bool:
    if obj.type != "ARMATURE":
        return False

    is_linked = obj.library
    if is_linked:
        # Only show overridden objects
        if not obj.override_library:
            return False

    return True


def armature_bone_list(self: bpy.types.bpy_struct, context, edit_text):
    armature = self.armature or context.scene.OVRContext.armature
    return [b.name for b in armature.data.bones]


def tracker_binding_change_callback(self: bpy.types.bpy_struct, context):
    armature: bpy.types.Object = self.armature or context.scene.OVRContext.armature

    bound_bone: bpy.types.PoseBone = armature.pose.bones.get(self.bone)
    prev_bone: bpy.types.PoseBone = armature.pose.bones.get(self.prev_bone)

    # Remove existing constraint
    if prev_bone:
        constraint = prev_bone.constraints.get("Tracker Binding")
        if constraint:
            prev_bone.constraints.remove(constraint)

    # Create new constraint
    if bound_bone:
        constraint = bound_bone.constraints.new("COPY_TRANSFORMS")
        constraint.name = "Tracker Binding"
        constraint.target = self.joint.object

        self.prev_bone = bound_bone.name


class OVRTracker(bpy.types.PropertyGroup):
    index: bpy.props.IntProperty(name="OpenVR name")
    name: bpy.props.StringProperty(name="Tracker name", update=tracker_name_change_callback)
    prev_name: bpy.props.StringProperty(name="Tracker name before renaming")
    serial: bpy.props.StringProperty(name="Tracker serial string")
    type: bpy.props.StringProperty(name="Tracker type")

    connected: bpy.props.BoolProperty(name="Is tracker connected")

    target: bpy.props.PointerProperty(type=OVRTarget)
    joint: bpy.props.PointerProperty(type=OVRTarget)  # Joint offset

    bone: bpy.props.StringProperty(name="Bound bone", search=armature_bone_list, update=tracker_binding_change_callback)
    prev_bone: bpy.props.StringProperty(name="Previously bound bone")

    armature: bpy.props.PointerProperty(name="Override armature", type=bpy.types.Object, poll=armature_filter)


def selected_tracker_change_callback(self: bpy.types.bpy_struct, context):
    selected_tracker: OVRTracker = self.trackers[self.selected_tracker]

    obj = selected_tracker.joint.object
    if not obj:
        return

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj


class OVRContext(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(name="OpenVR active", default=False)
    calibration_stage: bpy.props.IntProperty(name="Stage number of OpenVR Calibration", default=0)
    recording: bpy.props.BoolProperty(name="OpenVR recording", default=False)

    trackers: bpy.props.CollectionProperty(type=OVRTracker)
    selected_tracker: bpy.props.IntProperty(name="Selected tracker", default=0, update=selected_tracker_change_callback)

    offset: bpy.props.PointerProperty(type=OVRTransform, name="Tracker offset")

    record_start_frame: bpy.props.IntProperty(name="Recording start frame", default=0)

    armature: bpy.props.PointerProperty(name="Default Armature", type=bpy.types.Object, poll=armature_filter)


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
