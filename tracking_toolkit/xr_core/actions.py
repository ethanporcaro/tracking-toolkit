import re
from dataclasses import dataclass
from typing import Literal

import mathutils


@dataclass
class ActionData:
    name: str
    action_path: str
    subaction_path: str
    type: Literal["pose", "trigger"] = "pose"


@dataclass
class PoseData:
    pose: mathutils.Matrix
    trigger: float


# Default actions.
default_action_data = [
    # Left Hand.
    ActionData(
        name="left_hand",
        action_path="/user/hand/left",
        subaction_path="/input/grip/pose",
    ),
    ActionData(
        name="left_hand_trigger",
        action_path="/user/hand/left",
        subaction_path="/input/trigger/value",
        type="trigger",
    ),
    # Right Hand.
    ActionData(
        name="right_hand",
        action_path="/user/hand/right",
        subaction_path="/input/grip/pose",
    ),
    ActionData(
        name="right_hand_trigger",
        action_path="/user/hand/right",
        subaction_path="/input/trigger/value",
        type="trigger",
    ),
]

# Vive tracker actions.
vive_role_strings = [
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

vive_tracker_action_data = []
for role in vive_role_strings:
    vive_tracker_action_data.extend(
        [
            ActionData(
                name=role,
                action_path=f"/user/vive_tracker_htcx/role/{role}",
                subaction_path="/input/grip/pose",
            ),
            ActionData(
                name=f"{role}_trigger",
                action_path=f"/user/vive_tracker_htcx/role/{role}",
                subaction_path="/input/trigger/value",
                type="trigger",
            ),
        ]
    )

all_role_strings = ["head", "left_hand", "right_hand", *vive_role_strings]


def reformat_role_string(role_string: str):
    """
    Reformat left/right nicknames to work better with bone symmetry.
    """
    new_nn = role_string
    if re.match(f"(l(eft)?)|(r(ight)?)_", new_nn):
        new_nn = re.sub(r"([lr])((eft)|(ight))?_(.+)", r"\5.\1", new_nn)

    return new_nn
