"""One exception handler, so a bad request reads as 400 and not 500.

Views raise plain ValueError for bad input ("bbox must be ...", "lat and lon are
required floats"). Without this they would surface as a 500 with an HTML
traceback and the frontend could not tell them apart from a real fault.
"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def ps05_exception_handler(exc, context):
    if isinstance(exc, ValueError):
        return Response({"detail": str(exc), "code": "invalid"},
                        status=status.HTTP_400_BAD_REQUEST)
    return exception_handler(exc, context)
