# Guide mentor : Projet 4, Deployez un modele de machine learning (Futurisys)

Suit la structure de la partie 2 de [METHODOLOGY.md](../ai-engineer/METHODOLOGY.md).
Premier projet d'**ingenierie** du parcours : il n'y a presque pas d'analyse de
donnees, le sujet est de transformer un modele de notebook en service de production.

Le modele deploye est celui du projet 2 (« Anticipez les besoins en consommation de
batiments »). L'enonce laissait le choix entre celui-la et le modele de classification
du projet 3.

---

## 1. Contexte metier

**Le probleme.** Futurisys veut rendre ses modeles utilisables par ses equipes et ses
clients. Un modele qui ne vit que dans un notebook n'a aucune valeur : il disparait a
la fermeture de Jupyter, personne d'autre ne peut l'appeler, et rien ne trace ce qu'il
a repondu.

**L'alternative evidente, et pourquoi on ne l'a pas prise.** On aurait pu livrer le
notebook et un fichier de modele, en demandant aux utilisateurs de lancer Python
eux-memes. Trois raisons de ne pas le faire : il faudrait installer les bonnes
versions sur chaque poste, chacun reecrirait sa propre preparation des donnees avec le
risque d'un ecart silencieux, et aucun appel ne serait trace.

**Ce que le service apporte.** Une adresse HTTP, une reponse en quelques
millisecondes, une seule version du code de preparation, et un journal complet des
appels.

---

## 2. Perimetre et nettoyage (chiffres exacts)

La chaine du projet 2 a ete rejouee **a l'identique** en code testable. Les comptes
sont verifies par un test qui echoue si un seul chiffre bouge :

| Etape | Critere | Avant | Apres |
|---|---|---:|---:|
| depart | releve 2016 brut | | 3 376 |
| 1 | hors logements (perimetre de la mission) | 3 376 | 1 668 |
| 2 | releve declare conforme par la ville | 1 668 | 1 548 |
| 3 | consommation renseignee et positive | 1 548 | 1 538 |
| 4 | au moins 1 etage | 1 538 | 1 523 |
| 5 | non signale aberrant par la ville | 1 523 | 1 523 |
| 6 | hors extremes (ecart interquartile a 1,5) | 1 523 | 1 508 |

**Valeur aberrante contre outlier.** Les etapes 3 et 4 retirent des valeurs *fausses* :
une consommation absente, un batiment de 0 etage. Aucun debat. L'etape 6 retire des
batiments *reels mais extremes*, et c'est un choix discutable, assume dans les limites.

L'etape 5 ne retire rien sur ce millesime. Elle est conservee parce que le code doit
tourner sur les autres annees du releve.

---

## 3. Valeurs manquantes

Aucune imputation dans ce projet, et c'est volontaire.

- **La cible** : les 10 batiments sans consommation mesuree sont supprimes, jamais
  imputes. Deviner la reponse qu'on cherche a apprendre revient a apprendre sa propre
  invention.
- **La surface de l'activite principale** : quand elle est absente, le ratio vaut 1,0.
  Ce n'est pas une imputation statistique mais une **regle metier** : pas de deuxieme
  usage renseigne signifie mono-usage.
- **Les colonnes d'energie** : une case vide signifie « pas de raccordement », pas une
  valeur perdue. Elle devient donc `false`, pas une moyenne.
- **Cote API** : une valeur manquante est refusee en 422 avant d'atteindre le modele.
  Le modele n'a pas d'etape d'imputation : il planterait.

---

## 4. Feature engineering

Trois colonnes calculees, reprises du projet 2 :

| Colonne | Calcul | Justification metier |
|---|---|---|
| `building_age` | 2016 moins l'annee de construction | l'isolation et les equipements datent de la construction |
| `largest_use_ratio` | surface de l'activite principale / surface totale | un batiment mono-usage se comporte autrement qu'un batiment mixte |
| `neighborhood_grouped` | 8 quartiers frequents, le reste en `AUTRE` | evite d'apprendre une regle sur 2 batiments |

**Le point d'ingenierie, et c'est le coeur du projet.** Ces trois calculs vivent dans
un seul fichier, `ml/features.py`, importe a la fois par l'entrainement et par l'API.

