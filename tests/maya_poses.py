"""Poses the Maya control rig tests use, shared by the mayapy check script and the pytest file."""
import math

POSE = {"root": [0.05, 0.9, 0.1], "yaw": 0.3, "pelvis": [0.1, -0.05], "spine": [0.3, 0.1, 0.2], "head": [0.2, 0.1, 0.3],
        "neck": [0.1, 0, 0.1], "clavL": [0.1, 0.05], "armL": [1.2, 0.3, 0.2], "elbowL": [0.9, 0.3],
        "handL": [0.3, 0.1], "armR": [math.pi / 2, 0.0, 0.0], "elbowR": [0.4, 0.0],
        "footL": [-0.15, 0.12, 0.25, 0.1, 0.2], "rollL": [0.3, 0.0, 0.6], "kneeL": 0.2,
        "footR": [0.12, 0.09, -0.15, 0.0, -0.1], "rollR": [-0.2, 0.1, 0.6],
        "fingersL": [0.8, 0.4, 1.5, 0.1, 1.6, 0.0, 1.7, -0.05, 1.8, -0.1]}
ROLLS = {"heel": {"rollL": [-0.4, 0, 0.6]}, "ball": {"rollL": [0.4, 0, 0.6]}, "toe": {"rollL": [1.2, 0, 0.6]},
         "bank_out": {"rollL": [0, 0.25, 0.6]}, "bank_in": {"rollL": [0, -0.25, 0.6]},
         "bank_heel": {"rollL": [-0.3, 0.2, 0.6]}, "bank_toe": {"rollL": [1.0, -0.2, 0.5]}, "tap": {"toeL": 0.4},
         "stretch": {"legSL": 1.1, "armSR": 0.9, "sq": 1.05, "neckS": 1.1}}
