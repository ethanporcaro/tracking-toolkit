from dataclasses import dataclass


@dataclass
class ActionData:
    name: str
    action_path: str
    subaction_path: str


# Default actions.
default_action_data = [
    ActionData(
        name="left_hand",
        action_path="/user/hand/left",
        subaction_path="/input/grip/pose"
    ),
    ActionData(
        name="right_hand",
        action_path="/user/hand/right",
        subaction_path="/input/grip/pose"
    )
]

# Vive tracker actions.
vive_role_strings = [
    "handheld_object",
    "left_foot",
    "right_foot",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_knee",
    "right_knee",
    "left_wrist",  # Rev 3.
    "right_wrist",  # Rev 3.
    "left_ankle",  # Rev 3.
    "right_ankle",  # Rev 3.
    "waist",
    "chest",
    "camera",
    "keyboard",
]
vive_tracker_action_data = [
    ActionData(
        name=role,
        action_path=f"/user/vive_tracker_htcx/role/{role}",
        subaction_path="/input/grip/pose"
    ) for role in vive_role_strings
]

all_role_strings = ["head", "l_hand", "r_hand", *vive_role_strings]
