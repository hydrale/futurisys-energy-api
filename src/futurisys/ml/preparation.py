"""La chaine de nettoyage du notebook, rejouee en code.

Elle part des 3 376 batiments bruts du releve 2016 de la ville de Seattle et en
garde 1 508. Chaque filtre est isole dans sa propre etape et rend le nombre de lignes
avant et apres : c'est ce compte qui sert de preuve que le code fait bien ce que le
notebook faisait, et les tests le verifient ligne a ligne.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from futurisys.ml.features import (
    compute_building_age,
    compute_largest_use_ratio,
    group_neighborhood,
)

# La colonne a predire : la consommation totale du site, corrigee de la meteo.
# "WN" = weather normalized. Corrigee, parce qu'un hiver froid fait monter la
# consommation de tous les batiments a la fois : sans correction le modele
# apprendrait la meteo de 2016 au lieu d'apprendre les proprietes du batiment.
TARGET = "SiteEnergyUseWN(kBtu)"

# Le modele n'apprend pas la consommation brute mais son logarithme. Un entrepot
# consomme 200 000 kBtu, un hopital 400 millions : sur l'echelle brute, l'erreur
# commise sur l'hopital ecrase tout le reste et le modele ne s'occupe plus que des
# geants. Le log ramene ces ecarts a la meme echelle (asymetrie de 11,03 a 0,34).
LOG_TARGET = "log_target"

# Les logements sont hors perimetre : la mission de la ville porte sur les batiments
# non residentiels, dont la consommation obeit a une logique differente (horaires
# d'ouverture, equipements) de celle d'un immeuble d'habitation.
RESIDENTIAL_TYPES = [
    "Multifamily LR (1-4)",
    "Multifamily MR (5-9)",
    "Multifamily HR (10+)",
]

# Ces colonnes contiennent deja la reponse, en tout ou en partie : ce sont les
# consommations mesurees, les intensites energetiques (consommation / surface), les
# emissions de gaz a effet de serre qui en decoulent, et le score ENERGY STAR qui est
# calcule a partir de la consommation. Les garder reviendrait a donner la reponse au
# modele : il aurait un score parfait a l'entrainement et serait inutilisable en vrai,
# puisqu'on ne connait aucune de ces valeurs avant d'avoir mesure le batiment.
LEAKAGE_COLUMNS = [
    "SiteEUI(kBtu/sf)",
    "SiteEUIWN(kBtu/sf)",
    "SourceEUI(kBtu/sf)",
    "SourceEUIWN(kBtu/sf)",
    "SiteEnergyUse(kBtu)",
    "SteamUse(kBtu)",
    "Electricity(kWh)",
    "Electricity(kBtu)",
    "NaturalGas(therms)",
    "NaturalGas(kBtu)",
    "TotalGHGEmissions",
    "GHGEmissionsIntensity",
    "ENERGYSTARScore",
    "YearsENERGYSTARCertified",
]

# Ces colonnes ne trichent pas, elles font doublon : leur information a deja ete
# extraite dans une colonne calculee. YearBuilt est devenue building_age,
# LargestPropertyUseTypeGFA est devenue largest_use_ratio, Neighborhood est devenue
# neighborhood_grouped. Les garder en double donnerait deux fois le meme signal.
REDUNDANT_COLUMNS = [
    "ListOfAllPropertyUseTypes",
    "LargestPropertyUseType",
    "LargestPropertyUseTypeGFA",
    "SecondLargestPropertyUseType",
    "SecondLargestPropertyUseTypeGFA",
    "ThirdLargestPropertyUseType",
    "ThirdLargestPropertyUseTypeGFA",
    "YearBuilt",
    "PropertyGFABuilding(s)",
    "Neighborhood",
    "CouncilDistrictCode",
]

# Combien de quartiers gardent leur propre etiquette. 8 est le choix du notebook :
# au-dela, les quartiers suivants tombent sous la dizaine de batiments.
TOP_NEIGHBORHOODS_COUNT = 8

# Les 15 colonnes vues par le modele, rangees par le traitement qu'elles recoivent.
NUMERIC_FEATURES = [
    "PropertyGFATotal",
    "PropertyGFAParking",
    "NumberofFloors",
    "NumberofBuildings",
    "Latitude",
    "Longitude",
    "building_age",
    "largest_use_ratio",
]
CATEGORICAL_FEATURES = ["BuildingType", "PrimaryPropertyType", "neighborhood_grouped"]
BINARY_FEATURES = ["is_multi_use", "has_electricity", "has_natural_gas", "has_steam"]
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES + BINARY_FEATURES


@dataclass
class CleaningReport:
    """Le nombre de batiments restants apres chaque filtre.

    Sert a deux choses : afficher la chaine dans les logs d'entrainement, et donner
    aux tests des chiffres exacts a verifier. Si un filtre derive, un test casse.
    """

    steps: list[tuple[str, int, int]] = field(default_factory=list)

    # Les 8 quartiers frequents ne sont pas une constante : ils sont *appris* sur les
    # donnees d'entrainement. Ils sont ranges ici pour etre sauvegardes avec le modele,
    # parce que l'API doit ranger un quartier recu exactement comme a l'entrainement.
    top_neighborhoods: list[str] = field(default_factory=list)

    def record(self, label: str, before: int, after: int) -> None:
        self.steps.append((label, before, after))

    def as_text(self) -> str:
        return "\n".join(
            f"  {label:<38} {before:>5} -> {after:>5}  ({after - before:+d})"
            for label, before, after in self.steps
        )


def load_raw_dataset(csv_path: str | Path) -> pd.DataFrame:
    """Lit le fichier brut de la ville de Seattle, sans aucune transformation."""
    return pd.read_csv(csv_path)


def clean_dataset(raw: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    """Applique les 6 filtres du notebook, dans le meme ordre, et trace chaque etape.

    L'ordre compte : le filtre par ecart interquartile de la derniere etape travaille
    sur le logarithme de la cible, qui n'existe qu'une fois les lignes sans mesure
    ecartees. Inverser deux etapes donnerait un jeu de donnees different.
    """
    report = CleaningReport()
    data = raw.copy()

    # Etape 1 - perimetre. "Nonresidential WA" est une faute de frappe de
    # "NonResidential" : verifie via PrimaryPropertyType, l'unique batiment concerne
    # est bien un batiment non residentiel. Sans la correction il formerait a lui seul
    # une categorie d'un batiment.
    before = len(data)
    data["BuildingType"] = data["BuildingType"].replace("Nonresidential WA", "NonResidential")
    data = data[~data["BuildingType"].isin(RESIDENTIAL_TYPES)].copy()
    report.record("1. hors logements", before, len(data))

    # Etape 2 - fiabilite de la mesure. La ville marque elle-meme les releves
    # douteux. Apprendre sur une consommation que la ville declare fausse revient a
    # apprendre du bruit : on garde uniquement les releves conformes.
    before = len(data)
    data = data[data["ComplianceStatus"] == "Compliant"].copy()
    data = data.drop(columns=["ComplianceStatus"])
    report.record("2. releve conforme", before, len(data))

    # Etape 3 - la cible doit exister. Une consommation manquante ou nulle ne
    # s'invente pas : c'est la reponse, on ne l'impute jamais, on retire la ligne.
    before = len(data)
    data = data[data[TARGET] > 0].copy()
    report.record("3. consommation renseignee", before, len(data))

    # Etape 4 - valeur physiquement impossible. Un batiment a au moins un etage ;
    # NumberofFloors = 0 est une erreur de saisie, pas un batiment extreme.
    before = len(data)
    data = data[data["NumberofFloors"] > 0].copy()
    report.record("4. au moins 1 etage", before, len(data))

    # log1p plutot que log : log1p(x) = log(1+x), qui accepte x = 0 sans erreur.
    data[LOG_TARGET] = np.log1p(data[TARGET])

    # Etape 5 - les aberrations signalees par la ville elle-meme. La colonne Outlier
    # porte son diagnostic (High / Low). On fait confiance au producteur de la donnee
    # plutot que de rejuger nous-memes.
    before = len(data)
    data = data[data["Outlier"].isna()].copy()
    data = data.drop(columns=["Outlier"])
    report.record("5. non signale par la ville", before, len(data))

    data, report.top_neighborhoods = _add_engineered_columns(data)

    # Etape 6 - les extremes restants, par ecart interquartile. On calcule l'intervalle
    # ou se tient le gros du peloton, elargi de 1,5 fois sa largeur, et on coupe
    # au-dela. C'est un choix discutable et assume : ces batiments sont reels, pas
    # faux. Les retirer rend le modele plus stable sur les cas courants, mais il ne
    # saura pas extrapoler face a un futur campus hors norme (voir les limites).
    before = len(data)
    q1, q3 = data[LOG_TARGET].quantile([0.25, 0.75])
    iqr = q3 - q1
    low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    data = data[data[LOG_TARGET].between(low, high)].copy()
    report.record("6. hors extremes (IQR 1,5)", before, len(data))

    dropped = [c for c in LEAKAGE_COLUMNS + REDUNDANT_COLUMNS if c in data.columns]
    data = data.drop(columns=dropped)

    return data, report


def _add_engineered_columns(data: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Ajoute les colonnes calculees, et rend la liste des quartiers retenus."""
    # notna() : une deuxieme activite renseignee signifie un batiment multi-usages.
    data["is_multi_use"] = data["SecondLargestPropertyUseType"].notna()
    data["building_age"] = compute_building_age(data["YearBuilt"])
    data["largest_use_ratio"] = compute_largest_use_ratio(
        data["LargestPropertyUseTypeGFA"], data["PropertyGFATotal"]
    )

    # Quelles energies arrivent au batiment. Ce n'est pas de la triche : on lit ici
    # la presence d'un raccordement, pas la quantite consommee, et un exploitant sait
    # avant toute mesure si son batiment est raccorde au gaz ou au reseau de vapeur.
    # fillna(0) : une colonne vide signifie pas de raccordement, pas une valeur perdue.
    data["has_electricity"] = data["Electricity(kBtu)"].fillna(0) > 0
    data["has_natural_gas"] = data["NaturalGas(kBtu)"].fillna(0) > 0
    data["has_steam"] = data["SteamUse(kBtu)"].fillna(0) > 0

    data["Neighborhood"] = data["Neighborhood"].str.upper()
    kept = find_top_neighborhoods(data["Neighborhood"])
    data["neighborhood_grouped"] = group_neighborhood(data["Neighborhood"], kept)
    return data, kept


def find_top_neighborhoods(neighborhood: pd.Series) -> list[str]:
    """Les 8 quartiers les plus representes, calcules sur les donnees d'entrainement.

    Cette liste doit etre sauvegardee avec le modele : l'API en a besoin pour ranger
    un quartier recu dans la bonne case. Si elle etait recalculee a l'usage, un
    quartier pourrait changer de camp entre l'entrainement et la prediction.
    """
    return list(neighborhood.value_counts().nlargest(TOP_NEIGHBORHOODS_COUNT).index)


def build_feature_frame(data: pd.DataFrame) -> pd.DataFrame:
    """Isole les 15 colonnes du modele et fixe leur type.

    astype(str) sur les categories et astype(int) sur les binaires : le modele a ete
    entraine sur ces types precis. Un booleen Python et un entier 0/1 ne traversent
    pas l'encodeur de la meme facon, et l'ecart passerait inapercu sans erreur.
    """
    features = data[FEATURE_COLUMNS].copy()
    features[CATEGORICAL_FEATURES] = features[CATEGORICAL_FEATURES].astype(str)
    features[BINARY_FEATURES] = features[BINARY_FEATURES].astype(int)
    return features
