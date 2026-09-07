# Deploiement

L'API est livree sous forme d'**image Docker publique**, publiee et verifiee
automatiquement a chaque version. C'est la cible retenue, apres deux hebergeurs
essayes et ecartes.

## 1. Le registre GitHub, la cible retenue

L'image est publique : elle se telecharge et se lance **sans compte, sans carte et
sans configuration**.

```bash
docker run -p 8000:7860 \
  -e DATABASE_URL=sqlite:////tmp/futurisys.db \
  -e SECRET_KEY=une-cle-a-vous \
  -e ADMIN_PASSWORD=un-mot-de-passe-a-vous \
  ghcr.io/hydrale/futurisys-energy-api:latest
```

Puis <http://localhost:8000/docs>. L'API cree ses tables et insere les 1 508 batiments
toute seule au demarrage : rien d'autre a preparer.

A chaque tag, le pipeline entraine le modele, construit l'image, la publie, **la
demarre et interroge son etat de sante** avant de la declarer bonne. Une image qui ne
demarre pas ne sort jamais.

L'image est construite pour **x86 et ARM**. Sans la variante ARM, les Mac recents la
feraient tourner en emulation, avec un avertissement a chaque lancement et des
performances degradees. Or la demonstration se fait justement sur un Mac ARM.

Versions publiees : `v1.2.1`, `v1.3.0`, `v1.4.0`, `latest`.

## 1 bis. Exposer l'API le temps d'une demonstration

L'image tourne en local. Pour qu'un evaluateur l'essaie **depuis sa propre machine**
pendant une soutenance, un tunnel suffit : il n'y a ni compte a creer, ni carte, ni
port a ouvrir sur la box.

```bash
# 1. Lancer l'API avec des secrets forts, generes pour l'occasion
CLE=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
MDP=$(python3 -c "import secrets; print('demo-' + secrets.token_urlsafe(12))")
docker run -d --name demo -p 8000:7860 \
  -e DATABASE_URL=sqlite:////tmp/futurisys.db \
  -e SECRET_KEY="$CLE" -e ADMIN_USERNAME=admin -e ADMIN_PASSWORD="$MDP" \
  ghcr.io/hydrale/futurisys-energy-api:latest
echo "mot de passe : $MDP"

# 2. Ouvrir le tunnel : l'URL HTTPS publique s'affiche en une dizaine de secondes
cloudflared tunnel --url http://localhost:8000
```

Le tunnel est une connexion **sortante** de la machine vers Cloudflare : contrairement
a une redirection de port sur la box, il n'ouvre aucune breche permanente, il donne du
HTTPS sans certificat a gerer, et il disparait entierement des qu'on l'interrompt.

### Ce que ce n'est pas

Ce n'est **pas un hebergement**. L'URL vit tant que la machine est allumee et que la
commande tourne, et elle change a chaque relance. C'est un moyen de faire essayer le
service en direct, pas une adresse de production a inscrire dans un livrable.

### Le point de vigilance

Des que le tunnel est ouvert, le service est reellement exposé a Internet. Les secrets
de developpement (`SECRET_KEY=cle-de-demo`, mot de passe simple) n'ont plus leur place :
d'ou la generation de valeurs fortes dans la commande ci-dessus, a refaire a chaque
session plutot qu'a reutiliser.

## 2. Render, essaye et ecarte

Render annonce un palier gratuit : 512 Mo, conteneur Docker, adresse publique.
La consommation de l'image a ete mesuree sous cette contrainte avant d'aller plus
loin : 373 Mo au demarrage, 373 Mo apres 25 predictions d'affilee, aucun arret pour
depassement. Techniquement, ca passait.

Le service a ete configure jusqu'au bout (depot public, Docker, palier a 0 $/mois,
variables d'environnement, controle de sante sur `/health`). Le dernier clic ouvre
une demande de **carte bancaire** :

> To verify your card, Render will perform a temporary authorization for $1 USD.

Le palier reste a 0 $/mois, mais l'inscription exige un moyen de paiement. Ecarte
pour cette raison, pas pour une raison technique.

La configuration est conservee dans [`render.yaml`](render.yaml) : le service repart
en un clic le jour ou une carte est disponible. A savoir : le palier gratuit endort
le service apres inactivite, et le reveil prend une trentaine de secondes.

## 3. Hugging Face Spaces, essaye et ecarte

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

## Ce que ces deux refus disent

Les deux hebergeurs qui proposaient hier un palier gratuit sans condition demandent
aujourd'hui un abonnement ou une carte. La reponse a ete de ne dependre d'aucun
d'eux : l'image publiee dans le registre de GitHub s'installe partout, y compris
chez ces deux hebergeurs le jour ou on le decide, et le code de deploiement vers
Hugging Face reste en place et fonctionnel.

L'enonce prevoit ce cas : il ecrit « Hugging Face Spaces **ou equivalent** », et
demande une infrastructure de deploiement automatisee « autant que possible avec la
solution choisie ».

## Le port

L'image lit son port dans la variable `PORT`, et retombe sur 7860 si elle est absente.
Hugging Face impose 7860, Render impose le sien : un numero ecrit en dur aurait
condamne le projet a une seule plateforme. Les deux cas sont verifies.
