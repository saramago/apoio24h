from __future__ import annotations

from core.providers.farmacias_provider import FarmaciasProvider
from core.providers.infarmed_infomed import InfarmedInfomedProvider
from core.providers.maps_provider import MapsProvider
from core.providers.sns_portal import SnsPortalProvider
from core.providers.sns_transparencia import SnsTransparenciaProvider


def build_provider_registry() -> dict[str, object]:
    return {
        "sns_portal": SnsPortalProvider(),
        "sns_transparencia": SnsTransparenciaProvider(),
        "infarmed_infomed": InfarmedInfomedProvider(),
        "farmacias_provider": FarmaciasProvider(),
        "maps_provider": MapsProvider(),
    }
