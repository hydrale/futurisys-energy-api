"""L'interface visuelle de demonstration, servie sur la racine de l'API.

Une seule page HTML, avec son CSS et son JavaScript embarques : aucun fichier
statique a copier ni a monter, aucune etape de compilation. Elle parle a l'API par
des appels fetch en relatif (meme origine, donc aucune configuration CORS a ajouter).

Cette page n'est pas un livrable en soi : le vrai contrat de l'API reste /docs
(Swagger) et /openapi.json, generes automatiquement et complets. Cette page est une
facon plus lisible de montrer la meme chose en soutenance.
"""

from __future__ import annotations

INDEX_HTML = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Futurisys - Consommation energetique</title>
<style>
:root {
  --forest: #1f4332;
  --moss: #6fa287;
  --amber: #c77b26;
  --ink: #1b2420;
  --grey: #5f6b65;
  --light: #eaf2ed;
  --white: #ffffff;
  --danger: #b3432f;
  --ok: #2f7d4f;
  --radius: 12px;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  background: var(--light);
  color: var(--ink);
}
header {
  background: var(--forest);
  color: var(--white);
  padding: 18px 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
header h1 { font-size: 1.15rem; margin: 0; font-weight: 700; }
header .sub { color: var(--moss); font-size: 0.8rem; letter-spacing: 0.04em; }
#etat {
  display: flex; align-items: center; gap: 8px; font-size: 0.85rem; color: var(--moss);
}
#etat .point { width: 9px; height: 9px; border-radius: 50%; background: #888; }
#etat .point.ok { background: #7cd992; }
#etat .point.ko { background: #e26a5a; }
main { max-width: 1080px; margin: 0 auto; padding: 24px 20px 60px; }

.carte {
  background: var(--white);
  border-radius: var(--radius);
  padding: 22px 24px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(20,30,25,0.08);
}
.carte h2 {
  margin: 0 0 4px;
  font-size: 1.05rem;
  color: var(--forest);
}
.carte p.explication { margin: 0 0 16px; color: var(--grey); font-size: 0.88rem; }

label { display: block; font-size: 0.8rem; color: var(--grey); margin: 10px 0 4px; }
input, select {
  width: 100%;
  padding: 9px 11px;
  border: 1px solid #d7ded9;
  border-radius: 8px;
  font-size: 0.92rem;
  background: var(--white);
  color: var(--ink);
}
input:focus, select:focus { outline: 2px solid var(--moss); border-color: var(--moss); }

.grille2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
.grille3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0 16px; }
@media (max-width: 640px) { .grille2, .grille3 { grid-template-columns: 1fr; } }

.checkrow { display: flex; gap: 18px; margin-top: 14px; flex-wrap: wrap; }
.checkrow label { display: flex; align-items: center; gap: 6px; margin: 0; color: var(--ink); font-size: 0.88rem; }
.checkrow input { width: auto; }

