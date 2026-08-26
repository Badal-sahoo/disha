"""One exception handler so an unimplemented service is legible from the wire.

Every service in this project is a stub on day 0. Without this handler a stub
surfaces as a 500 with an HTML traceback, and the frontend team cannot tell
"not built yet" apart from "you broke it". With it they get 501 + the message.
"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def ps05_exception_handler(exc, context):
    """
    IN:
      exc     = the exception raised inside a DRF view
      context = {"view": APIView, "args": tuple, "kwargs": dict, "request": Request}

    OUT: rest_framework.response.Response | None
      NotImplementedError -> 501 {"detail": str, "code": "not_implemented"}
      ValueError          -> 400 {"detail": str, "code": "invalid"}
      anything else       -> whatever DRF's default handler decides (None = re-raise)
    """
    if isinstance(exc, NotImplementedError):
        return Response(
            {"detail": str(exc) or "Not implemented yet.", "code": "not_implemented"},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )
    if isinstance(exc, ValueError):
        return Response(
            {"detail": str(exc), "code": "invalid"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return exception_handler(exc, context)