C'est le bug classique du deploiement : on recode la preparation dans l'API, avec un
detail different (l'age compte a partir de l'annee courante au lieu de 2016), et le
modele repond quand meme, sans la moindre erreur, avec des chiffres faux. Huit tests
unitaires figent ces fonctions.

**Redondance verifiee** : `YearBuilt` et `LargestPropertyUseTypeGFA` sont supprimees
apres avoir servi aux calculs, sinon la meme information serait donnee deux fois.

---

## 5. Data leakage

Quatorze colonnes retirees : les consommations mesurees par energie, les intensites
energetiques (consommation / surface), les emissions de gaz a effet de serre qui en
decoulent, et le score ENERGY STAR, calcule a partir de la consommation.

Le reflexe applique a chaque colonne : *est-ce que je connaitrais cette information
avant d'avoir mesure la consommation ?*

**Le cas discutable, a savoir defendre.** `has_electricity`, `has_natural_gas` et
`has_steam` sont derivees de ces memes colonnes de consommation. Elles ont ete
gardees parce qu'elles lisent la **presence d'un raccordement**, pas une quantite : un
exploitant sait avant toute mesure si son batiment est relie au gaz.

Si le mentor pousse : c'est un choix, pas une evidence. L'alternative serait de les
retirer aussi. Le cout serait un modele moins bon, le raccordement au gaz etant la
septieme variable la plus importante. Un test verifie qu'aucune colonne de la liste de
leakage ne survit au nettoyage.

---

## 6. Encodage et normalisation

| Traitement | Colonnes | Pourquoi celui-la |
|---|---|---|
| `StandardScaler` | les 8 numeriques | des surfaces en centaines de milliers et une latitude autour de 47 ne pesent pas pareil |
| `OneHotEncoder` | type, usage, quartier | categories **sans ordre** : numeroter un entrepot 1 et un hopital 2 ferait croire a un classement |
| `passthrough` | les 4 binaires | deja en 0/1, rien a faire |

**Une question probable du mentor** : un Random Forest n'a pas besoin de
normalisation, il compare des seuils, pas des distances. Vrai. Le `StandardScaler` est
conserve pour deux raisons : la comparaison du projet 2 incluait une regression
lineaire et un SVR, qui en ont besoin, et tous les modeles devaient recevoir
exactement le meme traitement pour que la comparaison ait un sens. Le garder ne coute
rien et permet de changer de famille de modele sans retoucher la chaine.

`handle_unknown="ignore"` sur l'encodeur : un type de batiment jamais vu donne des
zeros au lieu de faire tomber l'API en production.

---

## 7. Choix et comparaison des modeles

Repris du projet 2, quatre modeles evalues de la meme facon (meme decoupage, memes
metriques) :

| Modele | R2 en validation croisee |
|---|---:|
| Dummy (predit toujours la moyenne) | -0,006 |
| Regression lineaire | 0,571 |
| SVR | 0,651 |
| **Random Forest** | **0,686** |

**Justification par la nature des donnees, pas par le score.** La relation entre
surface et consommation n'est pas une droite : doubler la surface d'un entrepot et
doubler celle d'un hopital n'ont pas le meme effet. La regression lineaire ne peut pas
representer cela, le Random Forest si, en decoupant l'espace par seuils successifs.

Sa faiblesse est d'etre une boite noire. Acceptable ici : le client veut une
estimation chiffree, pas une explication.

**Verification independante.** Les hyperparametres sont figes dans le code pour que
l'entrainement prenne quinze secondes en integration continue plutot que plusieurs
minutes. Ils ne sont pas recopies a l'aveugle : la recherche complete (324
combinaisons, 1 620 entrainements) a ete rejouee dans ce projet et retrouve exactement
les memes reglages et les memes scores. Un test verifie que chaque valeur figee
appartient bien a la grille testee.

---

## 8. Methodologie d'evaluation

Le protocole 80/20 du projet 2, conserve tel quel :

- 1 206 batiments pour apprendre et regler, 302 mis au coffre avant tout entrainement.
- La validation croisee a 5 decoupages tourne **uniquement** sur les 1 206.
- Le coffre n'est ouvert qu'une fois, a la fin.

| | |
|---|---:|
| R2 en validation croisee | 0,690 |
| R2 sur le coffre | 0,709 |
| Ecart | 0,019 |

L'ecart tres faible montre l'absence d'apprentissage par coeur. Un test echoue si cet
ecart depasse 0,05.

