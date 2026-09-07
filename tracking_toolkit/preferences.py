import math

import bpy

from .protocol import default_tracker_names
from .utils import reformat_role_string
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

    for role_string in default_tracker_names:
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
    if new_nickname in [reformat_role_string(rs) for rs in default_tracker_names]:
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
            ("A", "A", "A Button"),
            ("B", "B", "B Button"),
            ("X", "X", "X Button"),
            ("Y", "Y", "Y Button"),
        ],
        default="Trigger",
    )
    INPUT_ROLE_PROPERTY = bpy.props.EnumProperty(
        name="Input Tracker Role",
        items=[
            ("None", "None", "None"),
            *[(n, n, n) for i, n in enumerate(default_tracker_names)],
        ],
    )

    # Actual properties.
    toggle_capture_role: INPUT_ROLE_PROPERTY
    toggle_capture_input: INPUT_TYPE_PROPERTY
    single_capture_role: INPUT_ROLE_PROPERTY
    single_capture_input: INPUT_TYPE_PROPERTY
    frame_forward_role: INPUT_ROLE_PROPERTY
    frame_forward_input: INPUT_TYPE_PROPERTY
    frame_backward_role: INPUT_ROLE_PROPERTY
    frame_backward_input: INPUT_TYPE_PROPERTY
    playback_role: INPUT_ROLE_PROPERTY
    playback_input: INPUT_TYPE_PROPERTY
    playback_restart: bpy.props.BoolProperty(default=False)


def convert_fps(self, _):
    """
    Handle framerate conversion when timing type is changed.
    """
    scene_fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base

    # Convert custom FPS to rounded interval.
    if self.record_timing_type == "Interval":
        custom_fps = self.record_custom_fps

        interval = int(round(scene_fps / custom_fps))
        self.record_custom_interval = interval

    # Convert custom interval to FPS.
    elif self.record_timing_type == "FPS":
        custom_fps = int(round(scene_fps / self.record_custom_interval))
        self.record_custom_fps = custom_fps

    # Reset custom.
    else:
        self.record_custom_fps = int(scene_fps)
        self.record_custom_interval = 1


class Preferences(bpy.types.AddonPreferences):
    bl_idname = base_package

    record_timing_type: bpy.props.EnumProperty(
        name="Recording Framerate",
        items=[
            ("Scene", "Scene FPS", "Use Scene FPS"),
            (
                "FPS",
                "Custom FPS",
                "Use Custom FPS",
            ),
            (
                "Interval",
                "Custom Interval",
                "Use Custom Interval on Scene FPS",
            ),
        ],
        default="Scene",
        update=convert_fps,
    )
    record_custom_fps: bpy.props.IntProperty(default=24, min=1, max=120, soft_max=90)
    record_custom_interval: bpy.props.IntProperty(default=1, min=1, soft_max=24)

    input_mapping: bpy.props.PointerProperty(type=PreferenceInputMapping)

    naming: bpy.props.CollectionProperty(
        name="Default Tracker Nicknames", type=PreferenceNaming
    )

    def _draw_recording_options(self):
        rec_box = self.layout.box()
        rec_box.label(text="Recording Options", icon="TIME")

        row = rec_box.row()
        row.prop(self, "record_timing_type", text="Recording Framerate")

        scene_fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base

        # If scene FPS is whole, convert to int for pretty display. Otherwise, round to 2 places.
        display_scene_fps = scene_fps
        if round(display_scene_fps) == display_scene_fps:
            display_scene_fps = int(display_scene_fps)
        else:
            display_scene_fps = round(display_scene_fps, 2)

        # Track working FPS for warnings at end.
        working_fps = scene_fps

        if self.record_timing_type == "FPS":
            row.prop(self, "record_custom_fps", text="Custom FPS")

            working_fps = self.record_custom_fps

        elif self.record_timing_type == "Interval":
            row.prop(self, "record_custom_interval", text="Custom Interval")
            interval_fps = scene_fps / self.record_custom_interval

            # If interval FPS is whole, convert to int. Otherwise, round to 2 places.
            if round(interval_fps) == interval_fps:
                interval_fps = round(interval_fps)
            else:
                interval_fps = round(interval_fps, 2)

            rec_box.label(
                text=f"Interval has {interval_fps} fps equivalent.",
                icon="STATUS_INFO",
            )

            working_fps = interval_fps
        else:

            rec_box.label(
                text=f"Current scene framerate is {display_scene_fps} fps.",
                icon="STATUS_INFO",
            )

            row.label(text="")

        # Subframe and high fps warnings.

        multiplier = scene_fps / working_fps
        is_inexact = round(multiplier) != multiplier
        if is_inexact:
            rec_box.label(
                text=f"Combination of custom framerate ({working_fps} fps) "
                f"and scene FPS ({display_scene_fps} fps) will create subframes.",
                icon="STATUS_WARNING",
            )

        if working_fps > 48:
            rec_box.label(
                text="High scene or custom FPS may cause performance issues.",
                icon="STATUS_WARNING",
            )

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

        ipt_box.label(
            text="Not all buttons are supported across controllers/trackers.",
            icon="STATUS_WARNING",
        )
        _draw_input_map("Start/Stop Capture", "toggle_capture")
        _draw_input_map("Capture Single Frame", "single_capture")
        _draw_input_map("Frame Backward", "frame_backward")
        _draw_input_map("Frame Forward", "frame_forward")
        _draw_input_map("Start/Stop Playback", "playback")

        ipt_box.separator()

        ipt_box.label(text="Input Settings")
        ipt_box.prop(
            self.input_mapping,
            "playback_restart",
            text="Restart playback from beginning",
        )

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
