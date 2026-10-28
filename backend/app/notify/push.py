"""Notifiche Web Push (D158): avvisi sul telefono anche con l'app chiusa (standard del browser, gratis).

Le chiavi VAPID (dicono al servizio push del browser che la notifica arriva davvero da ArchieBet) le genera l'app
al primo uso e le salva nella cartella dei dati, che non va su GitHub: niente da mettere a mano nel file .env.
"""

import base64
import json
from collections.abc import Callable, Iterable

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid02
from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PushSubscription

CONTACT = "https://github.com/giuseppecorso/archiebet"  # chi manda le notifiche (richiesto dallo standard)
TTL_SECONDS = 12 * 3600  # se il telefono è spento, la notifica aspetta al massimo 12 ore
GONE = (404, 410)  # il browser ha tolto il permesso o il dispositivo non esiste più


def _key_path():
    return get_settings().data_cache_dir.parent / "vapid_private.pem"


def vapid() -> Vapid02:
    path = _key_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        key = Vapid02()
        key.generate_keys()
        key.save_key(str(path))
    return Vapid02.from_file(str(path))


def public_key() -> str:
    """La chiave pubblica nel formato che vuole il browser (base64url senza "=")."""
    raw = vapid().public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def send(db: Session, title: str, body: str, url: str = "/", user_ids: Iterable[int] | None = None,
         sender: Callable = webpush) -> int:  # fmt: skip
    """Manda la notifica a tutti i dispositivi (o a quelli degli utenti indicati). Restituisce quante sono partite;
    i dispositivi che non esistono più si tolgono."""
    query = select(PushSubscription)
    if user_ids is not None:
        query = query.where(PushSubscription.user_id.in_(list(user_ids)))
    subs = list(db.scalars(query))
    if not subs:
        return 0
    key, data, sent = vapid(), json.dumps({"title": title, "body": body, "url": url}), 0
    for s in subs:
        try:
            sender(subscription_info={"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}}, data=data,
                   vapid_private_key=key, vapid_claims={"sub": CONTACT}, ttl=TTL_SECONDS, timeout=10)  # fmt: skip
            sent += 1
        except WebPushException as exc:
            if exc.response is not None and exc.response.status_code in GONE:
                db.delete(s)
        except OSError:
            pass  # rete: la prossima notifica riproverà
    db.commit()
    return sent
