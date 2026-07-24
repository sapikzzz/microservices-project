from rest_framework_simplejwt.authentication import JWTAuthentication


class JWTUser:
    is_anonymous = False
    is_authenticated = True

    def __init__(self, payload: dict):
        self.id = payload.get("user_id")
        self.role = payload.get("role")
        self.username = payload.get("username", "")

    def __str__(self):
        return f"JWTUser(id={self.id}, role={self.role})"


class ServiceJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        return JWTUser(validated_token)
