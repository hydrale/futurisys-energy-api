# Fiche du modele

## Ce qu'il fait

Il estime la consommation energetique annuelle d'un batiment non residentiel de
Seattle, a partir de son descriptif : surface, usage, annee de construction, quartier,
energies raccordees. Aucune mesure sur site n'est necessaire.

Le probleme metier vient du projet precedent : la ville veut connaitre la consommation
de son parc sans envoyer un releveur dans chaque batiment. Relever coute cher et prend
des mois ; un modele donne une estimation immediate a partir de donnees deja
declarees au cadastre.

## Les donnees

Le releve energetique 2016 de la ville de Seattle, 3 376 batiments au depart.
Six filtres successifs en gardent 1 508 :

| Etape | Ce qu'elle retire | Reste |
|---:|---|---:|
| depart | | 3 376 |
| 1 | les logements, hors perimetre de la mission | 1 668 |
| 2 | les releves que la ville declare non conformes | 1 548 |
| 3 | les batiments sans consommation mesuree | 1 538 |
| 4 | les batiments de 0 etage, physiquement impossibles | 1 523 |
| 5 | les batiments signales aberrants par la ville | 1 523 |
| 6 | les extremes restants (ecart interquartile a 1,5) | 1 508 |

L'etape 5 ne retire rien sur ce millesime : la ville n'avait signale aucun batiment
parmi ceux deja retenus. Elle est conservee parce que le code doit tourner sur les
autres annees du releve.

**Aberrant contre extreme.** Les etapes 3 et 4 retirent des valeurs fausses : une
consommation absente, un batiment sans etage. Aucun debat. L'etape 6 retire des
batiments reels mais hors norme, et c'est un choix : voir les limites.

## La cible

`SiteEnergyUseWN(kBtu)`, la consommation totale du site corrigee de la meteo. La
correction compte : un hiver froid fait monter la consommation de tous les batiments
en meme temps, et sans elle le modele apprendrait la meteo de 2016 plutot que les
proprietes des batiments.

Le modele n'apprend pas cette valeur directement mais son **logarithme**. Un entrepot
consomme 200 000 kBtu, un hopital 400 millions. Sur l'echelle brute, l'erreur commise
sur l'hopital ecrase tout le reste et le modele finit par ne s'occuper que des geants.
Le logarithme ramene ces ecarts a la meme echelle : l'asymetrie de la distribution
passe de 3,57 a 0,24.

**Consequence directe pour l'API** : le modele repond en logarithme. L'API applique
`expm1`, l'operation inverse, pour rendre des kBtu. Sans cette conversion, un client
recevrait `16,7` au lieu de `17 500 000`.

## Les 15 colonnes vues par le modele

| Traitement | Colonnes |
|---|---|
| Normalisees (StandardScaler) | surface totale, surface parking, nombre d'etages, nombre de batiments, latitude, longitude, age du batiment, part de l'usage principal |
| Encodees en 0/1 par categorie (OneHotEncoder) | type de batiment, usage principal, quartier regroupe |
| Deja en 0/1 | multi-usages, electricite, gaz naturel, vapeur |

Trois de ces colonnes n'existent pas dans le fichier source et sont **calculees** :

- **age du batiment** = 2016 moins l'annee de construction. 2016 et non l'annee
  courante : le releve porte sur 2016, utiliser la date du jour vieillirait tout le
  parc par rapport a ce que le modele a appris.
- **part de l'usage principal** = surface de l'activite principale divisee par la
  surface totale, plafonnee a 1. Un entrepot pur vaut 1,0 ; une tour qui melange
  bureaux et commerces vaut 0,6.
- **quartier regroupe** : les 8 quartiers les plus representes gardent leur nom, les
  autres deviennent `AUTRE`. Seattle compte une cinquantaine de quartiers, dont
  beaucoup n'ont que deux ou trois batiments : leur laisser une colonne apprendrait au
  modele des regles tirees de deux batiments.

Ces trois calculs vivent dans un seul fichier, `ml/features.py`, utilise a la fois par
l'entrainement et par l'API. Les dupliquer serait le bug classique du deploiement :
un ecart entre les deux ne provoque aucune erreur, seulement des predictions fausses.

## Le data leakage, et ce qui a ete retire

Une colonne fait du leakage quand elle contient deja la reponse, ou qu'elle ne serait
connue qu'apres avoir mesure ce qu'on cherche a predire. Quatorze colonnes ont ete
retirees a ce titre : les consommations mesurees par energie, les intensites
energetiques (consommation divisee par la surface), les emissions de gaz a effet de
serre qui en decoulent, et le score ENERGY STAR, lui-meme calcule a partir de la
consommation.

