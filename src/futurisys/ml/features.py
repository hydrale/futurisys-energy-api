"""Les 3 colonnes que le modele attend mais qui n'existent pas dans le fichier source.

Elles sont calculees ici, et nulle part ailleurs. C'est volontaire : l'entrainement et
l'API doivent appliquer exactement le meme calcul, sinon le modele recoit a l'usage des
valeurs construites autrement qu'a l'apprentissage et se trompe sans qu'aucune erreur
ne soit levee. Une seule fonction partagee rend cet ecart impossible.
"""

from __future__ import annotations

import pandas as pd

# Le releve de Seattle porte sur l'annee 2016 : l'age d'un batiment est donc compte
# par rapport a 2016, pas par rapport a l'annee courante. Utiliser l'annee courante
# vieillirait tout le parc de plusieurs annees par rapport a ce que le modele a appris.
REFERENCE_YEAR = 2016

# Valeur donnee aux quartiers rares. Les quartiers trop peu representes sont regroupes
# sous cette etiquette pour eviter de creer des colonnes qui ne concerneraient que
# quelques batiments (voir group_neighborhood).
OTHER_NEIGHBORHOOD = "AUTRE"


def compute_building_age(year_built: pd.Series | int) -> pd.Series | int:
    """Age du batiment en 2016."""
    return REFERENCE_YEAR - year_built


def compute_largest_use_ratio(
    largest_use_gfa: pd.Series,
    property_gfa_total: pd.Series,
) -> pd.Series:
    """Part de la surface occupee par l'activite principale, entre 0 et 1.

    Un entrepot pur vaut 1,0 ; une tour qui melange bureaux et commerces vaut 0,6.
    Le plafond a 1,0 traite les quelques lignes ou la surface declaree de l'activite
    depasse la surface totale du batiment (saisie incoherente de la ville) : sans lui,
    ces batiments passeraient au modele un ratio de 1,3 qu'il n'a jamais vu.
    Un ratio manquant vaut 1,0 : pas de deuxieme usage renseigne = mono-usage.
    """
    # astype(float) avant fillna : quand la surface de l'activite est absente, pandas
    # produit une colonne de type objet, et remplir un objet declenche une conversion
    # implicite que pandas signale comme depreciee. On fixe le type nous-memes.
    ratio = (largest_use_gfa / property_gfa_total).astype(float)
    return ratio.clip(upper=1.0).fillna(1.0)


def group_neighborhood(
    neighborhood: pd.Series,
    kept_neighborhoods: list[str],
) -> pd.Series:
    """Ramene le quartier a l'un des quartiers frequents, ou a AUTRE.

    Seattle compte une cinquantaine de quartiers, dont beaucoup n'ont que 2 ou 3
    batiments dans le jeu de donnees. Leur laisser chacun sa colonne apprendrait au
    modele des regles tirees de 2 batiments, qui ne tiendront pas sur de nouveaux cas.
    Le passage en majuscules corrige les memes quartiers ecrits differemment
    ("Downtown" et "DOWNTOWN" comptaient pour deux quartiers distincts).
    """
    normalized = neighborhood.str.upper()
    return normalized.where(normalized.isin(kept_neighborhoods), OTHER_NEIGHBORHOOD)
