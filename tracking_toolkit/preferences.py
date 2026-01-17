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

    nicknames: bpy.props.CollectionProperty(
        name="Default Tracker Nicknames",
        type=CUSTOM_PG_nicknames
    )

    def draw(self, _):
        layout = self.layout

        layout.label(text="Tracker Nicknames")

        for n in self.nicknames:
            layout.prop(n, "nickname", text=n.real_name)

        layout.operator(ResetNicknamesOperator.bl_idname, text="Reset All")
