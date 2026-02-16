"""
sample_module.py — Test fixture for DO-178C pipeline verification.
A simple calculator module with branches, loops, and error handling.
"""


def calculate_average(values):
    """Calculate the arithmetic mean of a list of numbers."""
    if not values:
        return 0.0
    if not isinstance(values, (list, tuple)):
        raise TypeError("Expected list or tuple")

    total = 0.0
    for val in values:
        if not isinstance(val, (int, float)):
            raise ValueError(f"Non-numeric value: {val}")
        total += val

    return total / len(values)


def classify_temperature(temp_celsius):
    """Classify temperature into categories."""
    if temp_celsius < -40:
        return "INVALID_LOW"
    elif temp_celsius < 0:
        return "FREEZING"
    elif temp_celsius < 20:
        return "COLD"
    elif temp_celsius < 35:
        return "WARM"
    elif temp_celsius < 50:
        return "HOT"
    else:
        return "INVALID_HIGH"


class SensorProcessor:
    """Process sensor readings with filtering."""

    def __init__(self, threshold=100.0):
        self.threshold = threshold
        self.readings = []

    def add_reading(self, value):
        """Add a sensor reading, filtering outliers."""
        try:
            numeric_val = float(value)
        except (ValueError, TypeError):
            return False

        if abs(numeric_val) > self.threshold:
            return False

        self.readings.append(numeric_val)
        return True

    def get_filtered_average(self):
        """Return average of valid readings."""
        if not self.readings:
            return None
        return sum(self.readings) / len(self.readings)
