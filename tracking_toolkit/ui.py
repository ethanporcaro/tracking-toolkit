import bpy
from bl_ui.space_view3d_toolbar import View3DPanel

from .operators import ToggleActiveOperator, CreateRefsOperator, ToggleRecordOperator
from .protocol import is_xr_running
from .utils import get_context, get_state


class PANEL_UL_TrackerList(bpy.types.UIList):
    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_property,
        index,
        flt_flag,
    ):
        selected_tracker = item

        layout.prop(
            selected_tracker.naming, "nickname", text="", emboss=False, icon="TRACKER"
        )

        if selected_tracker.hidden:
            layout.prop(item, "hidden", icon="HIDE_ON", icon_only=True, emboss=False)
        else:
            layout.prop(item, "hidden", icon="HIDE_OFF", icon_only=True, emboss=False)


class TTKPanel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Track TK"


class RecorderPanel(TTKPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_openxr_recorder_menu"
    bl_label = "Tracking Toolkit Recorder"

    def draw(self, context: bpy.types.Context):
        layout = self.layout

        xr_context = get_context()
        xr_state = get_state()
        is_running = is_xr_running()

        # Toggle active button
        # It's super annoying to have Blender not save the state of this button on save, so we just label it funny
        activate_label = "Stop OpenXR" if is_running else "Start OpenXR"
        layout.operator(ToggleActiveOperator.bl_idname, text=activate_label)

        # Trackers
        layout.label(text="Manage Trackers")

        # Tracker management
        layout.template_list(
            "PANEL_UL_TrackerList",
            "",
            xr_context,
            "trackers",
            xr_context,
            "selected_tracker",
            rows=len(xr_context.trackers),
            type="DEFAULT",
        )

        layout.label(text="Headset must be awake to find trackers.")

        # SteamVR specific warnings.
        # Use startswith because SteamVR sometimes appends additional text.
        if xr_state.runtime.startswith("SteamVR/OpenXR"):
            # Some users will just be using trackers and not wearing the headset.
            # If this happens, the XR state won't become XR_FOCUSED, and we won't get data.
            # In the future, we could somehow check if it's disabled based on tracker movement.
            layout.label(
                text="Ensure 'Pause VR when headset is idle' is disabled in SteamVR."
            )

        # Create empties
        layout.prop(
            data=xr_context, property="use_bones", text="Use Bones For Trackers"
        )
        layout.operator(CreateRefsOperator.bl_idname, text="Create References")

        # Show the rest if OpenXR is running
        if not is_running:
            return

        # Recording
        layout.label(text="Recording")

        is_delaying = xr_state.countdown > 0

        # Make button big
        record_btn_row = layout.row()
        record_btn_row.scale_y = 2
        record_btn_row.alert = xr_state.recording and not is_delaying

        start_record_label = "Start Recording"
        stop_record_label = "Stop Recording"
        active_record_label = (
            stop_record_label if xr_state.recording else start_record_label
        )

        if xr_state.recording and is_delaying:
            active_record_label = f"Starting in {xr_state.countdown}s..."

        start_record_icon = "RECORD_OFF"
        stop_record_icon = "RECORD_ON"
        active_record_icon = (
            stop_record_icon if xr_state.recording else start_record_icon
        )

        record_btn_row.operator(
            ToggleRecordOperator.bl_idname,
            text=active_record_label,
            icon=active_record_icon,
            depress=True,
        )

        layout.prop(data=xr_context, property="timer", text="Delay")
        if xr_context.timer == "CUSTOM":
            layout.prop(data=xr_context, property="timer_custom", text="Seconds")


class SessionSettingsPanel(TTKPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_openxr_settings_menu"
    bl_label = "View Settings"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: bpy.types.Context):

        layout = self.layout
        session_settings = context.window_manager.xr_session_settings

        # Replicate VR scene inspector, but simplified.

        col = layout.column(align=True)
        col.prop(session_settings, "show_floor", text="Floor")
        col.prop(session_settings, "show_passthrough", text="Passthrough")

        col.prop(session_settings, "show_selection", text="Selection")
        col.prop(session_settings, "show_controllers", text="Controllers")

        col = layout.column(align=True)
        col.prop(session_settings, "view_scale", text="View Scale")
