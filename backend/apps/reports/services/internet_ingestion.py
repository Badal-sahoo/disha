"""The with-internet path: the citizen app posts a report straight to the API."""
from ..models import Incident
from .make_incident import create_incident


def report_from_app(data):
    """Turn a validated app payload into an Incident.

    accuracy_m is used for triage upstream and is not stored on the model.
    """
    payload = dict(data)
    payload.pop("accuracy_m", None)
    return create_incident(payload, source=Incident.Source.APP)
