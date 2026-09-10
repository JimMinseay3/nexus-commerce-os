import uuid


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))[:64]
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        return response