**Ce que ce projet ajoute.** L'evaluation n'est plus un resultat de notebook : elle est
rejouee a chaque envoi de code par l'integration continue, et un test echoue si le R2
s'ecarte de 0,709 de plus de 0,005. Un modele qui se degraderait sans que personne ne
le remarque est le risque principal d'un service de machine learning.

---

## 9. Choix de metrique

| Metrique | Valeur | A quoi elle sert |
|---|---:|---|
| R2 | 0,709 | **choisir** entre modeles : sans unite, donc comparable |
| MAE en logarithme | 0,482 | l'erreur sur l'echelle d'apprentissage |
| Erreur relative mediane | 36 % | **decider si on s'en sert** : la seule que le client comprend |

Deux metriques minimum, jamais une seule : une pour comparer, une pour interpreter.

La mediane et non la moyenne pour l'erreur relative : quelques gros ecarts tirent la
moyenne vers le haut et donnent une image fausse du cas courant.

**Traduction pour Aurelien** : sur un batiment courant, l'estimation s'ecarte d'environ
un tiers de la mesure reelle. Assez pour classer un parc et reperer les batiments a
auditer en priorite. Pas assez pour facturer.

---

## 10. Interpretation du modele

`feature_importances_` du Random Forest, calculee pendant l'entrainement :

| Variable | Part |
|---|---:|
| Surface totale | 63 % |
| Latitude | 5 % |
| Longitude | 4 % |
| Age du batiment | 4 % |
| Usage supermarche | 3 % |
| Usage entrepot | 3 % |
| Raccordement au gaz | 3 % |

**Importance n'est pas causalite.** La latitude ne fait rien consommer. Elle sert de
raccourci au modele pour reperer les quartiers d'affaires, ou se trouvent les grandes
tours. Dire « la latitude influence la consommation » serait faux.

La domination de la surface (63 %) est coherente avec le metier et rassurante : le
modele a appris ce qu'un thermicien aurait dit en premier.

---

## 11. Limites et risques

**Le modele.**
- Il ne connait que Seattle et seulement 2016. L'API refuse toute coordonnee hors de
  l'emprise de la ville, plutot que de repondre un chiffre fabrique.
- Il plafonne sur les batiments hors norme : les 15 plus gros consommateurs ont ete
  retires a l'etape 6. Face a un grand campus hospitalier, il ne saura pas extrapoler
  et repondra une valeur proche du maximum qu'il connait. C'est la contrepartie
  assumee d'un modele plus stable sur les cas courants.
- Il vieillit. Les renovations energetiques menees depuis 2016 ne sont pas dans ses
  donnees : sur un batiment renove, il surestime.

**Le service.**
- SQLite en production de demonstration, pas PostgreSQL : l'hebergement gratuit ne
  permet pas d'en faire tourner un a cote. L'enonce autorise explicitement une base
  locale. Le code ne voit pas la difference, c'est l'ORM qui traduit.
- Pas de limitation du nombre d'appels par compte : un client pourrait saturer le
  service.
- Jetons valables une heure sans mecanisme de rafraichissement : il faut se
  reconnecter.
- Le modele est charge en memoire une seule fois. Le remplacer demande un redemarrage.

---

## 12. Communication

**En une phrase.** Le modele du projet precedent est devenu un service que n'importe
qui peut appeler, dont chaque reponse est tracee, et dont la mise a jour est
automatisee.

**Le verdict.** Ca marche, sous condition. Le service est fonctionnel de bout en bout,
teste a 99 %, et se deploie tout seul. La condition tient au modele, pas au service :
36 % d'erreur mediane conviennent pour prioriser des audits, pas pour facturer.

**Les chiffres a retenir.**

| | |
|---|---:|
| Batiments d'entrainement | 1 508 |
| Colonnes vues par le modele | 15 |
| R2 sur donnees jamais vues | 0,709 |
| Erreur relative mediane | 36 % |
| Temps de reponse de l'API | environ 10 ms |
| Tests | 143 |
| Couverture | 98 % |

---

## Questions probables du mentor, reponses courtes

