"""Le pont entre une demande recue par l'API et le modele entraine.

Trois choses se passent ici, et aucune n'est evidente vue de l'exterieur :
1. le modele est charge une seule fois, pas a chaque appel (11 Mo a lire sur disque) ;
2. les colonnes calculees sont reconstruites, avec le meme code qu'a l'entrainement ;
3. la prediction est reconvertie en kBtu, parce que le modele repond en logarithme.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from futurisys.config import get_settings
from futurisys.ml.features import (
    compute_building_age,
    compute_largest_use_ratio,
    group_neighborhood,
)
from futurisys.ml.preparation import build_feature_frame


class ModelNotAvailable(RuntimeError):
    """Le fichier du modele est absent. L'API doit repondre 503, pas planter."""


@dataclass(frozen=True)
class Prediction:
    """Le resultat d'un appel au modele, sous ses deux formes plus le temps de calcul."""

    log_value: float
    kbtu: float
    duration_ms: float


class EnergyPredictor:
    """Charge le modele une fois et repond aux demandes."""

    def __init__(self, artifact_path: str | Path):
        path = Path(artifact_path)
        if not path.exists():
            raise ModelNotAvailable(
                f"Modele introuvable : {path}. Lancer d'abord : python -m futurisys.ml.train"
            )
        artifact = joblib.load(path)
        self.pipeline = artifact["pipeline"]
        self.metadata: dict = artifact["metadata"]
        self.top_neighborhoods: list[str] = self.metadata["top_neighborhoods"]

    def build_features(self, payload: dict) -> pd.DataFrame:
        """Transforme une demande de l'API en la ligne de 15 colonnes attendue.

        C'est l'etape la plus fragile du deploiement : le modele ne verifie pas ce
        qu'on lui donne. S'il recoit une annee de construction la ou il attend un age,
        il repond quand meme, avec un chiffre faux et sans le moindre message.
        """
        # DataFrame d'une seule ligne : le pipeline scikit-learn attend un tableau,
        # pas un dictionnaire, et les noms de colonnes doivent etre exactement ceux
        # vus a l'entrainement.
        frame = pd.DataFrame([payload])

        frame["building_age"] = compute_building_age(frame["year_built"])
        frame["largest_use_ratio"] = compute_largest_use_ratio(
            frame["largest_property_use_gfa"], frame["property_gfa_total"]
        )
        frame["neighborhood_grouped"] = group_neighborhood(
            frame["neighborhood"], self.top_neighborhoods
        )
        # Les noms de l'API sont en minuscules avec des tirets bas ; ceux du modele
        # viennent du fichier de la ville de Seattle. La correspondance se fait ici.
        frame = frame.rename(
            columns={
                "building_type": "BuildingType",
                "primary_property_type": "PrimaryPropertyType",
                "property_gfa_total": "PropertyGFATotal",
                "property_gfa_parking": "PropertyGFAParking",
                "number_of_floors": "NumberofFloors",
                "number_of_buildings": "NumberofBuildings",
                "latitude": "Latitude",
                "longitude": "Longitude",
            }
        )
        return build_feature_frame(frame)

    def predict(self, payload: dict) -> Prediction:
        """Predit la consommation annuelle d'un batiment, en kBtu."""
        features = self.build_features(payload)
        started = time.perf_counter()
        log_value = float(self.pipeline.predict(features)[0])
        duration_ms = (time.perf_counter() - started) * 1000

        # expm1 est l'inverse exact de log1p utilise a l'entrainement. Sans cette
        # ligne l'API renverrait 15,2 au lieu de 4 000 000 : un chiffre qui a l'air
        # d'une reponse valide, et que personne ne verrait passer.
        kbtu = float(np.expm1(log_value))
        return Prediction(
            log_value=round(log_value, 6),
            kbtu=round(kbtu, 1),
            duration_ms=round(duration_ms, 2),
        )


@lru_cache
def get_predictor() -> EnergyPredictor:
    """Le modele, charge au premier appel et garde en memoire ensuite.

    Sans lru_cache, chaque requete relirait 11 Mo sur le disque et reconstruirait
    400 arbres : la reponse passerait de quelques millisecondes a plus d'une seconde.
    """
    return EnergyPredictor(get_settings().model_path)
