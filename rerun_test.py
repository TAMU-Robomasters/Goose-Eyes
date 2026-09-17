from math import tau

import numpy as np
import rerun as rr
from rerun.utilities import bounce_lerp, build_color_spiral

# native viewer
# rr.init("rerun_example_dna_abacus", spawn=True)

# server viewer
rr.init("rerun_example_dna_abacus")
rr.connect_grpc()

NUM_POINTS = 100
RADIUS = 0.08
points1, colors1 = build_color_spiral(NUM_POINTS)
points2, colors2 = build_color_spiral(NUM_POINTS, angular_offset=tau * 0.5)

rr.set_time("stable_time", duration=0)

rr.log(
    "dna/structure/right", rr.Points3D(points1, colors=colors1, radii=RADIUS)
)
rr.log(
    "dna/structure/left", rr.Points3D(points2, colors=colors2, radii=RADIUS)
)

rr.log(
    "dna/structure/scaffolding",
    rr.LineStrips3D(
        np.stack((points1, points2), axis=1), colors=[128, 128, 128]
    ),
)

offsets = np.random.rand(NUM_POINTS)
for i in range(400):
    time = i * 0.01
    rr.set_time("stable_time", duration=time)

    times = np.repeat(time, NUM_POINTS) + offsets
    beads = [
        bounce_lerp(points1[n], points2[n], times[n])
        for n in range(NUM_POINTS)
    ]
    colors = [
        [int(bounce_lerp(80, 230, offsets[n] * 2))] for n in range(NUM_POINTS)
    ]
    rr.log(
        "dna/structure/scaffolding/beads",
        rr.Points3D(beads, radii=0.06, colors=np.repeat(colors, 3, axis=-1)),
    )
    
    rr.log(
        "dna/structure",
        rr.Transform3D(
            rotation=rr.RotationAxisAngle(
                axis=[0, 0, 1], radians=time / 4.0 * tau
            )
        )
    )

