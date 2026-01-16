import bpy


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
