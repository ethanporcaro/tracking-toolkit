import bpy

from .xr_core.actions import all_role_strings, reformat_role_string
from .. import __package__ as base_package


def get_preferences() -> "Preferences | bpy.types.AddonPreferences":
    """
    Get the preferences object for this addon.
    """
    return bpy.context.preferences.addons[base_package].preferences


def initialize_preferences():
    """
    Reset nickname preferences to defaults.
    Optionally reconform_existing existing (can only be called from an operator).
    """
    preferences = get_preferences()

    for role_string in all_role_strings:
        # Skip existing.
        if role_string in [n.role_string for n in preferences.naming]:
            continue

        # Better role string names with .r, .l, etc.
        default_nn = reformat_role_string(role_string)

        naming: PreferenceNaming = preferences.naming.add()
        naming.role_string = role_string
        naming["nickname"] = default_nn
        naming.prev_nickname = default_nn


class ResetNicknamesOperator(bpy.types.Operator):
    bl_idname = "id.reset_nickname_prefs"
    bl_label = "Reset global tracker nicknames"
    bl_options = {"UNDO"}

    def execute(self, context):
        get_preferences().naming.clear()
        initialize_preferences()
        return {"FINISHED"}


def preference_nickname_change(self, _):
    role_string = self.role_string
    default_name = reformat_role_string(role_string)

    # This will have been updated by the time the callback happens.
    new_nickname = self.nickname

    # Black nicknames reset to default.
    if new_nickname == "":
        self["nickname"] = default_name

    # Prevent renaming to existing nickname.
    existing_names = [
        naming.nickname
        for naming in get_preferences().naming
        if naming.role_string != role_string
    ]
    if new_nickname in existing_names:
        # Revert to previous.
        self["nickname"] = self.prev_nickname
        raise ValueError(
            f"Cannot rename {role_string} to an existing nickname or object: {new_nickname}."
        )

    # Nickname cannot be set to a default, unless it's the tracker's own.
    if new_nickname in [reformat_role_string(rs) for rs in all_role_strings]:
        # If we are renaming to another's.
        if new_nickname != default_name:
            # Revert to previous nickname (or default).
            self["nickname"] = self.prev_nickname or default_name
            raise ValueError(
                "You cannot use the real name of different tracker as a nickname."
            )

    print(f"Set preferences nickname of {role_string} to {new_nickname}")
    self.prev_nickname = new_nickname


class PreferenceNaming(bpy.types.PropertyGroup):
    role_string: bpy.props.StringProperty()
    prev_nickname: bpy.props.StringProperty()
    nickname: bpy.props.StringProperty(
        name="Tracker nickname", update=preference_nickname_change
    )


class PreferenceInputMapping(bpy.types.PropertyGroup):
    # Reusable types.
    INPUT_TYPE_PROPERTY = bpy.props.EnumProperty(
        name="Input Type",
        items=[
            ("Trigger", "Trigger", "Controller Trigger"),
            ("Grip", "Grip", "Controller Grip"),
            ("A", "A", "A Button"),
            ("B", "B", "B Button"),
            ("X", "X", "X Button"),
            ("Y", "Y", "Y Button"),
        ],
    )
    INPUT_ROLE_PROPERTY = bpy.props.EnumProperty(
        name="Input Tracker Role",
        items=[
            ("None", "None", "None"),
            *[(n, n, n) for i, n in enumerate(all_role_strings)],
        ],
    )

    # Actual properties.
    toggle_capture_role: INPUT_ROLE_PROPERTY
    toggle_capture_input: INPUT_TYPE_PROPERTY
    frame_forward_role: INPUT_ROLE_PROPERTY
    frame_forward_input: INPUT_TYPE_PROPERTY
    frame_backward_role: INPUT_ROLE_PROPERTY
    frame_backward_input: INPUT_TYPE_PROPERTY


class Preferences(bpy.types.AddonPreferences):
    bl_idname = base_package

    record_at_scene_fps: bpy.props.BoolProperty(default=True)
    record_custom_fps: bpy.props.IntProperty(default=24, min=1, max=120, soft_max=90)

    input_mapping: bpy.props.PointerProperty(type=PreferenceInputMapping)

    naming: bpy.props.CollectionProperty(
        name="Default Tracker Nicknames", type=PreferenceNaming
    )

    def _draw_recording_options(self):
        rec_box = self.layout.box()
        rec_box.label(text="Recording Options", icon="TIME")

        rec_box.prop(self, "record_at_scene_fps", text="Record at Scene FPS")
        if not self.record_at_scene_fps:
            rec_box.prop(self, "record_custom_fps", text="Custom FPS")
            rec_box.label(text="Warning: Using custom FPS. Subframes may be created.")
        rec_box.label(text="High scene or custom FPS can cause performance issues.")

    def _draw_input_options(self):
        ipt_box = self.layout.box()
        ipt_box.label(text="Input Mapping", icon="MOUSE_LMB")

        def _draw_input_map(text: str, action_name: str):
            """
            Utility to draw a tracker role/input mapping.
            """
            row = ipt_box.row()
            if getattr(self.input_mapping, f"{action_name}_role", None) == "None":
                row.prop(self.input_mapping, f"{action_name}_role", text=text)
                row.label(text="")
            else:
                row.prop(self.input_mapping, f"{action_name}_role", text=text)
                row.prop(self.input_mapping, f"{action_name}_input", text="")

        _draw_input_map("Start/Stop Capture", "toggle_capture")
        _draw_input_map("Frame Forward", "frame_forward")
        _draw_input_map("Frame Backward", "frame_backward")

    def _draw_nickname_options(self):
        nn_box = self.layout.box()
        nn_box.label(text="Tracker Nicknames", icon="TEXT")
        nn_box.label(
            text="These apply going forward, and will not replace the current nicknames in your scene."
        )

        for n in self.naming:
            nn_box.prop(n, "nickname", text=n.role_string)

        nn_box.operator(ResetNicknamesOperator.bl_idname, text="Reset Nicknames")

    def draw(self, _):
        self._draw_recording_options()
        self._draw_input_options()
        self._draw_nickname_options()
