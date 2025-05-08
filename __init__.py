import bpy
import bpy_extras
import openvr
from bl_ui.space_view3d_toolbar import View3DPanel
from bpy.app.handlers import persistent
from mathutils import Matrix


####################################
# Constants
####################################

# We can't bundle it for licensing reasons
install_dir = "C:/Program Files (x86)/Steam/steamapps/common/SteamVR"  # Change this if needed
tracker_model_path = f"{install_dir}/drivers/htc/resources/rendermodels/vr_tracker_vive_3_0/vr_tracker_vive_3_0.obj"
controller_model_path = f"{install_dir}/resources/rendermodels/vr_controller_vive_1_5/vr_controller_vive_1_5.obj"
hmd_model_path = f"{install_dir}/resources/rendermodels/generic_hmd/generic_hmd.obj"


####################################
# Properties
####################################

class OVRTransform(bpy.types.PropertyGroup):
    location: bpy.props.FloatVectorProperty(name="Location", default=(0, 0, 0))
    rotation: bpy.props.FloatVectorProperty(name="Rotation", default=(0, 0, 0))
    scale: bpy.props.FloatVectorProperty(name="Scale", default=(1, 1, 1))


class OVRTarget(bpy.types.PropertyGroup):
    object: bpy.props.StringProperty(name="Target object")
    transform: bpy.props.PointerProperty(type=OVRTransform)
    calibration_transform: bpy.props.PointerProperty(type=OVRTransform)


class OVRTracker(bpy.types.PropertyGroup):
    index: bpy.props.IntProperty(name="OpenVR name")
    name: bpy.props.StringProperty(name="Tracker name")
    serial: bpy.props.StringProperty(name="Tracker serial string")
    type: bpy.props.StringProperty(name="Tracker type")

    connected: bpy.props.BoolProperty(name="Is tracker connected")

    target: bpy.props.PointerProperty(type=OVRTarget)
    joint: bpy.props.PointerProperty(type=OVRTarget)  # Joint offset


