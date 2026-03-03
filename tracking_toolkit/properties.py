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

    if bpy.context.scene.XRContext.use_bones:
        armature = bpy.data.objects.get("XR Trackers")
        bones = armature.pose.bones

        tracker_point = bones.get(self.prev_nickname)
        if tracker_point:
            tracker_point.name = self.nickname

        tracker_offset = bones.get(f"{self.prev_nickname} Offset")
        if tracker_offset:
            tracker_offset.name = f"{self.nickname} Offset"

    else:
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


def tracker_visible_change(self, _):
    # Apply tracker visibility settings.

    if bpy.context.scene.XRContext.use_bones:
        armature = bpy.data.objects.get("XR Trackers")
        bones = armature.pose.bones

        tracker_point = bones.get(self.nickname)
        if tracker_point:
            tracker_point.hide = self.hidden

        tracker_offset = bones.get(f"{self.nickname} Offset")
        if tracker_offset:
            tracker_offset.hide = self.hidden

    else:
        tracker_point = bpy.data.objects.get(self.nickname)
        if tracker_point:
            tracker_point.hide_viewport = self.hidden

        tracker_offset = bpy.data.objects.get(f"{self.nickname} Offset")
        if tracker_offset:
            tracker_offset.hide_viewport = self.hidden


class XRTracker(bpy.types.PropertyGroup):
    index: bpy.props.IntProperty(name="Tracker index")
    name: bpy.props.StringProperty(name="Tracker name")
    nickname: bpy.props.StringProperty(name="Tracker nickname", update=tracker_nickname_change)
    prev_nickname: bpy.props.StringProperty()
    hidden: bpy.props.BoolProperty(name="Hidden in viewport", default=False, update=tracker_visible_change)

    target: bpy.props.PointerProperty(type=XRTarget)
    offset: bpy.props.PointerProperty(type=XRTarget)


def selected_tracker_change_callback(self: "XRContext", context):
    """
    Select the tracker object in the viewport when the selected tracker changes.
    This does not work with bones.
    """
    if self.use_bones:
        return

    selected_tracker = self.trackers[self.selected_tracker]

    obj = bpy.data.objects.get(selected_tracker.nickname)
    if not obj:
        return

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj


def get_timer_items():
    return [
        ("0", "None", "No timer"),
        ("5", "5s", "5 seconds"),
        ("10", "10s", "10 seconds"),
        ("15", "15s", "15 seconds"),
        ("CUSTOM", "Custom", "Custom duration"),
    ]


class XRContext(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(name="OpenXR active", default=False, options={"SKIP_SAVE"})
    recording: bpy.props.BoolProperty(name="OpenXR recording", default=False, options={"SKIP_SAVE"})
    use_bones: bpy.props.BoolProperty(name="Use Bone References", default=True)

    trackers: bpy.props.CollectionProperty(type=XRTracker)
    selected_tracker: bpy.props.IntProperty(name="Selected tracker", default=0, update=selected_tracker_change_callback)
    runtime: bpy.props.StringProperty(name="OpenXR runtime name", default="Unknown")

    timer: bpy.props.EnumProperty(name="Time length", items=get_timer_items(), default="0")
    timer_custom: bpy.props.IntProperty(name="Custom time length", default=15, min=0, max=60, step=5)
    countdown: bpy.props.IntProperty(name="Countdown value", options={"SKIP_SAVE"})
