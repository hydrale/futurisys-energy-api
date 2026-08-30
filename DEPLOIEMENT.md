# Deploiement

Trois cibles, par ordre de ce qui a ete retenu.

## 1. Render, la cible retenue

Palier **gratuit** : 512 Mo de memoire, conteneur Docker, adresse publique en HTTPS.
La consommation de l'image a ete mesuree sous contrainte avant de choisir : 373 Mo au
demarrage, 373 Mo apres 25 predictions d'affilee, aucun arret pour depassement.

Tout est decrit dans [`render.yaml`](render.yaml) : le service repart a l'identique
s'il doit etre recree, sans que personne ait a se souvenir des reglages.

### Mise en place, une seule fois

1. Creer un compte sur <https://render.com> et le relier a GitHub.
2. *New* > *Blueprint*, choisir le depot `futurisys-energy-api`. Render lit
   `render.yaml` et propose le service.
3. Renseigner `ADMIN_PASSWORD` (le seul reglage qui n'est pas dans le fichier :
   `sync: false` interdit de l'y ecrire). `SECRET_KEY` est tiree au hasard par Render.
4. *Apply*.

Ensuite, chaque envoi sur `main` redeploie tout seul (`autoDeploy: true`).

### La limite a connaitre

Le palier gratuit **endort** le service apres une periode sans trafic. Le premier
appel qui suit le reveille et met environ trente secondes. Avant une demonstration,
ouvrir l'adresse deux minutes a l'avance.

## 2. Le registre GitHub, toujours disponible

Chaque tag publie l'image, la demarre et l'interroge avant de la declarer bonne.
Elle ne depend d'aucun compte tiers ni d'aucun abonnement.

```bash
docker run -p 8000:7860 \
  -e DATABASE_URL=sqlite:////tmp/futurisys.db \
  -e SECRET_KEY=une-cle-a-vous \
  -e ADMIN_PASSWORD=un-mot-de-passe-a-vous \
  ghcr.io/hydrale/futurisys-energy-api:latest
```

Puis <http://localhost:8000/docs>. L'API cree ses tables et insere les 1 508 batiments
toute seule au demarrage.

## 3. Hugging Face Spaces, ecarte

C'etait la plateforme suggeree par l'enonce. Elle a ete tentee et **refusee par leur
facturation** :

```
402 Payment Required
Static Spaces are free for everyone, but hosting Gradio and Docker Spaces
on free cpu-basic requires a PRO subscription.
```

Le code correspondant est conserve et fonctionnel
([`scripts/deployer_sur_hugging_face.py`](scripts/deployer_sur_hugging_face.py)) : il
suffit d'un compte PRO pour que l'etape passe. Elle est en `continue-on-error` pour
que son echec, qui tient a un abonnement et non au code, ne masque pas la publication
reussie de l'image.

L'enonce prevoit ce cas : il ecrit « Hugging Face Spaces **ou equivalent** ».

## Le port

L'image lit son port dans la variable `PORT`, et retombe sur 7860 si elle est absente.
Hugging Face impose 7860, Render impose le sien : un numero ecrit en dur aurait
condamne le projet a une seule plateforme. Les deux cas sont verifies.