button {
  cursor: pointer;
  border: none;
  border-radius: 8px;
  padding: 10px 18px;
  font-size: 0.92rem;
  font-weight: 600;
  font-family: inherit;
}
button.principal { background: var(--forest); color: var(--white); }
button.principal:hover { background: #163326; }
button.discret { background: var(--light); color: var(--forest); }
button.discret:hover { background: #dcebe2; }
button:disabled { opacity: 0.55; cursor: default; }

.ligne-action { display: flex; gap: 10px; align-items: center; margin-top: 16px; flex-wrap: wrap; }

.resultat {
  margin-top: 18px;
  padding: 16px 18px;
  border-radius: 10px;
  background: var(--light);
  display: none;
}
.resultat.visible { display: block; }
.resultat .chiffres { display: flex; gap: 32px; flex-wrap: wrap; margin-top: 10px; }
.resultat .bloc-chiffre .valeur { font-size: 1.7rem; font-weight: 700; color: var(--forest); }
.resultat .bloc-chiffre .valeur.pred { color: var(--amber); }
.resultat .bloc-chiffre .legende { font-size: 0.78rem; color: var(--grey); margin-top: 2px; }
.resultat .barre-comparaison {
  margin-top: 14px; height: 10px; background: #dbe6df; border-radius: 6px; overflow: hidden; display: flex;
}
.resultat .barre-comparaison .segment.pred { background: var(--amber); }
.resultat .barre-comparaison .segment.reste { background: transparent; }
.erreur {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: 8px;
  background: #fbecea;
  color: var(--danger);
  font-size: 0.87rem;
  display: none;
  white-space: pre-line;
}
.erreur.visible { display: block; }

table { width: 100%; border-collapse: collapse; font-size: 0.86rem; margin-top: 8px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #edf1ee; }
th { color: var(--grey); font-weight: 600; font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.03em; }
tr:last-child td { border-bottom: none; }
.vide { color: var(--grey); font-size: 0.86rem; padding: 10px 0; }

#ecran-connexion {
  max-width: 380px; margin: 80px auto; text-align: center;
}
#ecran-connexion .carte { text-align: left; }
#ecran-connexion .logo { font-size: 1.6rem; margin-bottom: 4px; }
#tableau-de-bord { display: none; }
#tableau-de-bord.visible { display: block; }

.pied {
  text-align: center; color: var(--grey); font-size: 0.78rem; margin-top: 30px;
}
.pied a { color: var(--forest); }

.badge {
  display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 0.72rem;
  background: var(--light); color: var(--forest); font-weight: 600;
}
</style>
</head>
<body>

<header>
  <div>
    <h1>Futurisys &mdash; Consommation energetique</h1>
    <div class="sub">API de prediction, batiments de Seattle</div>
  </div>
  <div id="etat"><span class="point" id="etat-point"></span><span id="etat-texte">verification...</span></div>
</header>

<main>

<section id="ecran-connexion">
  <div class="logo">Se connecter</div>
  <div class="carte">
    <p class="explication">Compte de demonstration : <code>admin</code></p>
    <label for="c-user">Utilisateur</label>
    <input id="c-user" value="admin" autocomplete="username">
    <label for="c-pass">Mot de passe</label>
    <input id="c-pass" type="password" autocomplete="current-password">
    <div class="ligne-action">
      <button class="principal" onclick="seConnecter()">Se connecter</button>
    </div>
    <div class="erreur" id="c-erreur"></div>
  </div>
</section>

<div id="tableau-de-bord">

  <section class="carte" id="carte-modele">
    <h2>Le modele en service</h2>
    <p class="explication">Chargement...</p>
  </section>

  <section class="carte">
    <h2>Estimer un batiment du jeu de donnees</h2>
    <p class="explication">Predit pour un batiment deja en base et compare a sa consommation reellement mesuree en 2016.</p>
    <label for="b-id">Identifiant Seattle du batiment (essayer 1, 2, 3...)</label>
    <div class="ligne-action">
      <input id="b-id" value="1" style="max-width:160px">
      <button class="principal" onclick="predireBatimentConnu()">Estimer</button>
    </div>
    <div class="erreur" id="b-erreur"></div>
    <div class="resultat" id="b-resultat">
      <div class="chiffres">
        <div class="bloc-chiffre"><div class="valeur pred" id="b-predit">-</div><div class="legende">estime par le modele (kBtu)</div></div>
        <div class="bloc-chiffre"><div class="valeur" id="b-mesure">-</div><div class="legende">mesure par la ville en 2016 (kBtu)</div></div>
        <div class="bloc-chiffre"><div class="valeur" id="b-ecart">-</div><div class="legende">ecart relatif</div></div>
        <div class="bloc-chiffre"><div class="valeur" id="b-duree">-</div><div class="legende">temps de calcul</div></div>
      </div>
    </div>
  </section>

  <section class="carte">
    <h2>Estimer un nouveau batiment</h2>
    <p class="explication">Decrire un batiment de zero. Les valeurs hors de l'emprise de Seattle sont refusees avant meme d'appeler le modele.</p>

    <div class="grille3">
      <div>
        <label for="n-type">Type de batiment</label>
        <select id="n-type">
          <option>NonResidential</option>
          <option>Campus</option>
          <option>Nonresidential COS</option>
          <option>SPS-District K-12</option>
        </select>
      </div>
      <div>
        <label for="n-usage">Usage principal</label>
        <select id="n-usage">
          <option>Large Office</option>
          <option>Hotel</option>
          <option>Hospital</option>
          <option>Warehouse</option>
          <option>Retail Store</option>
          <option>K-12 School</option>
          <option>Mixed Use Property</option>
          <option>Other</option>
        </select>
      </div>
      <div>
        <label for="n-quartier">Quartier</label>
        <select id="n-quartier">
          <option>DOWNTOWN</option>
          <option>EAST</option>
          <option>NORTHEAST</option>
          <option>NORTHWEST</option>
          <option>LAKE UNION</option>
          <option>MAGNOLIA / QUEEN ANNE</option>
          <option>GREATER DUWAMISH</option>
          <option>BALLARD</option>
          <option>AUTRE</option>
        </select>
      </div>
    </div>

    <div class="grille3">
      <div>
        <label for="n-surface">Surface totale (pi&sup2;)</label>
        <input id="n-surface" type="number" value="250000">
      </div>
      <div>
        <label for="n-parking">Surface de parking (pi&sup2;)</label>
        <input id="n-parking" type="number" value="30000">
      </div>
      <div>
        <label for="n-etages">Nombre d'etages</label>
        <input id="n-etages" type="number" value="12">
      </div>
    </div>

    <div class="grille3">
      <div>
        <label for="n-annee">Annee de construction</label>
        <input id="n-annee" type="number" value="1985">
      </div>
      <div>
        <label for="n-lat">Latitude</label>
        <input id="n-lat" type="number" step="0.0001" value="47.6101">
      </div>
      <div>
        <label for="n-lon">Longitude</label>
        <input id="n-lon" type="number" step="0.0001" value="-122.3344">
      </div>
    </div>

    <div class="checkrow">
      <label><input type="checkbox" id="n-multi" checked> Multi-usages</label>
      <label><input type="checkbox" id="n-elec" checked> Electricite</label>
      <label><input type="checkbox" id="n-gaz" checked> Gaz naturel</label>
      <label><input type="checkbox" id="n-vapeur"> Vapeur urbaine</label>
    </div>

    <div class="ligne-action">
      <button class="principal" onclick="predireNouveau()">Estimer la consommation</button>
      <button class="discret" onclick="remplirParisPourTest()">Remplir avec Paris (pour voir le refus)</button>
    </div>
    <div class="erreur" id="n-erreur"></div>
    <div class="resultat" id="n-resultat">
      <div class="chiffres">
        <div class="bloc-chiffre"><div class="valeur pred" id="n-predit">-</div><div class="legende">consommation estimee (kBtu/an)</div></div>
        <div class="bloc-chiffre"><div class="valeur" id="n-duree">-</div><div class="legende">temps de calcul</div></div>
      </div>
    </div>
  </section>

  <section class="carte">
    <h2>Journal des appels</h2>
    <p class="explication">Chaque prediction est ecrite en base avant et apres l'appel au modele. Voici les dernieres.</p>
    <div class="ligne-action" style="margin-top:0">
      <button class="discret" onclick="chargerJournal()">Rafraichir</button>
    </div>
    <div id="journal-zone"><p class="vide">Aucun appel pour l'instant.</p></div>
  </section>

</div>

<p class="pied">
  Documentation technique complete : <a href="/docs">/docs</a> (Swagger) &middot;
  <a href="/redoc">/redoc</a> &middot;
  <a href="/openapi.json">/openapi.json</a>
</p>

</main>

<script>
let jeton = sessionStorage.getItem("futurisys_jeton") || null;

function formatNombre(n) {
  return Math.round(n).toLocaleString("fr-FR");
}

async function verifierSante() {
  const point = document.getElementById("etat-point");
  const texte = document.getElementById("etat-texte");
  try {
    const r = await fetch("/health");
    const d = await r.json();
    const sain = d.status === "ok";
    point.className = "point " + (sain ? "ok" : "ko");
    texte.textContent = sain
      ? "service en ligne, modele charge"
      : "service degrade (base ou modele indisponible)";
  } catch (e) {
    point.className = "point ko";
    texte.textContent = "service injoignable";
  }
}

function afficherErreur(id, message) {
  const zone = document.getElementById(id);
  zone.textContent = message;
  zone.classList.add("visible");
}
function masquerErreur(id) {
  document.getElementById(id).classList.remove("visible");
}

function messageDepuisReponse(corps) {
  if (!corps) return "Une erreur inattendue s'est produite.";
  if (typeof corps.detail === "string") return corps.detail;
  if (Array.isArray(corps.detail)) {
    return corps.detail.map(function (d) {
      const champ = d.loc[d.loc.length - 1];
      return champ + " : " + d.msg;
    }).join("\\n");
  }
  return "Une erreur inattendue s'est produite.";
}

async function appel(chemin, options) {
  options = options || {};
  options.headers = options.headers || {};
  if (jeton) options.headers["Authorization"] = "Bearer " + jeton;
  const reponse = await fetch(chemin, options);
  let corps = null;
  try { corps = await reponse.json(); } catch (e) {}
  if (reponse.status === 401) {
    seDeconnecter();
    throw new Error("Session expiree, reconnectez-vous.");
  }
  if (!reponse.ok) {
    throw new Error(messageDepuisReponse(corps));
  }
  return corps;
}

async function seConnecter() {
  masquerErreur("c-erreur");
  const utilisateur = document.getElementById("c-user").value.trim();
  const motDePasse = document.getElementById("c-pass").value;
  try {
    const corps = new URLSearchParams();
    corps.set("username", utilisateur);
    corps.set("password", motDePasse);
    const reponse = await fetch("/auth/token", { method: "POST", body: corps });
    const donnees = await reponse.json();
    if (!reponse.ok) throw new Error(messageDepuisReponse(donnees));
    jeton = donnees.access_token;
    sessionStorage.setItem("futurisys_jeton", jeton);
    afficherTableauDeBord();
  } catch (e) {
    afficherErreur("c-erreur", e.message);
  }
}

function seDeconnecter() {
  jeton = null;
  sessionStorage.removeItem("futurisys_jeton");
  document.getElementById("tableau-de-bord").classList.remove("visible");
  document.getElementById("ecran-connexion").style.display = "block";
}

async function afficherTableauDeBord() {
  document.getElementById("ecran-connexion").style.display = "none";
  document.getElementById("tableau-de-bord").classList.add("visible");
  chargerModele();
  chargerJournal();
}

async function chargerModele() {
  const carte = document.getElementById("carte-modele");
  try {
    const m = await appel("/model");
    carte.innerHTML =
      '<h2>Le modele en service <span class="badge">' + m.model_version + '</span></h2>' +
      '<p class="explication">' + m.algorithm + ', entraine sur ' + m.n_train +
      ' batiments. R&sup2; de ' + m.metrics.r2_test + ' sur ' + m.n_test +
      ' batiments jamais vus a l\\'entrainement.</p>';
  } catch (e) {
    carte.innerHTML = '<h2>Le modele en service</h2><p class="explication">Impossible de charger la fiche du modele.</p>';
  }
}

async function predireBatimentConnu() {
  masquerErreur("b-erreur");
  document.getElementById("b-resultat").classList.remove("visible");
  const id = document.getElementById("b-id").value.trim();
  if (!id) { afficherErreur("b-erreur", "Indiquer un identifiant de batiment."); return; }
  try {
    const p = await appel("/predictions/buildings/" + encodeURIComponent(id), { method: "POST" });
    document.getElementById("b-predit").textContent = formatNombre(p.predicted_kbtu);
    document.getElementById("b-mesure").textContent = formatNombre(p.actual_kbtu);
    document.getElementById("b-ecart").textContent = (p.relative_error * 100).toFixed(1) + " %";
    document.getElementById("b-duree").textContent = p.duration_ms.toFixed(1) + " ms";
    document.getElementById("b-resultat").classList.add("visible");
    chargerJournal();
  } catch (e) {
    afficherErreur("b-erreur", e.message);
  }
}

function remplirParisPourTest() {
  document.getElementById("n-lat").value = "48.85";
  document.getElementById("n-lon").value = "2.35";
}

async function predireNouveau() {
  masquerErreur("n-erreur");
  document.getElementById("n-resultat").classList.remove("visible");
  const batiment = {
    building_type: document.getElementById("n-type").value,
    primary_property_type: document.getElementById("n-usage").value,
    neighborhood: document.getElementById("n-quartier").value,
    property_gfa_total: Number(document.getElementById("n-surface").value),
    property_gfa_parking: Number(document.getElementById("n-parking").value),
    number_of_floors: Number(document.getElementById("n-etages").value),
    number_of_buildings: 1,
    latitude: Number(document.getElementById("n-lat").value),
    longitude: Number(document.getElementById("n-lon").value),
    year_built: Number(document.getElementById("n-annee").value),
    largest_property_use_gfa: Number(document.getElementById("n-surface").value),
    is_multi_use: document.getElementById("n-multi").checked,
    has_electricity: document.getElementById("n-elec").checked,
    has_natural_gas: document.getElementById("n-gaz").checked,
    has_steam: document.getElementById("n-vapeur").checked,
  };
  try {
    const p = await appel("/predictions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(batiment),
    });
    document.getElementById("n-predit").textContent = formatNombre(p.predicted_kbtu);
    document.getElementById("n-duree").textContent = p.duration_ms.toFixed(1) + " ms";
    document.getElementById("n-resultat").classList.add("visible");
    chargerJournal();
  } catch (e) {
    afficherErreur("n-erreur", e.message);
  }
}

async function chargerJournal() {
  const zone = document.getElementById("journal-zone");
  try {
    const lignes = await appel("/predictions?limit=10");
    if (!lignes.length) {
      zone.innerHTML = '<p class="vide">Aucun appel pour l\\'instant.</p>';
      return;
    }
    let html = '<table><thead><tr><th>Demande</th><th>Predit (kBtu)</th><th>Duree</th><th>Heure</th></tr></thead><tbody>';
    lignes.forEach(function (l) {
      const heure = new Date(l.created_at).toLocaleTimeString("fr-FR");
      html += '<tr><td>#' + l.request_id + '</td><td>' + formatNombre(l.predicted_kbtu) +
        '</td><td>' + l.duration_ms.toFixed(1) + ' ms</td><td>' + heure + '</td></tr>';
    });
    html += '</tbody></table>';
    zone.innerHTML = html;
  } catch (e) {
    zone.innerHTML = '<p class="vide">Impossible de charger le journal.</p>';
  }
}

document.getElementById("c-pass").addEventListener("keydown", function (e) {
  if (e.key === "Enter") seConnecter();
});

verifierSante();
setInterval(verifierSante, 15000);
if (jeton) { afficherTableauDeBord(); }
</script>
</body>
</html>
"""
