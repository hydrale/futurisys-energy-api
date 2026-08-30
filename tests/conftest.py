"""Le decor commun a tous les tests.

Deux principes, qui expliquent presque tout le fichier :

1. Les tests ne touchent jamais la base de developpement. Ils travaillent sur une base
   jetable, creee vide au debut et supprimee a la fin. Sans cette separation, lancer
   les tests effacerait les donnees de la machine sur laquelle on travaille.
2. La base de test est pilotee par TEST_DATABASE_URL. En local, la variable n'est pas
   definie et les tests tournent sur SQLite, sans rien installer. En integration
   continue, elle pointe vers un vrai PostgreSQL : le meme code de test verifie alors
   le moteur reellement utilise en production.
"""

from __future__ import annotations

import os
from pathlib import Path

# Doit etre pose AVANT l'import de l'application : les reglages sont lus une seule
# fois, au premier import. Sans cette ligne, le demarrage de l'API pendant les tests
# creerait les tables dans la base de developpement du poste.
os.environ["AUTO_INIT_DB"] = "false"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from futurisys.api.main import app
from futurisys.api.security import hash_password
from futurisys.db.models import Base, Building, User
from futurisys.db.session import get_session

DATASET = Path("data/building_energy_2016.csv")
MODEL_ARTIFACT = Path("models/energy_model.joblib")

ADMIN_PASSWORD = "motdepasse-admin-de-test"
USER_PASSWORD = "motdepasse-user-de-test"


@pytest.fixture(scope="session")
def engine(tmp_path_factory):
    """Le moteur de la base de test, PostgreSQL en CI et SQLite en local."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        test_engine = create_engine(url, pool_pre_ping=True)
    else:
        database_file = tmp_path_factory.mktemp("db") / "test.sqlite"
        test_engine = create_engine(
            f"sqlite:///{database_file}", connect_args={"check_same_thread": False}
        )
    # drop_all avant create_all : si une execution precedente s'est arretee en cours
    # de route, les tables restantes fausseraient les comptages.
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture
def session(engine) -> Session:
    """Une session ouverte sur la base de test, refermee apres chaque test."""
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db_session:
        yield db_session


@pytest.fixture(autouse=True)
def clean_tables(engine):
    """Vide les tables avant chaque test.

    autouse : s'applique sans que les tests aient a la demander. Sans ce nettoyage,
    un test qui cree un compte ferait echouer le suivant qui compte les comptes, et
    l'ordre d'execution deviendrait significatif.
    """
    from sqlalchemy import delete

    from futurisys.db.models import (
        ModelVersion,
        PredictionRequest,
        PredictionResult,
    )

    factory = sessionmaker(bind=engine)
    with factory() as db_session:
        # L'ordre suit les cles etrangeres : les enfants d'abord, sinon la suppression
        # d'un parent encore reference est refusee par la base.
        for table in (PredictionResult, PredictionRequest, Building, ModelVersion, User):
            db_session.execute(delete(table))
        db_session.commit()
    yield


@pytest.fixture
def client(engine) -> TestClient:
    """Un client HTTP qui appelle l'API en la branchant sur la base de test.

    dependency_overrides remplace la vraie connexion par celle des tests, sans
    modifier une seule ligne du code de l'application.
    """
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_session():
        db_session = factory()
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin(session) -> User:
    user = User(
        username="admin_test",
        hashed_password=hash_password(ADMIN_PASSWORD),
        is_admin=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def standard_user(session) -> User:
    user = User(
        username="user_test",
        hashed_password=hash_password(USER_PASSWORD),
        is_admin=False,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post("/auth/token", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def admin_headers(client, admin) -> dict[str, str]:
    return _login(client, admin.username, ADMIN_PASSWORD)


@pytest.fixture
def user_headers(client, standard_user) -> dict[str, str]:
    return _login(client, standard_user.username, USER_PASSWORD)


@pytest.fixture
def sample_building(session) -> Building:
    """Un batiment de reference, aux valeurs plausibles, insere en base."""
    building = Building(
        ose_building_id=999001,
        property_name="Batiment de test",
        building_type="NonResidential",
        primary_property_type="Large Office",
        neighborhood_grouped="DOWNTOWN",
        property_gfa_total=250000.0,
        property_gfa_parking=30000.0,
        number_of_floors=12.0,
        number_of_buildings=1.0,
        latitude=47.6101,
        longitude=-122.3344,
        building_age=31,
        largest_use_ratio=0.88,
        is_multi_use=True,
        has_electricity=True,
        has_natural_gas=True,
        has_steam=False,
        site_energy_use_wn_kbtu=17_000_000.0,
    )
    session.add(building)
    session.commit()
    session.refresh(building)
    return building


@pytest.fixture
def valid_payload() -> dict:
    """Une demande de prediction correcte, servant de base aux variantes fautives."""
    return {
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
        "is_multi_use": True,
        "has_electricity": True,
        "has_natural_gas": True,
        "has_steam": False,
    }


# Certains tests ont besoin du modele entraine ou du fichier de donnees. Plutot que de
# les faire echouer avec une erreur obscure, on les ignore avec un message explicite.
needs_model = pytest.mark.skipif(
    not MODEL_ARTIFACT.exists(),
    reason="modele absent : lancer python -m futurisys.ml.train",
)
needs_dataset = pytest.mark.skipif(not DATASET.exists(), reason="jeu de donnees absent")