**Le cas discutable, a savoir defendre.** Les colonnes `has_electricity`,
`has_natural_gas` et `has_steam` sont derivees de ces memes consommations. Elles ont
ete conservees parce qu'elles lisent la *presence d'un raccordement*, pas une
quantite : un exploitant sait avant toute mesure si son batiment est relie au gaz ou
au reseau de vapeur urbain. C'est un choix, pas une evidence. L'alternative serait de
les retirer aussi, au prix d'un modele moins bon (le raccordement au gaz est la
septieme variable la plus importante).

## Le modele retenu

`RandomForestRegressor`, choisi contre trois concurrents evalues exactement de la
meme facon (meme decoupage, memes metriques) :

| Modele | R2 en validation croisee | Lecture |
|---|---:|---|
| Dummy (predit toujours la moyenne) | -0,006 | le seuil minimum a battre |
| Regression lineaire | 0,571 | suppose une relation en ligne droite |
| SVR | 0,651 | plus souple, mais plus lent et opaque |
| **Random Forest** | **0,686** | capture les relations non lineaires |

Le Random Forest gagne parce que la relation entre surface et consommation n'est pas
une droite : doubler la surface d'un entrepot et doubler celle d'un hopital n'ont pas
le meme effet. La regression lineaire ne peut pas representer cela, le Random Forest
si, en decoupant l'espace par seuils successifs.

Son defaut est de rester une boite noire, moins interpretable qu'une droite. C'est
acceptable ici : l'usage est une estimation chiffree, pas une explication.

**Reglages retenus**, issus d'une recherche sur 324 combinaisons evaluees sur
5 decoupages, soit 1 620 entrainements :

```
n_estimators = 400, max_depth = 20, min_samples_leaf = 1,
min_samples_split = 2, max_features = None
```

## Les scores

| Metrique | Valeur | Ce qu'elle dit |
|---|---:|---|
| R2 en validation croisee (1 206 batiments) | 0,690 | part de la variation expliquee, pour comparer les modeles |
| R2 sur les 302 batiments jamais vus | 0,709 | le score honnete, sur des donnees mises de cote avant tout entrainement |
| Ecart entre les deux | 0,019 | tres faible : le modele n'a pas appris par coeur |
| MAE en logarithme | 0,482 | l'erreur moyenne sur l'echelle d'apprentissage |
| Erreur relative mediane | 36 % | ce que le client comprend : sur un batiment courant, l'estimation s'ecarte d'environ un tiers |

Les deux dernieres lignes disent la meme chose autrement, et les deux sont
necessaires : le R2 sert a **choisir** un modele, l'erreur en pourcentage sert a
**decider si on s'en sert**.

## Ce qui compte le plus dans la prediction

La surface totale, et de tres loin : elle porte 63 % des decisions du modele.
Viennent ensuite la position geographique (latitude 5 %, longitude 4 %), l'age du
batiment (4 %), puis certains usages (supermarche, entrepot).

**Important** : cela dit quelle variable pese le plus dans les decisions du modele,
pas quelle variable *cause* la consommation. La latitude ne fait rien consommer ; elle
sert de raccourci au modele pour reperer les quartiers d'affaires, ou se trouvent les
grandes tours.

## Les limites, et ou le modele est le moins fiable

**Il ne connait que Seattle, et seulement 2016.** Un batiment ailleurs, ou une annee
avec un parc renove, sortent de son domaine. L'API refuse d'ailleurs toute coordonnee
hors de l'emprise de Seattle.

**Il plafonne sur les batiments hors norme.** L'etape 6 du nettoyage a retire les
15 batiments les plus consommateurs. Le modele ne les a jamais vus : face a un grand
campus hospitalier, il ne saura pas extrapoler et repondra une valeur proche du
maximum qu'il connait. C'est la contrepartie assumee d'un modele plus stable sur les
cas courants.

**Une erreur mediane de 36 % reste importante.** Le service convient pour classer un
parc, reperer les batiments a auditer en priorite, ou estimer un ordre de grandeur.
Il ne convient pas pour facturer, ni pour verifier un engagement contractuel.

**Il vieillit.** Il a appris sur des batiments de 2016. Les renovations energetiques
menees depuis ne sont pas dans ses donnees : sur un batiment renove, il surestimera.
Un reentrainement sur un releve plus recent est le premier chantier de maintenance.
