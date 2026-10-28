"""Checking who is signed in (card 13).

The site signs people in with Supabase Auth. Every request that saves,
loads, or deletes someone's data carries their access token, a JWT signed by
Supabase. This module checks it on the server, so a request can't act for
someone else just by changing what the browser sends.

Supabase signs tokens with an asymmetric key and publishes the public half
at <project>/auth/v1/.well-known/jwks.json, so the check needs no secret and
no network call per request (the keys are cached for 10 minutes). Projects
still on the older shared-secret (HS256) keys are checked by asking
Supabase's /auth/v1/user instead, as Supabase recommends.
"""

import httpx
import jwt
from jwt import PyJWKClient

SIGN_IN_AGAIN = "Sign in again to continue."
SESSION_EXPIRED = "Your session expired. Sign in again to continue."


class AuthError(Exception):
    def __init__(self, message, expired=False):
        super().__init__(message)
        self.message = message
        self.expired = expired


class SupabaseAuth:
    def __init__(self, url, secret_key, key_for=None):
        """url: https://<project>.supabase.co. secret_key: only used for
        HS256 projects. key_for: a function returning the public key for a
        token, to stand in for the JWKS download in tests."""
        self.url = url.rstrip("/")
        self.issuer = f"{self.url}/auth/v1"
        self.secret_key = secret_key
        if key_for is None:
            jwks = PyJWKClient(f"{self.issuer}/.well-known/jwks.json", cache_keys=True, lifespan=600)
            key_for = lambda token: jwks.get_signing_key_from_jwt(token).key  # noqa: E731
        self.key_for = key_for

    def verify(self, token):
        """{"id", "email"} for a valid token. Raises AuthError otherwise."""
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise AuthError(SIGN_IN_AGAIN) from None
        if header.get("alg") == "HS256":
            return self._verify_with_supabase(token)
        try:
            claims = jwt.decode(
                token,
                self.key_for(token),
                algorithms=["ES256", "RS256"],
                audience="authenticated",
                issuer=self.issuer,
            )
        except jwt.ExpiredSignatureError:
            raise AuthError(SESSION_EXPIRED, expired=True) from None
        except jwt.PyJWTError:  # bad signature, wrong issuer, or the keys couldn't be fetched
            raise AuthError(SIGN_IN_AGAIN) from None
        return {"id": claims["sub"], "email": claims.get("email")}

    def _verify_with_supabase(self, token):
        try:
            res = httpx.get(
                f"{self.issuer}/user",
                headers={"apikey": self.secret_key, "Authorization": f"Bearer {token}"},
                timeout=10,
            )
        except httpx.HTTPError:
            raise AuthError("Couldn't check your sign-in. Try again in a minute.") from None
        if res.status_code != 200:
            raise AuthError(SESSION_EXPIRED, expired=True)
        user = res.json()
        return {"id": user["id"], "email": user.get("email")}
