import bpy

from .. import __package__ as base_package


class XRTransform(bpy.types.PropertyGroup):
    location: bpy.props.FloatVectorProperty(name="Location", default=(0, 0, 0))
    rotation: bpy.props.FloatVectorProperty(name="Rotation", default=(0, 0, 0))
    scale: bpy.props.FloatVectorProperty(name="Scale", default=(1, 1, 1))


class XRTarget(bpy.types.PropertyGroup):
    object: bpy.props.PointerProperty(name="Target object", type=bpy.types.Object)
    transform: bpy.props.PointerProperty(type=XRTransform)


def tracker_nickname_change(self, _):
    # Make sure the new names don't conflict
    if bpy.data.objects.get(self.nickname) or bpy.data.objects.get(f"{self.nickname} Offset"):
        print("Cannot rename tracker to an existing nickname.")
        return

    # Set new names if the objects exist.

    tracker_point = bpy.data.objects.get(self.prev_nickname)
    if tracker_point:
        tracker_point.name = self.nickname

    tracker_offset = bpy.data.objects.get(f"{self.prev_nickname} Offset")
    if tracker_offset:
        tracker_offset.name = f"{self.nickname} Offset"

    # Save to preferences

    preferences = bpy.context.preferences.addons[base_package].preferences
    for n in preferences.nicknames:
        if self.name == n.real_name:
            n.nickname = self.nickname

    # Track this new nickname as the next previous one.
    self.prev_nickname = self.nickname


class XRTracker(bpy.types.PropertyGroup):
    index: bpy.props.IntProperty(name="Tracker index")
    name: bpy.props.StringProperty(name="Tracker name")
    nickname: bpy.props.StringProperty(name="Tracker nickname", update=tracker_nickname_change)
    prev_nickname: bpy.props.StringProperty()

    target: bpy.props.PointerProperty(type=XRTarget)
    offset: bpy.props.PointerProperty(type=XRTarget)


def selected_tracker_change_callback(self: "XRContext", context):
    selected_tracker = self.trackers[self.selected_tracker]

    obj = selected_tracker.offset.object
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

    record_start_frame: bpy.props.IntProperty(name="Recording start frame", default=0)