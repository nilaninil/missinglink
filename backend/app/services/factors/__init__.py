"""Factor registry. To add a factor: create a file, add one line here, add one weight."""
from .photo import PhotoFactor
from .age import AgeFactor
from .gender import GenderFactor
from .clothing import ClothingFactor
from .location import LocationFactor
from .time import TimeFactor
from .corroboration import CorroborationFactor
from .occupation import OccupationFactor

FACTORS = [
    PhotoFactor(), AgeFactor(), GenderFactor(), ClothingFactor(),
    LocationFactor(), TimeFactor(), CorroborationFactor(),
    OccupationFactor(),  # active only when its weight > 0
]
