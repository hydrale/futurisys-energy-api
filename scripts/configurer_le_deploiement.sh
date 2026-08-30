#!/usr/bin/env bash
# Configure le deploiement en une commande.
#
#   bash scripts/configurer_le_deploiement.sh
#
# Le jeton Hugging Face est saisi a l'invite, sans echo a l'ecran, et transmis a
# GitHub par l'entree standard. Il n'apparait donc ni dans l'historique du shell, ni
# dans la liste des processus, ni dans un fichier.

set -euo pipefail

DEPOT="hydrale/futurisys-energy-api"
VERSION="v1.2.0"

echo "Configuration du deploiement pour $DEPOT"
echo

# --- 1. Le jeton, saisi sans etre affiche ---
# read -s : la frappe n'apparait pas a l'ecran, comme pour un mot de passe.
read -rsp "Jeton Hugging Face (droit d'ecriture) : " JETON
echo
if [ -z "$JETON" ]; then
  echo "Aucun jeton saisi. Rien n'a ete modifie." >&2
  exit 1
fi

# --- 2. Retrouver le compte Hugging Face a partir du jeton ---
# Evite d'avoir a taper son pseudo, et verifie au passage que le jeton est valide
# avant d'aller plus loin : mieux vaut echouer ici que dans le workflow.
COMPTE=$(JETON="$JETON" python3 - <<'PY'
import json, os, sys, urllib.error, urllib.request

requete = urllib.request.Request(
    "https://huggingface.co/api/whoami-v2",
    headers={"Authorization": "Bearer " + os.environ["JETON"]},
)
try:
    with urllib.request.urlopen(requete, timeout=20) as reponse:
        compte = json.load(reponse)
except urllib.error.HTTPError as erreur:
    sys.exit(f"Jeton refuse par Hugging Face (HTTP {erreur.code}).")

# Le droit d'ecriture est indispensable : un jeton en lecture seule passe cette
# etape mais fait echouer la creation du Space, avec un message bien moins clair.
droits = compte.get("auth", {}).get("accessToken", {}).get("role")
if droits not in (None, "write", "fineGrained"):
    sys.exit(f"Ce jeton est en '{droits}'. Il en faut un de type Write.")

print(compte["name"])
PY
)

echo "Compte Hugging Face : $COMPTE"
SPACE="$COMPTE/futurisys-energy-api"

# --- 3. Poser les secrets sur GitHub ---
# printf | gh : la valeur passe par l'entree standard et non par un argument, qui
# serait visible dans la liste des processus de la machine.
printf '%s' "$JETON" | gh secret set HF_TOKEN --repo "$DEPOT"
echo "  secret HF_TOKEN pose"
unset JETON

# Cle de signature des jetons d'acces de l'API, generee ici et jamais lue par personne.
python3 -c "import secrets; print(secrets.token_urlsafe(48))" \
  | gh secret set SECRET_KEY --repo "$DEPOT"
echo "  secret SECRET_KEY pose"

python3 -c "import secrets; print(secrets.token_urlsafe(18))" \
  | gh secret set ADMIN_PASSWORD --repo "$DEPOT"
echo "  secret ADMIN_PASSWORD pose"

# Le nom du Space n'est pas sensible : c'est une variable, pas un secret.
gh variable set HF_SPACE --repo "$DEPOT" --body "$SPACE"
echo "  variable HF_SPACE = $SPACE"

# --- 4. Declencher la mise en ligne ---
echo
echo "Mise en ligne de $VERSION..."
git push origin "$VERSION" 2>/dev/null || echo "  (tag deja pousse)"

echo
echo "Suivi du deploiement :"
echo "  gh run watch --repo $DEPOT"
echo
echo "Une fois termine, l'API sera sur :"
echo "  https://$(echo "$SPACE" | tr '/' '-' | tr '[:upper:]' '[:lower:]').hf.space/docs"
