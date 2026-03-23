import bpy

from .xr_core.actions import all_role_strings


def tracker_nickname_change(self, _):
    role_string = self.role_string
    new_nickname = (
        self.nickname
    )  # This will have been updated by the time the callback happens.

    # Avoid trying to access objects on init.
    if not hasattr(bpy.data, "objects"):
        return

    # Nickname cannot be set to a role_string, unless it's the tracker's own.
    if new_nickname in all_role_strings:
        # If we are renaming to another's.
        if new_nickname != role_string:
            # Revert to previous nickname (or role string).
            self["nickname"] = self.prev_nickname or self.role_string

            raise ValueError(
                "You cannot use the real name of different tracker as a nickname."
            )

    def _prevent_conflict(items):
        """
        Function that errors when renaming to an existing nickname.
        """
        existing_names = [i.name for i in items]
        if new_nickname in existing_names:
            # Revert to previous nickname (or role string).
            self["nickname"] = self.prev_nickname or self.role_string

            raise ValueError(
                f"Cannot rename {role_string} to an existing nickname: {new_nickname}."
            )

    if bpy.context.scene.XRContext.use_bones:
        armature = bpy.data.objects.get("XR Trackers")
        if armature:
            bones = armature.pose.bones
            _prevent_conflict(bones)

            # Find and rename bones.
            for bone in bones:
                if bone.get("role_string") != role_string:
                    continue

                if bone.get("ref_type") == "tracker":
                    bone.name = new_nickname
                elif bone.get("ref_type") == "offset":
                    bone.name = f"{new_nickname} Offset"

    else:
        _prevent_conflict(bpy.data.objects)

        # Find and rename empties.
        for obj in bpy.data.objects:
            if not obj.get("role_string") == role_string:
                continue

            if obj.get("ref_type") == "tracker":
                obj.name = new_nickname
            elif obj.get("ref_type") == "offset":
                obj.name = f"{new_nickname} Offset"

    print(f"Set nickname of {role_string} to {new_nickname}")
    self.prev_nickname = new_nickname


class XRTrackerNaming(bpy.types.PropertyGroup):
    role_string: bpy.props.StringProperty()
    prev_nickname: bpy.props.StringProperty()
    nickname: bpy.props.StringProperty(
        name="Tracker nickname", update=tracker_nickname_change
    )


def tracker_visible_change(self, _):
    # Apply tracker visibility settings.

    nickname = self.naming.nickname

    # Try with bones.
    armature = bpy.data.objects.get("XR Trackers")
    if armature:
        bones = armature.pose.bones

        tracker_point = bones.get(nickname)
        if tracker_point:
            tracker_point.hide = self.hidden

        tracker_offset = bones.get(f"{nickname} Offset")
        if tracker_offset:
            tracker_offset.hide = self.hidden

    # Try with empties.
    tracker_point = bpy.data.objects.get(nickname)
    if tracker_point:
        tracker_point.hide_viewport = self.hidden

    tracker_offset = bpy.data.objects.get(f"{nickname} Offset")
    if tracker_offset:
        tracker_offset.hide_viewport = self.hidden


class XRTracker(bpy.types.PropertyGroup):
    index: bpy.props.IntProperty(name="Tracker index")
    name: bpy.props.StringProperty(name="Tracker name")
    naming: bpy.props.PointerProperty(type=XRTrackerNaming)
    hidden: bpy.props.BoolProperty(
        name="Hidden in viewport", default=False, update=tracker_visible_change
    )


def selected_tracker_change_callback(self: "XRContext", context):
    """
    Select the tracker object in the viewport when the selected tracker changes.
    This does not work with bones.
    """
    if self.use_bones:
        return

    selected_tracker = self.trackers[self.selected_tracker]

    obj = bpy.data.objects.get(selected_tracker.naming.nickname)
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
    enabled: bpy.props.BoolProperty(
        name="OpenXR active", default=False, options={"SKIP_SAVE"}
    )
    recording: bpy.props.BoolProperty(
        name="OpenXR recording", default=False, options={"SKIP_SAVE"}
    )
    use_bones: bpy.props.BoolProperty(name="Use Bone References", default=True)

    trackers: bpy.props.CollectionProperty(type=XRTracker)
    selected_tracker: bpy.props.IntProperty(
        name="Selected tracker", default=0, update=selected_tracker_change_callback
    )
    runtime: bpy.props.StringProperty(name="OpenXR runtime name", default="Unknown")

    timer: bpy.props.EnumProperty(
        name="Time length", items=get_timer_items(), default="0"
    )
    timer_custom: bpy.props.IntProperty(
        name="Custom time length", default=15, min=0, max=60, step=5
    )
    countdown: bpy.props.IntProperty(name="Countdown value", options={"SKIP_SAVE"})
