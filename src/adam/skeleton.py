# ─── Skeleton map for Mixamo Xbot (T-pose rest) ───
# All rotations are OFFSETS from T-pose (degrees). 0 = rest/T-pose.
# "note" tells the LLM what each axis does in plain English.
# This rig represents a full-body humanoid. Motions should be planned as human
# movement using the available major joints, even when the request is complex.
SKELETON_MAP = {
    "Hips": {
        "axes": ["x", "y", "z"],
        "range": {"x": [-35, 35], "y": [-180, 180], "z": [-35, 35]},
        "note": "Root pelvis. x: tilt fwd(+)/back(−). y: rotate whole body left(+)/right(−). z: tilt sideways. Use for balance, crouching, turns, gait, and weight transfer."
    },
    "Spine": {
        "axes": ["x", "y", "z"],
        "range": {"x": [-40, 40], "y": [-30, 30], "z": [-20, 20]},
        "note": "Lower torso. x: bend fwd(+)/back(−). y: twist torso. z: side bend. Coordinate with Spine1 and Spine2 for realistic human bending."
    },
    "Spine1": {
        "axes": ["x", "y", "z"],
        "range": {"x": [-25, 25], "y": [-20, 20], "z": [-15, 15]},
        "note": "Mid torso. Same as Spine but smaller range."
    },
    "Spine2": {
        "axes": ["x", "y", "z"],
        "range": {"x": [-20, 20], "y": [-15, 15], "z": [-10, 10]},
        "note": "Upper chest. Small corrections. Arms attach here."
    },
    "Neck": {
        "axes": ["x", "y", "z"],
        "range": {"x": [-40, 40], "y": [-70, 70], "z": [-30, 30]},
        "note": "x: look down(+)/up(−). y: turn head left(+)/right(−). z: tilt head sideways."
    },
    "Head": {
        "axes": ["x", "y", "z"],
        "range": {"x": [-30, 30], "y": [-60, 60], "z": [-25, 25]},
        "note": "Same axes as Neck. Combine Neck + Head for full head range."
    },
    "LeftShoulder": {
        "axes": ["x", "y", "z"],
        "range": {"x": [-15, 15], "y": [-10, 10], "z": [-10, 30]},
        "note": "Clavicle. +z: shrug up. Keep small — this is a subtle bone."
    },
    "LeftArm": {
        "axes": ["x", "y", "z"],
        "range": {"x": [-80, 80], "y": [-90, 90], "z": [-90, 180]},
        "note": "Upper arm. T-pose=0. x: swing fwd(+)/back(−). y: twist/roll. z: raise overhead(+)/lower to side(−). −90z = arm hanging at side. Combine with shoulder, forearm, hand, spine, and hips for reaching and expressive human gestures."
    },
    "LeftForeArm": {
        "axes": ["x", "y"],
        "range": {"x": [-10, 10], "y": [-145, 0]},
        "note": "Elbow. y(−): bend elbow (curl toward bicep). x: minor wrist pronation."
    },
    "LeftHand": {
        "axes": ["x", "z"],
        "range": {"x": [-60, 60], "z": [-40, 40]},
        "note": "Wrist. x: flex down(+)/extend up(−). z: side bend."
    },
    "RightShoulder": {
        "axes": ["x", "y", "z"],
        "range": {"x": [-15, 15], "y": [-10, 10], "z": [-30, 10]},
        "note": "Clavicle (mirror). −z: shrug up."
    },
    "RightArm": {
        "axes": ["x", "y", "z"],
        "range": {"x": [-80, 80], "y": [-90, 90], "z": [-180, 90]},
        "note": "Upper arm (mirror). x: fwd(+)/back(−). y: twist. z: raise overhead(−)/lower to side(+). +90z = arm hanging at side. Combine with shoulder, forearm, hand, spine, and hips for reaching and expressive human gestures."
    },
    "RightForeArm": {
        "axes": ["x", "y"],
        "range": {"x": [-10, 10], "y": [0, 145]},
        "note": "Elbow (mirror). y(+): bend elbow."
    },
    "RightHand": {
        "axes": ["x", "z"],
        "range": {"x": [-60, 60], "z": [-40, 40]},
        "note": "Wrist. Same as LeftHand."
    },
    "LeftUpLeg": {
        "axes": ["x", "y", "z"],
        "range": {"x": [-120, 35], "y": [-45, 45], "z": [-30, 45]},
        "note": "Thigh. x: kick forward(−)/extend back(+). y: twist. z: spread outward(+)/inward(−). Primary driver for walking, running, crouching, stepping, and jumping."
    },
    "LeftLeg": {
        "axes": ["x"],
        "range": {"x": [0, 145]},
        "note": "Knee. x(+): bend knee. Cannot hyperextend."
    },
    "LeftFoot": {
        "axes": ["x", "z"],
        "range": {"x": [-45, 50], "z": [-20, 20]},
        "note": "Ankle. x: point toes down(−)/flex up(+). z: ankle roll."
    },
    "LeftToeBase": {
        "axes": ["x"],
        "range": {"x": [-30, 60]},
        "note": "Toe pivot. x(+): curl toes up."
    },
    "RightUpLeg": {
        "axes": ["x", "y", "z"],
        "range": {"x": [-120, 35], "y": [-45, 45], "z": [-45, 30]},
        "note": "Thigh (mirror). x: kick forward(−)/back(+). z: spread outward(−)/inward(+)."
    },
    "RightLeg": {
        "axes": ["x"],
        "range": {"x": [0, 145]},
        "note": "Knee (mirror). Same as LeftLeg. Critical for stepping, landing, crouching, and human gait shock absorption."
    },
    "RightFoot": {
        "axes": ["x", "z"],
        "range": {"x": [-45, 50], "z": [-20, 20]},
        "note": "Ankle. Same as LeftFoot."
    },
    "RightToeBase": {
        "axes": ["x"],
        "range": {"x": [-30, 60]},
        "note": "Toe pivot (mirror). Same as LeftToeBase."
    },
}
