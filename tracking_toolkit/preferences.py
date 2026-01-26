import bpy

from .xr_core.actions import vive_role_strings
from .. import __package__ as base_package


def initialize_preferences():
    preferences: Preferences | None = bpy.context.preferences.addons[base_package].preferences

    for role_string in ["head", "l_hand", "r_hand", *vive_role_strings]:
        if role_string in [n.real_name for n in preferences.nicknames]:
            continue

        nickname = preferences.nicknames.add()
        nickname.real_name = role_string
        nickname.nickname = role_string


class ResetNicknamesOperator(bpy.types.Operator):
    bl_idname = "id.reset_nickname_prefs"
    bl_label = "Reset global tracker nicknames"
    bl_options = {"UNDO"}

    def execute(self, context):
        preferences: Preferences | None = context.preferences.addons[base_package].preferences
        preferences.nicknames.clear()
        initialize_preferences()
        return {"FINISHED"}


class CUSTOM_PG_nicknames(bpy.types.PropertyGroup):
    real_name: bpy.props.StringProperty()
    nickname: bpy.props.StringProperty()


class Preferences(bpy.types.AddonPreferences):
    bl_idname = base_package

    record_at_scene_fps: bpy.props.BoolProperty(default=True)
    record_custom_fps: bpy.props.IntProperty(default=24, min=1, max=120, soft_max=90)

    nicknames: bpy.props.CollectionProperty(
        name="Default Tracker Nicknames",
        type=CUSTOM_PG_nicknames
    )

    def draw(self, _):
        layout = self.layout

        layout.label(text="Recording Options")

        layout.prop(self, "record_at_scene_fps", text="Record at Scene FPS")
        if not self.record_at_scene_fps:
            layout.prop(self, "record_custom_fps", text="Custom FPS")
            layout.label(text="Warning: Using custom FPS. Subframes may be created.")
        layout.label(text="High scene or custom FPS can cause performance issues.")

        layout.separator_spacer()

        # Tracker nickname options.

        layout.label(text="Tracker Nicknames")

        for n in self.nicknames:
            layout.prop(n, "nickname", text=n.real_name)

        layout.operator(ResetNicknamesOperator.bl_idname, text="Reset Nicknames")
