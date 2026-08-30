# Futurisys : API de prediction de consommation energetique

Service qui estime la consommation energetique annuelle d'un batiment non residentiel
de Seattle a partir de son descriptif, sans aucune mesure sur site.

Le modele vient du projet precedent du parcours (« Anticipez les besoins en
consommation de batiments »). Ce depot le transforme en service de production :
une API, une base de donnees, des tests, et une mise en ligne automatisee.

| | |
|---|---|
| **Modele** | Random Forest, 400 arbres, entraine sur 1 508 batiments |
| **Qualite** | R2 de 0,709 sur 302 batiments jamais vus, erreur mediane de 36 % |
| **API** | FastAPI, documentation interactive sur `/docs` |
| **Base** | PostgreSQL 16, 5 tables, chaque appel trace |
| **Tests** | 146 tests Pytest, 98 % de couverture |
| **Livraison** | Image Docker publique, publiee et verifiee a chaque version |

---

## Sommaire

- [Demarrage rapide](#demarrage-rapide)
- [Ce que fait le service](#ce-que-fait-le-service)
- [Installation detaillee](#installation-detaillee)
- [Utilisation de l'API](#utilisation-de-lapi)
- [Structure du depot](#structure-du-depot)
- [Base de donnees](#base-de-donnees)
- [Authentification et securite](#authentification-et-securite)
- [Tests](#tests)
- [Integration et livraison continues](#integration-et-livraison-continues)
- [Deploiement](#deploiement)
- [Conventions Git](#conventions-git)
- [Maintenance](#maintenance)

---

## Demarrage rapide

Trois commandes, environ deux minutes. Prerequis : Python 3.11 et Docker.

```bash
git clone https://github.com/hydrale/futurisys-energy-api.git
cd futurisys-energy-api
cp .env.example .env
```

Ouvrir `.env` et remplacer `SECRET_KEY` et `ADMIN_PASSWORD` par des valeurs a soi.
Pour la cle :

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Puis :

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d
PYTHONPATH=src python -m futurisys.ml.train
PYTHONPATH=src python -m futurisys.db.create_db
PYTHONPATH=src uvicorn futurisys.api.main:app --reload
```

La documentation interactive est sur <http://localhost:8000/docs>.

**Encore plus court**, tout dans Docker, sans installer Python :

```bash
docker build -t futurisys-api .
docker run -p 8000:7860 -e DATABASE_URL=sqlite:////tmp/db.sqlite \
  -e SECRET_KEY=une-cle-a-vous -e ADMIN_PASSWORD=un-mot-de-passe-a-vous \
  futurisys-api
```

L'API cree ses tables et insere les 1 508 batiments toute seule au demarrage.

---

## Ce que fait le service

**Le probleme.** La ville de Seattle veut connaitre la consommation de son parc
tertiaire. Envoyer un releveur dans chaque batiment coute cher et prend des mois.

**La solution.** Un modele estime la consommation a partir de donnees deja declarees
(surface, usage, annee de construction, quartier, energies raccordees). La reponse est
immediate.

**Ce qu'il faut savoir avant de s'en servir.** L'estimation s'ecarte de la mesure
reelle d'environ 36 % sur un batiment courant. C'est suffisant pour classer un parc et
reperer les batiments a auditer en priorite. Ce n'est pas suffisant pour facturer.

Le detail du modele, de ses scores et de ses limites : [`docs/modele.md`](docs/modele.md).

---

## Installation detaillee

### Prerequis

| Outil | Version | Pourquoi |
|---|---|---|
| Python | 3.11 | Version utilisee en CI et dans l'image de production |
| Docker | recent | Fait tourner PostgreSQL sans l'installer sur la machine |
| Git | recent | |

### 1. Environnement Python

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
```

`requirements.txt` contient ce qui est necessaire pour faire tourner le service.
`requirements-dev.txt` ajoute les outils de test et de qualite de code, jamais
installes dans l'image de production.

Les versions sont figees. Le modele est un objet serialise par scikit-learn : une
version differente au chargement peut casser la lecture du fichier ou changer les
predictions sans prevenir.

### 2. Configuration

```bash
cp .env.example .env
```

| Variable | Role | A changer |
|---|---|---|
| `APP_ENV` | `dev`, `test` ou `prod` | selon l'usage |
| `DATABASE_URL` | adresse de la base | si le port 5432 est pris |
| `SECRET_KEY` | signe les jetons d'acces | **oui, toujours** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | duree de validite d'un jeton | non |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | compte cree au premier demarrage | **oui, toujours** |
| `AUTO_INIT_DB` | prepare la base au demarrage | non |

`.env` est dans `.gitignore` et n'est jamais versionne.

### 3. Base de donnees

```bash
docker compose up -d
docker compose ps        # attendre l'etat "healthy"
```

PostgreSQL tourne dans un conteneur plutot qu'installe sur la machine : il s'allume et
s'eteint en une commande, la version est la meme pour tout le monde, et c'est la meme
image que celle utilisee par les tests automatiques.

### 4. Entrainement du modele

```bash
PYTHONPATH=src python -m futurisys.ml.train
```

Rejoue toute la chaine depuis le fichier brut : 3 376 batiments filtres en 1 508,
entrainement, evaluation, et ecriture de `models/energy_model.joblib` (11 Mo).
Environ quinze secondes.

Pour refaire la recherche complete d'hyperparametres (324 combinaisons, plusieurs
minutes) :

```bash
PYTHONPATH=src python -m futurisys.ml.train --full-grid
```

### 5. Creation de la base

```bash
PYTHONPATH=src python -m futurisys.db.create_db
```

Cree les 5 tables, insere les 1 508 batiments, cree le compte administrateur du
fichier `.env` et enregistre la version du modele. La commande est rejouable : sur une
base deja remplie, elle ne fait rien. Pour repartir de zero : `--reset`.

### 6. Lancement

```bash
PYTHONPATH=src uvicorn futurisys.api.main:app --reload
```

---

## Utilisation de l'API

### Les endpoints

| Methode | Chemin | Acces | Role |
|---|---|---|---|
| `GET` | `/health` | libre | etat du service, de la base et du modele |
| `POST` | `/auth/token` | libre | se connecter, obtenir un jeton |
| `GET` | `/auth/me` | connecte | le compte courant |
| `POST` | `/auth/users` | administrateur | creer un compte |
| `GET` | `/model` | connecte | fiche du modele : scores, reglages, valeurs acceptees |
| `POST` | `/predictions` | connecte | estimer un batiment decrit de zero |
| `POST` | `/predictions/buildings/{id}` | connecte | estimer un batiment de la base, compare a la mesure reelle |
| `GET` | `/predictions` | connecte | ses propres predictions passees |
| `GET` | `/predictions/{id}` | connecte | relire une prediction |
| `GET` | `/buildings` | connecte | lister et filtrer les 1 508 batiments |
| `GET` | `/buildings/{id}` | connecte | consulter un batiment |

La documentation complete, avec les schemas de donnees et un bouton pour essayer
chaque endpoint, est generee automatiquement sur `/docs` (Swagger) et `/redoc`.

### Exemple complet

**Se connecter.** Le formulaire est envoye en `x-www-form-urlencoded`, comme l'impose
la norme OAuth2 :

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -d 'username=admin&password=votre-mot-de-passe' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
```

**Estimer un batiment :**

```bash
curl -X POST http://localhost:8000/predictions \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "building_type": "NonResidential",
    "primary_property_type": "Large Office",
    "neighborhood": "DOWNTOWN",
    "property_gfa_total": 250000,
    "property_gfa_parking": 30000,
    "number_of_floors": 12,
    "number_of_buildings": 1,
    "latitude": 47.6101,
    "longitude": -122.3344,
    "year_built": 1985,
    "largest_property_use_gfa": 220000,
    "is_multi_use": true,
    "has_electricity": true,
    "has_natural_gas": true,
    "has_steam": false
  }'
```

Reponse :

```json
{
  "request_id": 1,
  "predicted_kbtu": 17272108.9,
  "predicted_log_value": 16.664604,
  "model_version": "1.0.0",
  "duration_ms": 12.97,
  "created_at": "2026-08-30T16:35:36Z"
}
```

`predicted_kbtu` est la reponse a lire. `predicted_log_value` est la sortie brute du
modele, fournie pour pouvoir rejouer le calcul.

**Comparer a un batiment reel :**

```bash
curl -X POST http://localhost:8000/predictions/buildings/60 -H "Authorization: Bearer $TOKEN"
```

Ajoute `actual_kbtu` (la consommation mesuree en 2016) et `relative_error` a la
reponse. Utile pour se faire une idee concrete de la fiabilite.

### Les valeurs acceptees

L'API refuse une demande hors bornes avec un code 422 et la liste des champs fautifs,
avant meme d'appeler le modele. Ces bornes viennent des batiments d'entrainement,
elargies d'une marge : au-dela, le modele extrapole et sa reponse n'a plus de valeur.

| Champ | Borne | Pourquoi |
|---|---|---|
| `property_gfa_total` | > 0 et <= 4 000 000 | le double du plus grand batiment observe |
| `property_gfa_parking` | >= 0 | 0 est valide : beaucoup de batiments n'ont pas de parking |
| `number_of_floors` | > 0 | les batiments de 0 etage ont ete ecartes a l'entrainement |
| `latitude` | 47,45 a 47,79 | l'emprise de Seattle |
| `longitude` | -122,47 a -122,20 | idem |
| `year_built` | 1850 a 2016 | le releve porte sur 2016 |

`GET /model` renvoie la liste exacte des types de batiments, usages et quartiers
connus du modele.

### Les codes de reponse

| Code | Signification |
|---|---|
| `200` / `201` | tout va bien |
| `401` | jeton absent, invalide ou expire |
| `403` | jeton valide, mais droits insuffisants (endpoint reserve aux administrateurs) |
| `404` | ressource introuvable |
| `409` | nom d'utilisateur deja pris |
| `422` | donnee refusee par la validation, avec le detail des champs |
| `500` | la prediction a echoue ; l'incident est enregistre en base |
| `503` | le modele n'est pas charge : lancer l'entrainement |

---

## Structure du depot

```
futurisys-energy-api/
├── .github/workflows/
│   ├── ci.yml                    tests, qualite, image, a chaque envoi
│   └── deploy.yml                mise en ligne, sur un tag de version
├── data/
│   └── building_energy_2016.csv  le releve brut de Seattle, 3 376 batiments
├── docs/
│   ├── modele.md                 fiche du modele : donnees, scores, limites
│   └── schema_base_de_donnees.md schema UML et choix de conception
├── models/                       le modele entraine (produit, non versionne)
├── src/futurisys/
│   ├── config.py                 reglages, lus dans l'environnement
│   ├── api/
│   │   ├── main.py               assemblage, /health, /model
│   │   ├── schemas.py            formats d'entree/sortie et validation
│   │   ├── security.py           mots de passe et jetons
│   │   └── routes/               auth, predictions, buildings
│   ├── db/
│   │   ├── models.py             les 5 tables
│   │   ├── session.py            connexions
│   │   └── create_db.py          creation et remplissage
│   └── ml/
│       ├── features.py           les 3 colonnes calculees
│       ├── preparation.py        la chaine de nettoyage
│       ├── train.py              entrainement et sauvegarde
│       └── predictor.py          chargement et prediction
├── scripts/
│   ├── configurer_le_deploiement.sh   secrets et premiere mise en ligne
│   ├── deployer_sur_hugging_face.py   envoi du code vers le Space
│   └── interroger_base.py             consultation et export des donnees
├── tests/                        146 tests
├── Dockerfile                    image de production
├── docker-compose.yml            PostgreSQL local
└── requirements.txt              dependances figees
```

Rien a la racine sauf la configuration. Le code applicatif est sous `src/`, ce qui
evite qu'un import fonctionne par accident depuis le dossier courant et echoue une
fois le paquet installe.

**La separation qui compte** : `ml/features.py` est utilise a la fois par
l'entrainement et par l'API. Un ecart entre les deux ne provoquerait aucune erreur,
seulement des predictions fausses.

---

## Base de donnees

Cinq tables. Le schema complet, les contraintes et les index sont dans
[`docs/schema_base_de_donnees.md`](docs/schema_base_de_donnees.md).

```
users  1──N  prediction_requests  1──1  prediction_results  N──1  model_versions
buildings  1──N  prediction_requests   (lien facultatif)
```

**Le principe** : le modele n'est jamais appele en direct. Chaque appel ecrit une
demande, puis interroge le modele, puis ecrit un resultat. Un echec du modele laisse
une ligne avec son message d'erreur, au lieu de disparaitre.

**Interroger la base directement :**

```bash
docker exec -it futurisys-db psql -U futurisys -d futurisys
```

```sql
-- Le journal des appels, avec leur reponse
SELECT q.id, u.username, q.primary_property_type,
       round(r.predicted_kbtu::numeric) AS predit,
       round(r.duration_ms::numeric, 1) AS ms, m.version
FROM prediction_requests q
JOIN prediction_results r ON r.request_id = q.id
JOIN users u ON u.id = q.user_id
JOIN model_versions m ON m.id = r.model_version_id
ORDER BY q.created_at DESC LIMIT 20;

-- Consommation moyenne mesuree, par usage
SELECT primary_property_type, count(*) AS batiments,
       round(avg(site_energy_use_wn_kbtu)::numeric) AS moyenne_kbtu
FROM buildings GROUP BY 1 ORDER BY 3 DESC;

-- Les appels qui ont echoue
SELECT r.created_at, r.error_message
FROM prediction_results r WHERE NOT r.succeeded ORDER BY 1 DESC;
```

**Sans ecrire de SQL**, un script rend les memes informations et sait les exporter :

```bash
PYTHONPATH=src python scripts/interroger_base.py
PYTHONPATH=src python scripts/interroger_base.py --export exports/
```

Il produit quatre tableaux : le volume de chaque table, la consommation mesuree par
usage, le journal complet des appels (entrees envoyees et sorties produites), et deux
indicateurs de sante du service. Tout passe par l'ORM, donc il fonctionne aussi bien
sur PostgreSQL que sur SQLite.

### Besoins analytiques

Les tables sont concues pour repondre a trois questions sans traitement
supplementaire :

- **Usage du service** : nombre d'appels par compte et par periode, via
  `prediction_requests` (index sur `user_id` et `created_at`).
- **Sante du modele** : temps de calcul et taux d'echec, via `prediction_results`
  (`duration_ms`, `succeeded`). Une derive du temps de reponse ou une remontee des
  echecs se voient sans instrumentation supplementaire.
- **Comparaison entre versions** : chaque resultat pointe vers la version qui l'a
  produit, ce qui permet de comparer deux modeles sur les memes demandes.

---

## Authentification et securite

### Le principe

Deux mecanismes distincts, souvent confondus.

**Le hachage** protege les mots de passe stockes. La base ne contient jamais un mot de
passe lisible, seulement son empreinte bcrypt, qui ne se remonte pas. Une fuite de la
base ne livre donc aucun mot de passe utilisable ailleurs.

bcrypt est volontairement lent, quelques dizaines de millisecondes. Imperceptible a la
connexion, mais cela ramene une attaque par dictionnaire de millions d'essais par
seconde a quelques dizaines. Il ajoute aussi un sel unique par mot de passe : deux
comptes avec le meme mot de passe ont deux empreintes differentes.

**Le jeton** evite de renvoyer le mot de passe a chaque appel. L'utilisateur s'annonce
une fois sur `/auth/token` et recoit un jeton JWT signe, valable une heure. Le jeton
n'est pas chiffre, il est *signe* : n'importe qui peut lire ce qu'il contient,
personne ne peut le modifier sans la cle du serveur. On n'y met donc jamais
d'information sensible.

### Les mesures en place

| Mesure | Ce qu'elle empeche |
|---|---|
| Mots de passe haches en bcrypt, avec sel | Qu'une fuite de la base livre des mots de passe |
| Jetons signes, expiration a 60 minutes | Qu'un jeton vole reste utilisable indefiniment |
| Message identique pour compte inconnu et mot de passe faux | Qu'on devine quels comptes existent |
| Temps de reponse identique dans les deux cas | La meme chose, par la mesure du temps |
| 12 caracteres minimum | Les mots de passe cassables par force brute |
| Creation de comptes reservee aux administrateurs | Que n'importe qui s'inscrive |
| `404` et non `403` sur la ressource d'un autre | Qu'on confirme l'existence d'une prediction |
| Comptes desactivables (`is_active`) | Qu'un depart laisse un acces ouvert |
| Secrets uniquement en variables d'environnement | Qu'une cle parte dans l'historique Git |
| Mot de passe de la base masque dans les journaux | Qu'il finisse dans les logs du serveur |
| Conteneur execute sans privileges root | Qu'une compromission donne la main sur l'hote |

### Gestion des secrets

| Ou | Comment |
|---|---|
| Poste de developpement | fichier `.env`, dans `.gitignore` |
| Tests automatiques | variables du workflow, valeurs jetables regenerees |
| Production | secrets GitHub Actions, environnement `production` |

Aucun secret n'est ecrit dans le code, et `.env.example` ne contient que des valeurs
d'exemple explicitement marquees comme a remplacer.

### Ce qui manquerait pour un vrai service

Ce projet est un proof of concept. Avant une mise en production reelle :
limitation du nombre d'appels par compte, HTTPS obligatoire, jetons de rafraichissement
plutot qu'une reconnexion toutes les heures, journalisation structuree vers un
collecteur externe, et rotation programmee de la cle de signature.

---

## Tests

```bash
PYTHONPATH=src pytest                                   # les 146 tests
PYTHONPATH=src pytest --cov --cov-report=term-missing   # avec la couverture
PYTHONPATH=src pytest --cov --cov-report=html           # rapport lisible : htmlcov/index.html
```

Par defaut les tests tournent sur SQLite, sans rien installer. Pour les jouer sur
PostgreSQL, comme le fait l'integration continue :

```bash
TEST_DATABASE_URL=postgresql+psycopg://futurisys:futurisys@localhost:5432/futurisys_test \
  PYTHONPATH=src pytest
```

### Ce que couvrent les 146 tests

| Fichier | Nombre | Ce qui est verifie |
|---|---:|---|
| `test_features.py` | 8 | les 3 colonnes calculees, y compris les cas limites |
| `test_preparation.py` | 11 | la chaine de nettoyage, filtre par filtre, avec les comptes exacts |
| `test_train.py` | 12 | la structure du pipeline et le score atteint |
| `test_security.py` | 12 | hachage, jetons, jeton expire, jeton contrefait |
| `test_database.py` | 10 | contraintes, unicite, cascades, types apres aller-retour |
| `test_create_db.py` | 10 | l'initialisation, et son idempotence |
| `test_api_auth.py` | 12 | connexion, refus, droits |
| `test_api_predictions.py` | 24 | le parcours complet, la validation, le cloisonnement |
| `test_api_buildings.py` | 12 | filtres, pagination, 404 |
| `test_error_paths.py` | 11 | modele absent, base injoignable, prediction en echec |
| `test_cli_and_session.py` | 5 | les commandes de deploiement, la fermeture des sessions |
| `test_deploiement.py` | 9 | ce qui part sur l'hebergeur, et le nom du Space |
| `test_interroger_base.py` | 10 | les requetes du script de consultation et son export |

Couverture : **98 %**, code des scripts inclus. Les lignes non couvertes sont la recherche complete d'hyperparametres, qui prend
plusieurs minutes, les gardes `if __name__ == "__main__"`, et les appels reseau vers
Hugging Face : les tester demanderait un vrai jeton et creerait un vrai Space a chaque
execution. La partie du deploiement verifiable sans reseau, la preparation des
fichiers envoyes, est isolee et couverte par 6 tests.

### Les tests qui comptent vraiment

Trois familles justifient l'essentiel de l'effort :

**Les colonnes calculees** (`test_features.py`). Elles tournent a deux endroits,
entrainement et API. Un ecart entre les deux ne leve aucune erreur, il produit
seulement des predictions fausses. Ces tests sont la seule protection.

**La conversion logarithme vers kBtu** (`test_api_predictions.py`). Sans elle, l'API
renverrait `16,7` au lieu de `17 500 000` : un nombre qui ressemble a une reponse
valide et qui est faux d'un facteur d'un million.

**La trace en base d'une prediction qui echoue** (`test_error_paths.py`). Sans elle,
les seuls appels qu'on perdrait seraient justement ceux qui posent probleme.

---

## Integration et livraison continues

### `ci.yml`, a chaque envoi de code

Deux jobs enchaines :

1. **tests** — installe les dependances, verifie le style de tout le code (ruff), **reentraine le
   modele depuis les donnees brutes**, cree la base sur un vrai PostgreSQL 16, lance
   les 146 tests, refuse une couverture sous 90 %, et publie le rapport.
2. **image** — construit l'image Docker, la demarre, et interroge `/health`. Une API
   dont les tests passent mais dont l'image ne demarre pas n'est pas deployable.

Le modele est reentraine a chaque execution plutot que repris du depot : c'est la
preuve que la chaine complete tourne encore, pas seulement que le fichier se charge.

PostgreSQL est utilise et non SQLite : les deux moteurs different sur les cles
etrangeres, les booleens et les contraintes, et ce sont precisement ces
comportements-la que les tests verifient.

### `deploy.yml`, sur un tag de version

Ne se declenche que sur un tag `v*`. Deployer a chaque commit sur `main` mettrait en
ligne du travail en cours ; le tag est la decision explicite de publier, et il donne un
point de retour en arriere identifiable.

Le workflow verifie d'abord que les secrets sont configures (avec un message qui dit
quoi faire), reentraine le modele, envoie le tout sur Hugging Face Spaces, puis attend
que le Space reponde sur `/health` avant de se declarer reussi.

### Les trois environnements

| | `dev` | `test` | `prod` |
|---|---|---|---|
| Ou | poste de developpement | GitHub Actions | Hugging Face Spaces |
| Base | PostgreSQL en conteneur | PostgreSQL en service GitHub | SQLite |
| Secrets | fichier `.env` | variables du workflow, jetables | secrets GitHub |
| Declencheur | manuel | chaque envoi de code | tag de version |

SQLite en production de demonstration est un choix assume : l'hebergement gratuit ne
permet pas de faire tourner un PostgreSQL a cote, et l'enonce autorise explicitement
une base locale. Le code ne voit pas la difference, c'est l'ORM qui traduit.

---

## Deploiement

L'API est livree sous forme d'**image Docker publique**. Elle se telecharge et se
lance sans compte, sans carte et sans configuration :

```bash
docker run -p 8000:7860 \
  -e DATABASE_URL=sqlite:////tmp/futurisys.db \
  -e SECRET_KEY=une-cle-a-vous \
  -e ADMIN_PASSWORD=un-mot-de-passe-a-vous \
  ghcr.io/hydrale/futurisys-energy-api:latest
```

Puis <http://localhost:8000/docs>. L'API cree ses tables et insere les 1 508 batiments
toute seule.

A chaque tag, le pipeline entraine le modele, construit l'image, la publie, **la
demarre et interroge son etat de sante** avant de la declarer bonne : une image qui ne
demarre pas ne sort jamais.

Deux hebergeurs ont ete essayes et ecartes, tous deux pour une raison commerciale et
non technique : Hugging Face facture desormais les Spaces Docker, Render exige une
carte bancaire meme sur son palier a 0 $. Le detail, les mesures et le code conserve
pour chacun sont dans [`DEPLOIEMENT.md`](DEPLOIEMENT.md).

### Hugging Face, si un compte PRO devient disponible

**1. Un jeton Hugging Face avec droit d'ecriture** : sur
<https://huggingface.co/settings/tokens>, creer un jeton de type *Write*.

**2. Tout configurer en une commande** :

```bash
bash scripts/configurer_le_deploiement.sh
```

Le script demande le jeton sans l'afficher, verifie aupres de Hugging Face qu'il est
valide et en ecriture, pose les trois secrets sur GitHub, puis pousse le tag qui
declenche la mise en ligne.

Le compte proprietaire du Space est deduit du jeton : il n'y a pas de pseudo a taper.
La variable `HF_SPACE` ne sert qu'a viser un autre compte ou un autre nom.

Le jeton passe par l'entree standard, jamais par un argument de commande : il
n'apparait ni dans l'historique du shell, ni dans la liste des processus de la
machine. Rien n'est pose tant que le jeton n'a pas ete valide.

`HF_TOKEN`, `SECRET_KEY` et `ADMIN_PASSWORD` sont des *secrets* : GitHub les chiffre
et ne les reaffiche jamais. `HF_SPACE`, facultative, est une *variable* : le nom du
Space n'est pas une information sensible.

Le Space n'a pas besoin d'etre cree a la main : le script de deploiement le cree au
premier passage.

### Publier une version

```bash
git tag -a v1.1.0 -m "Description de la version"
git push origin v1.1.0
```

Le workflow part tout seul. Suivi dans l'onglet Actions du depot.

### Revenir en arriere

Republier le tag precedent depuis l'onglet Actions (bouton *Run workflow*), ou
deployer a nouveau depuis le tag voulu. Chaque version deployee reste identifiable.

---

## Conventions Git

### Branches

| Prefixe | Usage |
|---|---|
| `main` | toujours deployable ; jamais de commit direct |
| `feat/` | nouvelle fonctionnalite (`feat/api-predictions`) |
| `fix/` | correction (`fix/conversion-log-kbtu`) |
| `docs/` | documentation seule |

Une branche par fonctionnalite, fusionnee dans `main` en `--no-ff` pour que
l'historique garde la trace du regroupement.

### Commits

Format `type: description a l'infinitif`, en francais :

```
feat: exposer le modele via un endpoint de prediction
fix: convertir la sortie du modele en kBtu avant de la renvoyer
test: couvrir les scenarios d'echec du modele
docs: documenter le schema de la base
ci: verifier que l'image Docker demarre
```

### Tags

Versionnage semantique : `vMAJEUR.MINEUR.CORRECTIF`. Un tag est la seule chose qui
declenche une mise en ligne.

---

## Maintenance

### Reentrainer le modele

```bash
PYTHONPATH=src python -m futurisys.ml.train --full-grid
```

Puis verifier que les tests de score passent toujours, incrementer la version dans
`src/futurisys/__init__.py`, et poser un tag. La nouvelle version s'enregistre
automatiquement en base au demarrage, et les anciennes predictions restent rattachees
a la version qui les a produites.

**Quand le faire.** Le modele a appris sur des batiments de 2016. Les renovations
energetiques menees depuis ne sont pas dans ses donnees : sur un batiment renove, il
surestime. Un reentrainement sur un releve plus recent est le premier chantier.

### Surveiller

```sql
-- Le temps de calcul derive-t-il ?
SELECT date_trunc('day', created_at) AS jour, count(*),
       round(avg(duration_ms)::numeric, 1) AS ms_moyen
FROM prediction_results GROUP BY 1 ORDER BY 1 DESC LIMIT 14;

-- Y a-t-il des echecs ?
SELECT count(*) FILTER (WHERE NOT succeeded) AS echecs, count(*) AS total
FROM prediction_results;
```

`GET /health` renvoie l'etat de la base et du modele, sans authentification : c'est
l'endpoint a brancher sur un outil de supervision.

### En cas de probleme

| Symptome | Cause probable | Solution |
|---|---|---|
| `503` sur `/predictions` | modele absent | `python -m futurisys.ml.train` |
| `/health` : `database_reachable: false` | PostgreSQL arrete | `docker compose up -d` |
| `401` alors que le mot de passe est bon | jeton expire (1 h) | se reconnecter |
| Les tests echouent sur les cles etrangeres | ancienne base de test | supprimer le fichier SQLite temporaire |
| L'image Docker ne demarre pas | `models/` vide | entrainer avant de construire |

---

## Licence

MIT.

Donnees : releve energetique 2016 de la ville de Seattle, donnees publiques.