class OVRContext(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(name="OpenVR active", default=False)
    calibration_stage: bpy.props.IntProperty(name="Stage number of OpenVR Calibration", default=0)

    trackers: bpy.props.CollectionProperty(type=OVRTracker)
    selected_tracker: bpy.props.IntProperty(name="Selected tracker", default=0)

    offset: bpy.props.PointerProperty(type=OVRTransform, name="Tracker offset")


####################################
# Tracking
####################################

def load_trackers(ovr_context: OVRContext, reset=False):
    system = openvr.VRSystem()

    if reset:
        ovr_context.trackers.clear()

    for i in range(openvr.k_unMaxTrackedDeviceCount):
        if system.getTrackedDeviceClass(i) == openvr.TrackedDeviceClass_Invalid:
            continue

        tracker_serial = system.getStringTrackedDeviceProperty(i, openvr.Prop_SerialNumber_String)
        matches = [tracker for tracker in ovr_context.trackers if tracker.serial == tracker_serial]
        assert len(matches) < 2, "No two trackers should have the same serial number!"

        # Existing tracker
        if len(matches) == 1:
            tracker = matches[0]
        else:
            tracker = ovr_context.trackers.add()
            tracker.name = tracker_serial
            tracker.serial = tracker_serial
            tracker.type = str(system.getTrackedDeviceClass(i))

        tracker.index = i  # Just in case, do it for both existing and non-existing
        tracker.connected = bool(system.isTrackedDeviceConnected(i))


def track_trackers(ovr_context: OVRContext):
    poses, _ = openvr.VRCompositor().waitGetPoses([], None)
    for tracker in ovr_context.trackers:
        absolute_pose = poses[tracker.index].mDeviceToAbsoluteTracking

        mat = Matrix([list(absolute_pose[0]), list(absolute_pose[1]), list(absolute_pose[2]), [0, 0, 0, 1]])
        mat_world = bpy_extras.io_utils.axis_conversion("Z", "Y", "Y", "Z").to_4x4()
        mat_world = mat_world @ mat

        # Apply scale
        root = bpy.data.objects.get("OVR Root")
        if root:
            mat_world.translation = mat_world.translation * (root.scale * 2)
            mat_world = mat_world @ Matrix.Scale(root.scale.length, 4)

        # Apply
        tracker_obj = bpy.data.objects.get(tracker.name)

        # If it doesn't exist, resync the trackers.
        if not tracker_obj:
            load_trackers(ovr_context)
            continue  # We'll catch it next time around

        tracker_obj.matrix_world = mat_world

        if bpy.context.scene.tool_settings.use_keyframe_insert_auto:
            tracker_obj.keyframe_insert("location")
            tracker_obj.keyframe_insert("rotation_euler")
            tracker_obj.keyframe_insert("scale")


####################################
# Operators
####################################

class ToggleCalibrationOperator(bpy.types.Operator):
    bl_idname = "id.toggle_calibration"
    bl_label = "Toggle OpenVR calibration"

    @staticmethod
    def obj_t_to_prop(obj: bpy.types.Object, prop: OVRTransform):
        prop.location = obj.location
        prop.rotation = obj.rotation_euler
        # Scale shouldn't be applicable to calibration, and OpenVR will sometimes provide non-1 scale factors.
        # Just keep it as is, since some armatures depend on scale and it causes issues.

    @staticmethod
    def prop_t_to_obj(prop: OVRTransform, obj: bpy.types.Object):
        obj.location = prop.location
        obj.rotation_euler = prop.rotation
        # Same as above, skip scale.

    def restore_calibration_transforms(self, ovr_context):
        # Restore transform of trackers
        for tracker in ovr_context.trackers:
            tracker_name = tracker.name

            tracker_obj = bpy.data.objects.get(tracker_name)

            # Save original transforms
            self.obj_t_to_prop(tracker_obj, tracker.target.transform)

            # Restore calibration transforms
            self.prop_t_to_obj(tracker.target.calibration_transform, tracker_obj)

    def save_calibration_transforms(self, ovr_context):
        # Save transform of trackers
        for tracker in ovr_context.trackers:
            tracker_name = tracker.name

            tracker_obj = bpy.data.objects.get(tracker_name)

            # Save calibration transforms
            self.obj_t_to_prop(tracker_obj, tracker.target.calibration_transform)

            # Restore original transforms
            self.prop_t_to_obj(tracker.target.transform, tracker_obj)

    @staticmethod
    def enable_rest():
        # Put all armatures in rest position
        for obj in bpy.context.scene.objects:
            if obj.type == "ARMATURE":
                obj.data.pose_position = "REST"
        return {"FINISHED"}

    @staticmethod
    def disable_rest():
        # Put all armatures in rest position
        for obj in bpy.context.scene.objects:
            if obj.type == "ARMATURE":
                obj.data.pose_position = "POSE"
        return {"FINISHED"}

    def execute(self, context):
        ovr_context: OVRContext = context.scene.OVRContext

        # Next stage
        ovr_context.calibration_stage += 1
        if ovr_context.calibration_stage > 2:
            ovr_context.calibration_stage = 0

        # Cycle through stages
        if ovr_context.calibration_stage == 0:  # Complete calibration
            self.save_calibration_transforms(ovr_context)
            self.disable_rest()
        elif ovr_context.calibration_stage == 1:  # Tracker Alignment
            self.restore_calibration_transforms(ovr_context)
            self.enable_rest()
        elif ovr_context.calibration_stage == 2:  # Tracker Offsetting
            self.disable_rest()

        return {"FINISHED"}


class ToggleActiveOperator(bpy.types.Operator):
    bl_idname = "id.toggle_active"
    bl_label = "Toggle OpenVR's tracking state"

    def execute(self, context):
        ovr_context: OVRContext = context.scene.OVRContext
        if ovr_context.enabled:
            openvr.shutdown()
        else:
            openvr.init(openvr.VRApplication_Scene)
            load_trackers(ovr_context)

        ovr_context.enabled = not ovr_context.enabled
        return {"FINISHED"}


class ResetTrackersOperator(bpy.types.Operator):
    bl_idname = "id.reset_trackers"
    bl_label = "Are you sure you want to trim and reset ALL OpenVR Trackers?"
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        ovr_context: OVRContext = context.scene.OVRContext
        if ovr_context.enabled:
            load_trackers(ovr_context, reset=True)

        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class ReloadTrackersOperator(bpy.types.Operator):
    bl_idname = "id.reload_trackers"
    bl_label = "Reload OpenVR tracker list"

    def execute(self, context):
        ovr_context: OVRContext = context.scene.OVRContext
        if ovr_context.enabled:
            load_trackers(ovr_context)

        return {"FINISHED"}


class CreateRefsOperator(bpy.types.Operator):
    bl_idname = "id.add_tracker_res"
    bl_label = "Create tracker target references"
    bl_options = {"UNDO"}

    def execute(self, context):
        ovr_context: OVRContext = context.scene.OVRContext

        # Set to object mode while keeping track of the previous one
        prev_obj = bpy.context.object
        if prev_obj:
            prev_mode = prev_obj.mode
            if prev_mode != "OBJECT":  # Safe against linked library immutability
                bpy.ops.object.mode_set(mode="OBJECT")

        # Create root
        root_empty = bpy.data.objects.get("OVR Root")
        if not root_empty:
            bpy.ops.object.empty_add(type="CUBE", location=(0, 0, 0))
            root_empty = bpy.context.object
            root_empty.name = "OVR Root"
            root_empty.empty_display_size = 0.1

        # Import models
        bpy.ops.wm.obj_import(filepath=tracker_model_path)
        tracker_model = bpy.context.object

        bpy.ops.wm.obj_import(filepath=controller_model_path)
        controller_model = bpy.context.object

        bpy.ops.wm.obj_import(filepath=hmd_model_path)
        hmd_model = bpy.context.object

        tracker_model.location = (0, 0, 0)
        tracker_model.rotation_euler = (0, 0, 0)

        controller_model.location = (0, 0, 0)
        controller_model.rotation_euler = (0, 0, 0)

        hmd_model.location = (0, 0, 0)
        hmd_model.rotation_euler = (0, 0, 0)

        # Create references
        def select_model(target_model: bpy.types.Object):
            bpy.ops.object.select_all(action="DESELECT")
            target_model.select_set(True)
            bpy.context.view_layer.objects.active = target_model

        for tracker in ovr_context.trackers:
            # Create new tracker empty if it doesn't exist
            tracker_name = tracker.name

            # Chose correct model
            if tracker.type == str(openvr.TrackedDeviceClass_Controller):
                model = controller_model
            elif tracker.type == str(openvr.TrackedDeviceClass_HMD):
                model = hmd_model
            else:
                model = tracker_model

            tracker_target = bpy.data.objects.get(tracker_name)
            if not tracker_target:
                # Select render model and duplicate it
                select_model(model)

                bpy.ops.object.duplicate()

                tracker_target = bpy.context.object
                tracker_target.name = tracker_name

                tracker_target.show_name = True
                tracker_target.hide_render = True

            # Create another empty as a joint offset. This is useful when you use a "Copy Transforms" constraint but
            # the physical tracker doesn't align perfectly with a character's joint
            # Create one if it doesn't exist
            joint_name = f"{tracker_name} Joint"

            tracker_joint = bpy.data.objects.get(joint_name)
            if not tracker_joint:
                select_model(model)
                bpy.ops.object.duplicate()

                tracker_joint = bpy.context.object
                tracker_joint.name = joint_name

                tracker_joint.display_type = "WIRE"
                tracker_joint.show_in_front = True
                tracker_target.hide_render = True

            # Assign names
            tracker.target.target = tracker_target.name
            tracker.target.joint = tracker_joint.name

            # Set up parenting
            tracker_target.parent = root_empty
            tracker_joint.parent = tracker_target

        # Clean up
        select_model(tracker_model)
        bpy.ops.object.delete()
        select_model(controller_model)
        bpy.ops.object.delete()
        select_model(hmd_model)
        bpy.ops.object.delete()

        # Restore previous selection
        if prev_obj:
            prev_obj.select_set(True)
            bpy.context.view_layer.objects.active = prev_obj

            # I can't stand warnings, okay?
            # noinspection PyUnboundLocalVariable
            if bpy.context.object.mode != prev_mode:  # Safe against linked library immutability
                bpy.ops.object.mode_set(mode=prev_mode)

        return {"FINISHED"}


####################################
# UI
####################################

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
        layout.prop(selected_tracker, "name", text="", emboss=False, icon_value=icon)


class OpenVRPanel(View3DPanel, bpy.types.Panel):
    bl_idname = "VIEW3D_PT_openvr_menu"
    bl_label = "Blender OpenVR"
    bl_category = "OpenVR"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        ovr_context: OVRContext = context.scene.OVRContext

        layout.label(text="Blender OpenVR")

        # Toggle active button
        activate_label = "Stop OpenVR" if ovr_context.enabled else "Start OpenVR"
        layout.operator(ToggleActiveOperator.bl_idname, text=activate_label)

        if not ovr_context.enabled:
            return

        layout.label(text="Calibration:")

        # Toggle calibration button
        if ovr_context.calibration_stage == 1:
            calibrate_btn_label = "Continue to Offset"
            calibrate_hint = "Stage 1: Line up the opaque tracker models with the character"
        elif ovr_context.calibration_stage == 2:
            calibrate_btn_label = "Complete Calibration"
            calibrate_hint = "Stage 2: Offset the wireframe tracker models to correct the pose"
        else:
            calibrate_btn_label = "Start Calibration"
            calibrate_hint = "Calibration complete"

        layout.operator(ToggleCalibrationOperator.bl_idname, text=calibrate_btn_label)
        layout.label(text=calibrate_hint)

        # Tracker management
        layout.template_list(
            "PANEL_UL_TrackerList",
            "",
            ovr_context,
            "trackers",
            ovr_context,
            "selected_tracker",
            rows=len(ovr_context.trackers),
            type="DEFAULT"
        )

        layout.label(text="If you rename any trackers you will need to recreate empties!")
        layout.label(text="You will probably want to delete the old ones.")

        # Reload tracker button
        layout.operator(ReloadTrackersOperator.bl_idname, text="Reload Trackers")

        # Create empties
        layout.operator(CreateRefsOperator.bl_idname, text="Create References")

        # Reset names button
        layout.operator_context = "INVOKE_DEFAULT"
        layout.operator(ResetTrackersOperator.bl_idname, text="Trim And Reset All Trackers And Names")


####################################
# Entrypoint
####################################

@persistent
def on_frame(scene: bpy.types.Scene):
    """
    Handler for Blender frame play
    """
    ovr_context: OVRContext = scene.OVRContext
    if not ovr_context.enabled:
        return

    if ovr_context.calibration_stage != 0:
        return

    track_trackers(ovr_context)


def register():
    print("Loading Blender OpenVR")

    # Props
    bpy.utils.register_class(OVRTransform)
    bpy.utils.register_class(OVRTarget)
    bpy.utils.register_class(OVRTracker)
    bpy.utils.register_class(OVRContext)

    # Operators
    bpy.utils.register_class(ToggleCalibrationOperator)
    bpy.utils.register_class(ResetTrackersOperator)
    bpy.utils.register_class(ToggleActiveOperator)
    bpy.utils.register_class(CreateRefsOperator)
    bpy.utils.register_class(ReloadTrackersOperator)

    # Contexts
    bpy.types.Scene.OVRContext = bpy.props.PointerProperty(type=OVRContext)

    # Events
    bpy.app.handlers.frame_change_post.append(on_frame)

    # UI
    bpy.utils.register_class(PANEL_UL_TrackerList)
    bpy.utils.register_class(OpenVRPanel)


def unregister():
    print("Unloading Blender OpenVR...")

    # UI
    bpy.utils.unregister_class(PANEL_UL_TrackerList)
    bpy.utils.unregister_class(OpenVRPanel)

    # Events
    bpy.app.handlers.frame_change_post.remove(on_frame)

    # Contexts
    del bpy.types.Scene.OVRContext

    # Classes
    bpy.utils.unregister_class(ReloadTrackersOperator)
    bpy.utils.unregister_class(CreateRefsOperator)
    bpy.utils.unregister_class(ToggleActiveOperator)
    bpy.utils.unregister_class(ResetTrackersOperator)
    bpy.utils.unregister_class(ToggleCalibrationOperator)

    # Props
    bpy.utils.unregister_class(OVRContext)
    bpy.utils.unregister_class(OVRTracker)
    bpy.utils.unregister_class(OVRTarget)
    bpy.utils.unregister_class(OVRTransform)

    print("Unloaded Blender OpenVR")


if __name__ == "__main__":
    register()
