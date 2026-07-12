import re

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

all_role_strings = ["head", "left_hand", "right_hand", *vive_role_strings]


def reformat_role_string(role_string: str):
    """
    Reformat left/right nicknames to work better with bone symmetry.
    """
    new_nn = role_string
    if re.match(f"(l(eft)?)|(r(ight)?)_", new_nn):
        new_nn = re.sub(r"([lr])((eft)|(ight))?_(.+)", r"\5.\1", new_nn)

    return new_nn
