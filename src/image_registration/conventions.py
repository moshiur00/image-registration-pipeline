"""Project-wide registration and coordinate conventions.

These constants make assumptions inspectable in code and tests instead of
leaving transformation direction implicit.
"""

FIXED_IMAGE_ROLE = "reference_target"
MOVING_IMAGE_ROLE = "source_to_align"
REGISTERED_IMAGE_ROLE = "moving_resampled_on_fixed_grid"

# Logical transformation returned/stored by registration modules.
STORED_TRANSFORM_DIRECTION = "moving_to_fixed"

# Geometric point order, not NumPy array indexing order.
COORDINATE_ORDER = "x_y"

# NumPy accesses a 2D image as image[y, x].
NUMPY_INDEX_ORDER = "y_x"

# Positive image-plane angles rotate counterclockwise on the displayed image.
# Because image y increases downward, the 2x2 point matrix differs in sign from
# the usual y-up Cartesian rotation matrix.
POSITIVE_ROTATION_DIRECTION = "counterclockwise_in_display"
ANGLE_UNIT = "degrees"

# The current 2D pipeline uses homogeneous coordinates.
HOMOGENEOUS_DIMENSION = 3
