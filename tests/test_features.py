"""Tests unitaires des 3 colonnes calculees.

Ce sont les tests les plus importants du projet : ces fonctions tournent a deux
endroits (entrainement et API), et un ecart entre les deux ne provoque aucune erreur,
seulement des predictions fausses. Les figer par des tests est la seule protection.
"""

from __future__ import annotations

import pandas as pd
import pytest

from futurisys.ml.features import (
    OTHER_NEIGHBORHOOD,
    REFERENCE_YEAR,
    compute_building_age,
    compute_largest_use_ratio,
    group_neighborhood,
)


def test_age_compte_a_partir_de_2016_pas_de_l_annee_courante():
    """Le releve porte sur 2016 : un batiment de 1985 a 31 ans, pas davantage."""
    assert compute_building_age(pd.Series([1985])).iloc[0] == 31
    assert REFERENCE_YEAR == 2016


def test_age_nul_pour_un_batiment_de_l_annee_du_releve():
    assert compute_building_age(pd.Series([2016])).iloc[0] == 0


def test_ratio_usage_principal_cas_normal():
    """220 000 pieds carres d'activite dans 250 000 au total font 0,88."""
    ratio = compute_largest_use_ratio(pd.Series([220_000.0]), pd.Series([250_000.0]))
    assert ratio.iloc[0] == pytest.approx(0.88)


def test_ratio_plafonne_a_1_quand_la_saisie_est_incoherente():
    """Une activite declaree plus grande que le batiment est ramenee a 1,0.

    Sans ce plafond, ces lignes enverraient au modele une valeur de 1,3 qu'il n'a
    jamais rencontree a l'entrainement.
    """
    ratio = compute_largest_use_ratio(pd.Series([300_000.0]), pd.Series([250_000.0]))
    assert ratio.iloc[0] == 1.0


def test_ratio_absent_vaut_1_car_le_batiment_est_mono_usage():
    ratio = compute_largest_use_ratio(pd.Series([None]), pd.Series([250_000.0]))
    assert ratio.iloc[0] == 1.0


def test_quartier_connu_est_conserve():
    result = group_neighborhood(pd.Series(["DOWNTOWN"]), ["DOWNTOWN", "EAST"])
    assert result.iloc[0] == "DOWNTOWN"


def test_quartier_rare_bascule_en_autre():
    """Un quartier hors de la liste apprise ne doit pas creer de categorie inconnue."""
    result = group_neighborhood(pd.Series(["INTERBAY"]), ["DOWNTOWN", "EAST"])
    assert result.iloc[0] == OTHER_NEIGHBORHOOD


def test_quartier_insensible_a_la_casse():
    """downtown et DOWNTOWN sont le meme quartier, pas deux categories."""
    result = group_neighborhood(pd.Series(["downtown", "DoWnToWn"]), ["DOWNTOWN"])
    assert list(result) == ["DOWNTOWN", "DOWNTOWN"]
