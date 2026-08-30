"""Tests de la chaine de nettoyage, chiffres du notebook a l'appui.

Chaque filtre a un nombre de batiments attendu. Si un seul derive, le modele
reentraine ne sera plus celui qui a ete valide, et ce test le signale immediatement.
"""

from __future__ import annotations

import numpy as np
import pytest

from futurisys.ml.preparation import (
    BINARY_FEATURES,
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    LEAKAGE_COLUMNS,
    LOG_TARGET,
    NUMERIC_FEATURES,
    TARGET,
    build_feature_frame,
    clean_dataset,
    load_raw_dataset,
)
from tests.conftest import DATASET, needs_dataset

# Les comptes exacts releves dans le notebook du projet precedent.
EXPECTED_STEPS = [
    ("1. hors logements", 3376, 1668),
    ("2. releve conforme", 1668, 1548),
    ("3. consommation renseignee", 1548, 1538),
    ("4. au moins 1 etage", 1538, 1523),
    ("5. non signale par la ville", 1523, 1523),
    ("6. hors extremes (IQR 1,5)", 1523, 1508),
]


@pytest.fixture(scope="module")
def cleaned():
    return clean_dataset(load_raw_dataset(DATASET))


@needs_dataset
def test_chaque_filtre_garde_le_nombre_de_batiments_attendu(cleaned):
    _, report = cleaned
    assert report.steps == EXPECTED_STEPS


@needs_dataset
def test_le_jeu_final_fait_1508_batiments_et_15_colonnes(cleaned):
    clean, _ = cleaned
    assert len(clean) == 1508
    assert build_feature_frame(clean).shape == (1508, 15)


@needs_dataset
def test_aucune_colonne_de_leakage_ne_survit(cleaned):
    """La verification la plus importante : une seule de ces colonnes qui reste et le
    modele triche, avec un score parfait et aucune valeur reelle."""
    clean, _ = cleaned
    assert [c for c in LEAKAGE_COLUMNS if c in clean.columns] == []


@needs_dataset
def test_la_cible_est_toujours_strictement_positive(cleaned):
    """Une consommation nulle ou manquante rendrait le logarithme impossible."""
    clean, _ = cleaned
    assert (clean[TARGET] > 0).all()


@needs_dataset
def test_le_log_reduit_l_asymetrie_de_la_cible(cleaned):
    """L'asymetrie tombe de 3,57 a 0,24 : c'est la raison d'etre du logarithme.

    Le notebook annonce 11,03 : ce chiffre est mesure avant le filtre des extremes,
    qui retire justement les batiments responsables du gros de l'asymetrie. Sur le jeu
    final, l'asymetrie residuelle est de 3,57, et le log la ramene sous 0,5.
    """
    clean, _ = cleaned
    assert clean[TARGET].skew() == pytest.approx(3.57, abs=0.05)
    assert clean[LOG_TARGET].skew() == pytest.approx(0.24, abs=0.05)


@needs_dataset
def test_le_log_est_bien_l_inverse_de_expm1(cleaned):
    """Verifie la conversion utilisee par l'API pour rendre des kBtu."""
    clean, _ = cleaned
    reconstructed = np.expm1(clean[LOG_TARGET])
    assert np.allclose(reconstructed, clean[TARGET])


@needs_dataset
def test_aucune_valeur_manquante_dans_les_features(cleaned):
    """Le modele n'a pas d'etape d'imputation : une valeur manquante le ferait planter."""
    clean, _ = cleaned
    assert build_feature_frame(clean).isna().sum().sum() == 0


@needs_dataset
def test_les_types_des_features_sont_ceux_de_l_entrainement(cleaned):
    """Categories en texte, binaires en entier : le modele a ete entraine ainsi."""
    clean, _ = cleaned
    features = build_feature_frame(clean)
    for column in CATEGORICAL_FEATURES:
        assert features[column].dtype == object
    for column in BINARY_FEATURES:
        assert features[column].dtype.kind == "i"
    for column in NUMERIC_FEATURES:
        assert features[column].dtype.kind in "if"


@needs_dataset
def test_aucun_batiment_de_zero_etage_ne_subsiste(cleaned):
    """Valeur physiquement impossible : c'est une aberration, pas un cas extreme."""
    clean, _ = cleaned
    assert (clean["NumberofFloors"] > 0).all()


@needs_dataset
def test_huit_quartiers_sont_appris(cleaned):
    _, report = cleaned
    assert len(report.top_neighborhoods) == 8
    assert "DOWNTOWN" in report.top_neighborhoods


def test_les_15_colonnes_sont_bien_reparties_en_trois_familles():
    assert len(FEATURE_COLUMNS) == 15
    assert set(FEATURE_COLUMNS) == set(NUMERIC_FEATURES + CATEGORICAL_FEATURES + BINARY_FEATURES)
