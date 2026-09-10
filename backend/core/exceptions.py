from rest_framework.views import exception_handler


def erp_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        request = context.get("request")
        response.data = {
            "error": {
                "code": getattr(exc, "default_code", "request_error"),
                "message": response.data,
                "request_id": getattr(request, "request_id", ""),
            }
        }
    return response

