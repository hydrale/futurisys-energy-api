"""Publie l'API sur un Space Hugging Face.

    python scripts/deployer_sur_hugging_face.py --space compte/nom-du-space --version v1.2.0

Appele par le workflow de deploiement, jamais a la main en temps normal. Il est ecrit
en Python plutot qu'en lignes de commande dans le YAML pour trois raisons : la
bibliotheque Hugging Face garde la meme interface Python d'une version a l'autre alors
que son outil en ligne de commande a change de nom, le script se relit et se corrige,
et il peut preparer les fichiers avant de les envoyer.

Le jeton est lu dans la variable d'environnement HF_TOKEN. Il n'est jamais passe en
argument : un argument de ligne de commande est visible par tous les processus de la
machine et finit dans les journaux.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

# Ce qui part sur le Space, et rien d'autre. Les tests, la documentation et les
# fichiers d'integration continue n'ont rien a y faire : ils alourdissent l'image et
# elargissent la surface exposee.
FICHIERS = ["Dockerfile", "requirements.txt"]
DOSSIERS = ["src", "models", "data"]

# Hugging Face lit la configuration du Space dans l'en-tete de son README.md : le type
# d'hebergement et le port ecoute. Le README du projet n'a pas cet en-tete, donc c'est
# README_HF.md qui doit arriver sous le nom README.md. Sans cette bascule, le Space ne
# sait pas qu'il doit construire une image Docker et reste bloque au demarrage.
README_DU_SPACE = "README_HF.md"


def preparer(destination: Path) -> None:
    """Recopie dans un dossier temporaire ce qui doit partir, et rien de plus."""
    for nom in FICHIERS:
        shutil.copy2(RACINE / nom, destination / nom)
    for nom in DOSSIERS:
        shutil.copytree(
            RACINE / nom,
            destination / nom,
            # Les caches Python et les fichiers macOS n'ont aucune raison de voyager.
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
        )
    shutil.copy2(RACINE / README_DU_SPACE, destination / "README.md")

    modele = destination / "models" / "energy_model.joblib"
    if not modele.exists():
        raise SystemExit(
            "Modele absent : lancer 'python -m futurisys.ml.train' avant de deployer. "
            "Le Space demarrerait sans modele et repondrait 503 a chaque prediction."
        )


def deployer(space: str, version: str) -> str:  # pragma: no cover
    # Exclu de la mesure de couverture : cette fonction ne fait que des appels a la
    # plateforme Hugging Face. La tester demanderait un vrai jeton et creerait un vrai
    # Space a chaque execution des tests. Ce qui est verifiable sans reseau, la
    # preparation des fichiers, est isole dans preparer() et couvert par 6 tests.
    from huggingface_hub import HfApi

    jeton = os.environ.get("HF_TOKEN")
    if not jeton:
        raise SystemExit("Variable HF_TOKEN absente.")

    api = HfApi(token=jeton)

    # exist_ok : le script cree le Space au premier deploiement et le reutilise ensuite.
    # Sans cela, le tout premier deploiement echouerait sur un Space introuvable.
    api.create_repo(repo_id=space, repo_type="space", space_sdk="docker", exist_ok=True)
    print(f"Space pret : {space}")

    # Les secrets du Space sont poses avant l'envoi du code, pour que le conteneur
    # les trouve des son premier demarrage. Ils viennent des secrets GitHub : aucune
    # valeur sensible ne transite par le depot ni par les journaux.
    secrets = {
        "SECRET_KEY": os.environ.get("APP_SECRET_KEY"),
        "ADMIN_PASSWORD": os.environ.get("APP_ADMIN_PASSWORD"),
    }
    for cle, valeur in secrets.items():
        if valeur:
            api.add_space_secret(repo_id=space, key=cle, value=valeur)
            print(f"  secret pose : {cle}")
        else:
            print(f"  secret absent, valeur par defaut utilisee : {cle}")

    # PostgreSQL n'est pas disponible sur un Space : la base tombe sur SQLite dans
    # /tmp, seul emplacement garanti inscriptible. L'enonce autorise explicitement une
    # base locale pour la demonstration.
    api.add_space_variable(repo_id=space, key="DATABASE_URL", value="sqlite:////tmp/futurisys.db")
    api.add_space_variable(repo_id=space, key="APP_ENV", value="prod")

    with tempfile.TemporaryDirectory() as dossier:
        destination = Path(dossier)
        preparer(destination)
        envoyes = sum(1 for _ in destination.rglob("*") if _.is_file())
        print(f"Envoi de {envoyes} fichiers...")
        api.upload_folder(
            folder_path=str(destination),
            repo_id=space,
            repo_type="space",
            commit_message=f"Deploiement {version}",
        )

    # L'adresse publique du Space : le nom du depot, barre oblique remplacee par un
    # tiret, en minuscules.
    return f"https://{space.replace('/', '-').lower()}.hf.space"


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", required=True, help="compte/nom-du-space")
    parser.add_argument("--version", default="manuel")
    arguments = parser.parse_args()

    adresse = deployer(arguments.space, arguments.version)
    print(f"\nSpace en construction : {adresse}")
    # Le workflow lit cette sortie pour savoir quelle adresse interroger ensuite.
    if sortie := os.environ.get("GITHUB_OUTPUT"):
        Path(sortie).open("a").write(f"space_url={adresse}\n")


if __name__ == "__main__":
    main()
    sys.exit(0)
