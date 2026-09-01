from image_registration.conventions import (
    ANGLE_UNIT,
    COORDINATE_ORDER,
    HOMOGENEOUS_DIMENSION,
    NUMPY_INDEX_ORDER,
    POSITIVE_ROTATION_DIRECTION,
    STORED_TRANSFORM_DIRECTION,
)


def test_stored_transform_direction_is_moving_to_fixed() -> None:
    assert STORED_TRANSFORM_DIRECTION == "moving_to_fixed"


def test_geometric_and_array_coordinate_orders_are_explicit() -> None:
    assert COORDINATE_ORDER == "x_y"
    assert NUMPY_INDEX_ORDER == "y_x"


def test_homogeneous_dimension_is_three() -> None:
    assert HOMOGENEOUS_DIMENSION == 3


def test_rotation_convention_is_explicit() -> None:
    assert POSITIVE_ROTATION_DIRECTION == "counterclockwise_in_display"
    assert ANGLE_UNIT == "degrees"
