from rest_framework_simplejwt.authentication import JWTAuthentication


class JWTUser:
    """
    Lekki obiekt użytkownika zbudowany z payloadu JWT.
    Nie trafia do bazy danych — Order Service tylko czyta token wydany przez User Service.
    """

    is_anonymous = False
    is_authenticated = True

    def __init__(self, payload: dict):
        self.id = payload.get('user_id')

    def __str__(self):
        return f'JWTUser(id={self.id})'


class ServiceJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        return JWTUser(validated_token)
