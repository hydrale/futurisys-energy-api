# Modele de donnees

## Le schema en un coup d'oeil

```mermaid
erDiagram
    users ||--o{ prediction_requests : "envoie"
    buildings ||--o{ prediction_requests : "concerne (optionnel)"
    prediction_requests ||--|| prediction_results : "produit"
    model_versions ||--o{ prediction_results : "a calcule"

    users {
        int id PK
        string username UK "unique, indexe"
        string hashed_password "empreinte bcrypt, jamais le mot de passe"
        bool is_admin
        bool is_active
        datetime created_at
    }

    buildings {
        int id PK
        int ose_building_id UK "identifiant officiel de la ville de Seattle"
        string property_name "facultatif"
        string building_type "indexe"
        string primary_property_type "indexe"
        string neighborhood_grouped "indexe"
        float property_gfa_total
        float property_gfa_parking
        float number_of_floors
        float number_of_buildings
        float latitude
        float longitude
        int building_age
        float largest_use_ratio
        bool is_multi_use
        bool has_electricity
        bool has_natural_gas
        bool has_steam
        float site_energy_use_wn_kbtu "la consommation reellement mesuree"
    }

    model_versions {
        int id PK
        string version
        string algorithm
        string trained_at
        float r2_test
        float mae_log_test
        bool is_active
        datetime created_at
    }

    prediction_requests {
        int id PK
        int user_id FK "RESTRICT"
        int building_id FK "facultatif"
        string building_type
        string primary_property_type
        string neighborhood
        float property_gfa_total
        float property_gfa_parking
        float number_of_floors
        float number_of_buildings
        float latitude
        float longitude
        int year_built
        float largest_property_use_gfa "facultatif"
        bool is_multi_use
        bool has_electricity
        bool has_natural_gas
        bool has_steam
        datetime created_at "indexe"
    }

    prediction_results {
        int id PK
        int request_id FK "unique, CASCADE"
        int model_version_id FK
        float predicted_log_value "la sortie brute du modele"
        float predicted_kbtu "la valeur rendue au client"
        float duration_ms
        bool succeeded
        text error_message "rempli seulement en cas d'echec"
        datetime created_at
    }
```

## Les choix de conception, et ce qu'ils evitent

### Pourquoi deux tables pour un seul appel

`prediction_requests` garde ce qu'on a recu, `prediction_results` ce qu'on a repondu.
Une table unique perdrait les appels qui echouent : la ligne ne serait ecrite qu'une
fois la prediction reussie. Or ce sont exactement ces appels-la qu'on cherche quand un
client se plaint.

Concretement, l'ordre d'ecriture est : demande enregistree, puis modele appele, puis
resultat enregistre. Un plantage du modele laisse donc une demande et un resultat en
echec, avec son message d'erreur.

### Pourquoi une table des versions du modele

Une prediction gardee six mois serait inexplicable sans elle : on ne saurait plus quel
modele l'a produite ni ce qu'il valait. Chaque resultat pointe vers sa version, avec
son R2 et sa date d'entrainement.

### Ce que les contraintes empechent

| Contrainte | Ce qu'elle empeche |
|---|---|
| `users.username` unique | Deux comptes homonymes, donc une connexion ambigue |
| `buildings.ose_building_id` unique | Le meme batiment de Seattle insere deux fois |
| `prediction_results.request_id` unique | Deux reponses differentes pour une meme demande |
| `prediction_requests.user_id` obligatoire | Une prediction anonyme, non tracable |
| `user_id` en RESTRICT | La suppression d'un compte effacant son historique |
| `request_id` en CASCADE | Un resultat orphelin, rattache a rien |
| `site_energy_use_wn_kbtu` obligatoire | Un batiment de reference sans sa consommation mesuree |

### Les index, et pourquoi ceux-la

Un index accelere la recherche sur une colonne, au prix d'un peu d'espace et d'une
ecriture legerement plus lente. On n'en met donc que sur ce qui sert reellement a
filtrer.

- `buildings.ose_building_id` : la cle par laquelle un batiment est demande.
- `buildings.building_type`, `primary_property_type`, `neighborhood_grouped` : les
  trois filtres exposes par `GET /buildings`.
- `prediction_requests.user_id` et `created_at` : le journal d'un compte est toujours
  lu filtre par utilisateur et trie par date.
- `users.username` : lu a chaque connexion et a chaque verification de jeton.

### Le volume

Les 1 508 batiments sont figes : ils viennent du releve 2016. Ce sont les deux tables
de predictions qui grossissent, d'une ligne chacune par appel. Sur cette base,
100 000 appels representent environ 30 Mo, ce qu'un PostgreSQL absorbe sans reglage
particulier. La pagination de `GET /buildings` et de `GET /predictions` est plafonnee
a 200 lignes pour qu'aucune requete ne puisse demander la table entiere.
