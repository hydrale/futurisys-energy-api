"""Tests du script de deploiement, hors appels reseau.

Ce qui est verifiable sans jeton et sans plateforme distante, c'est la preparation des
fichiers. C'est justement la partie ou une erreur coute cher : un Space qui recoit le
mauvais README reste bloque au demarrage sans message clair, et un Space qui recoit le
code sans le modele repond 503 a chaque prediction.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.deployer_sur_hugging_face import DOSSIERS, FICHIERS, preparer
from tests.conftest import needs_model


@pytest.fixture
def prepare(tmp_path) -> Path:
    destination = tmp_path / "envoi"
    destination.mkdir()
    preparer(destination)
    return destination


@needs_model
def test_le_readme_du_space_remplace_celui_du_projet(prepare):
    """Hugging Face lit la configuration du Space dans l'en-tete de son README.md.

    Le README du projet n'a pas cet en-tete : envoye tel quel, le Space ne sait pas
    qu'il doit construire une image Docker et reste bloque au demarrage.
    """
    readme = (prepare / "README.md").read_text()
    assert readme.startswith("---")
    assert "sdk: docker" in readme
    assert "app_port: 7860" in readme
    # Le README long du projet ne doit pas etre celui-la.
    assert "Sommaire" not in readme


@needs_model
def test_le_modele_part_avec_le_code(prepare):
    """Sans le fichier du modele, le Space demarre et repond 503 a chaque prediction."""
    assert (prepare / "models" / "energy_model.joblib").exists()


@needs_model
def test_les_fichiers_necessaires_a_l_image_sont_presents(prepare):
    for nom in FICHIERS:
        assert (prepare / nom).exists(), nom
    for nom in DOSSIERS:
        assert (prepare / nom).is_dir(), nom
    assert (prepare / "src" / "futurisys" / "api" / "main.py").exists()
    assert (prepare / "data" / "building_energy_2016.csv").exists()


@needs_model
def test_rien_d_inutile_ne_part(prepare):
    """Tests, documentation et fichiers de CI n'ont rien a faire sur le Space :
    ils alourdissent l'image et elargissent la surface exposee."""
    for indesirable in ("tests", "docs", ".github", "htmlcov", ".env", "scripts"):
        assert not (prepare / indesirable).exists(), indesirable


@needs_model
def test_aucun_cache_python_ne_part(prepare):
    assert list(prepare.rglob("__pycache__")) == []
    assert list(prepare.rglob("*.pyc")) == []


def test_un_modele_absent_arrete_le_deploiement(tmp_path, monkeypatch):
    """Mieux vaut un deploiement qui refuse de partir qu'un Space en ligne et casse."""
    faux_projet = tmp_path / "projet"
    faux_projet.mkdir()
    for nom in FICHIERS:
        (faux_projet / nom).write_text("x")
    for nom in DOSSIERS:
        (faux_projet / nom).mkdir()
    (faux_projet / "README_HF.md").write_text("---\nsdk: docker\n---\n")

    import scripts.deployer_sur_hugging_face as module

    monkeypatch.setattr(module, "RACINE", faux_projet)
    destination = tmp_path / "envoi"
    destination.mkdir()
    with pytest.raises(SystemExit) as erreur:
        module.preparer(destination)
    assert "train" in str(erreur.value)
    shutil.rmtree(destination)


class ApiFictive:
    """Un faux client Hugging Face : whoami() sans reseau ni jeton."""

    def __init__(self, compte: str):
        self._compte = compte

    def whoami(self) -> dict:
        return {"name": self._compte}


def test_le_compte_est_deduit_du_jeton_quand_rien_n_est_impose():
    """Evite d'avoir a saisir son pseudo : le jeton porte deja l'information."""
    from scripts.deployer_sur_hugging_face import nom_du_space

    assert nom_du_space(ApiFictive("hydrale"), None) == "hydrale/futurisys-energy-api"


def test_un_space_impose_a_la_main_est_respecte():
    """Permet de viser un autre compte ou un autre nom, sans toucher au code."""
    from scripts.deployer_sur_hugging_face import nom_du_space

    assert nom_du_space(ApiFictive("hydrale"), "orga/autre-nom") == "orga/autre-nom"


def test_un_space_vide_est_traite_comme_absent():
    """Une variable GitHub non renseignee arrive comme une chaine vide, pas comme None."""
    from scripts.deployer_sur_hugging_face import nom_du_space

    assert nom_du_space(ApiFictive("hydrale"), "") == "hydrale/futurisys-energy-api"
