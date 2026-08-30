# Fiche de demonstration

A garder sous les yeux pendant la soutenance. Tout tient en une commande et trois
appels.

## Avant de commencer

Verifier que Docker tourne :

```bash
docker info > /dev/null && echo "Docker est pret"
```

Si la commande ne repond pas, ouvrir l'application Docker Desktop et attendre que sa
baleine se stabilise dans la barre de menus.

**Une seule fois**, si l'API a deja ete lancee sur cette machine avant aout 2026 :

```bash
docker rm -f $(docker ps -aq --filter ancestor=ghcr.io/hydrale/futurisys-energy-api) 2>/dev/null
docker rmi -f ghcr.io/hydrale/futurisys-energy-api:latest
```

Cela force le telechargement de la version ARM, trois fois plus rapide sur un Mac
recent et sans message d'avertissement au lancement.

## 1. Lancer l'API

```bash
docker run -p 8000:7860 \
  -e DATABASE_URL=sqlite:////tmp/futurisys.db \
  -e SECRET_KEY=cle-de-demonstration \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=demo-BuP63IL9C9x7Fj \
  ghcr.io/hydrale/futurisys-energy-api:latest
```

Ce qui doit s'afficher, en une poignee de secondes :

```
Initialisation de la base : {'database': 'sqlite:////tmp/futurisys.db',
 'admin_created': True, 'model_version_registered': True, 'buildings_inserted': 1508}
INFO:     Uvicorn running on http://0.0.0.0:7860
```

**1508, c'est le chiffre a montrer** : l'API a cree ses tables et insere tout le jeu
de donnees toute seule, sans qu'on lui demande quoi que ce soit.

Laisser cette fenetre ouverte. Elle affiche les appels en direct.

## 2. Ouvrir la documentation

<http://localhost:8000/docs>

La page decrit d'elle-meme ce que le modele sait faire, ce qu'il ne sait pas faire,
et comment s'en servir. Onze points d'entree, ranges par theme.

## 3. Se connecter

Bouton **Authorize**, en haut a droite.

```
username : admin
password : demo-BuP63IL9C9x7Fj
```

Puis *Authorize*, puis *Close*. Le cadenas des points d'entree se ferme : ils sont
maintenant accessibles.

## 4. Les trois choses a montrer, dans cet ordre

### La prediction comparee a la realite

`POST /predictions/buildings/{ose_building_id}` > *Try it out* > mettre **1** > *Execute*.

```json
{
  "predicted_kbtu": 7356541.0,
  "actual_kbtu": 7456910.0,
  "relative_error": 0.0135,
  "duration_ms": 9.2
}
```

La phrase a dire : *le modele annonce 7,36 millions, la ville a mesure 7,46 millions,
soit 1,4 % d'ecart, en 9 millisecondes.*

Le batiment **3** donne 24 % d'ecart : le montrer aussi, c'est plus honnete que de
ne presenter que le cas favorable.

### Le refus d'une donnee invalide

`POST /predictions` > *Try it out*. L'exemple est deja rempli. Remplacer la latitude
`47.6101` par `48.85`, qui est celle de Paris, puis *Execute*.

```
422 Unprocessable Entity
latitude : Input should be less than or equal to 47.79
```

La phrase a dire : *le modele n'a vu que Seattle. Sur un batiment parisien il
repondrait un chiffre d'apparence normale et totalement faux. L'API refuse avant de
l'appeler.*

Meme demonstration avec une surface negative.

### La trace en base

`GET /predictions` > *Try it out* > *Execute*. La liste des appels qui viennent
d'etre faits, avec leur horodatage et leur duree.

La phrase a dire : *le modele n'est jamais appele en direct. La demande est ecrite en
base avant l'appel, la reponse apres. Meme un plantage du modele laisse une ligne
avec son message d'erreur.*

## Si l'evaluateur veut essayer chez lui

L'image est publique, il n'a besoin d'aucun compte :

```bash
docker run -p 8000:7860 -e DATABASE_URL=sqlite:////tmp/f.db \
  -e SECRET_KEY=une-cle -e ADMIN_PASSWORD=un-mot-de-passe \
  ghcr.io/hydrale/futurisys-energy-api:latest
```

## Pour arreter

`Ctrl+C` dans la fenetre du terminal. Rien n'est laisse derriere : la base vit dans
le conteneur et disparait avec lui.

## En cas de pepin

| Ce qui se passe | Quoi faire |
|---|---|
| `port is already allocated` | Un conteneur tourne deja : `docker rm -f $(docker ps -q --filter publish=8000)` |
| `Cannot connect to the Docker daemon` | Docker Desktop n'est pas lance |
| `platform ... does not match` | Ancienne image x86, refaire la purge du paragraphe *Avant de commencer* |
| La page `/docs` ne charge pas | Attendre 5 secondes de plus, l'image charge 11 Mo de modele |
| `401` sur un appel | La session Swagger a expire au bout d'une heure : recliquer *Authorize* |