**Quels defis avez-vous rencontres avec FastAPI ?**
Le principal n'etait pas FastAPI mais l'ecart entre le notebook et la production. Le
modele repond en logarithme : renvoye tel quel, le client recevait 16,7 au lieu de
17 500 000. Un nombre qui ressemble a une reponse valide, et faux d'un facteur d'un
million. C'est teste explicitement. Le deuxieme point etait les trois colonnes
calculees : je les ai mises dans un fichier unique partage par l'entrainement et
l'API, plutot que de les recoder des deux cotes.

**Pourquoi FastAPI plutot que Flask ou Django ?**
La validation des entrees. Avec Pydantic, les 15 champs et leurs bornes sont declares
une fois et servent a trois choses : refuser les mauvaises donnees, generer la
documentation Swagger, et documenter les types dans le code. Avec Flask il aurait
fallu ecrire les trois separement. Django est surdimensionne pour une API sans
interface.

**Quelle est votre strategie de tests ?**
Trois couches. Les tests unitaires figent les fonctions dont une derive serait
silencieuse : les colonnes calculees et la conversion logarithme. Les tests
fonctionnels parcourent l'API de la connexion a la trace en base. Les tests d'erreur
simulent les pannes : modele absent, base injoignable, prediction qui echoue.
Le seuil de 90 % de couverture est verifie par la CI, qui refuse la fusion en dessous.

**Comment savez-vous que votre couverture est suffisante ?**
Elle ne l'est pas par son pourcentage. 98 % de lignes executees ne dit pas que les bons
cas sont testes. Ce qui compte est la liste des scenarios : chaque borne de validation
a son test, chaque code d'erreur a le sien, et le chemin d'echec du modele est verifie
jusqu'a la ligne ecrite en base.

**Comment avez-vous gere la base et son integration avec le modele ?**
Le modele n'est jamais appele en direct. La demande est ecrite en base, puis le modele
est interroge, puis le resultat est ecrit. Cet ordre est volontaire : en ecrivant
apres, on perdrait exactement les appels qui echouent. J'ai separe demandes et
resultats en deux tables pour la meme raison : un echec laisse une ligne avec son
message d'erreur au lieu de disparaitre.

**Pourquoi une table des versions du modele ?**
Une prediction gardee six mois serait inexplicable sans elle : on ne saurait plus quel
modele l'a produite ni ce qu'il valait. Chaque resultat pointe vers sa version, avec
son R2 et sa date d'entrainement.

**Pourquoi PostgreSQL et pas SQLite partout ?**
SQLite n'applique pas les cles etrangeres par defaut. Mes tests sur les contraintes
passaient a tort jusqu'a ce que je force le reglage : ils donnaient une fausse
assurance. La CI tourne sur un vrai PostgreSQL 16, la meme version qu'en local.

**Comment gerez-vous les secrets ?**
Trois endroits, aucun dans le code. Un fichier `.env` en developpement, jamais
versionne. Des valeurs jetables regenerees a chaque execution en CI. Des secrets
GitHub chiffres pour la production. Le mot de passe de la base est meme masque dans
les journaux de demarrage, pour qu'il ne finisse pas dans les logs du serveur.

**Pourquoi les hyperparametres sont-ils ecrits en dur ?**
Pour que la CI reentraine en quinze secondes au lieu de plusieurs minutes. Mais ils ne
sont pas recopies a l'aveugle : j'ai rejoue la recherche complete, 324 combinaisons,
et elle retrouve exactement les memes valeurs. Un test verifie en plus que chaque
valeur figee fait bien partie de la grille testee. `--full-grid` rejoue la recherche.

**Pourquoi ne pas versionner le modele dans Git ?**
C'est un produit du code, pas du code. 11 Mo qui changeraient a chaque reentrainement
et gonfleraient l'historique. La CI et le deploiement le reconstruisent depuis les
donnees brutes, ce qui prouve au passage que la chaine complete tourne encore.

**Pourquoi un tag pour deployer, et pas chaque commit sur main ?**
Deployer a chaque commit mettrait en ligne du travail en cours. Le tag est la decision
explicite de publier, et il donne un point de retour en arriere identifiable.

**Que feriez-vous avant une vraie mise en production ?**
Une limitation du nombre d'appels par compte, HTTPS obligatoire, des jetons de
rafraichissement plutot qu'une reconnexion toutes les heures, une journalisation
envoyee vers un collecteur externe, et un vrai PostgreSQL heberge. Et une alerte sur
la derive du modele : aujourd'hui je peux la mesurer en base, mais personne n'est
prevenu automatiquement.
