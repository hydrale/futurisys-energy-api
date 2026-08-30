"""Interroge la base et exporte des exemples d'entrees et de sorties du modele.

    python scripts/interroger_base.py                  # affiche les tableaux
    python scripts/interroger_base.py --export dossier # ecrit aussi les fichiers CSV

Sert a deux choses : verifier a la main ce que le service a enregistre, et produire
les exemples d'entrees en base demandes dans les livrables. Toutes les requetes
passent par l'ORM, donc le script fonctionne aussi bien sur PostgreSQL que sur SQLite.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from futurisys.db.models import (  # noqa: E402
    Building,
    ModelVersion,
    PredictionRequest,
    PredictionResult,
    User,
)
from futurisys.db.session import SessionLocal  # noqa: E402


def volumes(session: Session) -> list[dict]:
    """Combien de lignes dans chaque table. Le premier controle apres une installation."""
    return [
        {"table": nom, "lignes": session.scalar(select(func.count()).select_from(modele))}
        for nom, modele in [
            ("users", User),
            ("buildings", Building),
            ("model_versions", ModelVersion),
            ("prediction_requests", PredictionRequest),
            ("prediction_results", PredictionResult),
        ]
    ]


def consommation_par_usage(session: Session) -> list[dict]:
    """La consommation mesuree, moyenne par type d'usage.

    Repond a une vraie question metier : quels usages consomment le plus, et sur
    combien de batiments cette moyenne est-elle calculee.
    """
    lignes = session.execute(
        select(
            Building.primary_property_type,
            func.count().label("batiments"),
            func.avg(Building.site_energy_use_wn_kbtu).label("moyenne"),
        )
        .group_by(Building.primary_property_type)
        .order_by(func.avg(Building.site_energy_use_wn_kbtu).desc())
    ).all()
    return [
        {"usage": usage, "batiments": n, "consommation_moyenne_kbtu": round(float(m))}
        for usage, n, m in lignes
    ]


def journal_des_appels(session: Session, limite: int = 100) -> list[dict]:
    """Les appels au modele : ce qui a ete envoye, ce qui a ete repondu.

    C'est la table qui prouve la tracabilite : une ligne par appel, avec l'auteur,
    les entrees, la sortie, le temps de calcul et la version du modele utilisee.
    """
    lignes = session.execute(
        select(PredictionRequest, PredictionResult, User, ModelVersion)
        .join(PredictionResult, PredictionResult.request_id == PredictionRequest.id)
        .join(User, User.id == PredictionRequest.user_id)
        .join(ModelVersion, ModelVersion.id == PredictionResult.model_version_id)
        .order_by(PredictionRequest.id)
        .limit(limite)
    ).all()
    return [
        {
            "demande_id": demande.id,
            "horodatage": demande.created_at.isoformat(timespec="seconds"),
            "compte": compte.username,
            # --- les entrees envoyees au modele ---
            "type_batiment": demande.building_type,
            "usage_principal": demande.primary_property_type,
            "quartier": demande.neighborhood,
            "surface_totale": demande.property_gfa_total,
            "surface_parking": demande.property_gfa_parking,
            "nb_etages": demande.number_of_floors,
            "nb_batiments": demande.number_of_buildings,
            "latitude": demande.latitude,
            "longitude": demande.longitude,
            "annee_construction": demande.year_built,
            "surface_usage_principal": demande.largest_property_use_gfa,
            "multi_usages": demande.is_multi_use,
            "electricite": demande.has_electricity,
            "gaz": demande.has_natural_gas,
            "vapeur": demande.has_steam,
            # --- les sorties produites par le modele ---
            "prediction_kbtu": resultat.predicted_kbtu,
            "prediction_log": resultat.predicted_log_value,
            "duree_ms": resultat.duration_ms,
            "reussi": resultat.succeeded,
            "version_modele": version.version,
        }
        for demande, resultat, compte, version in lignes
    ]


def sante_du_service(session: Session) -> list[dict]:
    """Temps de calcul et taux d'echec. Ce qu'on regarde pour surveiller le service."""
    total = session.scalar(select(func.count()).select_from(PredictionResult)) or 0
    echecs = (
        session.scalar(
            select(func.count()).select_from(PredictionResult).where(~PredictionResult.succeeded)
        )
        or 0
    )
    moyenne = session.scalar(select(func.avg(PredictionResult.duration_ms))) or 0
    return [
        {"indicateur": "appels enregistres", "valeur": total},
        {"indicateur": "appels en echec", "valeur": echecs},
        {"indicateur": "temps de calcul moyen (ms)", "valeur": round(float(moyenne), 2)},
    ]


def afficher(titre: str, lignes: list[dict]) -> None:
    print(f"\n=== {titre} ===")
    if not lignes:
        print("  (aucune ligne)")
        return
    colonnes = list(lignes[0])
    largeurs = {c: max(len(c), *(len(str(ligne[c])) for ligne in lignes)) for c in colonnes}
    print("  " + "  ".join(c.ljust(largeurs[c]) for c in colonnes))
    for ligne in lignes[:15]:
        print("  " + "  ".join(str(ligne[c]).ljust(largeurs[c]) for c in colonnes))
    if len(lignes) > 15:
        print(f"  ... et {len(lignes) - 15} autres lignes")


def exporter(lignes: list[dict], chemin: Path) -> None:
    if not lignes:
        return
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("w", newline="", encoding="utf-8") as fichier:
        redacteur = csv.DictWriter(fichier, fieldnames=list(lignes[0]))
        redacteur.writeheader()
        redacteur.writerows(lignes)
    print(f"  ecrit : {chemin} ({len(lignes)} lignes)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, help="dossier ou ecrire les fichiers CSV")
    args = parser.parse_args()

    with SessionLocal() as session:
        rapports = {
            "volumes_par_table": ("Volume de chaque table", volumes(session)),
            "consommation_par_usage": (
                "Consommation mesuree par usage",
                consommation_par_usage(session),
            ),
            "journal_des_appels": ("Journal des appels au modele", journal_des_appels(session)),
            "sante_du_service": ("Sante du service", sante_du_service(session)),
        }

    for titre, lignes in rapports.values():
        afficher(titre, lignes)

    if args.export:
        print(f"\n=== Export vers {args.export} ===")
        for nom, (_, lignes) in rapports.items():
            exporter(lignes, args.export / f"{nom}.csv")


if __name__ == "__main__":
    main()
